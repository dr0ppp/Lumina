"""Explicit local parameter commands, independent of XMP and the CLI."""

from .rules import Adjustment, parse_instructions

__all__ = ["Adjustment", "parse_instructions"]
