# -*- coding: utf-8 -*-
"""Live mux: continuous MPEG-TS video plus telemetry dicts."""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from pymisb.constants import UAS_LS_KEY
from pymisb.klvdata import StreamParser
from pymisb.mux import LiveMuxer, metadata_to_klv
from pymisb.mux.engine import _crc32_mpeg, _pid_of

VIDEO_PID = 0x0100
PMT_PID = 0x1000


def _pad(packet: bytes) -> bytes:
    return packet + b"\xFF" * (188 - len(packet))


def _psi(pid: int, table: bytes) -> bytes:
    header = bytes([0x47, 0x40 | ((pid >> 8) & 0x1F), pid & 0xFF, 0x10, 0x00])
    return _pad(header + table)


def _table(table_id: int, body: bytes) -> bytes:
    section_length = len(body) + 4
    raw = bytes([table_id, 0xB0 | ((section_length >> 8) & 0x0F), section_length & 0xFF]) + body
    return raw + _crc32_mpeg(raw).to_bytes(4, "big")


def _pat() -> bytes:
    body = b"\x00\x01\xc1\x00\x00" + (1).to_bytes(2, "big") + (0xE000 | PMT_PID).to_bytes(2, "big")
    return _psi(0, _table(0x00, body))


def _pmt() -> bytes:
    body = (
        (1).to_bytes(2, "big")
        + b"\xc1\x00\x00"
        + (0xE000 | VIDEO_PID).to_bytes(2, "big")
        + b"\xf0\x00"
        + b"\x1b"
        + (0xE000 | VIDEO_PID).to_bytes(2, "big")
        + b"\xf0\x00"
    )
    return _psi(PMT_PID, _table(0x02, body))


def _video(pcr: int) -> bytes:
    packet = bytearray(188)
    packet[0] = 0x47
    packet[1] = 0x40 | ((VIDEO_PID >> 8) & 0x1F)
    packet[2] = VIDEO_PID & 0xFF
    packet[3] = 0x30
    packet[4] = 7
    packet[5] = 0x10
    packet[6:12] = ((pcr & 0x1FFFFFFFF) << 15 | (0x3F << 9)).to_bytes(6, "big")
    return bytes(packet)


def _stream() -> bytes:
    return _pat() + _pmt() + _video(0) + _video(90_000) + _video(180_000)


def _packets(data: bytes) -> list[bytes]:
    assert len(data) % 188 == 0
    return [data[i:i + 188] for i in range(0, len(data), 188)]


def _pids(data: bytes) -> set[int]:
    return {_pid_of(pkt) for pkt in _packets(data)}


class TestMetadataToKlv:
    def test_friendly_names_roundtrip(self):
        when = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
        klv = metadata_to_klv({
            "latitude": 41.387,
            "longitude": 2.168,
            "altitude": 100.0,
            "heading": 90.0,
            "timestamp": when.isoformat(),
        })
        assert klv.startswith(UAS_LS_KEY)
        parsed = next(StreamParser(klv))
        meta = parsed.MetadataList()
        assert abs(float(meta[13][1]) - 41.387) < 1e-4
        assert abs(float(meta[14][1]) - 2.168) < 1e-4
        assert abs(float(meta[15][1]) - 100.0) < 0.5
        assert abs(float(meta[5][1]) - 90.0) < 0.01


class TestLiveMuxer:
    def test_interleaves_video_and_metadata(self):
        muxer = LiveMuxer()
        # Unaligned slices, and a sample only on the second video frame.
        raw = _stream()
        out = muxer.feed(raw[:100], None)
        out += muxer.feed(raw[100:300], {"latitude": 10.0, "longitude": 20.0, "timestamp": 1_700_000_000})
        out += muxer.feed(raw[300:], None)
        out += muxer.close()

        assert len(out) % 188 == 0
        pids = _pids(out)
        assert VIDEO_PID in pids
        assert 0 in pids
        klv_pids = pids - {0, PMT_PID, VIDEO_PID}
        assert len(klv_pids) == 1
        assert out.count(UAS_LS_KEY) == 1

        pmt = next(pkt for pkt in _packets(out) if _pid_of(pkt) == PMT_PID)
        assert b"\x15" in pmt  # stream_type of the KLV elementary stream

        parsed = next(StreamParser(out[out.find(UAS_LS_KEY):]))
        meta = parsed.MetadataList()
        assert abs(float(meta[13][1]) - 10.0) < 1e-4
        assert abs(float(meta[14][1]) - 20.0) < 1e-4

    def test_no_metadata_adds_no_klv(self):
        muxer = LiveMuxer()
        out = muxer.feed(_stream())
        out += muxer.close()
        assert UAS_LS_KEY not in out
        assert len(out) % 188 == 0

    def test_sample_before_pcr_is_flushed_later(self):
        muxer = LiveMuxer()
        out = muxer.feed(_pat() + _pmt(), {"latitude": 5, "longitude": 6, "timestamp_us": 1})
        assert UAS_LS_KEY not in out
        out += muxer.feed(_video(90_000))
        out += muxer.close()
        assert out.count(UAS_LS_KEY) == 1

    def test_close_is_idempotent(self):
        muxer = LiveMuxer()
        muxer.feed(_stream(), {"latitude": 1, "longitude": 2})
        muxer.close()
        assert muxer.close() == b""

    def test_example_script(self, tmp_path: Path):
        out = tmp_path / "muxed_data.ts"
        root = Path(__file__).resolve().parents[1]
        script = root / "examples" / "live_mux.py"
        env = os.environ.copy()
        env["PYTHONPATH"] = str(root)
        subprocess.run(
            [sys.executable, str(script), "--out", str(out), "--seconds", "2", "--hz", "1"],
            check=True,
            env=env,
        )
        data = out.read_bytes()
        assert len(data) % 188 == 0
        assert data.count(UAS_LS_KEY) == 2  # t = 0 and t = 1
