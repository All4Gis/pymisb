"""Vendored klvdata — MISB ST 0601 / ST 336 KLV parser.

Originally from <https://github.com/paretech/klvdata> (MIT License).
Extended with improvements from the QGISFMV fork (non-standard header
support, additional MISB 0102 elements, enhanced formatting).
"""

# These imports trigger @StreamParser.add_parser decorators that register
# the ST0601/0102/EG0104 parsers. Removing them breaks the decoder.
from . import misb0601  # noqa: F401
from . import misb0102  # noqa: F401
from . import misbEG0104  # noqa: F401
from .streamparser import StreamParser
