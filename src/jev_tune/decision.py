"""Compatibility alias for jev_tune.domains.pid.decision; same module object."""
import sys

from .domains.pid import decision as _module

sys.modules[__name__] = _module
