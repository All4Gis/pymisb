"""MISB ST 0601 UAS Datalink Local Set — tag definitions and parsers.

Originally from paretech/klvdata (MIT License).
Extended with additional tags from the QGISFMV fork.
"""

from .common import hexstr_to_bytes
from .element import UnknownElement
from .elementparser import (
    BytesElementParser, DateTimeElementParser,
    MappedElementParser, StringElementParser,
)
from .setparser import SetParser
from .streamparser import StreamParser


class UnknownElement(UnknownElement):
    pass


@StreamParser.add_parser
class UASLocalMetadataSet(SetParser):
    key = hexstr_to_bytes("06 0E 2B 34 - 02 0B 01 01 - 0E 01 03 01 - 01 00 00 00")
    name = "UAS Datalink Local Set"
    key_length = 1
    parsers = {}
    _unknown_element = UnknownElement


@UASLocalMetadataSet.add_parser
class Checksum(BytesElementParser):
    key = b"\x01"
    TAG = 1
    UDSKey = "-"
    LDSName = "Checksum"
    ESDName = ""
    UDSName = ""


@UASLocalMetadataSet.add_parser
class PrecisionTimeStamp(DateTimeElementParser):
    key = b"\x02"
    TAG = 2
    UDSKey = "06 0E 2B 34 01 01 01 03 07 02 01 01 01 05 00 00"
    LDSName = "Precision Time Stamp"
    ESDName = ""
    UDSName = "User Defined Time Stamp"


@UASLocalMetadataSet.add_parser
class MissionID(StringElementParser):
    key = b"\x03"
    TAG = 3
    UDSKey = "06 0E 2B 34 01 01 01 01 01 05 05 00 00 00 00 00"
    LDSName = "Mission ID"
    ESDName = "Mission Number"
    UDSName = "Episode Number"
    min_length, max_length = 0, 127


@UASLocalMetadataSet.add_parser
class PlatformTailNumber(StringElementParser):
    key = b"\x04"
    TAG = 4
    UDSKey = "-"
    LDSName = "Platform Tail Number"
    ESDName = "Platform Tail Number"
    UDSName = ""
    min_length, max_length = 0, 127


@UASLocalMetadataSet.add_parser
class PlatformHeadingAngle(MappedElementParser):
    key = b"\x05"
    TAG = 5
    UDSKey = "06 0E 2B 34 01 01 01 07 07 01 10 01 06 00 00 00"
    LDSName = "Platform Heading Angle"
    ESDName = "UAV Heading (INS)"
    UDSName = "Platform Heading Angle"
    _domain = (0, 2**16 - 1)
    _range = (0, 360)
    _error = None


@UASLocalMetadataSet.add_parser
class PlatformPitchAngle(MappedElementParser):
    key = b"\x06"
    TAG = 6
    UDSKey = "06 0E 2B 34 01 01 01 07 07 01 10 01 05 00 00 00"
    LDSName = "Platform Pitch Angle"
    ESDName = "UAV Pitch (INS)"
    UDSName = "Platform Pitch Angle"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-20, 20)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class PlatformRollAngle(MappedElementParser):
    key = b"\x07"
    TAG = 7
    UDSKey = "06 0E 2B 34 01 01 01 07 07 01 10 01 04 00 00 00"
    LDSName = "Platform Roll Angle"
    ESDName = "UAV Roll (INS)"
    UDSName = "Platform Roll Angle"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-50, 50)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class PlatformTrueAirspeed(MappedElementParser):
    key = b"\x08"
    TAG = 8
    UDSKey = "-"
    LDSName = "Platform True Airspeed"
    ESDName = "True Airspeed"
    UDSName = ""
    _domain = (0, 2**8 - 1)
    _range = (0, 255)
    _error = None


@UASLocalMetadataSet.add_parser
class PlatformIndicatedAirspeed(MappedElementParser):
    key = b"\x09"
    TAG = 9
    UDSKey = "-"
    LDSName = "Platform Indicated Airspeed"
    ESDName = "Indicated Airspeed"
    UDSName = ""
    _domain = (0, 2**8 - 1)
    _range = (0, 255)
    _error = None


@UASLocalMetadataSet.add_parser
class PlatformDesignation(StringElementParser):
    key = b"\x0A"
    TAG = 10
    UDSKey = "06 0E 2B 34 01 01 01 01 01 01 20 01 00 00 00 00"
    LDSName = "Platform Designation"
    ESDName = "Project ID Code"
    UDSName = "Device Designation"
    min_length, max_length = 0, 127


