"""Base Element and UnknownElement classes.

Originally from paretech/klvdata (MIT License).
Modernized for Python 3.10+.
"""

from abc import ABC, abstractmethod
from .common import ber_encode


class Element(ABC):
    """Abstract base for Key-Length-Value elements per SMPTE ST 336.

    Every element has a ``key`` (bytes), a ``value``, and can serialize
    itself to ``bytes(key) + ber_length(len(value)) + bytes(value)``.
    """

    def __init__(self, key: bytes, value):
        self.key = key
        self.value = value

    @property
    def name(self) -> str:
        """Human-readable class name of this element."""
        return type(self).__name__

    @property
    def length(self) -> bytes:
        """BER-encoded byte length of the value (used in serialization)."""
        return ber_encode(len(self))

    def __bytes__(self) -> bytes:
        """Serialize to full TLV bytes: key + BER length + value."""
        return self.key + self.length + bytes(self.value)

    def __len__(self) -> int:
        """Byte length of the value portion only."""
        if self.value is None:
            return 0
        return len(bytes(self.value))

    @abstractmethod
    def __repr__(self) -> str: ...

    def __str__(self) -> str:
        return f"{self.name}: ({self.key!r}, {len(self)}, {self.value})"


class UnknownElement(Element):
    """Fallback element for unrecognized KLV keys — preserves raw bytes."""

    def __repr__(self) -> str:
        return f"UnknownElement({bytes(self.key)!r}, {bytes(self.value)!r})"
