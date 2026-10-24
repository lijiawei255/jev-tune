"""Compatibility alias for jev_tune.domains.pid.matlab_baseline; same module object."""
import sys

from .domains.pid import matlab_baseline as _module

sys.modules[__name__] = _module
