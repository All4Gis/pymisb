"""Typed element parsers for KLV values.

Originally from paretech/klvdata (MIT License).
Modernized for Python 3.10+.
"""

import struct
from abc import abstractmethod
from .common import (
    bytes_to_datetime, bytes_to_float, bytes_to_hexstr,
    bytes_to_int, bytes_to_str, datetime_to_bytes,
    float_to_bytes, str_to_bytes, ieee754_bytes_to_fp,
)
from .element import Element


class ElementParser(Element):
    """Base class for typed element parsers."""

    key: bytes

    def __init__(self, value):
        super().__init__(self.key, value)

    def __repr__(self) -> str:
        return f"{self.name}({bytes(self.value)!r})"


class BaseValue:
    """Abstract base for value wrappers."""

    @abstractmethod
    def __bytes__(self) -> bytes: ...

    @abstractmethod
    def __str__(self) -> str: ...


class BytesElementParser(ElementParser):
    def __init__(self, value):
        super().__init__(BytesValue(value))


class BytesValue(BaseValue):
    def __init__(self, value: bytes):
        try:
            self.value = bytes_to_int(value)
        except TypeError:
            self.value = value

    def __bytes__(self) -> bytes:
        return bytes(self.value) if isinstance(self.value, int) else self.value

    def __str__(self) -> str:
        if isinstance(self.value, int):
            return f"0x{self.value:X}"
        return bytes_to_hexstr(self.value, start="0x", sep="")


class DateTimeElementParser(ElementParser):
    def __init__(self, value):
        super().__init__(DateTimeValue(value))


class DateTimeValue(BaseValue):
    def __init__(self, value: bytes):
        self.value = bytes_to_datetime(value)

    def __bytes__(self) -> bytes:
        return datetime_to_bytes(self.value)

    def __str__(self) -> str:
        return self.value.isoformat(sep=" ")


class StringElementParser(ElementParser):
    def __init__(self, value):
        super().__init__(StringValue(value))


class StringValue(BaseValue):
    def __init__(self, value: bytes):
        try:
            self.value = bytes_to_str(value)
        except TypeError:
            self.value = value

    def __bytes__(self) -> bytes:
        return str_to_bytes(self.value)

    def __str__(self) -> str:
        return str(self.value) if self.value is not None else ""


class MappedElementParser(ElementParser):
    _domain: tuple
    _range: tuple
    _error: object

    def __init__(self, value):
        super().__init__(MappedValue(value, self._domain, self._range, self._error))


class MappedValue(BaseValue):
    def __init__(self, value: bytes, _domain: tuple, _range: tuple, _error):
        self._domain = _domain
        self._range = _range
        self._error = _error
        try:
            self.value = bytes_to_float(value, _domain, _range, _error)
        except TypeError:
            self.value = value

    def __bytes__(self) -> bytes:
        return float_to_bytes(self.value, self._domain, self._range, self._error)

    def __str__(self) -> str:
        return format(self.value) if self.value is not None else ""

    def __float__(self) -> float:
        if self.value is None:
            raise TypeError("Cannot convert None to float")
        return self.value


class IEEE754ElementParser(ElementParser):
    def __init__(self, value):
        super().__init__(IEEE754Value(value))


class IEEE754Value(BaseValue):
    def __init__(self, value: bytes):
        self._raw = value
        try:
            self.value = ieee754_bytes_to_fp(value)
        except TypeError:
            self.value = value

    def __bytes__(self) -> bytes:
        if isinstance(self.value, float):
            size = len(self._raw)
            return struct.pack(">f" if size == 4 else ">d", self.value)
        return self._raw if isinstance(self._raw, bytes) else b""

    def __str__(self) -> str:
        return str(self.value) if self.value is not None else ""
