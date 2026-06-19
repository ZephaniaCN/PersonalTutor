"""DeepTutor plugin discovery hook.

This package is a **reserved extension point** in upstream DeepTutor: the
capability registry (:mod:`deeptutor.runtime.registry.capability_registry`)
and the plugins API (:mod:`deeptutor.api.routers.plugins_api`) both do
``import deeptutor.plugins.loader`` and gracefully no-op when the module is
absent.

PersonalTutor fills this slot so its capabilities and tools are discovered
automatically by an **unmodified** upstream registry — no patch to
``BUILTIN_CAPABILITY_CLASSES`` required. This file therefore stays minimal
and forwards everything to the isolated :mod:`personal_tutor` package, so an
upstream ``git rebase`` over ``deeptutor/`` touches this directory only if
upstream itself ships a ``plugins/`` package (in which case this file is the
single merge point).

See ``personal_tutor/plugins.py`` for the actual discovery implementation.
"""

from __future__ import annotations


def _load():
    """Import the real discovery implementation lazily.

    Importing :mod:`personal_tutor` here keeps this shim free of heavy deps
    at collection time; failure is swallowed by the registry's ``except``.
    """
    from personal_tutor.plugins import discover_plugins, load_plugin_capability

    return discover_plugins, load_plugin_capability


def discover_plugins():
    """Return plugin manifests discovered by PersonalTutor.

    Mirrors the contract the upstream registry expects: an iterable of
    manifests each carrying at least ``name`` / ``type`` / ``description`` /
    ``entry`` fields. See :mod:`personal_tutor.plugins` for details.
    """
    discover, _ = _load()
    return discover()


def load_plugin_capability(manifest):
    """Instantiate the capability described by *manifest*, or ``None``."""
    _, load = _load()
    return load(manifest)


__all__ = ["discover_plugins", "load_plugin_capability"]
