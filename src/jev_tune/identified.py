"""Compatibility alias for jev_tune.domains.pid.identified; same module object."""
import sys

from .domains.pid import identified as _module

sys.modules[__name__] = _module
