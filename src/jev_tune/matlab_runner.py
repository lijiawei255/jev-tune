"""Compatibility alias for jev_tune.domains.pid.matlab_runner; same module object."""
import sys

from .domains.pid import matlab_runner as _module

sys.modules[__name__] = _module
