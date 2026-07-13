# Author: Fran Raga <franka1986@gmail.com>

"""MPEG-TS muxing engine — PES/PCR primitives, KLV injection, FFmpeg wrapper.

Creates a MISB ST0601 / STANAG 4609 video (MPEG-TS) with VIDEO + AUDIO +
a TIMED KLV data channel, from a DJI video and its telemetry log.
"""

from __future__ import annotations

import os
import sys
import struct
import shutil
import argparse
import subprocess

from ..common import (
    default_output,
    build_klv_packets, build_klv_packets_from_txt, write_klv_stream,
)


# ══════════════════════════════════════════════════════════════════════════
# 1. MPEG-TS PRIMITIVES  (PES with PTS, PCR, PSI tables)
# ══════════════════════════════════════════════════════════════════════════

def _crc32_mpeg(data: bytes) -> int:
    """Compute CRC-32 for MPEG PSI tables.

    Uses the MPEG CRC-32 polynomial 0x04C11DB7 (MSB-first), as defined
    by ISO 13818-1.  Used to validate and rebuild PAT/PMT tables when
    injecting the KLV PID.
    """
    crc = 0xFFFFFFFF
    for byte in data:
        crc ^= byte << 24
        for _ in range(8):
            crc = ((crc << 1) ^ 0x04C11DB7) & 0xFFFFFFFF if crc & 0x80000000 else (crc << 1) & 0xFFFFFFFF
    return crc


def _encode_pts(pts: int) -> bytes:
    """Encode a 33-bit PTS (Presentation Time Stamp) into 5 PES header bytes.

    The PTS is in units of the 90 kHz MPEG clock.  The encoding follows
    the PES header format: marker bits (0010 xxx1 xxx1 xxx1 xxx1) with
    the 33-bit value split across 5 bytes.
    """
    pts &= 0x1FFFFFFFF
    return bytes([
        0x21 | ((pts >> 29) & 0x0E),
        (pts >> 22) & 0xFF,
        0x01 | ((pts >> 14) & 0xFE),
        (pts >> 7) & 0xFF,
        0x01 | ((pts << 1) & 0xFE),
    ])


def _encode_pcr(pcr_base: int) -> bytes:
    """Encode a 48-bit PCR (Program Clock Reference) into 6 bytes.

    The PCR consists of a 33-bit base at 90 kHz, 6 reserved bits
    (set to 0x3F), and a 9-bit extension (set to 0).  Used in the
    adaptation field of the first TS packet of each PES.
    """
    return ((pcr_base & 0x1FFFFFFFF) << 15 | (0x3F << 9)).to_bytes(6, "big")


def _build_pes(payload: bytes, pts: int) -> bytes:
    """Wrap a KLV unit in a private_stream_1 (0xBD) PES packet with PTS.

    Creates a complete PES packet with the 4-byte start code, PES header
    containing the PTS, and the KLV payload.  The stream_id 0xBD identifies
    it as private_stream_1 (used for KLV metadata in MISB/STANAG 4609).
    """
    body = b"\x80\x80\x05" + _encode_pts(pts) + payload
    return b"\x00\x00\x01\xBD" + struct.pack(">H", len(body)) + body


def _packetize_pes(pid: int, pes: bytes, pcr: int, cc: int, with_pcr: bool = True) -> tuple[bytes, int]:
    """Split a PES into 188-byte MPEG-TS packets.

    Each TS packet has a 4-byte header (sync byte 0x47, PID, flags)
    followed by a payload.  The first packet may include a PCR in its
    adaptation field.  Continuity counter (*cc*) is incremented per packet.

    Args:
        pid: The TS Packet Identifier for this stream.
        pes: The complete PES packet bytes.
        pcr: The PCR value for the first packet's adaptation field.
        cc: Current continuity counter (0-15).
        with_pcr: If True, include PCR in the first packet's adaptation field.

    Returns:
        Tuple of (packetized_bytes, updated_cc).
    """
    out = bytearray()
    data = pes
    first = True
    while data or first:
        pkt = bytearray([0x47, ((0x40 if first else 0x00) | ((pid >> 8) & 0x1F)), pid & 0xFF])
        if first and with_pcr:
            space = 184 - 1 - 7
            chunk = data[:space]
            stuffing = space - len(chunk)
            pkt.append(0x30 | (cc & 0x0F))
            pkt.append(7 + stuffing)
            pkt.append(0x10)
            pkt += _encode_pcr(pcr)
            pkt += b"\xFF" * stuffing
            pkt += chunk
            data = data[len(chunk):]
        elif len(data) >= 184:
            pkt.append(0x10 | (cc & 0x0F))
            pkt += data[:184]
            data = data[184:]
        else:
            pkt.append(0x30 | (cc & 0x0F))
            afl = 183 - len(data)
            pkt.append(afl)
            if afl > 0:
                pkt.append(0x00)
                pkt += b"\xFF" * (afl - 1)
            pkt += data
            data = b""
        cc = (cc + 1) & 0x0F
        first = False
        out.extend(pkt)
    return bytes(out), cc


