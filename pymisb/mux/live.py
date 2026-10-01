# Author: Fran Raga <franka1986@gmail.com>

"""Live MPEG-TS muxer: a continuous video stream plus telemetry dicts.

``mux_with_ffmpeg`` waits for a finished file and a finished telemetry log.
A live source is different: video bytes arrive continuously, and a metadata
sample shows up only when the drone answers. ``LiveMuxer`` interleaves the
two into one STANAG 4609 MPEG-TS as they arrive.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..common.encoder import build_st0601_packet
from .engine import (
    _build_pes,
    _elementary_pids,
    _packetize_pes,
    _parse_pat_pmt_pid,
    _pid_of,
    _read_pcr,
    _rewrite_pmt_packet,
)

_TS_PACKET = 188

# Names a caller is likely to use, mapped onto build_st0601_packet keys.
_KEY_ALIASES = {
    "latitude": "sensor_lat",
    "lat": "sensor_lat",
    "longitude": "sensor_lon",
    "lon": "sensor_lon",
    "lng": "sensor_lon",
    "altitude": "sensor_alt",
    "alt": "sensor_alt",
    "heading": "platform_heading",
    "pitch": "platform_pitch",
    "roll": "platform_roll",
}


def metadata_to_klv(metadata: dict) -> bytes:
    """Convert one telemetry dict into a MISB ST0601 KLV packet.

    Accepts the encoder's own keys (``sensor_lat``, ``timestamp_us``, ...)
    and the shorter names a live source usually has (``latitude``,
    ``longitude``, ``altitude``, ``heading``, ``timestamp``). ``timestamp``
    may be an ISO-8601 string, a ``datetime``, or Unix seconds.

    A sample with no timestamp is stamped with the current UTC time, so
    tag 2 (Precision Time Stamp) is always present.
    """
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be a dict of telemetry values")
    return build_st0601_packet(_normalize_metadata(metadata))


def _normalize_metadata(metadata: dict) -> dict:
    values: dict = {}
    for key, val in metadata.items():
        if key == "timestamp":
            continue
        values[_KEY_ALIASES.get(key, key)] = val
    if "timestamp_us" not in values:
        stamp = metadata.get("timestamp")
        if stamp is None:
            stamp = datetime.now(timezone.utc)
        values["timestamp_us"] = _to_timestamp_us(stamp)
    return values


def _to_timestamp_us(stamp: datetime | str | int | float) -> int:
    if isinstance(stamp, datetime):
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return int(stamp.timestamp() * 1_000_000)
    if isinstance(stamp, str):
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        return _to_timestamp_us(parsed)
    if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
        raise TypeError(f"Unsupported timestamp: {stamp!r}")
    value = float(stamp)
    if value > 1e14:  # already microseconds
        return int(value)
    if value > 1e11:  # milliseconds
        return int(value * 1_000)
    return int(value * 1_000_000)


class LiveMuxer:
    """Mux an MPEG-TS video byte stream with telemetry dicts as they arrive.

    The video argument of :meth:`feed` is the next slice of an MPEG-TS
    (a file read, a socket recv, or any chunk size). It does not have to
    fall on a 188-byte boundary. ``metadata`` is the latest sample, or
    ``None`` when the drone has not produced one for this slice.

    Each metadata sample is inserted at the latest PCR, so it lines up
    with the video frame that was current when the sample arrived. The
    clock inside the KLV packet is the timestamp from the dict.

    The video must already be MPEG-TS. An MP4 or a raw elementary stream
    has to be remuxed first (``ffmpeg -c copy -f mpegts``).

    Example::

        muxer = LiveMuxer()
        with open("muxed_data.ts", "wb") as fh:
            for chunk in video_chunks():          # continuous MPEG-TS
                sample = poll_drone()             # dict, or None
                fh.write(muxer.feed(chunk, sample))
            fh.write(muxer.close())
    """

    def __init__(self, klv_pid: int | None = None):
        self._requested_pid = klv_pid
        self._klv_pid: int | None = None
        self._pmt_pid: int | None = None
        self._buf = bytearray()
        self._synced = False
        self._seen: set[int] = set()
        self._klv_cc = 0
        self._pcr: int | None = None
        self._pending: list[bytes] = []
        self._closed = False

    def feed(self, video: bytes, metadata: dict | None = None) -> bytes:
        """Push video bytes and, optionally, one telemetry sample.

        Returns the MPEG-TS bytes to write or send next. Pending metadata
        that arrived before the first PCR is included as soon as the clock
        and the KLV PID are known.
        """
        if self._closed:
            raise RuntimeError("LiveMuxer is closed")
        if video:
            self._buf.extend(video)
        out = bytearray(self._drain())
        if metadata is not None:
            out += self._emit_metadata(metadata)
        return bytes(out)

    def close(self) -> bytes:
        """Flush telemetry still waiting on the clock. Call this once at the end."""
        if self._closed:
            return b""
        self._closed = True
        out = bytearray(self._drain(final=True))
        out += self._flush_pending()
        self._buf.clear()
        self._pending.clear()
        return bytes(out)

    def _emit_metadata(self, metadata: dict) -> bytes:
        klv = metadata_to_klv(metadata)
        if self._klv_pid is None or self._pcr is None:
            self._pending.append(klv)
            return b""
        return self._packetize(klv, self._pcr)

    def _packetize(self, klv: bytes, pcr: int) -> bytes:
        if self._klv_pid is None:
            return b""
        pts = pcr & 0x1FFFFFFFF
        pes = _build_pes(klv, pts)
        data, self._klv_cc = _packetize_pes(
            self._klv_pid, pes, pts, self._klv_cc, with_pcr=False
        )
        return data

    def _flush_pending(self) -> bytes:
        if not self._pending or self._klv_pid is None or self._pcr is None:
            return b""
        out = bytearray()
        waiting, self._pending = self._pending, []
        for klv in waiting:
            out += self._packetize(klv, self._pcr)
        return bytes(out)

    def _drain(self, final: bool = False) -> bytes:
        out = bytearray()
        while True:
            if not self._synced:
                if len(self._buf) < _TS_PACKET * 2:
                    break
                if self._buf[0] == 0x47 and self._buf[_TS_PACKET] == 0x47:
                    self._synced = True
                else:
                    del self._buf[0]
                    continue
            if len(self._buf) < _TS_PACKET:
                break
            if self._buf[0] != 0x47:
                self._synced = False
                continue
            # Hold the last packet until the next sync byte confirms it,
            # unless the stream is ending.
            if not final and len(self._buf) < _TS_PACKET * 2:
                break
            if not final and self._buf[_TS_PACKET] != 0x47:
                self._synced = False
                del self._buf[0]
                continue
            packet = bytes(self._buf[:_TS_PACKET])
            del self._buf[:_TS_PACKET]
            out += self._handle_packet(packet)
        return bytes(out)

    def _handle_packet(self, packet: bytes) -> bytes:
        pid = _pid_of(packet)
        self._seen.add(pid)
        if pid == 0 and (packet[1] & 0x40) and self._pmt_pid is None:
            self._pmt_pid = _parse_pat_pmt_pid(packet)

        pcr = _read_pcr(packet)
        if pcr is not None:
            self._pcr = pcr

        if (
            self._pmt_pid is not None
            and pid == self._pmt_pid
            and (packet[1] & 0x40)
        ):
            self._ensure_pid(packet)
            klv_pid = self._klv_pid
            if klv_pid is None:
                raise RuntimeError("No free PID for the KLV stream.")
            packet = _rewrite_pmt_packet(packet, klv_pid)

        # KLV follows the video packet that established the current PCR,
        # so a sample lines up with the frame it arrived with.
        return packet + self._flush_pending()

    def _ensure_pid(self, pmt_packet: bytes) -> None:
        if self._klv_pid is not None:
            return
        used = set(self._seen)
        used |= _elementary_pids(pmt_packet)
        used.add(0)
        if self._pmt_pid is not None:
            used.add(self._pmt_pid)
        if self._requested_pid is not None:
            if self._requested_pid in used:
                raise RuntimeError(
                    f"KLV PID 0x{self._requested_pid:04X} is already used by the video"
                )
            self._klv_pid = self._requested_pid
            return
        self._klv_pid = next(
            pid for pid in range(0x0100, 0x1FFE) if pid not in used
        )
