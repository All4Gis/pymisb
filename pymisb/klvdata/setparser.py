"""Base class for parsing KLV local sets.

Originally from paretech/klvdata (MIT License).
Modernized for Python 3.10+: removed Python 2 hacks, simplified MetadataList().
"""

from abc import ABC, abstractmethod
from collections import OrderedDict
from pprint import pformat
from struct import error as StructError
from .element import Element
from .klvparser import KLVParser


def _element_value(element):
    """Return the decoded Python value from a parsed KLV element."""
    if element is None:
        return None
    value = getattr(element, "value", None)
    if value is None:
        return None
    if hasattr(value, "value"):
        return value.value
    return value


class SetParser(Element):
    """Parsable Element for KLV local sets (e.g. UASLocalMetadataSet).

    Iterates over the value using ``KLVParser`` and dispatches each
    sub-element to its registered parser class.  Unrecognized tags
    become ``UnknownElement`` instances.
    """

    def __init__(self, value, key_length: int = 1):
        super().__init__(self.key, value)
        self.items: OrderedDict[bytes, Element] = OrderedDict()
        self.parse()

    def __getitem__(self, key):
        """Get a parsed element by its raw key bytes."""
        return self.items[bytes(key)]

    def __getattr__(self, name):
        """Expose decoded fields by MISB element class name (e.g. SensorLatitude)."""
        if name.startswith("_"):
            raise AttributeError(name)
        parsers = type(self).parsers
        for key, parser_cls in parsers.items():
            if parser_cls.__name__ == name:
                return _element_value(self.items.get(key))
        raise AttributeError(f"{type(self).__name__!r} has no attribute {name!r}")

    def parse(self):
        """Parse the raw value into typed sub-elements."""
        for key, value in KLVParser(self.value, self.key_length):
            try:
                self.items[key] = self.parsers[key](value)
            except (KeyError, TypeError, ValueError):
                self.items[key] = self._unknown_element(key, value)
            except StructError:
                self.items[key] = self._unknown_element(key, value)

    @classmethod
    def add_parser(cls, obj):
        """Register a parser class for a specific element key.

        Used as a decorator: ``@UASLocalMetadataSet.add_parser``.
        """
        cls.parsers[bytes(obj.key)] = obj
        return obj

    parsers: dict[bytes, type]

    def __repr__(self) -> str:
        return pformat(self.items, indent=1)

    def __str__(self) -> str:
        return "\n".join(
            f"{'':>{0}}{item}" if not isinstance(item, Element)
            else f"{item}"
            for item in self.items.values()
        )

    def MetadataList(self) -> OrderedDict:
        """Return metadata as an OrderedDict.

        Top-level: {tag: (LDSName, value_string)}
        Nested:    {tag: (LDSName, ESDName, UDSName, {subtag: ...})}
        """
        metadata: dict = {}

        def _walk(items, parent_tag: int = 0):
            for item in items:
                if not hasattr(item.value, "value"):
                    continue
                try:
                    val_str = str(item.value.value)
                except Exception:
                    continue

                if not parent_tag:
                    metadata[item.TAG] = (item.LDSName, val_str)
                else:
                    parent = metadata[parent_tag]
                    if isinstance(parent, tuple) and len(parent) >= 4:
                        parent_dict = parent[-1]
                        if isinstance(parent_dict, dict):
                            parent_dict[item.TAG] = (item.LDSName, item.ESDName, item.UDSName, val_str)

                if hasattr(item, "items"):
                    sub: dict = {}
                    metadata[item.TAG] = (item.LDSName, item.ESDName, item.UDSName, sub)
                    _walk(item.items.values(), item.TAG)

        _walk(self.items.values())
        return OrderedDict(metadata)

    def structure(self):
        """Walk and print the metadata tag tree."""
        def _walk(items, depth: int = 0):
            for item in items:
                tag = getattr(item, "TAG", "?")
                name = getattr(item, "LDSName", type(item).__name__)
                print(f"{'  ' * depth}[{tag}] {name}")
                if hasattr(item, "items"):
                    _walk(item.items.values(), depth + 1)
        _walk(self.items.values())