# ══════════════════════════════════════════════════════════════════════════
# 2. KLV PID INJECTION INTO AN EXISTING TS
# ══════════════════════════════════════════════════════════════════════════

def _pid_of(pkt: bytes) -> int:
    """Extract the 13-bit Packet Identifier (PID) from a TS packet header."""
    return ((pkt[1] & 0x1F) << 8) | pkt[2]


def _read_pcr(pkt: bytes) -> int | None:
    """Read the PCR value from a TS packet's adaptation field.

    Returns the 33-bit PCR base value (in 90 kHz units), or None if
    the packet has no adaptation field or no PCR flag set.
    """
    afc = (pkt[3] >> 4) & 0x03
    if afc in (2, 3) and pkt[4] > 0 and (pkt[5] & 0x10):
        b = pkt[6:12]
        return (b[0] << 25) | (b[1] << 17) | (b[2] << 9) | (b[3] << 1) | (b[4] >> 7)
    return None


def _parse_pat_pmt_pid(pkt: bytes) -> int | None:
    """Parse a PAT (Program Association Table) packet to find the PMT PID.

    Walks the PAT entries and returns the PID of the first non-zero
    program (the PMT).  Returns None if no PMT PID is found.
    """
    ptr = pkt[4]
    t = pkt[5 + ptr:]
    section_length = ((t[1] & 0x0F) << 8) | t[2]
    section = t[3:3 + section_length]
    entries = section[5:section_length - 4]
    for i in range(0, len(entries), 4):
        program = (entries[i] << 8) | entries[i + 1]
        pid = ((entries[i + 2] & 0x1F) << 8) | entries[i + 3]
        if program != 0:
            return pid
    return None


def _merged_pmt_table(pmt_pkt: bytes, klv_pid: int) -> bytes:
    """Build a new PMT table with an added KLV ES entry.

    Takes the existing PMT packet and appends a new elementary stream
    entry with stream_type 0x15 (KLVA descriptor) pointing to *klv_pid*.
    Recomputes the CRC-32 to keep the table valid.
    """
    meta_desc = b"\x26\x09\x01\x00\xFFKLVA\x00\x00"
    meta_std = b"\x27\x09\xC0\x00\x00\xC0\x00\x00\xC0\x00\x00"
    desc = meta_desc + meta_std
    new_es = (b"\x15" + struct.pack(">H", 0xE000 | (klv_pid & 0x1FFF))
              + struct.pack(">H", 0xF000 | (len(desc) & 0x0FFF)) + desc)

    ptr = pmt_pkt[4]
    t = pmt_pkt[5 + ptr:]
    section_length = ((t[1] & 0x0F) << 8) | t[2]
    section = t[3:3 + section_length]
    body = section[:-4]
    new_body = body + new_es
    new_len = len(new_body) + 4
    table = b"\x02" + bytes([0xB0 | ((new_len >> 8) & 0x0F), new_len & 0xFF]) + new_body
    return table + struct.pack(">I", _crc32_mpeg(table))


def _all_pids(pkts) -> set:
    """Collect all PIDs present in a list of TS packets."""
    return {_pid_of(p) for p in pkts if len(p) == 188 and p[0] == 0x47}


