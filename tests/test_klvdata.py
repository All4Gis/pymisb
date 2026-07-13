# -*- coding: utf-8 -*-
"""Tests for the vendored klvdata decoder — ported from paretech/klvdata (MIT).

These validate that our klvdata correctly parses MISB ST 0601 elements
according to the official test vectors from MISB ST 0601.11 Section 8
and MISB ST 0902.5.
"""

from __future__ import annotations

import os
import struct
import pytest

from pymisb.klvdata.common import hexstr_to_bytes, bytes_to_int, ber_encode, ber_decode
from pymisb.klvdata.elementparser import (
    BytesElementParser, DateTimeElementParser, StringElementParser,
    MappedElementParser, IEEE754ElementParser,
)
from pymisb.klvdata.misb0601 import (
    Checksum, PrecisionTimeStamp, MissionID, PlatformTailNumber,
    PlatformHeadingAngle, PlatformPitchAngle, PlatformRollAngle,
    SensorLatitude, SensorLongitude, SensorTrueAltitude,
    SensorHorizontalFieldOfView, SensorVerticalFieldOfView,
    SensorRelativeAzimuthAngle, SensorRelativeElevationAngle,
    SensorRelativeRollAngle, SlantRange, TargetWidth,
    FrameCenterLatitude, FrameCenterLongitude, FrameCenterElevation,
    UASLocalMetadataSet,
)
from pymisb.klvdata.klvparser import KLVParser
from pymisb.klvdata.streamparser import StreamParser


# ══════════════════════════════════════════════════════════════════════════
# common.py utilities
# ══════════════════════════════════════════════════════════════════════════

class TestHexstrToBytes:
    def test_with_spaces(self):
        assert hexstr_to_bytes("06 0E 2B 34") == b"\x06\x0E\x2B\x34"

    def test_with_dashes(self):
        assert hexstr_to_bytes("06-0E-2B-34") == b"\x06\x0E\x2B\x34"

    def test_continuous(self):
        assert hexstr_to_bytes("060E2B34") == b"\x06\x0E\x2B\x34"


class TestBER:
    def test_short_form(self):
        assert ber_encode(0) == b"\x00"
        assert ber_encode(127) == b"\x7F"

    def test_long_form(self):
        result = ber_encode(256)
        assert result[0] & 0x80
        assert len(result) == 3

    def test_roundtrip(self):
        for n in [0, 1, 127, 128, 256, 1000, 65535]:
            assert ber_decode(ber_encode(n)) == n


# ══════════════════════════════════════════════════════════════════════════
# ST0601 element parsers — test vectors from MISB ST 0601.11 Section 8
# ══════════════════════════════════════════════════════════════════════════

class TestChecksum:
    def test_decode(self):
        value = hexstr_to_bytes("AA 43")
        elem = Checksum(value)
        assert str(elem.value) == "0xAA43"

    def test_roundtrip_decode(self):
        """Checksum value bytes are preserved after decode."""
        value = hexstr_to_bytes("AA 43")
        elem = Checksum(value)
        # BytesElementParser stores as int, verify the decode is correct
        assert elem.value.value == 0xAA43


class TestPrecisionTimeStamp:
    def test_decode_misb0902(self):
        """MISB ST 0902.5 example."""
        value = hexstr_to_bytes("00 04 60 50 58 4E 01 80")
        elem = PrecisionTimeStamp(value)
        assert str(elem.value) == "2009-01-12 22:08:22+00:00"

    def test_decode_misb0601(self):
        """MISB ST 0601.9 example."""
        value = hexstr_to_bytes("00 04 59 F4 A6 AA 4A A8")
        elem = PrecisionTimeStamp(value)
        assert str(elem.value) == "2008-10-24 00:13:29.913000+00:00"

    def test_roundtrip(self):
        value = hexstr_to_bytes("00 04 60 50 58 4E 01 80")
        elem = PrecisionTimeStamp(value)
        assert bytes(elem) == hexstr_to_bytes("02 08 00 04 60 50 58 4E 01 80")


