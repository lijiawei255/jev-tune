"""Compatibility alias for jev_tune.domains.pid.model; same module object."""
import sys

from .domains.pid import model as _module

sys.modules[__name__] = _module
