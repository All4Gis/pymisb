# Author: Fran Raga <franka1986@gmail.com>

"""MISB ST0601 KLV encoder — builds complete packets from value dicts.

Self-contained encoder that produces the 16-byte universal key, BER length,
tagged elements, and BCC-16 checksum.  No external dependencies.
"""

from __future__ import annotations

import struct

from ..constants import HFOV_DEG, VFOV_DEG, ST0601_VERSION, UAS_LS_KEY


# ── Low-level encoding helpers ────────────────────────────────────────────

def _clamp(value: float, lo: float, hi: float) -> float:
    """Restrict *value* to the range [lo, hi]."""
    return max(lo, min(hi, value))


def encode_unsigned(value: float, vmin: float, vmax: float, nbytes: int) -> int:
    """Map a float in [vmin, vmax] to an unsigned integer of *nbytes*.

    The value is clamped to the valid range first, then linearly mapped
    to [0, 2^(8*nbytes)-1].  Used to encode MISB elements like heading
    (0..360 -> uint16) or altitude (-900..19000 -> uint16).
    """
    value = _clamp(value, vmin, vmax)
    full = (1 << (8 * nbytes)) - 1
    return int(round((value - vmin) / (vmax - vmin) * full))


def encode_signed(value: float, vabs: float, nbytes: int) -> int:
    """Map a float in [-vabs, vabs] to a signed integer of *nbytes*.

    The value is clamped, then linearly mapped to the two's complement
    range.  Used for signed MISB elements like pitch (-20..20 -> int16)
    or latitude (-90..90 -> int32).
    """
    value = _clamp(value, -vabs, vabs)
    half = (1 << (8 * nbytes - 1)) - 1
    return int(round(value / vabs * half))


def build_tlv(tag: int, value: bytes) -> bytes:
    """Build a Tag-Length-Value triplet for a local set element.

    Uses a 1-byte tag and 1-byte length, as defined by MISB ST0601
    for elements inside the UAS Datalink Local Set.
    """
    return bytes([tag, len(value)]) + value


def ber_encode_length(n: int) -> bytes:
    """Encode an integer length in BER (Basic Encoding Rules).

    Short form (1 byte) for values < 128; long form (1+N bytes) for
    larger values, as required by SMPTE 336 / MISB ST0601.
    """
    if n < 128:
        return bytes([n])
    out = bytearray()
    while n > 0:
        out.append(n & 0xFF)
        n >>= 8
    out.reverse()
    return bytes([0x80 | len(out)]) + bytes(out)


def bcc_16(data: bytes) -> int:
    """Compute the ST0601 16-bit Block Check Code (BCC-16).

    Sums bytes weighted by even/odd position within the data.
    The result is used as the checksum appended to every ST0601 packet.
    """
    s = 0
    for i, b in enumerate(data):
        s += b << (8 * ((i + 1) % 2))
    return s & 0xFFFF


# ── Main encoder ──────────────────────────────────────────────────────────

def build_st0601_packet(values: dict) -> bytes:
    """Build a complete MISB ST0601 packet from a dict of quantities.

    Constructs the full binary packet: 16-byte universal key + BER length
    + encoded TLV elements + 2-byte BCC-16 checksum.  This is the main
    entry point for creating KLV packets that can be muxed into a TS stream.

    Args:
        values: Dict with keys like ``timestamp_us``, ``sensor_lat``,
            ``platform_heading``, etc.  Missing optional keys are skipped.

    Returns:
        The raw bytes of the complete ST0601 packet.
    """
    parts: list[bytes] = []

    def add_tlv(tag: int, val: bytes):
        parts.append(build_tlv(tag, val))

    # Tag 2 - Precision Time Stamp (UNIX UTC microseconds, uint64)
    if "timestamp_us" in values:
        add_tlv(2, struct.pack(">Q", int(values["timestamp_us"])))

    # Tag 65 - UAS LS Version Number
    add_tlv(65, bytes([ST0601_VERSION]))

    # Tags 5-7 - Platform attitude
    if "platform_heading" in values:
        add_tlv(5, struct.pack(">H", encode_unsigned(values["platform_heading"], 0, 360, 2)))
    if "platform_pitch" in values:
        add_tlv(6, struct.pack(">h", encode_signed(values["platform_pitch"], 20, 2)))
    if "platform_roll" in values:
        add_tlv(7, struct.pack(">h", encode_signed(values["platform_roll"], 50, 2)))

    # Tags 13-15 - Sensor position
    if "sensor_lat" in values:
        add_tlv(13, struct.pack(">i", encode_signed(values["sensor_lat"], 90, 4)))
    if "sensor_lon" in values:
        add_tlv(14, struct.pack(">i", encode_signed(values["sensor_lon"], 180, 4)))
    if "sensor_alt" in values:
        add_tlv(15, struct.pack(">H", encode_unsigned(values["sensor_alt"], -900, 19000, 2)))

    # Tags 16-17 - Sensor FOV
    add_tlv(16, struct.pack(">H", encode_unsigned(HFOV_DEG, 0, 180, 2)))
    add_tlv(17, struct.pack(">H", encode_unsigned(VFOV_DEG, 0, 180, 2)))

    # Tags 18-20 - Sensor relative angles
    if "sensor_rel_az" in values:
        add_tlv(18, struct.pack(">I", encode_unsigned(values["sensor_rel_az"], 0, 360, 4)))
    if "sensor_rel_el" in values:
        add_tlv(19, struct.pack(">i", encode_signed(values["sensor_rel_el"], 180, 4)))
    if "sensor_rel_roll" in values:
        add_tlv(20, struct.pack(">I", encode_unsigned(values["sensor_rel_roll"], 0, 360, 4)))

    # Tags 21-22 - Slant range and target width
    if "slant_range" in values:
        add_tlv(21, struct.pack(">I", encode_unsigned(values["slant_range"], 0, 5_000_000, 4)))
    if "target_width" in values:
        add_tlv(22, struct.pack(">H", encode_unsigned(values["target_width"], 0, 10_000, 2)))

    # Tags 23-25 - Frame center
    if "fc_lat" in values:
        add_tlv(23, struct.pack(">i", encode_signed(values["fc_lat"], 90, 4)))
    if "fc_lon" in values:
        add_tlv(24, struct.pack(">i", encode_signed(values["fc_lon"], 180, 4)))
    if "fc_elev" in values:
        add_tlv(25, struct.pack(">H", encode_unsigned(values["fc_elev"], -900, 19000, 2)))

    # Assemble: key + BER length + payload + checksum TLV + BCC-16
    payload = b"".join(parts)
    total_len = len(payload) + 4  # + checksum TLV (tag 1, len 2, value 2)
    pre_checksum = UAS_LS_KEY + ber_encode_length(total_len) + payload + b"\x01\x02"
    return pre_checksum + struct.pack(">H", bcc_16(pre_checksum))
