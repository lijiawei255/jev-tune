"""Compatibility alias for jev_tune.domains.pid.plot; same module object."""
import sys

from .domains.pid import plot as _module

sys.modules[__name__] = _module
