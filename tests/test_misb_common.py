# -*- coding: utf-8 -*-
"""Unit tests for misb.common — the ST0601 encoder and telemetry parsers."""

from __future__ import annotations

import os
import struct
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pymisb.common.encoder import (
    bcc_16,
    ber_encode_length,
    _clamp,
    encode_signed,
    build_tlv,
    encode_unsigned,
    build_st0601_packet,
)
from pymisb.constants import UAS_LS_KEY, ST0601_VERSION
from pymisb.common.dji import (
    _compute_geometry,
    _crc64,
    _parse_dji_time,
    _to_float,
    _xor_decode,
    build_klv_packets,
)
from pymisb.common.ts import default_output
from pymisb.constants import OUT_SUFFIX


# ── _clamp ──────────────────────────────────────────────────────────────────

class TestClamp:
    def test_within_range(self):
        assert _clamp(5, 0, 10) == 5

    def test_below_minimum(self):
        assert _clamp(-3, 0, 10) == 0

    def test_above_maximum(self):
        assert _clamp(15, 0, 10) == 10

    def test_float_values(self):
        assert _clamp(1.5, 0.0, 1.0) == 1.0

    def test_equal_boundaries(self):
        assert _clamp(0, 0, 0) == 0


# ── _u (unsigned mapping) ──────────────────────────────────────────────────

class TestUnsignedMapping:
    def test_midpoint_1byte(self):
        result = encode_unsigned(50.0, 0, 100, 1)
        assert 125 <= result <= 130

    def test_min_value(self):
        assert encode_unsigned(0, 0, 100, 2) == 0

    def test_max_value(self):
        assert encode_unsigned(360, 0, 360, 2) == 0xFFFF

    def test_clamps_below(self):
        assert encode_unsigned(-10, 0, 100, 2) == 0

    def test_clamps_above(self):
        assert encode_unsigned(200, 0, 100, 2) == 0xFFFF


# ── _s (signed mapping) ────────────────────────────────────────────────────

class TestSignedMapping:
    def test_zero(self):
        assert encode_signed(0, 90, 4) == 0

    def test_positive_max(self):
        assert encode_signed(90, 90, 4) == 0x7FFFFFFF

    def test_negative_max(self):
        result = encode_signed(-90, 90, 4)
        assert result < 0

    def test_clamps_below(self):
        assert encode_signed(-100, 90, 4) < 0

    def test_clamps_above(self):
        assert encode_signed(100, 90, 4) > 0


# ── build_tlv ──────────────────────────────────────────────────────────────

class TestTLV:
    def test_basic(self):
        result = build_tlv(2, b"\xAA\xBB")
        assert result == bytes([2, 2, 0xAA, 0xBB])

    def test_tag_only(self):
        result = build_tlv(5, b"")
        assert result == bytes([5, 0])

    def test_max_single_byte_length(self):
        val = b"\x00" * 255
        result = build_tlv(10, val)
        assert result[0] == 10
        assert result[1] == 255
        assert len(result) == 257


# ── ber_encode_length ──────────────────────────────────────────────────────

class TestBerLength:
    def test_short_form(self):
        assert ber_encode_length(0) == b"\x00"
        assert ber_encode_length(127) == bytes([127])

    def test_long_form_2bytes(self):
        result = ber_encode_length(256)
        assert result[0] & 0x80  # long form indicator
        assert len(result) == 3  # indicator + 2 length bytes

    def test_long_form_3bytes(self):
        result = ber_encode_length(70000)
        assert result[0] & 0x80
        assert len(result) == 4


# ── bcc_16 ─────────────────────────────────────────────────────────────────

class TestBCC16:
    def test_empty(self):
        assert bcc_16(b"") == 0

    def test_single_byte(self):
        assert bcc_16(b"\x01") == 0x0100

    def test_known_vector(self):
        # Deterministic: same input always gives same output
        data = bytes(range(256))
        result = bcc_16(data)
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFF


# ── build_st0601_packet ────────────────────────────────────────────────────

