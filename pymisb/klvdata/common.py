"""Low-level KLV encoding/decoding utilities (vendored from paretech/klvdata).

This module is part of the vendored klvdata package used internally by the
demux decoder.  Do NOT confuse with ``misb.common`` which contains the
project's own encoder and DJI parsers.
"""

from datetime import datetime, timezone
from struct import pack, unpack


def datetime_to_bytes(value: datetime) -> bytes:
    """Encode a datetime as 8-byte big-endian UNIX microseconds (MISB Tag 2)."""
    return pack(">Q", int(value.timestamp() * 1e6))


def bytes_to_datetime(value: bytes) -> datetime:
    """Decode 8-byte big-endian UNIX microseconds into a UTC datetime."""
    return datetime.fromtimestamp(int.from_bytes(value) / 1e6, tz=timezone.utc)


def bytes_to_int(value: bytes, signed: bool = False) -> int:
    """Decode big-endian bytes into an integer."""
    return int.from_bytes(value, byteorder="big", signed=signed)


def int_to_bytes(value: int, length: int = 1, signed: bool = False) -> bytes:
    """Encode an integer as big-endian bytes of *length*."""
    return int(value).to_bytes(length, byteorder="big", signed=signed)


def ber_decode(value: bytes) -> int:
    """Decode a BER-encoded length from bytes.

    Short form: 1 byte if < 128.  Long form: first byte = 0x80 + N,
    followed by N bytes of the actual length.
    """
    first = value[0]
    if first < 128:
        if len(value) > 1:
            raise ValueError("BER short form: expected 1 byte")
        return first
    expected = first - 127
    if len(value) != expected:
        raise ValueError(f"BER long form: expected {expected} bytes, got {len(value)}")
    return int.from_bytes(value[1:], byteorder="big")


def ber_encode(value: int) -> bytes:
    """Encode an integer length as BER bytes (short or long form)."""
    if value < 128:
        return bytes([value])
    byte_length = ((value.bit_length() - 1) // 8) + 1
    return bytes([0x80 | byte_length]) + value.to_bytes(byte_length, byteorder="big")


def bytes_to_str(value: bytes) -> str:
    """Decode bytes as UTF-8 string."""
    return value.decode("utf-8")


def str_to_bytes(value: str) -> bytes:
    """Encode a string as UTF-8 bytes."""
    return value.encode("utf-8")


def hexstr_to_bytes(value: str) -> bytes:
    """Decode a hex string (spaces, dashes, colons are ignored) into bytes.

    Example: ``"06 0E 2B 34"`` -> ``b"\\x06\\x0E\\x2B\\x34"``.
    """
    return bytes.fromhex("".join(filter(str.isalnum, value)))


def bytes_to_hexstr(value: bytes, start: str = "", sep: str = " ") -> str:
    """Format bytes as a hex string, e.g. ``"06 0E 2B 34"``."""
    return start + sep.join(f"{b:02X}" for b in value)


def linear_map(src_value: float, src_domain: tuple, dst_range: tuple) -> float:
    """Linearly map *src_value* from *src_domain* to *dst_range*.

    Both domain and range are (min, max) tuples.  Used by MISB element
    parsers to convert binary integer values to physical units (and back).
    """
    src_min, src_max, dst_min, dst_max = src_domain + dst_range
    if not (src_min <= src_value <= src_max):
        raise ValueError(f"Value {src_value} outside domain [{src_min}, {src_max}]")
    slope = (dst_max - dst_min) / (src_max - src_min)
    return slope * (src_value - src_min) + dst_min


def bytes_to_float(value: bytes, _domain: tuple, _range: tuple, _error=None) -> float | None:
    """Decode fixed-point bytes to a float using *domain*->*range* mapping.

    Returns None if the raw value equals *_error* (the MISB error sentinel).
    """
    src_value = int.from_bytes(value, byteorder="big", signed=(min(_domain) < 0))
    if src_value == _error:
        return None
    return linear_map(src_value, _domain, _range)


def ieee754_bytes_to_fp(value: bytes) -> float:
    """Decode IEEE 754 bytes (4 or 8) into a Python float."""
    size = len(value)
    if size == 4:
        return unpack(">f", value)[0]
    elif size == 8:
        return unpack(">d", value)[0]
    raise ValueError(f"Unsupported IEEE754 size: {size} bytes")


def float_to_bytes(value: float, _domain: tuple, _range: tuple, _error=None) -> bytes:
    """Encode a float as fixed-point bytes using *domain*->*range* mapping."""
    src_domain, dst_range = _range, _domain
    src_min, src_max, dst_min, dst_max = src_domain + dst_range
    length = (dst_max.bit_length() + 7) // 8
    if value is None:
        dst_value = _error if _error is not None else 0
    else:
        dst_value = linear_map(value, src_domain=src_domain, dst_range=dst_range)
    return round(dst_value).to_bytes(length, byteorder="big", signed=(dst_min < 0))


def packet_checksum(data: bytes) -> bytes:
    """Compute the 2-byte BCC-16 checksum for SMPTE ST 336 KLV data.

    Sums 16-bit words of the data and returns the result as 2 big-endian
    bytes.  Used to verify packet integrity.
    """
    length = len(data) - 2
    word_size, mod = divmod(length, 2)
    words = sum(unpack(f">{word_size}H", data[:length - mod]))
    if mod:
        words += data[length - 1] << 8
    return pack(">H", words & 0xFFFF)
