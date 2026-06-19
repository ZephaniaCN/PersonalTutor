"""Domain registry — runtime registration of learning domains.

The registry is the single place capabilities look up "what domains exist".
Domains self-register at import time (see
:mod:`personal_tutor.domains.programming`), so adding a new field is just
"drop a package + import it" — no edits to capability code.
"""

from __future__ import annotations

import threading
from typing import Iterable

from .base import DomainSpec


class DomainRegistry:
    """Thread-safe registry of :class:`DomainSpec` instances."""

    def __init__(self) -> None:
        self._domains: dict[str, DomainSpec] = {}
        self._lock = threading.Lock()

    def register(self, spec: DomainSpec) -> None:
        if not getattr(spec, "domain_id", ""):
            raise ValueError("DomainSpec.domain_id must be a non-empty string")
        with self._lock:
            self._domains[spec.domain_id] = spec

    def unregister(self, domain_id: str) -> None:
        with self._lock:
            self._domains.pop(domain_id, None)

    def get(self, domain_id: str) -> DomainSpec | None:
        with self._lock:
            return self._domains.get(domain_id)

    def all(self) -> list[DomainSpec]:
        with self._lock:
            return list(self._domains.values())

    def ids(self) -> list[str]:
        with self._lock:
            return list(self._domains.keys())

    def require(self, domain_id: str) -> DomainSpec:
        spec = self.get(domain_id)
        if spec is None:
            available = ", ".join(self.ids()) or "<none>"
            raise KeyError(
                f"Unknown domain {domain_id!r}. Registered: {available}"
            )
        return spec

    def extend(self, specs: Iterable[DomainSpec]) -> None:
        for spec in specs:
            self.register(spec)


# --------------------------------------------------------------------------- #
# Module-level singleton
# --------------------------------------------------------------------------- #

_default_registry: DomainRegistry | None = None
_singleton_lock = threading.Lock()


def get_registry() -> DomainRegistry:
    """Return the process-wide :class:`DomainRegistry`.

    On first call the built-in domains (programming algorithms) are
    auto-registered. Call :func:`reset_registry` in tests to get a clean one.
    """
    global _default_registry
    with _singleton_lock:
        if _default_registry is None:
            registry = DomainRegistry()
            _autoregister_builtin_domains(registry)
            _default_registry = registry
        return _default_registry


def register(spec: DomainSpec) -> None:
    """Convenience: register *spec* on the default registry."""
    get_registry().register(spec)


def reset_registry() -> DomainRegistry:
    """Discard the default registry and return a freshly-built one.

    Intended for tests. The returned registry has the built-in domains
    re-registered (so a test gets a clean, predictable copy). The module
    singleton is cleared, so the *next* :func:`get_registry` call builds a new
    singleton rather than reusing this one — that avoids test registries
    leaking into production code paths.
    """
    global _default_registry
    with _singleton_lock:
        _default_registry = None
    # Build a fresh registry with built-ins, without touching the singleton so
    # the next get_registry() call rebuilds independently.
    fresh = DomainRegistry()
    _autoregister_builtin_domains(fresh)
    return fresh


def _autoregister_builtin_domains(registry: DomainRegistry) -> None:
    """Import and register the domains shipped with PersonalTutor.

    Imported lazily inside :func:`get_registry` so that simply importing
    :mod:`personal_tutor.domains` does not pull in every domain's deps (some
    future domains may ship heavy optional deps). Failures are logged but do
    not abort registry creation — a broken optional domain shouldn't take
    down the whole system.
    """
    import logging

    builtin_paths = [
        "personal_tutor.domains.programming.spec:ProgrammingDomain",
    ]
    for path in builtin_paths:
        try:
            module_path, cls_name = path.rsplit(":", 1)
            from importlib import import_module

            module = import_module(module_path)
            cls = getattr(module, cls_name)
            registry.register(cls())
        except Exception:  # pragma: no cover - defensive
            logging.getLogger(__name__).exception(
                "Failed to auto-register built-in domain %s", path
            )


__all__ = [
    "DomainRegistry",
    "get_registry",
    "register",
    "reset_registry",
]
