# Author: Fran Raga <franka1986@gmail.com>

"""TS output helpers — path defaults and KLV stream writing."""

import os

from ..constants import OUT_SUFFIX


def default_output(video_path: str) -> str:
    """Build a default output path next to the input video.

    Given ``video.mp4``, returns ``./video_MISB.ts`` in the same directory.
    If the path has no directory component, ``./`` is used.
    """
    base = os.path.splitext(os.path.basename(video_path))[0]
    return os.path.join(os.path.dirname(video_path) or ".", base + OUT_SUFFIX + ".ts")


def write_klv_stream(packets: list[tuple[float, bytes]], out_path: str) -> str:
    """Write KLV packets as a raw binary elementary stream.

    Concatenates the raw bytes of each ST0601 packet (without any TS
    framing) into a single .klv file.  Useful for debugging or for
    feeding into external TS muxers.

    Args:
        packets: List of ``(t_rel_seconds, packet_bytes)`` tuples.
        out_path: Destination file path.  Parent directories are created
            if they don't exist.

    Returns:
        The *out_path* that was written.
    """
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "wb") as fh:
        for _, pkt in packets:
            fh.write(pkt)
    return out_path
