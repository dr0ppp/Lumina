"""XMP handling independent of the command line and future parsers."""

from .reader import read_parameters
from .writer import set_exposure, set_parameters

__all__ = ["read_parameters", "set_exposure", "set_parameters"]
