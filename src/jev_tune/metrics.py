"""Compatibility alias for jev_tune.domains.pid.metrics; same module object."""
import sys

from .domains.pid import metrics as _module

sys.modules[__name__] = _module