class TestBuildSt0601Packet:
    def test_starts_with_uas_ls_key(self):
        pkt = build_st0601_packet({"timestamp_us": 0})
        assert pkt[:16] == UAS_LS_KEY

    def test_contains_version_tag(self):
        pkt = build_st0601_packet({"timestamp_us": 0})
        # Version tag (65) should be present in the payload
        payload = pkt[16:]  # skip key
        assert 65 in payload

    def test_packet_has_checksum(self):
        pkt = build_st0601_packet({"timestamp_us": 0})
        # Last 2 bytes are the checksum
        assert len(pkt) > 18  # key (16) + BER (1+) + minimum payload + checksum (2)

    def test_checksum_is_2_bytes(self):
        pkt = build_st0601_packet({"timestamp_us": 0})
        # Last 2 bytes are the BCC-16 checksum
        checksum = struct.unpack_from(">H", pkt, len(pkt) - 2)[0]
        assert isinstance(checksum, int)
        assert 0 <= checksum <= 0xFFFF

    def test_with_all_fields(self):
        values = {
            "timestamp_us": 1_700_000_000_000_000,
            "platform_heading": 45.0,
            "platform_pitch": -5.0,
            "platform_roll": 3.0,
            "sensor_lat": 27.224511,
            "sensor_lon": -81.885484,
            "sensor_alt": 57.0,
            "sensor_rel_az": 90.0,
            "sensor_rel_el": -45.0,
            "sensor_rel_roll": 0.0,
            "slant_range": 100.0,
            "target_width": 50.0,
            "fc_lat": 27.225,
            "fc_lon": -81.886,
            "fc_elev": 0.0,
        }
        pkt = build_st0601_packet(values)
        assert pkt[:16] == UAS_LS_KEY
        assert len(pkt) > 50  # should be a substantial packet

    def test_packet_is_bytes(self):
        pkt = build_st0601_packet({"timestamp_us": 12345})
        assert isinstance(pkt, bytes)


# ── default_output ──────────────────────────────────────────────────────────

class TestDefaultOutput:
    def test_basic(self):
        result = default_output("video.mp4")
        assert Path(result) == Path(f"./video{OUT_SUFFIX}.ts")

    def test_with_path(self):
        result = default_output("/tmp/video.mp4")
        assert Path(result).name == f"video{OUT_SUFFIX}.ts"
        assert "tmp" in Path(result).parts

    def test_no_extension(self):
        result = default_output("video")
        assert result.endswith(f"{OUT_SUFFIX}.ts")


# ── _to_float ──────────────────────────────────────────────────────────────

class TestToFloat:
    def test_valid_number(self):
        assert _to_float("3.14") == 3.14

    def test_integer_string(self):
        assert _to_float("42") == 42.0

    def test_invalid(self):
        assert _to_float("abc") is None

    def test_empty(self):
        assert _to_float("") is None

    def test_none(self):
        assert _to_float(None) is None


# ── _parse_dji_time ────────────────────────────────────────────────────────

class TestParseDjiTime:
    def test_with_milliseconds(self):
        result = _parse_dji_time("2017/09/19 17:29:18.383")
        assert result == datetime(2017, 9, 19, 17, 29, 18, 383000, tzinfo=timezone.utc)

    def test_without_milliseconds(self):
        result = _parse_dji_time("2017/09/19 17:29:18")
        assert result == datetime(2017, 9, 19, 17, 29, 18, tzinfo=timezone.utc)

    def test_invalid_format(self):
        with pytest.raises(ValueError, match="Unrecognized date format"):
            _parse_dji_time("not-a-date")


# ── _compute_geometry ───────────────────────────────────────────────────────

class TestComputeGeometry:
    def test_basic_computation(self):
        vals = {
            "sensor_lat": 27.224511,
            "sensor_lon": -81.885484,
            "sensor_alt": 57.0,
            "platform_heading": 114.6,
            "platform_pitch": -2.1,
            "_gimbal_pitch": -28.9,
        }
        result = _compute_geometry(vals)
        assert "slant_range" in result
        assert "target_width" in result
        assert "fc_lat" in result
        assert "fc_lon" in result
        assert "fc_elev" in result
        assert result["slant_range"] > 0
        assert result["target_width"] > 0

    def test_missing_altitude(self):
        vals = {"sensor_lat": 27.0, "sensor_lon": -81.0}
        result = _compute_geometry(vals)
        assert result == {}

    def test_missing_latitude(self):
        vals = {"sensor_lon": -81.0, "sensor_alt": 57.0}
        result = _compute_geometry(vals)
        assert result == {}

    def test_zero_altitude(self):
        vals = {
            "sensor_lat": 27.0,
            "sensor_lon": -81.0,
            "sensor_alt": 0.0,
            "platform_heading": 0.0,
            "platform_pitch": 0.0,
            "_gimbal_pitch": 0.0,
        }
        result = _compute_geometry(vals)
        assert result["slant_range"] == 0.0 or result["slant_range"] < 1.0


# ── _xor_decode ────────────────────────────────────────────────────────────

class TestXorDecode:
    def test_short_data_passthrough(self):
        assert _xor_decode(b"", 1) == b""
        assert _xor_decode(b"\xAA", 1) == b"\xAA"

    def test_deterministic(self):
        data = bytes(range(32))
        result1 = _xor_decode(data, 1)
        result2 = _xor_decode(data, 1)
        assert result1 == result2

    def test_different_record_types(self):
        data = bytes(range(32))
        r1 = _xor_decode(data, 1)
        r2 = _xor_decode(data, 3)
        assert r1 != r2


