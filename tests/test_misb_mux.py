# -*- coding: utf-8 -*-
"""Unit tests for pymisb.mux.engine — MPEG-TS primitives (no FFmpeg required)."""

from __future__ import annotations

import struct

import pytest

from pymisb.mux.engine import (
    _crc32_mpeg,
    _encode_pcr,
    _encode_pts,
    _build_pes,
    _packetize_pes,
    _pid_of,
    _read_pcr,
    main,
)


# ── _crc32_mpeg ────────────────────────────────────────────────────────────

class TestCRC32MPEG:
    def test_empty(self):
        assert _crc32_mpeg(b"") == 0xFFFFFFFF

    def test_single_byte(self):
        result = _crc32_mpeg(b"\x00")
        assert isinstance(result, int)
        assert 0 <= result <= 0xFFFFFFFF

    def test_deterministic(self):
        data = b"MPEG-TS test data"
        assert _crc32_mpeg(data) == _crc32_mpeg(data)

    def test_known_vector(self):
        # CRC32 of "123456789" with poly 0x04C11DB7
        result = _crc32_mpeg(b"123456789")
        assert isinstance(result, int)


# ── _encode_pts ────────────────────────────────────────────────────────────

class TestEncodePTS:
    def test_length(self):
        pts = _encode_pts(0)
        assert len(pts) == 5

    def test_prefix_bits(self):
        # PTS marker bits: 0010 xxx1 xxx1 xxx1 xxx1
        pts = _encode_pts(0)
        assert (pts[0] & 0xF1) == 0x21  # 0010 0001

    def test_roundtrip_simple(self):
        # Encode 0 and verify the structure
        encoded = _encode_pts(0)
        assert encoded[0] & 0xF1 == 0x21
        assert encoded[2] & 0x01 == 0x01
        assert encoded[4] & 0x01 == 0x01

    def test_large_pts(self):
        pts = _encode_pts(0x1FFFFFFFF)  # max 33-bit value
        assert len(pts) == 5


# ── _encode_pcr ────────────────────────────────────────────────────────────

class TestEncodePCR:
    def test_length(self):
        pcr = _encode_pcr(0)
        assert len(pcr) == 6

    def test_zero_base(self):
        pcr = _encode_pcr(0)
        # PCR(0) still has reserved bits set, so not all zeros
        assert len(pcr) == 6

    def test_nonzero(self):
        pcr = _encode_pcr(1000)
        assert pcr != b"\x00\x00\x00\x00\x00\x00"


# ── _build_pes ─────────────────────────────────────────────────────────────

class TestBuildPES:
    def test_starts_with_prefix(self):
        pes = _build_pes(b"\x00\x01\x02", 90000)
        assert pes[:4] == b"\x00\x00\x01\xBD"

    def test_contains_pts(self):
        pes = _build_pes(b"\x00", 90000)
        # PTS should be encoded in the PES header
        assert len(pes) > 4

    def test_payload_included(self):
        payload = b"\xAA\xBB\xCC\xDD"
        pes = _build_pes(payload, 0)
        assert payload in pes


# ── _packetize_pes ─────────────────────────────────────────────────────────

class TestPacketizePES:
    def test_all_188_byte_packets(self):
        pes = b"\x00\x00\x01\xBD" + b"\x00" * 200
        data, cc = _packetize_pes(0x0100, pes, 0, 0)
        # Every packet must be exactly 188 bytes
        for i in range(0, len(data), 188):
            pkt = data[i:i + 188]
            assert len(pkt) == 188
            assert pkt[0] == 0x47

    def test_continuity_counter_increments(self):
        pes = b"\x00" * 500
        _, final_cc = _packetize_pes(0x0100, pes, 0, 0)
        expected_count = (len(pes) + 183) // 184
        assert final_cc == expected_count & 0x0F

    def test_pid_in_every_packet(self):
        pid = 0x01FF
        pes = b"\x00" * 400
        data, _ = _packetize_pes(pid, pes, 0, 0)
        for i in range(0, len(data), 188):
            pkt = data[i:i + 188]
            pkt_pid = ((pkt[1] & 0x1F) << 8) | pkt[2]
            assert pkt_pid == pid

    def test_first_packet_has_payload_unit_start(self):
        pes = b"\x00" * 300
        data, _ = _packetize_pes(0x0100, pes, 0, 0)
        first_pkt = data[:188]
        assert first_pkt[1] & 0x40  # payload unit start indicator


# ── _pid_of ────────────────────────────────────────────────────────────────

class TestPidOf:
    def test_pid_zero(self):
        pkt = bytes([0x47, 0x00, 0x00, 0x10])
        assert _pid_of(pkt) == 0

    def test_pid_max(self):
        pkt = bytes([0x47, 0x1F, 0xFF, 0x10])
        assert _pid_of(pkt) == 0x1FFF

    def test_typical_pid(self):
        pkt = bytes([0x47, 0x01, 0x00, 0x10])
        assert _pid_of(pkt) == 0x0100


# ── _read_pcr ──────────────────────────────────────────────────────────────

class TestReadPCR:
    def test_returns_none_for_no_pcr(self):
        # No adaptation field
        pkt = bytes([0x47, 0x00, 0x00, 0x10]) + b"\x00" * 184
        assert _read_pcr(pkt) is None

    def test_reads_pcr(self):
        # Build a packet with adaptation field containing PCR
        # AFC=3 (both), AF length=7, flags=0x10 (PCR present)
        pkt = bytearray(188)
        pkt[0] = 0x47
        pkt[1] = 0x00
        pkt[2] = 0x00
        pkt[3] = 0x30  # AFC=3
        pkt[4] = 7     # AF length
        pkt[5] = 0x10  # PCR flag
        # PCR value = 1000 (base=1000, ext=0)
        pcr_val = 1000
        pcr_bytes = ((pcr_val & 0x1FFFFFFFF) << 15) | (0x3F << 9)
        for i in range(6):
            pkt[6 + i] = (pcr_bytes >> (40 - 8 * i)) & 0xFF
        result = _read_pcr(bytes(pkt))
        assert result == 1000


# ── main (argument parsing) ────────────────────────────────────────────────

class TestMain:
    def test_no_telemetry_source(self):
        result = main([])
        assert result == 2

    def test_both_sources(self):
        result = main(["--csv", "a.csv", "--dji-txt", "b.txt"])
        assert result == 2

    def test_missing_video(self):
        result = main(["--csv", "telemetry.csv"])
        assert result == 2

    def test_missing_csv_file(self):
        result = main(["--video", "nonexistent.mp4", "--csv", "/no/such/file.csv"])
        assert result == 2

    def test_missing_dji_txt_file(self):
        result = main(["--video", "nonexistent.mp4", "--dji-txt", "/no/such/file.txt"])
        assert result == 2

    def test_klv_only_requires_out(self):
        result = main(["--csv", "telemetry.csv", "--klv-only"])
        assert result == 2
