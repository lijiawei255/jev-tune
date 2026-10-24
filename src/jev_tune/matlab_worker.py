"""Compatibility alias for jev_tune.domains.pid.matlab_worker; same module object."""
import sys

from .domains.pid import matlab_worker as _module

sys.modules[__name__] = _module
