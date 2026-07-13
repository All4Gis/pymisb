"""MISB ST 0102 Security Metadata Local Set.

Originally from paretech/klvdata (MIT License).
"""

from .common import hexstr_to_bytes
from .element import UnknownElement
from .elementparser import MappedElementParser
from .setparser import SetParser
from .streamparser import StreamParser


class UnknownElement(UnknownElement):
    pass


@StreamParser.add_parser
class SecurityMetadataLocalSet(SetParser):
    key = hexstr_to_bytes("06 0E 2B 34 02 03 01 01 - 0E 01 03 03 02 00 00 00")
    name = "Security Metadata Local Set"
    key_length = 1
    parsers = {}
    _unknown_element = UnknownElement


@SecurityMetadataLocalSet.add_parser
class SecurityClassification(MappedElementParser):
    key = b"\x01"
    TAG = 1
    UDSKey = "-"
    LDSName = "Security Classification"
    ESDName = ""
    UDSName = ""
    _domain = (0, 2**8 - 1)
    _range = (0, 2**8 - 1)
    _error = None
