# Author: Fran Raga <franka1986@gmail.com>

"""MISB ST 0903 — Video Moving Target Indicator (VMTI) Local Set.

Defines parsers for the VMTI tags used in STANAG 4609 compliant streams.
This set is typically nested inside the ST0600/ST0601 security or video
metadata, and carries per-target information (centroid, velocity, size).
"""

from .common import hexstr_to_bytes
from .element import UnknownElement
from .elementparser import (
    BytesElementParser, MappedElementParser, StringElementParser,
)
from .setparser import SetParser
from .streamparser import StreamParser


class UnknownElement(UnknownElement):
    pass


@StreamParser.add_parser
class VMTILocalSet(SetParser):
    """MISB ST 0903 — Video Moving Target Indicator Local Set."""
    key = hexstr_to_bytes("06 0E 2B 34 02 0B 01 01 0E 01 03 03 06 00 00 00")
    name = "VMTI Local Set"
    key_length = 1
    parsers = {}
    _unknown_element = UnknownElement


@VMTILocalSet.add_parser
class NumberOfTargets(MappedElementParser):
    """Number of targets reported in the VMTI data."""
    key = b"\x01"
    TAG = 1
    LDSName = "Number of Targets"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**8 - 1)
    _range = (0, 255)
    _error = None


@VMTILocalSet.add_parser
class TargetCentroidLatitude(MappedElementParser):
    """Latitude of the target centroid (-90..90 degrees)."""
    key = b"\x02"
    TAG = 2
    LDSName = "Target Centroid Latitude"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@VMTILocalSet.add_parser
class TargetCentroidLongitude(MappedElementParser):
    """Longitude of the target centroid (-180..180 degrees)."""
    key = b"\x03"
    TAG = 3
    LDSName = "Target Centroid Longitude"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@VMTILocalSet.add_parser
class TargetHorizontalVelocity(MappedElementParser):
    """Target horizontal velocity in m/s."""
    key = b"\x04"
    TAG = 4
    LDSName = "Target Horizontal Velocity"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-200, 200)
    _error = -2**15


@VMTILocalSet.add_parser
class TargetVerticalVelocity(MappedElementParser):
    """Target vertical velocity in m/s."""
    key = b"\x05"
    TAG = 5
    LDSName = "Target Vertical Velocity"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-200, 200)
    _error = -2**15


@VMTILocalSet.add_parser
class TargetWidth(MappedElementParser):
    """Target width in meters."""
    key = b"\x06"
    TAG = 6
    LDSName = "Target Width"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**16 - 1)
    _range = (0, 10000)
    _error = None


@VMTILocalSet.add_parser
class TargetHeight(MappedElementParser):
    """Target height in meters."""
    key = b"\x07"
    TAG = 7
    LDSName = "Target Height"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**16 - 1)
    _range = (0, 10000)
    _error = None


@VMTILocalSet.add_parser
class TargetClassification(StringElementParser):
    """Target classification label (e.g. 'vehicle', 'person')."""
    key = b"\x08"
    TAG = 8
    LDSName = "Target Classification"
    ESDName = ""
    UDSName = ""
    min_length, max_length = 0, 127


@VMTILocalSet.add_parser
class TargetConfidenceLevel(MappedElementParser):
    """Confidence level for the target detection (0..100%)."""
    key = b"\x09"
    TAG = 9
    LDSName = "Target Confidence Level"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**8 - 1)
    _range = (0, 100)
    _error = None


@VMTILocalSet.add_parser
class TargetTrackUUID(StringElementParser):
    """Unique track identifier for the target."""
    key = b"\x0A"
    TAG = 10
    LDSName = "Target Track UUID"
    ESDName = ""
    UDSName = ""
    min_length, max_length = 0, 127


@VMTILocalSet.add_parser
class FrameNumber(MappedElementParser):
    """Frame number within the video stream."""
    key = b"\x0B"
    TAG = 11
    LDSName = "Frame Number"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**32 - 1)
    _range = (0, 2**32 - 1)
    _error = None


@VMTILocalSet.add_parser
class TargetLocationSource(MappedElementParser):
    """Source of the target location data."""
    key = b"\x0C"
    TAG = 12
    LDSName = "Target Location Source"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**8 - 1)
    _range = (0, 2**8 - 1)
    _error = None