@UASLocalMetadataSet.add_parser
class ImageSourceSensor(StringElementParser):
    key = b"\x0B"
    TAG = 11
    UDSKey = "06 0E 2B 34 01 01 01 01 04 20 01 02 01 01 00 00"
    LDSName = "Image Source Sensor"
    ESDName = "Sensor Name"
    UDSName = "Image Source Device"
    min_length, max_length = 0, 127


@UASLocalMetadataSet.add_parser
class ImageCoordinateSystem(StringElementParser):
    key = b"\x0C"
    TAG = 12
    UDSKey = "06 0E 2B 34 01 01 01 01 07 01 01 01 00 00 00 00"
    LDSName = "Image Coordinate System"
    ESDName = "Image Coordinate System"
    UDSName = "Image Coordinate System"
    min_length, max_length = 0, 127


@UASLocalMetadataSet.add_parser
class SensorLatitude(MappedElementParser):
    key = b"\x0D"
    TAG = 13
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 02 04 02 00"
    LDSName = "Sensor Latitude"
    ESDName = "Sensor Latitude"
    UDSName = "Device Latitude"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class SensorLongitude(MappedElementParser):
    key = b"\x0E"
    TAG = 14
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 02 06 02 00"
    LDSName = "Sensor Longitude"
    ESDName = "Sensor Longitude"
    UDSName = "Device Longitude"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class SensorTrueAltitude(MappedElementParser):
    key = b"\x0F"
    TAG = 15
    UDSKey = "06 0E 2B 34 01 01 01 01 07 01 02 01 02 02 00 00"
    LDSName = "Sensor True Altitude"
    ESDName = "Sensor Altitude"
    UDSName = "Device Altitude"
    _domain = (0, 2**16 - 1)
    _range = (-900, 19000)
    _error = None


@UASLocalMetadataSet.add_parser
class SensorHorizontalFieldOfView(MappedElementParser):
    key = b"\x10"
    TAG = 16
    UDSKey = "06 0E 2B 34 01 01 01 02 04 20 02 01 01 08 00 00"
    LDSName = "Sensor Horizontal Field of View"
    ESDName = "Field of View"
    UDSName = "Field of View (FOVHorizontal)"
    _domain = (0, 2**16 - 1)
    _range = (0, 180)
    _error = None


@UASLocalMetadataSet.add_parser
class SensorVerticalFieldOfView(MappedElementParser):
    key = b"\x11"
    TAG = 17
    UDSKey = "-"
    LDSName = "Sensor Vertical Field of View"
    ESDName = "Vertical Field of View"
    UDSName = ""
    _domain = (0, 2**16 - 1)
    _range = (0, 180)
    _error = None


@UASLocalMetadataSet.add_parser
class SensorRelativeAzimuthAngle(MappedElementParser):
    key = b"\x12"
    TAG = 18
    UDSKey = "-"
    LDSName = "Sensor Relative Azimuth Angle"
    ESDName = "Sensor Relative Azimuth Angle"
    UDSName = ""
    _domain = (0, 2**32 - 1)
    _range = (0, 360)
    _error = None


@UASLocalMetadataSet.add_parser
class SensorRelativeElevationAngle(MappedElementParser):
    key = b"\x13"
    TAG = 19
    UDSKey = "-"
    LDSName = "Sensor Relative Elevation Angle"
    ESDName = "Sensor Relative Elevation Angle"
    UDSName = ""
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class SensorRelativeRollAngle(MappedElementParser):
    key = b"\x14"
    TAG = 20
    UDSKey = "-"
    LDSName = "Sensor Relative Roll Angle"
    ESDName = "Sensor Relative Roll Angle"
    UDSName = ""
    _domain = (0, 2**32 - 1)
    _range = (0, 360)
    _error = None


@UASLocalMetadataSet.add_parser
class SlantRange(MappedElementParser):
    key = b"\x15"
    TAG = 21
    UDSKey = "06 0E 2B 34 01 01 01 01 07 01 08 01 01 00 00 00"
    LDSName = "Slant Range"
    ESDName = "Slant Range"
    UDSName = "Slant Range"
    _domain = (0, 2**32 - 1)
    _range = (0, 5e6)
    _error = None


@UASLocalMetadataSet.add_parser
class TargetWidth(MappedElementParser):
    key = b"\x16"
    TAG = 22
    UDSKey = "06 0E 2B 34 01 01 01 01 07 01 09 02 01 00 00 00"
    LDSName = "Target Width"
    ESDName = "Target Width"
    UDSName = "Target Width"
    _domain = (0, 2**16 - 1)
    _range = (0, 10e3)
    _error = None


