"""Plugin discovery for PersonalTutor.

This module is the single source of truth for *what* PersonalTutor exposes to
DeepTutor's plugin-aware registry. The upstream registry
(:mod:`deeptutor.runtime.registry.capability_registry`) calls:

* :func:`discover_plugins` -> iterable of manifests
* :func:`load_plugin_capability(manifest)` -> ``BaseCapability`` | None

A manifest is a lightweight data object. The registry only inspects:

* ``manifest.name``            — unique capability id
* ``manifest.entry``           — module path; entries ending in ``tool.py`` are
                                 *skipped* by the capability registry (they are
                                 reserved for a future tool-plugin path), so our
                                 capability entries deliberately end with
                                 ``capability.py``.
* ``manifest.type`` / ``description`` / ``stages`` / ``version`` / ``author``
                                 — surfaced in ``deeptutor plugin list`` and the
                                 ``/api/v1/plugins/list`` endpoint.

We keep a registry of *specs* (``PersonalCapabilitySpec``) rather than live
capability instances so that discovery is cheap (no heavy imports up front);
the capability is only instantiated on demand.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import import_module
from typing import Any, Callable

from . import __version__

# Type alias re-exported for convenience; resolved lazily to avoid importing
# DeepTutor at module import time (keeps ``import personal_tutor`` cheap and
# lets unit tests stub the registry without a live DeepTutor install).
BaseCapability: Any  # forward-declared for type hints only


@dataclass(frozen=True)
class PersonalCapabilitySpec:
    """Declarative description of a PersonalTutor capability plugin.

    ``entry`` must be ``"module.path:ClassName"`` where ``module.path`` resolves
    under :mod:`personal_tutor` and ``ClassName`` is a concrete
    :class:`deeptutor.core.capability_protocol.BaseCapability` subclass. The
    module path is deliberately chosen to end in ``capability`` so the file is
    ``capability.py`` — this is what keeps the upstream capability registry
    from skipping it (entries ending in ``tool.py`` are treated as tool plugins
    and ignored by ``CapabilityRegistry.load_plugins``).
    """

    name: str
    description: str
    entry: str  # "module.path:ClassName"
    stages: tuple[str, ...] = ()
    version: str = __version__
    author: str = "PersonalTutor"
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def type(self) -> str:
        # Surfaced in ``deeptutor plugin list``; matches upstream's category
        # naming ("capability" for deep modes, "tool" for atomic tools).
        return "capability"

    def to_manifest(self) -> "PersonalManifest":
        return PersonalManifest(
            name=self.name,
            type=self.type,
            description=self.description,
            stages=list(self.stages),
            version=self.version,
            author=self.author,
            entry=self.entry,
        )


@dataclass
class PersonalManifest:
    """Manifest object returned to upstream.

    Attribute names match what the upstream ``plugins_api`` router and
    capability registry read (``name``/``type``/``description``/``stages``/
    ``version``/``author``/``entry``).
    """

    name: str
    type: str
    description: str
    stages: list[str]
    version: str
    author: str
    entry: str


# --------------------------------------------------------------------------- #
# Spec registry
# --------------------------------------------------------------------------- #

_SPECS: list[PersonalCapabilitySpec] = []


def register_capability(spec: PersonalCapabilitySpec) -> None:
    """Register a capability spec for discovery.

    Duplicate names replace the earlier spec (last-wins) so tests and
    downstream domains can override defaults.
    """
    _SPECS[:] = [s for s in _SPECS if s.name != spec.name]
    _SPECS.append(spec)


def all_specs() -> list[PersonalCapabilitySpec]:
    """Return a copy of the currently registered specs."""
    return list(_SPECS)


def clear() -> None:
    """Drop all registered specs (used by unit tests)."""
    _SPECS.clear()


# --------------------------------------------------------------------------- #
# Defaults — the capabilities PersonalTutor ships with
# --------------------------------------------------------------------------- #

def _install_defaults() -> None:
    """Register the built-in PersonalTutor capabilities.

    Kept in a function (rather than module-level statements) so that callers
    can re-trigger registration in tests after :func:`clear`.
    """
    register_capability(
        PersonalCapabilitySpec(
            name="personal_hello",
            description=(
                "PersonalTutor smoke-test capability. Echoes a short report "
                "describing the active domain registry and installed "
                "capabilities. Use it to verify plugin injection is wired up."
            ),
            entry="personal_tutor.capabilities.hello.capability:HelloCapability",
            stages=("responding",),
        )
    )
    register_capability(
        PersonalCapabilitySpec(
            name="personal_diagnostic",
            description=(
                "PersonalTutor entry diagnostic. Samples a domain's knowledge "
                "graph, generates one question per sampled knowledge point, "
                "and emits the question set. Submit answers via the "
                "POST /api/v1/personal/diagnostics/{domain_id}/grade endpoint "
                "to update the BKT-based learner profile."
            ),
            entry="personal_tutor.capabilities.diagnostic.capability:DiagnosticCapability",
            stages=("preparing", "responding"),
        )
    )
    register_capability(
        PersonalCapabilitySpec(
            name="personal_quiz",
            description=(
                "PersonalTutor adaptive quiz. Picks the learner's weakest "
                "knowledge point, scales difficulty to current mastery, and "
                "emits one question. Grade via "
                "POST /api/v1/personal/quiz/{domain_id}/grade to update BKT."
            ),
            entry="personal_tutor.capabilities.adaptive_quiz.capability:AdaptiveQuizCapability",
            stages=("selecting", "responding"),
        )
    )


_install_defaults()


# --------------------------------------------------------------------------- #
# Hooks consumed by deeptutor.plugins.loader
# --------------------------------------------------------------------------- #

def discover_plugins() -> list[PersonalManifest]:
    """Return manifests for all registered PersonalTutor capabilities."""
    # Ensure defaults exist even if a caller cleared the registry.
    if not _SPECS:
        _install_defaults()
    return [spec.to_manifest() for spec in _SPECS]


def load_plugin_capability(manifest: PersonalManifest):  # -> BaseCapability | None
    """Instantiate the capability behind *manifest*.

    Returns ``None`` if the entry cannot be resolved so the upstream registry
    can continue loading other plugins.
    """
    try:
        module_path, class_name = manifest.entry.rsplit(":", 1)
        module = import_module(module_path)
        cls = getattr(module, class_name)
        return cls()
    except Exception:  # pragma: no cover - surfaced in upstream logs
        import logging

        logging.getLogger(__name__).exception(
            "Failed to load PersonalTutor capability %s", manifest.name
        )
        return None


__all__ = [
    "PersonalCapabilitySpec",
    "PersonalManifest",
    "register_capability",
    "all_specs",
    "clear",
    "discover_plugins",
    "load_plugin_capability",
]
