# Author: Fran Raga <franka1986@gmail.com>

"""MISB ST 0903 VMTI — Video Moving Target Indicator and Track Metadata.

Parses VMTI data streams containing per-target information such as:
  - Target centroid (lat/lon)
  - Target velocity (horizontal/vertical)
  - Target size (width/height)
  - Target classification and confidence
  - Track UUIDs for multi-frame tracking

Typical usage:
    from pymisb.vmti import decode_vmti_stream

    for target in decode_vmti_stream(vmti_bytes):
        print(target["lat"], target["lon"], target["classification"])
"""

from __future__ import annotations

import os
import sys
import shutil
import argparse
import subprocess

from ..klvdata import StreamParser
from ..klvdata.misb0903 import VMTILocalSet


# VMTI ST 0903 tag numbers
TAG_NUMBERS = {
    1: "number_of_targets",
    2: "target_centroid_lat",
    3: "target_centroid_lon",
    4: "target_h_velocity",
    5: "target_v_velocity",
    6: "target_width",
    7: "target_height",
    8: "target_classification",
    9: "target_confidence",
    10: "target_track_uuid",
    11: "frame_number",
    12: "target_location_source",
}


def extract_vmti(ts_path: str, ffmpeg_path: str | None = None) -> bytes:
    """Extract raw VMTI KLV data from a TS file using FFmpeg.

    Searches for a secondary data stream (stream 0:d:1) that typically
    carries VMTI metadata alongside the primary KLV channel.

    Args:
        ts_path: Path to the MPEG-TS file.
        ffmpeg_path: Optional path to ffmpeg.

    Returns:
        Raw VMTI bytes.

    Raises:
        RuntimeError: If ffmpeg fails or no data channel found.
    """
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("'ffmpeg' not found on the PATH.")
    cmd = [ffmpeg, "-v", "error", "-i", ts_path,
           "-map", "0:d:1", "-c", "copy", "-f", "data", "-"]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if res.returncode != 0 or not res.stdout:
        msg = res.stderr.decode("utf-8", "replace").strip()
        raise RuntimeError(f"Could not extract VMTI channel.\n{msg}")
    return res.stdout


def parse_vmti(data: bytes) -> list[dict]:
    """Parse raw VMTI bytes into a list of target dicts.

    Each dict contains decoded VMTI fields:
        ``number_of_targets``, ``target_centroid_lat``,
        ``target_centroid_lon``, ``target_classification``, etc.

    Args:
        data: Raw VMTI bytes (from ``extract_vmti`` or FFmpeg pipe).

    Returns:
        List of dicts, one per VMTI packet found in the stream.
    """
    results = []
    for pkt in StreamParser(data):
        if not isinstance(pkt, VMTILocalSet):
            continue
        meta = pkt.MetadataList()
        target: dict = {}
        for tag_id, key_name in TAG_NUMBERS.items():
            if tag_id in meta:
                val = meta[tag_id]
                target[key_name] = val[1] if isinstance(val, tuple) else val
        results.append(target)
    return results


def decode_vmti_stream(data: bytes) -> list[dict]:
    """Alias for ``parse_vmti`` — decode a complete VMTI byte stream.

    Convenience function for batch processing of VMTI data.
    """
    return parse_vmti(data)


def _fmt_target(target: dict) -> str:
    """Format a target dict as a readable one-line string."""
    parts = []
    if "target_track_uuid" in target:
        parts.append(f"track={target['target_track_uuid']}")
    if "target_centroid_lat" in target and "target_centroid_lon" in target:
        parts.append(f"lat={target['target_centroid_lat']}")
        parts.append(f"lon={target['target_centroid_lon']}")
    if "target_classification" in target:
        parts.append(f"class={target['target_classification']}")
    if "target_confidence" in target:
        parts.append(f"conf={target['target_confidence']}")
    if "target_h_velocity" in target:
        parts.append(f"vel_h={target['target_h_velocity']}")
    if "target_width" in target:
        parts.append(f"w={target['target_width']}")
    if "target_height" in target:
        parts.append(f"h={target['target_height']}")
    return "  ".join(parts)


def main(argv=None) -> int:
    """CLI entry point for ``python -m pymisb.vmti``."""
    parser = argparse.ArgumentParser(
        description="Decode MISB ST 0903 VMTI target data from a video.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pymisb.vmti output.ts\n"
            "  python -m pymisb.vmti output.ts --all\n"
        ),
    )
    parser.add_argument("video", help="MISB/TS video with VMTI channel")
    parser.add_argument("--all", action="store_true",
                        help="Show every target field")
    parser.add_argument("--ffmpeg", default=None,
                        help="Path to the ffmpeg binary")
    args = parser.parse_args(argv)

    if not os.path.isfile(args.video):
        print(f"[ERROR] Video does not exist: {args.video}", file=sys.stderr)
        return 2

    print(f"Extracting VMTI channel from {args.video} ...")
    try:
        data = extract_vmti(args.video, ffmpeg_path=args.ffmpeg)
    except RuntimeError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 3

    targets = parse_vmti(data)
    if not targets:
        print("[WARNING] No VMTI targets found.", file=sys.stderr)
        return 0

    print(f"{len(targets)} target(s) decoded.\n")
    for i, t in enumerate(targets):
        print(f"[{i:4d}] {_fmt_target(t)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