def inject_klv_into_ts(video_ts: str, packets: list[tuple[float, bytes]], out_ts: str) -> str:
    """Inject KLV packets with per-packet PTS into an existing MPEG-TS.

    This is the core muxing function.  It:
    1. Reads the video TS and parses all packets using memoryview (zero-copy).
    2. Finds the PAT/PMT and allocates a free PID for the KLV stream.
    3. Rewrites the PMT to advertise the new KLV elementary stream.
    4. Interleaves KLV PES packets at the correct PCR timestamps.
    5. Writes the complete merged TS to *out_ts*.

    Args:
        video_ts: Path to the input MPEG-TS file (video + audio).
        packets: List of ``(t_rel_seconds, st0601_packet_bytes)`` tuples.
        out_ts: Path for the output TS file with the added KLV stream.

    Returns:
        The *out_ts* path.

    Raises:
        RuntimeError: If the PMT cannot be found in the input TS.
    """
    if not packets:
        raise ValueError("No KLV packets to inject.")

    with open(video_ts, "rb") as fh:
        raw = fh.read()
    n = len(raw) // 188
    pkts = [raw[i * 188:(i + 1) * 188] for i in range(n)]

    pmt_pid = None
    for p in pkts:
        if _pid_of(p) == 0x0000 and (p[1] & 0x40):
            pmt_pid = _parse_pat_pmt_pid(p)
            break
    if pmt_pid is None:
        raise RuntimeError("PMT not found in the video TS.")

    used = _all_pids(pkts)
    klv_pid = next(pid for pid in range(0x0100, 0x1FFE) if pid not in used and pid != pmt_pid)

    new_pmt_table = None
    for p in pkts:
        if _pid_of(p) == pmt_pid and (p[1] & 0x40):
            new_pmt_table = _merged_pmt_table(p, klv_pid)
            break

    klv_items = []
    for t_rel, kdata in packets:
        pts = int(round(t_rel * 90000)) & 0x1FFFFFFFF
        klv_items.append((t_rel, _build_pes(kdata, pts), pts))

    if new_pmt_table is None:
        raise RuntimeError("Could not find PMT packet to rewrite.")

    out_parts = []
    klv_cc = 0
    ki = 0
    last_t = 0.0
    for p in pkts:
        if len(p) != 188 or p[0] != 0x47:
            continue
        pcr = _read_pcr(p)
        if pcr is not None:
            last_t = pcr / 90000.0
        if _pid_of(p) == pmt_pid and (p[1] & 0x40):
            payload = b"\x00" + new_pmt_table
            p = bytes([0x47, p[1], p[2], 0x10 | (p[3] & 0x0F)]) + payload
            p = p + b"\xFF" * (188 - len(p))
        while ki < len(klv_items) and klv_items[ki][0] <= last_t:
            chunk, klv_cc = _packetize_pes(klv_pid, klv_items[ki][1], klv_items[ki][2], klv_cc, with_pcr=False)
            out_parts.append(chunk)
            ki += 1
        out_parts.append(p)

    while ki < len(klv_items):
        chunk, klv_cc = _packetize_pes(klv_pid, klv_items[ki][1], klv_items[ki][2], klv_cc, with_pcr=False)
        out_parts.append(chunk)
        ki += 1

    with open(out_ts, "wb") as fh:
        fh.write(b"".join(out_parts))
    return out_ts


# ══════════════════════════════════════════════════════════════════════════
# 3. MUXING WITH FFMPEG
# ══════════════════════════════════════════════════════════════════════════

def mux_with_ffmpeg(video_path: str, packets: list[tuple[float, bytes]], out_path: str, ffmpeg_path: str | None = None) -> None:
    """Mux a DJI video + KLV packets into a MISB STANAG 4609 MPEG-TS.

    Two-step process:
    1. FFmpeg copies video+audio into a temporary TS (no re-encoding).
    2. Python injects the KLV PID with per-packet PTS into the TS.

    Args:
        video_path: Path to the input video (.mp4 or similar).
        packets: List of ``(t_rel_seconds, st0601_packet_bytes)`` tuples.
        out_path: Path for the output .ts file.
        ffmpeg_path: Optional path to the ffmpeg binary (searches PATH if None).

    Raises:
        RuntimeError: If ffmpeg is not found or fails.
    """
    ffmpeg = ffmpeg_path or shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("'ffmpeg' not found on the PATH. Use --ffmpeg to specify its location.")

    tmp_ts = os.path.splitext(out_path)[0] + ".video.ts"
    try:
        cmd = [
            ffmpeg, "-y",
            "-i", video_path,
            "-map", "0:v", "-map", "0:a?",
            "-c", "copy",
            "-muxpreload", "0", "-muxdelay", "0",
            "-f", "mpegts",
            tmp_ts,
        ]
        print("  ffmpeg (video/audio -> TS):", " ".join(cmd))
        res = subprocess.run(cmd)
        if res.returncode != 0:
            raise RuntimeError("ffmpeg failed to create the video/audio TS.")

        print("  Injecting timed KLV PID (per-packet PTS) in Python ...")
        inject_klv_into_ts(tmp_ts, packets, out_path)
    finally:
        try:
            os.remove(tmp_ts)
        except OSError:
            pass


