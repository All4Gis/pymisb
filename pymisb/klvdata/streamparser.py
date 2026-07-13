"""Top-level KLV stream iterator.

Originally from paretech/klvdata (MIT License).
Modernized for Python 3.10+.
"""

from __future__ import annotations

from typing import ClassVar

from .element import UnknownElement
from .klvparser import KLVParser


class StreamParser:
    """Top-level iterator that yields parsed KLV packets from a byte stream.

    Reads 16-byte universal keys and dispatches to registered parsers
    (e.g. ``UASLocalMetadataSet``).  Each yielded object has a
    ``MetadataList()`` method that returns an OrderedDict of decoded tags.
    """

    __slots__ = ("source", "iter_stream")
    parsers: ClassVar[dict[bytes, type]] = {}

    def __init__(self, source):
        """Initialize the stream parser.

        Args:
            source: Raw KLV bytes or a file-like object (e.g. from FFmpeg
                output via ``extract_klv()``).
        """
        self.source = source
        self.iter_stream = KLVParser(self.source, key_length=16)

    def __iter__(self):
        return self

    def __next__(self):
        key, value = next(self.iter_stream)
        parser = self.parsers.get(key)
        if parser is not None:
            return parser(value)
        return UnknownElement(key, value)

    @classmethod
    def add_parser(cls, obj):
        """Register a parser class for a 16-byte universal key.

        Used as a decorator: ``@StreamParser.add_parser``.
        """
        cls.parsers[bytes(obj.key)] = obj
        return obj