@UASLocalMetadataSet.add_parser
class FrameCenterLatitude(MappedElementParser):
    key = b"\x17"
    TAG = 23
    UDSKey = "06 0E 2B 34 01 01 01 01 07 01 02 01 03 02 00 00"
    LDSName = "Frame Center Latitude"
    ESDName = "Target Latitude"
    UDSName = "Frame Center Latitude"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class FrameCenterLongitude(MappedElementParser):
    key = b"\x18"
    TAG = 24
    UDSKey = "06 0E 2B 34 01 01 01 01 07 01 02 01 03 04 00 00"
    LDSName = "Frame Center Longitude"
    ESDName = "Target Longitude"
    UDSName = "Frame Center Longitude"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class FrameCenterElevation(MappedElementParser):
    key = b"\x19"
    TAG = 25
    UDSKey = "-"
    LDSName = "Frame Center Elevation"
    ESDName = "Frame Center Elevation"
    UDSName = ""
    _domain = (0, 2**16 - 1)
    _range = (-900, 19e3)
    _error = None


@UASLocalMetadataSet.add_parser
class OffsetCornerLatitudePoint1(MappedElementParser):
    key = b"\x1A"
    TAG = 26
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 07 01 00"
    LDSName = "Offset Corner Latitude Point 1"
    ESDName = "SAR Latitude 4"
    UDSName = "Corner Latitude Point 1"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class OffsetCornerLongitudePoint1(MappedElementParser):
    key = b"\x1B"
    TAG = 27
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0B 01 00"
    LDSName = "Offset Corner Longitude Point 1"
    ESDName = "SAR Longitude 4"
    UDSName = "Corner Longitude Point 1"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class OffsetCornerLatitudePoint2(MappedElementParser):
    key = b"\x1C"
    TAG = 28
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 08 01 00"
    LDSName = "Offset Corner Latitude Point 2"
    ESDName = "SAR Latitude 1"
    UDSName = "Corner Latitude Point 2"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class OffsetCornerLongitudePoint2(MappedElementParser):
    key = b"\x1D"
    TAG = 29
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0C 01 00"
    LDSName = "Offset Corner Longitude Point 2"
    ESDName = "SAR Longitude 1"
    UDSName = "Corner Longitude Point 2"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class OffsetCornerLatitudePoint3(MappedElementParser):
    key = b"\x1E"
    TAG = 30
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 09 01 00"
    LDSName = "Offset Corner Latitude Point 3"
    ESDName = "SAR Latitude 2"
    UDSName = "Corner Latitude Point 3"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class OffsetCornerLongitudePoint3(MappedElementParser):
    key = b"\x1F"
    TAG = 31
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0D 01 00"
    LDSName = "Offset Corner Longitude Point 3"
    ESDName = "SAR Longitude 2"
    UDSName = "Corner Longitude Point 3"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class OffsetCornerLatitudePoint4(MappedElementParser):
    key = b"\x20"
    TAG = 32
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0A 01 00"
    LDSName = "Offset Corner Latitude Point 4"
    ESDName = "SAR Latitude 3"
    UDSName = "Corner Latitude Point 4"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class OffsetCornerLongitudePoint4(MappedElementParser):
    key = b"\x21"
    TAG = 33
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0E 01 00"
    LDSName = "Offset Corner Longitude Point 4"
    ESDName = "SAR Longitude 3"
    UDSName = "Corner Longitude Point 4"
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-0.075, 0.075)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class SensorNorthVelocity(MappedElementParser):
    key = b"\x4F"
    TAG = 79
    UDSKey = "-"
    LDSName = "Sensor North Velocity"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-327, 327)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class SensorEastVelocity(MappedElementParser):
    key = b"\x50"
    TAG = 80
    UDSKey = "-"
    LDSName = "Sensor East Velocity"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**15 - 1), 2**15 - 1)
    _range = (-327, 327)
    _error = -2**15


