# Author: Fran Raga <franka1986@gmail.com>

"""DJI telemetry parsers — CSV and binary .txt flight records into KLV packets.

Parses DJI telemetry data from two sources:
  - CSV files exported by DJI Assistant / CsvView
  - Binary .txt flight records written by the drone firmware

Both produce ``(t_rel_seconds, st0601_packet_bytes)`` tuples ready for muxing.
"""

from __future__ import annotations

import os
import csv
import struct
from math import tan, cos, sin, radians, degrees
from datetime import datetime, timezone

from ..constants import TAN_HFOV_HALF, EARTH_MEAN_RADIUS
from .encoder import build_st0601_packet

# DJI CSV column -> (val_key, extra_key, normalize_angle)
_CSV_MAP = [
    ("OSD.yaw",          "platform_heading",  None,             True),
    ("OSD.pitch",        "platform_pitch",    None,             False),
    ("OSD.roll",         "platform_roll",     None,             False),
    ("OSD.latitude",     "sensor_lat",        None,             False),
    ("OSD.longitude",    "sensor_lon",        None,             False),
    ("OSD.altitude [m]", "sensor_alt",        None,             False),
    ("GIMBAL.yaw",       "sensor_rel_az",     None,             True),
    ("GIMBAL.pitch",     "sensor_rel_el",     "_gimbal_pitch",  False),
    ("GIMBAL.roll",      "sensor_rel_roll",   None,             True),
]


# ── Helpers ───────────────────────────────────────────────────────────────

