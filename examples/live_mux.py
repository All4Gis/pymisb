# Author: Fran Raga <franka1986@gmail.com>

"""Mux a continuous MPEG-TS with telemetry that arrives on its own clock.

The video is a byte stream. Metadata is a plain dict, produced at a fixed
rate, and is absent on the iterations where the drone has not answered.
No drone and no sample file are required: the video below is a synthetic
MPEG-TS, and the telemetry is random.

    python examples/live_mux.py
    python examples/live_mux.py --out muxed_data.ts --seconds 5 --hz 1

A real MPEG-TS (file, socket, or ``ffmpeg -c copy -f mpegts``) is fed the
same way: pass each chunk to ``LiveMuxer.feed`` together with the latest
sample, or ``None``.
"""

from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta, timezone

from pymisb.mux import LiveMuxer
from pymisb.mux.engine import _crc32_mpeg

VIDEO_PID = 0x0100
PMT_PID = 0x1000
PACKET_SECONDS = 0.1


def write_muxed_data(out_path: str, seconds: float, hz: float) -> None:
    """Write one MPEG-TS that carries the video and the telemetry samples."""
    muxer = LiveMuxer()
    period = 1.0 / hz
    next_sample = 0.0
    samples = 0
    with open(out_path, "wb") as fh:
        for kind, t_rel, video_packet in get_simulated_video_packet(seconds):
            # The drone is polled at `hz`. Between answers there is no sample.
            metadata = None
            if kind == "video" and t_rel + 1e-9 >= next_sample:
                metadata = get_metadata(t_rel)
                next_sample += period
                samples += 1
            fh.write(muxer.feed(video_packet, metadata))
        fh.write(muxer.close())
    print(f"Wrote {out_path}  ({samples} telemetry samples at {hz:g} Hz)")


def get_metadata(t_rel: float) -> dict:
    """One telemetry sample, shaped like a reading from the drone.

    The transport (unix socket, network, ...) is outside the library.
    Whatever arrives has to become a dict; ``LiveMuxer`` converts it to KLV.
    """
    latitude = random.randint(1, 89) + random.randint(0, 999_999) / 1_000_000
    longitude = random.randint(1, 179) + random.randint(0, 999_999) / 1_000_000
    timestamp = datetime.now(timezone.utc) + timedelta(seconds=t_rel)
    return {
        "latitude": latitude,
        "longitude": longitude,
        "altitude": 120.0,
        "heading": 15.0,
        "timestamp": timestamp.isoformat(timespec="milliseconds"),
    }


def get_simulated_video_packet(seconds: float):
    """Yield ``(kind, t_rel, ts_packet)`` for a short synthetic MPEG-TS.

    ``kind`` is ``"psi"`` for PAT/PMT and ``"video"`` for a frame packet.
    A live socket works the same: read whatever size comes off the wire
    and pass those bytes to ``feed``. 188-byte alignment is not required.
    """
    steps = int(seconds / PACKET_SECONDS)
    for index in range(steps):
        t_rel = index * PACKET_SECONDS
        if index % 10 == 0:
            yield "psi", t_rel, _psi_packet(0x0000, _pat_table(), cc=index & 0x0F)
            yield "psi", t_rel, _psi_packet(PMT_PID, _pmt_table(), cc=index & 0x0F)
        yield "video", t_rel, _video_packet(int(t_rel * 90_000), cc=index & 0x0F)


def _psi_packet(pid: int, table: bytes, cc: int) -> bytes:
    header = bytes([
        0x47,
        0x40 | ((pid >> 8) & 0x1F),
        pid & 0xFF,
        0x10 | (cc & 0x0F),
        0x00,  # pointer field
    ])
    return _pad(header + table)


def _pat_table() -> bytes:
    # One program: program 1 -> PMT at PMT_PID.
    body = b"\x00\x01\xc1\x00\x00" + (1).to_bytes(2, "big") + (0xE000 | PMT_PID).to_bytes(2, "big")
    return _psi_table(0x00, body)


def _pmt_table() -> bytes:
    # PCR and the single H.264 elementary stream share VIDEO_PID.
    body = (
        (1).to_bytes(2, "big")
        + b"\xc1\x00\x00"
        + (0xE000 | VIDEO_PID).to_bytes(2, "big")
        + b"\xf0\x00"          # no program descriptors
        + b"\x1b"              # H.264
        + (0xE000 | VIDEO_PID).to_bytes(2, "big")
        + b"\xf0\x00"          # no ES descriptors
    )
    return _psi_table(0x02, body)


def _psi_table(table_id: int, body_after_length: bytes) -> bytes:
    section_length = len(body_after_length) + 4  # CRC included
    table = bytes([table_id, 0xB0 | ((section_length >> 8) & 0x0F), section_length & 0xFF])
    table += body_after_length
    return table + _crc32_mpeg(table).to_bytes(4, "big")


def _video_packet(pcr: int, cc: int) -> bytes:
    packet = bytearray(188)
    packet[0] = 0x47
    packet[1] = 0x40 | ((VIDEO_PID >> 8) & 0x1F)
    packet[2] = VIDEO_PID & 0xFF
    packet[3] = 0x30 | (cc & 0x0F)  # adaptation field + payload
    packet[4] = 7
    packet[5] = 0x10  # PCR flag
    packet[6:12] = ((pcr & 0x1FFFFFFFF) << 15 | (0x3F << 9)).to_bytes(6, "big")
    packet[12:16] = b"\x00\x00\x01\xe0"  # video PES start code
    return bytes(packet)


def _pad(packet: bytes) -> bytes:
    if len(packet) > 188:
        raise RuntimeError(f"TS packet is {len(packet)} bytes")
    return packet + b"\xFF" * (188 - len(packet))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", default="muxed_data.ts", help="Output MPEG-TS (default: muxed_data.ts)")
    parser.add_argument("--seconds", type=float, default=5.0, help="Length of the simulated video")
    parser.add_argument("--hz", type=float, default=1.0, help="How often a telemetry sample arrives")
    args = parser.parse_args(argv)
    if args.seconds <= 0 or args.hz <= 0:
        parser.error("--seconds and --hz must be positive")
    write_muxed_data(args.out, args.seconds, args.hz)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