@UASLocalMetadataSet.add_parser
class CornerLatitudePoint1Full(MappedElementParser):
    key = b"\x52"
    TAG = 82
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 07 01 00"
    LDSName = "Corner Latitude Point 1 (Full)"
    ESDName = "SAR Latitude 4"
    UDSName = "Corner Latitude Point 1 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class CornerLongitudePoint1Full(MappedElementParser):
    key = b"\x53"
    TAG = 83
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0B 01 00"
    LDSName = "Corner Longitude Point 1 (Full)"
    ESDName = "SAR Longitude 4"
    UDSName = "Corner Longitude Point 1 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class CornerLatitudePoint2Full(MappedElementParser):
    key = b"\x54"
    TAG = 84
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 08 01 00"
    LDSName = "Corner Latitude Point 2 (Full)"
    ESDName = "SAR Latitude 1"
    UDSName = "Corner Latitude Point 2 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class CornerLongitudePoint2Full(MappedElementParser):
    key = b"\x55"
    TAG = 85
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0C 01 00"
    LDSName = "Corner Longitude Point 2 (Full)"
    ESDName = "SAR Longitude 1"
    UDSName = "Corner Longitude Point 2 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class CornerLatitudePoint3Full(MappedElementParser):
    key = b"\x56"
    TAG = 86
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 09 01 00"
    LDSName = "Corner Latitude Point 3 (Full)"
    ESDName = "SAR Latitude 2"
    UDSName = "Corner Latitude Point 3 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class CornerLongitudePoint3Full(MappedElementParser):
    key = b"\x57"
    TAG = 87
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0D 01 00"
    LDSName = "Corner Longitude Point 3 (Full)"
    ESDName = "SAR Longitude 2"
    UDSName = "Corner Longitude Point 3 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class CornerLatitudePoint4Full(MappedElementParser):
    key = b"\x58"
    TAG = 88
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0A 01 00"
    LDSName = "Corner Latitude Point 4 (Full)"
    ESDName = "SAR Latitude 3"
    UDSName = "Corner Latitude Point 4 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class CornerLongitudePoint4Full(MappedElementParser):
    key = b"\x59"
    TAG = 89
    UDSKey = "06 0E 2B 34 01 01 01 03 07 01 02 01 03 0E 01 00"
    LDSName = "Corner Longitude Point 4 (Full)"
    ESDName = "SAR Longitude 3"
    UDSName = "Corner Longitude Point 4 (Decimal Degrees)"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-180, 180)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class PlatformPitchAngleFull(MappedElementParser):
    key = b"\x5A"
    TAG = 90
    UDSKey = "06 0E 2B 34 01 01 01 07 07 01 10 01 05 00 00 00"
    LDSName = "Platform Pitch Angle (Full)"
    ESDName = "UAV Pitch (INS)"
    UDSName = "Platform Pitch Angle"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class PlatformRollAngleFull(MappedElementParser):
    key = b"\x5B"
    TAG = 91
    UDSKey = "06 0E 2B 34 01 01 01 07 07 01 10 01 04 00 00 00"
    LDSName = "Platform Roll Angle (Full)"
    ESDName = "UAV Roll (INS)"
    UDSName = "Platform Roll Angle"
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class PlatformAngleOfAttackFull(MappedElementParser):
    key = b"\x5C"
    TAG = 92
    UDSKey = "-"
    LDSName = "Platform Angle of Attack (Full)"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class PlatformSideslipAngleFull(MappedElementParser):
    key = b"\x5D"
    TAG = 93
    UDSKey = "-"
    LDSName = "Platform Sideslip Angle (Full)"
    ESDName = ""
    UDSName = ""
    _domain = (-(2**31 - 1), 2**31 - 1)
    _range = (-90, 90)
    _error = -2**31


@UASLocalMetadataSet.add_parser
class TargetWidthExtended(MappedElementParser):
    key = b"\x60"
    TAG = 96
    UDSKey = "06 0E 2B 34 01 01 01 01 07 01 09 02 01 00 00 00"
    LDSName = "Target Width Extended"
    ESDName = "Target Width"
    UDSName = "Target Width"
    _domain = (0, 2**8 - 1)
    _range = (0, 2**8 - 1)
    _error = None


@UASLocalMetadataSet.add_parser
class DensityAltitudeExtended(MappedElementParser):
    key = b"\x67"
    TAG = 103
    UDSKey = "06 0E 2B 34 01 01 01 01 0E 01 01 01 10 00 00 00"
    LDSName = "Density Altitude Extended"
    ESDName = "Density Altitude"
    UDSName = ""
    _domain = (0, 2**16 - 1)
    _range = (-900, 40000)
    _error = None


@UASLocalMetadataSet.add_parser
class SensorEllipsoidHeightExtended(MappedElementParser):
    key = b"\x68"
    TAG = 104
    UDSKey = "06 0E 2B 34 01 01 01 01 0E 01 02 01 82 47 00 00"
    LDSName = "Sensor Ellipsoid Height Extended"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**16 - 1)
    _range = (-900, 40000)
    _error = None


@UASLocalMetadataSet.add_parser
class AlternatePlatformEllipsoidHeightExtended(MappedElementParser):
    key = b"\x69"
    TAG = 105
    UDSKey = "06 0E 2B 34 01 01 01 01 0E 01 02 01 82 48 00 00"
    LDSName = "Alternate Platform Ellipsoid Height Extended"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**16 - 1)
    _range = (-900, 40000)
    _error = None
