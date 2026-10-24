"""Compatibility alias for jev_tune.domains.pid.expert; same module object."""
import sys

from .domains.pid import expert as _module

sys.modules[__name__] = _module
