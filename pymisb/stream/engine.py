# Author: Fran Raga <franka1986@gmail.com>

"""Real-time KLV extraction from live video streams.

Reads KLV telemetry from UDP, RTP, or RTSP streams using FFmpeg as a
subprocess.  The KLV packets are decoded on the fly and can be consumed
via a callback or an iterator interface.

Typical usage:

    # Iterator — process packets as they arrive
    with open_stream("udp://@:5000") as reader:
        for pkt in reader:
            meta = pkt.MetadataList()
            print(meta[13])  # Sensor Latitude

    # Callback — react to each packet immediately
    def on_packet(pkt):
        print(pkt.MetadataList()[13])

    reader = open_stream("rtsp://camera.local/stream")
    reader.start(callback=on_packet)
    reader.stop()
"""

from __future__ import annotations

import os
import sys
import time
import shutil
import struct
import threading
import subprocess
import argparse
from typing import Callable, Iterator

from ..klvdata import StreamParser


class StreamKLVReader:
    """Read KLV packets from a live stream via FFmpeg subprocess.

    Spawns FFmpeg to demux the data channel from the stream and reads
    the raw KLV bytes in real-time.  Supports both blocking iteration
    and callback-based consumption.

    Attributes:
        source: The stream URI (e.g. ``udp://@:5000``, ``rtsp://...``).
        ffmpeg_path: Path to the ffmpeg binary.
    """

    __slots__ = ("source", "ffmpeg_path", "_proc", "_running", "_thread")

    def __init__(self, source: str, ffmpeg_path: str | None = None):
        self.source = source
        self.ffmpeg_path = ffmpeg_path or shutil.which("ffmpeg") or "ffmpeg"
        self._proc: subprocess.Popen | None = None
        self._running = False
        self._thread: threading.Thread | None = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()

    def _drain_packets(self, buf: bytes, on_packet):
        """Parse *buf* for complete KLV packets, call *on_packet* for each."""
        while len(buf) >= 20:
            try:
                for pkt in StreamParser(buf):
                    on_packet(pkt)
                    pkt_bytes = bytes(pkt)
                    idx = buf.find(pkt_bytes)
                    if idx >= 0:
                        buf = buf[idx + len(pkt_bytes):]
                    else:
                        buf = buf[-20:]
            except (StopIteration, struct.error, ValueError, IndexError):
                break
        return buf

    def __iter__(self) -> Iterator:
        """Yield parsed ST0601 packets as they arrive."""
        self.start()
        try:
            buf = b""
            while self._running and self._proc and self._proc.poll() is None:
                chunk = self._proc.stdout.read(4096) if self._proc.stdout else b""
                if not chunk:
                    time.sleep(0.01)
                    continue
                buf += chunk
                while len(buf) >= 20:
                    try:
                        for pkt in StreamParser(buf):
                            yield pkt
                            pkt_bytes = bytes(pkt)
                            idx = buf.find(pkt_bytes)
                            if idx >= 0:
                                buf = buf[idx + len(pkt_bytes):]
                            else:
                                buf = buf[-20:]
                    except (StopIteration, struct.error, ValueError, IndexError):
                        break
        finally:
            self.stop()

    def start(self, callback: Callable | None = None):
        """Start reading from the stream.

        Args:
            callback: Optional function called with each parsed packet.
                If None, use the iterator interface instead.
        """
        if self._running:
            return

        cmd = [
            self.ffmpeg_path,
            "-fflags", "+nobuffer",
            "-analyzeduration", "0",
            "-probesize", "32",
            "-i", self.source,
            "-map", "0:d",
            "-c", "copy",
            "-f", "data",
            "-",
        ]

        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )
        self._running = True

        if callback:
            self._thread = threading.Thread(
                target=self._read_loop, args=(callback,), daemon=True
            )
            self._thread.start()

    def _read_loop(self, callback: Callable):
        """Background loop that reads and decodes KLV packets."""
        buf = b""
        while self._running and self._proc and self._proc.poll() is None:
            chunk = self._proc.stdout.read(4096) if self._proc.stdout else b""
            if not chunk:
                time.sleep(0.01)
                continue
            buf += chunk
            buf = self._drain_packets(buf, callback)

    def stop(self):
        """Stop reading and close the FFmpeg subprocess."""
        self._running = False
        if self._proc:
            try:
                if self._proc.stdout:
                    self._proc.stdout.close()
                self._proc.terminate()
                self._proc.wait(timeout=5)
            except Exception:
                try:
                    self._proc.kill()
                except OSError:
                    pass
            self._proc = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
            self._thread = None


def open_stream(source: str, ffmpeg_path: str | None = None) -> StreamKLVReader:
    """Open a live stream for real-time KLV reading.

    Args:
        source: Stream URI. Supports any format FFmpeg can read:
            - ``udp://@:5000`` — UDP multicast
            - ``udp://@:5000?pkt_size=1316`` — UDP with packet size
            - ``rtp://...`` — RTP stream
            - ``rtsp://camera.local/stream`` — RTSP camera
            - ``rtmp://...`` — RTMP stream
        ffmpeg_path: Optional path to ffmpeg binary.

    Returns:
        A ``StreamKLVReader`` instance (use as context manager or call
        ``start()``/``stop()`` directly).

    Example::

        with open_stream("udp://@:5000") as reader:
            for pkt in reader:
                meta = pkt.MetadataList()
                lat = meta.get(13, (None, "N/A"))[1]
                print(f"Lat: {lat}")
    """
    return StreamKLVReader(source, ffmpeg_path)


def main(argv=None) -> int:
    """CLI entry point for ``python -m pymisb.stream``.

    Reads KLV from a live stream and prints decoded packets in real-time.
    """
    parser = argparse.ArgumentParser(
        description="Read KLV telemetry from a live UDP/RTP/RTSP stream.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pymisb.stream udp://@:5000\n"
            "  python -m pymisb.stream rtsp://camera.local/stream\n"
            "  python -m pymisb.stream udp://@:5000 --all\n"
        ),
    )
    parser.add_argument("source", help="Stream URI (udp://, rtsp://, rtp://, ...)")
    parser.add_argument("--all", action="store_true",
                        help="Show every present tag")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="Seconds to wait before giving up (default: 10)")
    parser.add_argument("--ffmpeg", default=None,
                        help="Path to the ffmpeg binary")
    args = parser.parse_args(argv)

    print(f"Connecting to {args.source} ...")
    print(f"Reading KLV packets (Ctrl+C to stop, timeout={args.timeout}s)...\n")

    reader = open_stream(args.source, ffmpeg_path=args.ffmpeg)
    t0 = time.monotonic()
    count = 0

    try:
        for pkt in reader:
            elapsed = time.monotonic() - t0
            if elapsed > args.timeout:
                print(f"\n[TIMEOUT] No data received for {args.timeout}s.")
                break
            t0 = time.monotonic()  # reset on each packet
            count += 1
            meta = pkt.MetadataList()
            fields = sorted(meta) if args.all else [2, 13, 14, 15, 5, 6, 7]
            parts = []
            for tag in fields:
                if tag in meta:
                    label = {2: "t", 5: "hdg", 6: "pitch", 7: "roll",
                             13: "lat", 14: "lon", 15: "alt"}.get(tag, str(tag))
                    val = meta[tag][1]
                    parts.append(f"{label}={val}" if tag != 2 else str(val))
            print(f"[{count:4d}] {'  '.join(parts)}")
    except KeyboardInterrupt:
        print("\n[STOPPED] by user.")
    finally:
        reader.stop()

    print(f"\n{count} packets received.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
