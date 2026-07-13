# Author: Fran Raga <franka1986@gmail.com>

"""KLV extraction and decoding engine for MISB STANAG 4609 videos.

Uses FFmpeg to extract the data channel from a TS file, then decodes
the raw KLV bytes into structured ST0601 metadata via the vendored
klvdata parser.
"""

from __future__ import annotations

import os
import sys
import time
import shutil
import argparse
import subprocess
from datetime import datetime

from ..klvdata import StreamParser


# Short labels for the most common ST0601 tags (used in CLI output)
LABELS = {
    2: "t", 5: "hdg", 6: "pitch", 7: "roll",
    13: "lat", 14: "lon", 15: "alt",
    16: "hfov", 17: "vfov", 18: "g_az", 19: "g_el", 20: "g_roll",
    21: "slant", 22: "tw", 23: "fc_lat", 24: "fc_lon", 25: "fc_elev", 65: "ver",
}

# Default tags shown in CLI output (most useful for geolocation)
DEFAULT_FIELDS = [2, 13, 14, 15, 5, 6, 7, 21, 23, 24]


def extract_klv(ts_path: str, ffmpeg_path: str | None = None) -> bytes:
    """Extract the raw KLV data stream from a TS file using FFmpeg.

    Runs ``ffmpeg -map 0:d -c copy -f data -`` to pull out the data
    elementary stream without re-muxing.  The output is the raw KLV
    bytes that can be parsed by ``decode_packets``.

    Args:
        ts_path: Path to the MPEG-TS file containing a KLV stream.
        ffmpeg_path: Optional path to the ffmpeg binary.

    Returns:
        Raw KLV bytes.

    Raises:
        RuntimeError: If ffmpeg is not found or can't extract the data.
    """
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("'ffmpeg' not found on the PATH. Use --ffmpeg to specify its location.")
    cmd = [ffmpeg, "-v", "error", "-i", ts_path, "-map", "0:d", "-c", "copy", "-f", "data", "-"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not res.stdout:
        msg = res.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"FFmpeg could not extract the data channel.\n{msg}")
    return res.stdout


def decode_packets(klv_data: bytes) -> list:
    """Decode raw KLV bytes into a list of parsed ST0601 packets.

    Uses the vendored ``klvdata.StreamParser`` to iterate over the
    byte stream and return UASLocalMetadataSet objects with decoded
    tags.

    Args:
        klv_data: Raw KLV bytes (as returned by ``extract_klv``).

    Returns:
        List of parsed packet objects, each with a ``MetadataList()`` method.
    """
    return list(StreamParser(klv_data))


def _fmt_value(value: str | float | None) -> str:
    """Format a metadata value string, rounding floats to 5 decimals."""
    if value is None:
        return "N/A"
    try:
        return f"{float(value):.5f}"
    except (TypeError, ValueError):
        return str(value)


def _line(metadata: dict, fields: list[int]) -> str:
    """Format a single packet's metadata as a one-line summary string.

    Joins ``label=value`` pairs for each requested tag.  Tag 2 (timestamp)
    is shown without a label prefix.

    Args:
        metadata: Dict of ``{tag_int: (LDSName, value_string, ...)}``
        fields: List of tag integers to include in the output.

    Returns:
        A formatted string like ``"2024-01-01T00:00:00Z  lat=41.3  lon=2.1"``.
    """
    parts = []
    for tag in fields:
        if tag in metadata:
            label = LABELS.get(tag, str(tag))
            value = metadata[tag][1]
            parts.append(f"{label}={_fmt_value(value)}" if tag != 2 else f"{value}")
    return "  ".join(parts)


def _timestamp(metadata: dict) -> datetime | None:
    """Extract the Precision Time Stamp (tag 2) as a datetime.

    Returns None if tag 2 is missing or cannot be parsed as an ISO
    datetime string.
    """
    if 2 not in metadata:
        return None
    try:
        return datetime.fromisoformat(metadata[2][1])
    except (TypeError, ValueError):
        return None


def main(argv=None) -> int:
    """CLI entry point for ``python -m pymisb.demux``.

    Extracts the KLV channel from a MISB/TS video using FFmpeg, decodes
    the ST0601 packets, and prints the metadata.  Supports real-time
    playback simulation (--play) and full tag dump (--all).

    Returns:
        0 on success, 2 on file error, 3 on FFmpeg error, 4 if no KLV found.
    """
    parser = argparse.ArgumentParser(
        description="Demux and decode the KLV channel of a MISB video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pymisb.demux DJI_0047_MISB.ts\n"
            "  python -m pymisb.demux output.ts --play --speed 4\n"
            "  python -m pymisb.demux output.ts --all\n"
            "  python -m pymisb.demux output.ts --structure\n"
        ),
    )
    parser.add_argument("video", help="MISB/TS video to demux")
    parser.add_argument("--play", action="store_true",
                        help="Print values at the video's real rate")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Speed multiplier for --play (e.g. 4 = x4)")
    parser.add_argument("--all", action="store_true",
                        help="Show every present tag")
    parser.add_argument("--structure", action="store_true",
                        help="Show the tag tree of the first packet and exit")
    parser.add_argument("--ffmpeg", default=None,
                        help="Path to the ffmpeg binary")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.video):
        print(f"[ERROR] Video does not exist: {args.video}", file=sys.stderr)
        return 2

    print(f"Extracting the KLV channel from {args.video} ...")
    try:
        data = extract_klv(args.video, ffmpeg_path=args.ffmpeg)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 3

    packets = decode_packets(data)
    if not packets:
        print("[ERROR] No KLV packets found in the video.", file=sys.stderr)
        return 4
    print(f"{len(packets)} ST0601 packets decoded.\n")

    if args.structure:
        packets[0].structure()
        return 0

    metas = [p.MetadataList() for p in packets]

    if not args.play:
        for i, md in enumerate(metas):
            fields = sorted(md) if args.all else DEFAULT_FIELDS
            print(f"[{i:4d}] {_line(md, fields)}")
        return 0

    # Playback mode: print values in real-time using Precision Time Stamps
    print(f"Playing at x{args.speed:g} (Ctrl+C to stop)...\n")
    t0_meta = _timestamp(metas[0])
    t0_real = time.monotonic()
    for i, md in enumerate(metas):
        ts = _timestamp(md)
        if ts is not None and t0_meta is not None:
            target = (ts - t0_meta).total_seconds() / max(args.speed, 1e-6)
            delay = target - (time.monotonic() - t0_real)
            if delay > 0:
                time.sleep(delay)
        fields = sorted(md) if args.all else DEFAULT_FIELDS
        stamp = ts.strftime("%H:%M:%S.%f")[:-3] if ts else f"#{i}"
        print(f"[{stamp}] {_line(md, [f for f in fields if f != 2])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
