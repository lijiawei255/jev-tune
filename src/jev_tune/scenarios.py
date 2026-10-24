"""Compatibility alias for jev_tune.domains.pid.scenarios; same module object."""
import sys

from .domains.pid import scenarios as _module

sys.modules[__name__] = _module
