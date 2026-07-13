# Author: Fran Raga <franka1986@gmail.com>

"""Centralized constants for the pymisb package.

All shared values live here to avoid duplication across modules.
Import from this module, not from encoder/klvdata directly.
"""

from math import tan, radians

# ── MISB ST0601 / SMPTE 336 ──────────────────────────────────────────────

UAS_LS_KEY = b"\x06\x0E\x2B\x34\x02\x0B\x01\x01\x0E\x01\x03\x01\x01\x00\x00\x00"
"""16-byte universal key of the UAS Datalink Local Set (MISB ST0601)."""

KLV_HEADER_KEY = b"\x00\x00\x06\x0e+4\x02\x0b\x01\x01\x0e\x01\x03\x01\x01"
"""Shifted UAS key — some DJI/non-standard videos prepend extra bytes."""

ST0601_VERSION = 11
"""MISB ST0601 Local Set version number advertised in Tag 65."""

# ── Camera / sensor ───────────────────────────────────────────────────────

HFOV_DEG = 81.0
"""Horizontal field of view (degrees). Adjust to your DJI camera."""

VFOV_DEG = 66.0
"""Vertical field of view (degrees). Adjust to your DJI camera."""

TAN_HFOV_HALF = tan(radians(HFOV_DEG / 2.0))

# ── Geodetic ──────────────────────────────────────────────────────────────

EARTH_MEAN_RADIUS = 6378137.0
"""Earth mean radius in meters (WGS-84). Used for frame center projection."""

# ── TS output ─────────────────────────────────────────────────────────────

OUT_SUFFIX = "_MISB"
"""Suffix appended to video name for the output (e.g. video_MISB.ts)."""
