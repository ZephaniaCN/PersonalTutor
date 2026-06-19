"""Domain extension framework — the core extensibility layer of PersonalTutor.

A *domain* (programming algorithms, LLMs, photography, writing, ...) is
described declaratively by a :class:`DomainSpec`: its knowledge graph,
question generators, rubrics, and mastery thresholds. Domains register
themselves at import time (no source changes elsewhere), which is what lets
PersonalTutor grow to new fields on demand.

Public surface
--------------
* :class:`DomainSpec`, :class:`KnowledgeGraph`, :class:`KnowledgePoint`
* :class:`QuestionType`, :class:`QuestionGenerator`, :class:`Rubric`
* :class:`DomainRegistry`, :func:`get_registry`, :func:`register`

The built-in **programming algorithms** domain lives in
:mod:`personal_tutor.domains.programming` and is auto-registered when this
package is imported.
"""

from __future__ import annotations

from .base import (
    DiagnosticBlueprint,
    DomainSpec,
    KnowledgeGraph,
    KnowledgePoint,
    QuestionGenerator,
    QuestionType,
    Rubric,
)
from .registry import DomainRegistry, get_registry, register, reset_registry

__all__ = [
    "DiagnosticBlueprint",
    "DomainSpec",
    "KnowledgeGraph",
    "KnowledgePoint",
    "QuestionGenerator",
    "QuestionType",
    "Rubric",
    "DomainRegistry",
    "get_registry",
    "register",
    "reset_registry",
]