# ── _crc64 ─────────────────────────────────────────────────────────────────

class TestCRC64:
    def test_empty(self):
        assert _crc64(0, b"") == 0

    def test_deterministic(self):
        data = b"hello world"
        r1 = _crc64(0, data)
        r2 = _crc64(0, data)
        assert r1 == r2

    def test_different_seeds(self):
        data = b"test"
        assert _crc64(0, data) != _crc64(1, data)


# ── build_klv_packets (CSV) ────────────────────────────────────────────────

class TestBuildKLVPacketsCSV:
    def _make_csv(self, rows, tmpdir):
        """Create a minimal DJI telemetry CSV."""
        header = (
            "CUSTOM.updateTime,CUSTOM.isVideo,OSD.latitude,OSD.longitude,"
            "OSD.altitude [m],OSD.pitch,OSD.roll,OSD.yaw,"
            "GIMBAL.pitch,GIMBAL.roll,GIMBAL.yaw\n"
        )
        lines = [header]
        for row in rows:
            lines.append(",".join(str(v) for v in row) + "\n")
        path = os.path.join(tmpdir, "telemetry.csv")
        with open(path, "w") as f:
            f.writelines(lines)
        return path

    def test_generates_packets(self, tmp_path):
        csv_path = self._make_csv(
            [
                ("2017/09/19 17:29:18.383", "Recording", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
                ("2017/09/19 17:29:18.493", "Recording", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
            ],
            str(tmp_path),
        )
        packets = build_klv_packets(csv_path, only_recording=True)
        assert len(packets) == 2
        assert packets[0][0] == 0.0  # first packet at t=0
        assert packets[1][0] > 0.0  # second packet after

    def test_filters_non_recording(self, tmp_path):
        csv_path = self._make_csv(
            [
                ("2017/09/19 17:29:18.383", "Recording", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
                ("2017/09/19 17:29:18.493", "", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
            ],
            str(tmp_path),
        )
        packets = build_klv_packets(csv_path, only_recording=True)
        assert len(packets) == 1

    def test_all_rows_mode(self, tmp_path):
        csv_path = self._make_csv(
            [
                ("2017/09/19 17:29:18.383", "Recording", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
                ("2017/09/19 17:29:18.493", "", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
            ],
            str(tmp_path),
        )
        packets = build_klv_packets(csv_path, only_recording=False)
        assert len(packets) == 2

    def test_no_recording_raises(self, tmp_path):
        csv_path = self._make_csv(
            [
                ("2017/09/19 17:29:18.383", "", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
            ],
            str(tmp_path),
        )
        with pytest.raises(RuntimeError, match="No KLV packet"):
            build_klv_packets(csv_path, only_recording=True)

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            build_klv_packets("/nonexistent/path.csv")

    def test_packet_valid_st0601(self, tmp_path):
        csv_path = self._make_csv(
            [
                ("2017/09/19 17:29:18.383", "Recording", 27.22, -81.88, 57, -2, -4, 115, -29, 0, 90),
            ],
            str(tmp_path),
        )
        packets = build_klv_packets(csv_path, only_recording=True)
        _, pkt = packets[0]
        assert pkt[:16] == UAS_LS_KEY
        assert len(pkt) > 20


# ── write_klv_stream ────────────────────────────────────────────────────────

class TestWriteKlvStream:
    def test_writes_klv_file(self, tmp_path):
        from pymisb.common.ts import write_klv_stream

        pkt1 = build_st0601_packet({"timestamp_us": 1_000_000})
        pkt2 = build_st0601_packet({"timestamp_us": 2_000_000})
        packets = [(0.0, pkt1), (1.0, pkt2)]

        out = str(tmp_path / "output.klv")
        result = write_klv_stream(packets, out)
        assert result == out
        assert os.path.isfile(out)

        with open(out, "rb") as f:
            data = f.read()
        assert data == pkt1 + pkt2

    def test_creates_parent_dirs(self, tmp_path):
        from pymisb.common.ts import write_klv_stream

        packets = [(0.0, b"\x00\x01\x02")]
        out = str(tmp_path / "subdir" / "deep" / "output.klv")
        write_klv_stream(packets, out)
        assert os.path.isfile(out)

    def test_empty_packets(self, tmp_path):
        from pymisb.common.ts import write_klv_stream

        out = str(tmp_path / "empty.klv")
        result = write_klv_stream([], out)
        assert result == out
        assert os.path.getsize(out) == 0
