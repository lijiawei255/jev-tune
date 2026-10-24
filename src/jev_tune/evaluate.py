"""Compatibility alias for jev_tune.domains.pid.evaluate; same module object."""
import sys

from .domains.pid import evaluate as _module

sys.modules[__name__] = _module