class TestMissionID:
    def test_decode_misb0902(self):
        value = hexstr_to_bytes("4D 69 73 73 69 6F 6E 20 31 32")
        elem = MissionID(value)
        assert str(elem.value) == "Mission 12"

    def test_decode_misb0601(self):
        value = hexstr_to_bytes("4D 49 53 53 49 4F 4E 30 31")
        elem = MissionID(value)
        assert str(elem.value) == "MISSION01"


class TestPlatformTailNumber:
    def test_decode(self):
        value = hexstr_to_bytes("41 46 2D 31 30 31")
        elem = PlatformTailNumber(value)
        assert str(elem.value) == "AF-101"


class TestPlatformHeadingAngle:
    def test_decode(self):
        """MISB ST 0601.9 example: 159.97 degrees."""
        value = hexstr_to_bytes("71 C2")
        elem = PlatformHeadingAngle(value)
        assert float(elem.value) == pytest.approx(159.974, abs=0.01)

    def test_roundtrip(self):
        value = hexstr_to_bytes("71 C2")
        elem = PlatformHeadingAngle(value)
        assert bytes(elem) == hexstr_to_bytes("05 02 71 C2")


class TestPlatformPitchAngle:
    def test_decode(self):
        """MISB ST 0601.9 example: -0.43 degrees."""
        value = hexstr_to_bytes("FD 3D")
        elem = PlatformPitchAngle(value)
        assert float(elem.value) == pytest.approx(-0.4315, abs=0.001)


class TestSensorLatitude:
    def test_decode(self):
        """MISB ST 0601.11 example: 60.177 degrees."""
        value = hexstr_to_bytes("55 95 B6 6D")
        elem = SensorLatitude(value)
        assert float(elem.value) == pytest.approx(60.177, abs=0.001)

    def test_roundtrip(self):
        value = hexstr_to_bytes("55 95 B6 6D")
        elem = SensorLatitude(value)
        assert bytes(elem) == hexstr_to_bytes("0D 04 55 95 B6 6D")


class TestSensorLongitude:
    def test_decode(self):
        """MISB ST 0601.11 example: 128.427 degrees."""
        value = hexstr_to_bytes("5B 53 60 C4")
        elem = SensorLongitude(value)
        assert float(elem.value) == pytest.approx(128.427, abs=0.001)


class TestSensorTrueAltitude:
    def test_decode(self):
        """MISB ST 0601.11 example: 14190.72 meters."""
        value = hexstr_to_bytes("C2 21")
        elem = SensorTrueAltitude(value)
        assert float(elem.value) == pytest.approx(14190.72, abs=1.0)


class TestSensorFOV:
    def test_horizontal(self):
        value = hexstr_to_bytes("CD 9C")
        elem = SensorHorizontalFieldOfView(value)
        assert float(elem.value) == pytest.approx(144.57, abs=0.1)

    def test_vertical(self):
        value = hexstr_to_bytes("D9 17")
        elem = SensorVerticalFieldOfView(value)
        assert float(elem.value) == pytest.approx(152.64, abs=0.1)


class TestSensorRelativeAngles:
    def test_azimuth(self):
        value = hexstr_to_bytes("72 4A 0A 20")
        elem = SensorRelativeAzimuthAngle(value)
        assert float(elem.value) == pytest.approx(160.72, abs=0.1)

    def test_elevation(self):
        value = hexstr_to_bytes("87 F8 4B 86")
        elem = SensorRelativeElevationAngle(value)
        assert float(elem.value) == pytest.approx(-168.79, abs=0.1)

    def test_roll(self):
        value = hexstr_to_bytes("7D C5 5E CE")
        elem = SensorRelativeRollAngle(value)
        assert float(elem.value) == pytest.approx(176.87, abs=0.1)


