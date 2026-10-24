"""Compatibility alias for jev_tune.domains.pid.baselines; same module object."""
import sys

from .domains.pid import baselines as _module

sys.modules[__name__] = _module
