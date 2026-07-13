"""Low-level BER-TLV parser for SMPTE ST 336 KLV streams.

Originally from paretech/klvdata (MIT License).
Extended with non-standard header support from the QGISFMV fork.
Modernized for Python 3.10+.
"""

from io import BytesIO, IOBase
from .common import bytes_to_int
from ..constants import UAS_LS_KEY, KLV_HEADER_KEY


class KLVParser:
    """Low-level iterator that yields (key, value) tuples from a KLV byte stream.

    Handles BER length decoding and the DJI non-standard header hotfix
    (misaligned UAS key detection).  Used by ``StreamParser`` and
    ``SetParser`` to walk SMPTE ST 336 encoded data.
    """

    __slots__ = ("source", "key_length")

    def __init__(self, source, key_length: int):
        """Initialize the parser.

        Args:
            source: Raw bytes or a file-like object to read from.
            key_length: Number of bytes per key (16 for universal keys,
                1 for local set element tags).
        """
        if isinstance(source, IOBase):
            self.source = source
        else:
            self.source = BytesIO(source)
        self.key_length = key_length

    def __iter__(self):
        return self

    def __next__(self) -> tuple[bytes, bytes]:
        key = self._read(self.key_length)

        # Hotfix: some DJI videos have misaligned headers.
        if self.key_length == 16 and key.find(KLV_HEADER_KEY) > 0:
            key = UAS_LS_KEY
            byte_length = bytes_to_int(self._read(4))
        else:
            byte_length = bytes_to_int(self._read(1))

        if byte_length < 128:
            length = byte_length
        else:
            length = bytes_to_int(self._read(byte_length - 128))

        return key, self._read(length)

    def _read(self, size: int) -> bytes:
        """Read *size* bytes from the source, raising StopIteration on EOF."""
        if size == 0:
            return b""
        data = self.source.read(size)
        if not data:
            raise StopIteration
        return data