class TestSlantRange:
    def test_decode(self):
        value = hexstr_to_bytes("03 83 09 26")
        elem = SlantRange(value)
        assert float(elem.value) == pytest.approx(68590.98, abs=1.0)


class TestTargetWidth:
    def test_decode(self):
        value = hexstr_to_bytes("12 81")
        elem = TargetWidth(value)
        assert float(elem.value) == pytest.approx(722.82, abs=0.5)


class TestFrameCenter:
    def test_latitude(self):
        value = hexstr_to_bytes("F1 01 A2 29")
        elem = FrameCenterLatitude(value)
        assert float(elem.value) == pytest.approx(-10.542, abs=0.001)

    def test_longitude(self):
        value = hexstr_to_bytes("14 BC 08 2B")
        elem = FrameCenterLongitude(value)
        assert float(elem.value) == pytest.approx(29.158, abs=0.001)

    def test_elevation(self):
        value = hexstr_to_bytes("34 F3")
        elem = FrameCenterElevation(value)
        assert float(elem.value) == pytest.approx(3216.04, abs=1.0)


class TestPlatformCallSign:
    def test_decode(self):
        """PlatformCallSign (Tag 59) — not in vendored subset, verify gracefully."""
        assert b"\x3B" not in UASLocalMetadataSet.parsers  # not included


class TestUASLSVersionNumber:
    def test_decode(self):
        """UASLSVersionNumber (Tag 65) — not in vendored subset, verify gracefully."""
        assert b"\x41" not in UASLocalMetadataSet.parsers  # not included


# ══════════════════════════════════════════════════════════════════════════
# KLVParser — BER-TLV parsing
# ══════════════════════════════════════════════════════════════════════════

class TestKLVParser:
    def test_single_element_short_form(self):
        """Parse a single element with BER short-form length."""
        key = b"\x02"
        length = b"\x08"
        value = b"\x00\x04\x60\x50\x58\x4E\x01\x80"
        packet = key + length + value

        parser = KLVParser(packet, key_length=1)
        parsed_key, parsed_value = next(parser)
        assert parsed_key == key
        assert parsed_value == value

    def test_empty_source(self):
        """Empty source raises StopIteration."""
        parser = KLVParser(b"", key_length=1)
        with pytest.raises(StopIteration):
            next(parser)


# ══════════════════════════════════════════════════════════════════════════
# StreamParser — end-to-end decode of a synthetic KLV stream
# ══════════════════════════════════════════════════════════════════════════