# ══════════════════════════════════════════════════════════════════════════
# 4. CLI
# ══════════════════════════════════════════════════════════════════════════

def main(argv=None) -> int:
    """CLI entry point for ``python -m pymisb.mux``.

    Parses arguments, builds KLV packets from DJI telemetry (CSV or .txt),
    and muxes them into a MISB STANAG 4609 video using FFmpeg.

    Returns:
        0 on success, 2 on argument/validation error, other on failure.
    """
    parser = argparse.ArgumentParser(
        description="Create a MISB/STANAG 4609 video (video + audio + KLV) with FFmpeg.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pymisb.mux --video DJI_0047.mp4 --csv telemetry.csv\n"
            "  python -m pymisb.mux --csv telemetry.csv --out MISB.ts --klv-only\n"
            "  python -m pymisb.mux --dji-txt DJIFlightRecord.txt --klv-only\n"
        ),
    )
    parser.add_argument("--video", help="DJI video path (.mp4). Required unless --klv-only")
    parser.add_argument("--csv", help="DJI telemetry CSV")
    parser.add_argument("--dji-txt", help="DJI binary .txt flight record")
    parser.add_argument("--out", default=None, help="MPEG-TS output (.ts)")
    parser.add_argument("--all-rows", action="store_true",
                        help="Don't filter by CUSTOM.isVideo=Recording (CSV only)")
    parser.add_argument("--klv-only", action="store_true",
                        help="Only generate the .klv stream (no muxing)")
    parser.add_argument("--ffmpeg", default=None, help="Path to the ffmpeg binary")
    args = parser.parse_args(argv)

    if not args.csv and not args.dji_txt:
        print("[ERROR] One of --csv or --dji-txt is required.", file=sys.stderr)
        return 2
    if args.csv and args.dji_txt:
        print("[ERROR] Use only one of --csv or --dji-txt, not both.", file=sys.stderr)
        return 2
    if not args.klv_only and not args.video:
        print("[ERROR] --video is required (or use --klv-only to only build the .klv).",
              file=sys.stderr)
        return 2

    if args.out is None:
        if not args.video:
            print("[ERROR] --out is required when using --klv-only without --video.",
                  file=sys.stderr)
            return 2
        args.out = default_output(args.video)

    if args.csv:
        if not os.path.isfile(args.csv):
            print(f"[ERROR] CSV does not exist: {args.csv}", file=sys.stderr)
            return 2
        print(f"[1/2] Generating ST0601 KLV from {args.csv} ...")
        packets = build_klv_packets(args.csv, only_recording=not args.all_rows)
    else:
        if not os.path.isfile(args.dji_txt):
            print(f"[ERROR] DJI .txt does not exist: {args.dji_txt}", file=sys.stderr)
            return 2
        print(f"[1/2] Generating ST0601 KLV from {args.dji_txt} ...")
        packets = build_klv_packets_from_txt(args.dji_txt)

    dur = packets[-1][0] - packets[0][0]
    print(f"      {len(packets)} KLV packets  (~{dur:.1f}s, "
          f"{len(packets) / dur if dur else 0:.1f} Hz)")

    if args.klv_only:
        klv_path = os.path.splitext(args.out)[0] + ".klv"
        write_klv_stream(packets, klv_path)
        print(f"      KLV stream written to {klv_path}")
        return 0

    if not os.path.isfile(args.video):
        print(f"[ERROR] Video does not exist: {args.video}", file=sys.stderr)
        return 2

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    print(f"[2/2] Muxing (ffmpeg) -> {args.out} ...")
    mux_with_ffmpeg(args.video, packets, args.out, ffmpeg_path=args.ffmpeg)

    print(f"\n[OK] MISB video created: {args.out}")
    print(f"     Check it with: ffprobe {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
