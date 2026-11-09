"""claimgate: a reference runner for documented numerical accuracy claims."""

from .model import BOOK_SCHEMA, RUN_SCHEMA, TOOL_NAME, TOOL_VERSION

__all__ = ["BOOK_SCHEMA", "RUN_SCHEMA", "TOOL_NAME", "TOOL_VERSION"]
__version__ = TOOL_VERSION