class TestStreamParser:
    def _build_synthetic_stream(self) -> bytes:
        """Build a minimal ST0601 KLV stream for testing.

        Creates a single UAS Datalink Local Set packet with:
        - Tag 2 (PrecisionTimeStamp): 2024-01-01 00:00:00 UTC
        - Tag 65 (UAS LS Version): 11
        - Tag 5 (PlatformHeading): 90 degrees
        - Tag 13 (SensorLatitude): 27.22 degrees
        - Tag 14 (SensorLongitude): -81.88 degrees
        """
        from pymisb.klvdata.common import bytes_to_int

        uas_key = hexstr_to_bytes("06 0E 2B 34 02 0B 01 01 0E 01 03 01 01 00 00 00")

        # Build TLV elements
        def tlv(tag: int, val: bytes) -> bytes:
            return bytes([tag, len(val)]) + val

        # Tag 2: PrecisionTimeStamp (8 bytes, UNIX microseconds)
        ts_us = int(1704067200 * 1e6)  # 2024-01-01 00:00:00 UTC
        tag2 = tlv(2, struct.pack(">Q", ts_us))

        # Tag 65: UAS LS Version = 11
        tag65 = tlv(65, bytes([11]))

        # Tag 5: PlatformHeading = 90.0 degrees
        # 90 / 360 * 65535 = 16383
        heading_enc = int(round(90.0 / 360.0 * 65535))
        tag5 = tlv(5, struct.pack(">H", heading_enc))

        # Tag 13: SensorLatitude = 27.22 degrees
        lat_enc = int(round(27.22 / 90.0 * (2**31 - 1)))
        tag13 = tlv(13, struct.pack(">i", lat_enc))

        # Tag 14: SensorLongitude = -81.88 degrees
        lon_enc = int(round(-81.88 / 180.0 * (2**31 - 1)))
        tag14 = tlv(14, struct.pack(">i", lon_enc))

        payload = tag2 + tag65 + tag5 + tag13 + tag14
        total_len = len(payload) + 4  # + checksum TLV

        # BER length
        ber = bytes([total_len]) if total_len < 128 else b""

        # Checksum placeholder (tag 1, len 2, value 0)
        checksum_tlv = b"\x01\x02\x00\x00"

        return uas_key + ber + payload + checksum_tlv

    def test_parse_synthetic_stream(self):
        """Parse a synthetic ST0601 stream and verify decoded values."""
        stream = self._build_synthetic_stream()
        packets = list(StreamParser(stream))

        assert len(packets) == 1
        pkt = packets[0]
        meta = pkt.MetadataList()

        # Tag 5 - Heading (~90 degrees)
        assert 5 in meta
        heading = float(meta[5][1])
        assert 89.0 < heading < 91.0

        # Tag 13 - Latitude (~27.22 degrees)
        assert 13 in meta
        lat = float(meta[13][1])
        assert 27.0 < lat < 27.5

        # Tag 14 - Longitude (~-81.88 degrees)
        assert 14 in meta
        lon = float(meta[14][1])
        assert -82.0 < lon < -81.5

        # Tag 2 - PrecisionTimeStamp present
        assert 2 in meta

    def test_empty_stream(self):
        """Empty stream yields no packets."""
        packets = list(StreamParser(b""))
        assert packets == []

    def test_multiple_packets(self):
        """Parse a stream with two concatenated packets."""
        s1 = self._build_synthetic_stream()
        s2 = self._build_synthetic_stream()
        packets = list(StreamParser(s1 + s2))
        assert len(packets) == 2


# ══════════════════════════════════════════════════════════════════════════
# Integration test — binary test data from paretech/klvdata (MIT)
# Source: https://github.com/paretech/klvdata/blob/master/data/
# ══════════════════════════════════════════════════════════════════════════

class TestParetechIntegration:
    """Parse the official MISB ST 0902.5 test packet from paretech/klvdata."""

    DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "DynamicConstantMISMMSPacketData.bin")

    def test_parse_full_packet(self):
        """Parse the complete ST0601 packet and verify key tags."""
        with open(self.DATA_FILE, "rb") as f:
            data = f.read()

        packets = list(StreamParser(data))
        assert len(packets) == 1

        pkt = packets[0]
        meta = pkt.MetadataList()

        # Tag 3 - MissionID
        assert 3 in meta
        assert meta[3][1] == "Mission 12"

        # Tag 10 - PlatformDesignation
        assert 10 in meta
        assert meta[10][1] == "Predator"

        # Tag 11 - ImageSourceSensor
        assert 11 in meta
        assert meta[11][1] == "EO Nose"

        # Tag 12 - ImageCoordinateSystem
        assert 12 in meta
        assert meta[12][1] == "Geodetic WGS84"

        # Tag 13 - SensorLatitude present
        assert 13 in meta

        # Tag 14 - SensorLongitude present
        assert 14 in meta

        # Tag 21 - SlantRange present
        assert 21 in meta

    def test_packet_bytes_roundtrip(self):
        """The parsed packet can be serialized back to bytes."""
        with open(self.DATA_FILE, "rb") as f:
            data = f.read()

        packets = list(StreamParser(data))
        assert len(packets) == 1

        # Re-serialize and re-parse
        reserialized = bytes(packets[0])
        reparsed = list(StreamParser(reserialized))
        assert len(reparsed) == 1

        original_meta = packets[0].MetadataList()
        reparsed_meta = reparsed[0].MetadataList()
        assert original_meta.keys() == reparsed_meta.keys()
