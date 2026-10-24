"""Compatibility alias for jev_tune.domains.pid.plants; same module object."""
import sys

from .domains.pid import plants as _module

sys.modules[__name__] = _module
