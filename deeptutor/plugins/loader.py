"""Plugin loader shim — re-exports from :mod:`personal_tutor.plugins`.

Kept as a thin module so that ``import deeptutor.plugins.loader`` resolves to
the isolated implementation without PersonalTutor needing to modify any
upstream file. The real logic lives in
:mod:`personal_tutor.plugins` so that it can evolve independently and be unit
tested without importing DeepTutor's runtime.
"""

from personal_tutor.plugins import discover_plugins, load_plugin_capability

__all__ = ["discover_plugins", "load_plugin_capability"]