def _to_float(text: str):
    """Safely convert *text* to float, returning None on failure."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _parse_dji_time(text: str) -> datetime:
    """Parse a DJI timestamp string into a UTC datetime.

    DJI uses the format ``YYYY/MM/DD HH:MM:SS.fff`` (sometimes without
    milliseconds).  Returns a timezone-aware datetime in UTC.
    """
    for fmt in ("%Y/%m/%d %H:%M:%S.%f", "%Y/%m/%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise ValueError(f"Unrecognized date format: {text!r}")


def _compute_geometry(row_vals: dict) -> dict:
    """Compute sensor footprint geometry from the platform pose.

    Calculates slant range, target width, and frame center ground position
    from the sensor altitude, platform pitch, gimbal pitch, and heading.
    This is an approximation (same approach as QGISFMV) — good enough to
    draw the sensor footprint on a map.

    Args:
        row_vals: Must contain ``sensor_lat``, ``sensor_lon``,
            ``sensor_alt``, ``platform_heading``.  May contain
            ``platform_pitch`` and ``_gimbal_pitch``.

    Returns:
        Dict with ``slant_range``, ``target_width``, ``fc_lat``,
        ``fc_lon``, ``fc_elev`` (or empty dict if inputs are missing).
    """
    out: dict = {}
    lat = row_vals.get("sensor_lat")
    lon = row_vals.get("sensor_lon")
    alt = row_vals.get("sensor_alt")
    yaw = row_vals.get("platform_heading")
    pitch = row_vals.get("platform_pitch", 0.0) or 0.0
    gimbal_pitch = row_vals.get("_gimbal_pitch", 0.0) or 0.0

    if None in (lat, lon, alt) or yaw is None:
        return out

    lat = float(lat)
    lon = float(lon)
    alt = float(alt)
    yaw = float(yaw)

    depression = pitch + gimbal_pitch
    angle = 180.0 + depression
    cos_a = cos(radians(angle))
    if abs(cos_a) < 0.0017:
        cos_a = 0.0017 * (1 if cos_a >= 0 else -1)
    slant = abs(alt / cos_a)
    out["slant_range"] = slant
    out["target_width"] = 2.0 * slant * TAN_HFOV_HALF

    ground_angle = 90.0 + depression
    tg_dist = alt * tan(radians(ground_angle))
    dy = tg_dist * cos(radians(yaw))
    dx = tg_dist * sin(radians(yaw))
    fc_lat = lat + degrees(dy / EARTH_MEAN_RADIUS)
    cos_lat = cos(radians(lat)) or 1e-6
    fc_lon = lon + degrees(dx / EARTH_MEAN_RADIUS) / cos_lat
    out["fc_lat"] = fc_lat
    out["fc_lon"] = fc_lon
    out["fc_elev"] = 0.0
    return out


# ── CSV parser ────────────────────────────────────────────────────────────

def build_klv_packets(csv_path: str, only_recording: bool = True) -> list[tuple[float, bytes]]:
    """Parse a DJI telemetry CSV and return ST0601 KLV packets.

    Reads the CSV row by row, extracts OSD and gimbal values, computes
    the sensor footprint geometry, and encodes each row as an ST0601
    packet with an absolute UNIX timestamp.

    Args:
        csv_path: Path to the DJI telemetry CSV file.
        only_recording: When True (default), only rows where
            ``CUSTOM.isVideo`` equals ``'Recording'`` are used.

    Returns:
        List of ``(t_rel_seconds, packet_bytes)`` tuples, where
        ``t_rel`` is seconds since the first recording row (used as
        the PTS in the MPEG-TS mux).

    Raises:
        FileNotFoundError: If *csv_path* does not exist.
        RuntimeError: If no valid packets were generated.
    """
    if not os.path.isfile(csv_path):
        raise FileNotFoundError(csv_path)

    packets: list[tuple[float, bytes]] = []
    t0 = None

    with open(csv_path, newline="", encoding="utf-8", errors="replace") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            is_video = (row.get("CUSTOM.isVideo") or "").strip()
            if only_recording and not is_video:
                continue

            time_str = (row.get("CUSTOM.updateTime") or "").strip()
            if not time_str:
                continue
            t = _parse_dji_time(time_str)
            if t0 is None:
                t0 = t
            t_rel = (t - t0).total_seconds()
            if t_rel < 0:
                continue

            vals: dict = {"timestamp_us": int(t.timestamp() * 1_000_000)}

            for csv_col, val_key, extra_key, norm_angle in _CSV_MAP:
                v = _to_float(row.get(csv_col))
                if v is not None:
                    if norm_angle:
                        v = v % 360.0
                    vals[val_key] = v
                    if extra_key:
                        vals[extra_key] = v

            vals.update(_compute_geometry(vals))
            vals.pop("_gimbal_pitch", None)
            packets.append((t_rel, build_st0601_packet(vals)))

    if not packets:
        raise RuntimeError(
            "No KLV packet was generated. Does the CSV have rows with "
            "CUSTOM.isVideo = 'Recording'? Try --all-rows."
        )
    return packets


# ── Binary .txt parser ────────────────────────────────────────────────────

# CRC-64 lookup table (Jones polynomial) for XOR record decoding.
_CRC64_TABLE = [
    0x0, 0x7ad870c830358979, 0xf5b0e190606b12f2, 0x8f689158505e9b8b,
    0xc038e5739841b68f, 0xbae095bba8743ff6, 0x358804e3f82aa47d, 0x4f50742bc81f2d04,
    0xab28ecb46814fe75, 0xd1f09c7c5821770c, 0x5e980d24087fec87, 0x24407dec384a65fe,
    0x6b1009c7f05548fa, 0x11c8790fc060c183, 0x9ea0e857903e5a08, 0xe478989fa00bd371,
    0x7d08ff3b88be6f81, 0x7d08ff3b88be6f8, 0x88b81eabe8d57d73, 0xf2606e63d8e0f40a,
    0xbd301a4810ffd90e, 0xc7e86a8020ca5077, 0x4880fbd87094cbfc, 0x32588b1040a14285,
    0xd620138fe0aa91f4, 0xacf86347d09f188d, 0x2390f21f80c18306, 0x594882d7b0f40a7f,
    0x1618f6fc78eb277b, 0x6cc0863448deae02, 0xe3a8176c18803589, 0x997067a428b5bcf0,
    0xfa11fe77117cdf02, 0x80c98ebf2149567b, 0xfa11fe77117cdf0, 0x75796f2f41224489,
    0x3a291b04893d698d, 0x40f16bccb908e0f4, 0xcf99fa94e9567b7f, 0xb5418a5cd963f206,
    0x513912c379682177, 0x2be1620b495da80e, 0xa489f35319033385, 0xde51839b2936bafc,
    0x9101f7b0e12997f8, 0xebd98778d11c1e81, 0x64b116208142850a, 0x1e6966e8b1770c73,
    0x8719014c99c2b083, 0xfdc17184a9f739fa, 0x72a9e0dcf9a9a271, 0x8719014c99c2b08,
    0x4721e43f0183060c, 0x3df994f731b68f75, 0xb29105af61e814fe, 0xc849756751dd9d87,
    0x2c31edf8f1d64ef6, 0x56e99d30c1e3c78f, 0xd9810c6891bd5c04, 0xa3597ca0a188d57d,
    0xec09088b6997f879, 0x96d1784359a27100, 0x19b9e91b09fcea8b, 0x636199d339c963f2,
    0xdf7adabd7a6e2d6f, 0xa5a2aa754a5ba416, 0x2aca3b2d1a053f9d, 0x50124be52a30b6e4,
    0x1f423fcee22f9be0, 0x659a4f06d21a1299, 0xeaf2de5e82448912, 0x902aae96b271006b,
    0x74523609127ad31a, 0xe8a46c1224f5a63, 0x81e2d7997211c1e8, 0xfb3aa75142244891,
    0xb46ad37a8a3b6595, 0xceb2a3b2ba0eecec, 0x41da32eaea507767, 0x3b024222da65fe1e,
    0xa2722586f2d042ee, 0xd8aa554ec2e5cb97, 0x57c2c41692bb501c, 0x2d1ab4dea28ed965,
    0x624ac0f56a91f461, 0x1892b03d5aa47d18, 0x97fa21650afae693, 0xed2251ad3acf6fea,
    0x95ac9329ac4bc9b, 0x7382b9faaaf135e2, 0xfcea28a2faafae69, 0x8632586aca9a2710,
    0xc9622c4102850a14, 0xb3ba5c8932b0836d, 0x3cd2cdd162ee18e6, 0x460abd1952db919f,
    0x256b24ca6b12f26d, 0x5fb354025b277b14, 0xd0dbc55a0b79e09f, 0xaa03b5923b4c69e6,
    0xe553c1b9f35344e2, 0x9f8bb171c366cd9b, 0x10e3202993385610, 0x6a3b50e1a30ddf69,
    0x8e43c87e03060c18, 0xf49bb8b633338561, 0x7bf329ee636d1eea, 0x12b592653589793,
    0x4e7b2d0d9b47ba97, 0x34a35dc5ab7233ee, 0xbbcbcc9dfb2ca865, 0xc113bc55cb19211c,
    0x5863dbf1e3ac9dec, 0x22bbab39d3991495, 0xadd33a6183c78f1e, 0xd70b4aa9b3f20667,
    0x985b3e827bed2b63, 0xe2834e4a4bd8a21a, 0x6debdf121b863991, 0x1733afda2bb3b0e8,
    0xf34b37458bb86399, 0x8993478dbb8deae0, 0x6fbd6d5ebd3716b, 0x7c23a61ddbe6f812,
    0x3373d23613f9d516, 0x49aba2fe23cc5c6f, 0xc6c333a67392c7e4, 0xbc1b436e43a74e9d,
    0x95ac9329ac4bc9b5, 0xef74e3e19c7e40cc, 0x601c72b9cc20db47, 0x1ac40271fc15523e,
    0x5594765a340a7f3a, 0x2f4c0692043ff643, 0xa02497ca54616dc8, 0xdafce7026454e4b1,
    0x3e847f9dc45f37c0, 0x445c0f55f46abeb9, 0xcb349e0da4342532, 0xb1eceec59401ac4b,
    0xfebc9aee5c1e814f, 0x8464ea266c2b0836, 0xb0c7b7e3c7593bd, 0x71d40bb60c401ac4,
    0xe8a46c1224f5a634, 0x927c1cda14c02f4d, 0x1d148d82449eb4c6, 0x67ccfd4a74ab3dbf,
    0x289c8961bcb410bb, 0x5244f9a98c8199c2, 0xdd2c68f1dcdf0249, 0xa7f41839ecea8b30,
    0x438c80a64ce15841, 0x3954f06e7cd4d138, 0xb63c61362c8a4ab3, 0xcce411fe1cbfc3ca,
    0x83b465d5d4a0eece, 0xf96c151de49567b7, 0x76048445b4cbfc3c, 0xcdcf48d84fe7545,
    0x6fbd6d5ebd3716b7, 0x15651d968d029fce, 0x9a0d8ccedd5c0445, 0xe0d5fc06ed698d3c,
    0xaf85882d2576a038, 0xd55df8e515432941, 0x5a3569bd451db2ca, 0x20ed197575283bb3,
    0xc49581ead523e8c2, 0xbe4df122e51661bb, 0x3125607ab548fa30, 0x4bfd10b2857d7349,
    0x4ad64994d625e4d, 0x7e7514517d57d734, 0xf11d85092d094cbf, 0x8bc5f5c11d3cc5c6,
    0x12b5926535897936, 0x686de2ad05bcf04f, 0xe70573f555e26bc4, 0x9ddd033d65d7e2bd,
    0xd28d7716adc8cfb9, 0xa85507de9dfd46c0, 0x273d9686cda3dd4b, 0x5de5e64efd965432,
    0xb99d7ed15d9d8743, 0xc3450e196da80e3a, 0x4c2d9f413df695b1, 0x36f5ef890dc31cc8,
    0x79a59ba2c5dc31cc, 0x37deb6af5e9b8b5, 0x8c157a32a5b7233e, 0xf6cd0afa9582aa47,
    0x4ad64994d625e4da, 0x300e395ce6106da3, 0xbf66a804b64ef628, 0xc5bed8cc867b7f51,
    0x8aeeace74e645255, 0xf036dc2f7e51db2c, 0x7f5e4d772e0f40a7, 0x5863dbf1e3ac9de,
    0xe1fea520be311aaf, 0x9b26d5e88e0493d6, 0x144e44b0de5a085d, 0x6e963478ee6f8124,
    0x21c640532670ac20, 0x5b1e309b16452559, 0xd476a1c3461bbed2, 0xaeaed10b762e37ab,
    0x37deb6af5e9b8b5b, 0x4d06c6676eae0222, 0xc26e573f3ef099a9, 0xb8b627f70ec510d0,
    0xf7e653dcc6da3dd4, 0x8d3e2314f6efb4ad, 0x256b24ca6b12f26, 0x788ec2849684a65f,
    0x9cf65a1b368f752e, 0xe62e2ad306bafc57, 0x6946bb8b56e467dc, 0x139ecb4366d1eea5,
    0x5ccebf68aecec3a1, 0x2616cfa09efb4ad8, 0xa97e5ef8cea5d153, 0xd3a62e30fe90582a,
    0xb0c7b7e3c7593bd8, 0xca1fc72bf76cb2a1, 0x45775673a732292a, 0x3faf26bb9707a053,
    0x70ff52905f188d57, 0xa2722586f2d042e, 0x854fb3003f739fa5, 0xff97c3c80f4616dc,
    0x1bef5b57af4dc5ad, 0x61372b9f9f784cd4, 0xee5fbac7cf26d75f, 0x9487ca0fff135e26,
    0xdbd7be24370c7322, 0xa10fceec0739fa5b, 0x2e675fb4576761d0, 0x54bf2f7c6752e8a9,
    0xcdcf48d84fe75459, 0xb71738107fd2dd20, 0x387fa9482f8c46ab, 0x42a7d9801fb9cfd2,
    0xdf7adabd7a6e2d6, 0x772fdd63e7936baf, 0xf8474c3bb7cdf024, 0x829f3cf387f8795d,
    0x66e7a46c27f3aa2c, 0x1c3fd4a417c62355, 0x935745fc4798b8de, 0xe98f353477ad31a7,
    0xa6df411fbfb21ca3, 0xdc0731d78f8795da, 0x536fa08fdfd90e51, 0x29b7d047efec8728,
]

_MASK64 = 0xFFFFFFFFFFFFFFFF
_XOR_MAGIC = 0x123456789ABCDEF0


def _crc64(seed: int, data: bytes) -> int:
    """Compute CRC-64 (Jones polynomial) used for DJI XOR record decoding.

    The seed is combined with each byte of *data* via the precomputed
    lookup table to produce a 64-bit checksum.  This is an internal
    helper for ``_xor_decode``.
    """
    crc = seed & _MASK64
    for byte in data:
        index = (crc ^ byte) & 0xFF
        crc = _CRC64_TABLE[index] ^ (crc >> 8)
    return crc & _MASK64


def _xor_decode(data: bytes, record_type: int) -> bytes:
    """XOR-decode a DJI binary record payload (firmware v7+).

    The first byte of *data* is the key seed.  Combined with
    *record_type*, it produces a pseudo-random XOR key via CRC-64.
    Each payload byte (after the first) is XORed with the key to
    recover the plaintext.

    Args:
        data: Raw encrypted record payload (first byte = seed).
        record_type: The DJI record type identifier (1 = OSD, 3 = gimbal).

    Returns:
        Decrypted payload bytes (without the seed byte).
    """
    if len(data) < 2:
        return data
    first_byte = data[0]
    seed = (first_byte + record_type) & 0xFF
    key_input = ((_XOR_MAGIC * first_byte) & _MASK64).to_bytes(8, "little")
    key = _crc64(seed, key_input).to_bytes(8, "little")
    out = bytearray(len(data) - 1)
    for i in range(len(out)):
        out[i] = data[i + 1] ^ key[i % 8]
    return bytes(out)


def _parse_dji_txt(txt_path: str):
    """Parse a DJI binary .txt flight record.

    Reads the binary file, extracts OSD records (lat, lon, alt, pitch,
    roll, yaw) and gimbal records (pitch, roll, yaw).  Supports firmware
    format versions 1-12 (XOR-encoded).  Versions 13-14 (AES-encrypted)
    are not supported.

    Args:
        txt_path: Path to the DJI .txt flight record.

    Returns:
        Tuple of ``(osd_records, gimbal_records)`` where each OSD record
        is ``(lat, lon, alt, pitch, roll, yaw)`` and each gimbal record
        is ``(pitch, roll, yaw)``.

    Raises:
        RuntimeError: If the file is too small or corrupt.
    """
    with open(txt_path, "rb") as fh:
        body = fh.read()

    if len(body) < 12:
        raise RuntimeError(
            f"DJI .txt flight record is too small ({len(body)} bytes). "
            "The file may be corrupt or truncated."
        )

    header, detail_size, version = struct.unpack_from("<Qhb", body, 0)
    headsize = 100 if version >= 6 else 12

    if version >= 12:
        record_start = headsize + detail_size
        record_end = header
    else:
        record_start = headsize
        record_end = header

    record_area = body[record_start:record_end + 1]
    osd_records: list[tuple] = []
    gimbal_records: list[tuple] = []

    i = 0
    while i < len(record_area) - 2:
        record_type = record_area[i]
        record_size = record_area[i + 1]
        payload = record_area[i + 2:i + 2 + record_size]
        end_marker = record_area[i + 2 + record_size] if i + 2 + record_size < len(record_area) else 0
        i += record_size + 3

        if end_marker != 0xFF:
            continue

        if version >= 7:
            payload = _xor_decode(payload, record_type)

        try:
            if record_type == 1 and len(payload) >= 30:
                lon_rad, lat_rad = struct.unpack_from("<dd", payload, 0)
                height = struct.unpack_from("<h", payload, 16)[0]
                pitch_r = struct.unpack_from("<h", payload, 22)[0]
                roll_r = struct.unpack_from("<h", payload, 24)[0]
                yaw_r = struct.unpack_from("<h", payload, 26)[0]
                osd_records.append((
                    degrees(lat_rad), degrees(lon_rad),
                    height * 0.1, pitch_r * 0.1, roll_r * 0.1, yaw_r * 0.1,
                ))
            elif record_type == 3 and len(payload) >= 6:
                g_pitch, g_roll, g_yaw = struct.unpack_from("<hhh", payload, 0)
                gimbal_records.append((g_pitch * 0.1, g_roll * 0.1, g_yaw * 0.1))
        except (struct.error, IndexError):
            continue

    return osd_records, gimbal_records


def build_klv_packets_from_txt(txt_path: str) -> list[tuple[float, bytes]]:
    """Parse a DJI binary .txt flight record and return ST0601 KLV packets.

    Reads the binary file directly (no CSV conversion needed), extracts
    OSD and gimbal records, computes geometry, and encodes each sample
    as an ST0601 packet.

    Args:
        txt_path: Path to the DJI .txt flight record.

    Returns:
        List of ``(t_rel_seconds, packet_bytes)`` tuples at ~10 Hz.

    Raises:
        FileNotFoundError: If *txt_path* does not exist.
        RuntimeError: If no OSD records are found (may be AES-encrypted).
    """
    if not os.path.isfile(txt_path):
        raise FileNotFoundError(txt_path)

    osd_records, gimbal_records = _parse_dji_txt(txt_path)

    if not osd_records:
        raise RuntimeError(
            "No OSD records found in the DJI .txt flight record. "
            "The file may use a format version (v13-14) that requires "
            "AES decryption (not supported)."
        )

    packets: list[tuple[float, bytes]] = []
    for idx, (lat, lon, alt, pitch, roll, yaw) in enumerate(osd_records):
        t_rel = idx * 0.1  # ~10 Hz OSD sample rate

        vals: dict = {
            "timestamp_us": int(t_rel * 1_000_000),
            "platform_heading": yaw % 360.0,
            "platform_pitch": pitch,
            "platform_roll": roll,
            "sensor_lat": lat,
            "sensor_lon": lon,
            "sensor_alt": alt,
        }

        if idx < len(gimbal_records):
            gp, gr, gga = gimbal_records[idx]
            vals["sensor_rel_az"] = gga % 360.0
            vals["sensor_rel_el"] = gp
            vals["sensor_rel_roll"] = gr % 360.0
            vals["_gimbal_pitch"] = gp

        vals.update(_compute_geometry(vals))
        vals.pop("_gimbal_pitch", None)
        packets.append((t_rel, build_st0601_packet(vals)))

    if not packets:
        raise RuntimeError("No KLV packets generated from the .txt flight record.")
    return packets
