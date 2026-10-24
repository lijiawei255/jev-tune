"""Compatibility alias for jev_tune.core.primitives; same module object."""
import sys

from .core import primitives as _module

sys.modules[__name__] = _module
