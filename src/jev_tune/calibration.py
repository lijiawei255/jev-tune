"""Compatibility alias for jev_tune.core.calibration; same module object."""
import sys

from .core import calibration as _module

sys.modules[__name__] = _module
