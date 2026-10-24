"""Compatibility alias for jev_tune.domains.pid.state; same module object."""
import sys

from .domains.pid import state as _module

sys.modules[__name__] = _module
