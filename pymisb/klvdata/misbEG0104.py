"""MISB EG 0104 UAV Basic Universal Metadata Set.

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
class UAVBasicUniversalMetadataSet(SetParser):
    key = hexstr_to_bytes("06 0E 2B 34 02 0B 01 01 - 0E 01 01 01 01 00 00 00")
    name = "UAV Basic Universal Metadata Set"
    key_length = 1
    parsers = {}
    _unknown_element = UnknownElement
