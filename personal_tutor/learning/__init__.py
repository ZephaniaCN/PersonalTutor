"""PersonalTutor's learning engine — the pedagogy math.

This package is the "brain": pure-Python, dependency-light, and fully unit
testable without DeepTutor or an LLM. It deliberately parallels DeepTutor's
own ``deeptutor/learning/`` package but implements stronger models:

* :mod:`knowledge_tracing` — Bayesian Knowledge Tracing (BKT) with a clean
  per-KP 4-parameter model. This is the "richer model" DeepTutor's
  ``compute_mastery`` docstring invites you to plug in.
* :mod:`kt_store` — persistence of BKT state, riding DeepTutor's ``PathService``.
* :mod:`profile_builder` — aggregates BKT state into a learner profile and
  mirrors it into DeepTutor's Memory L3 ``profile`` slot.

Future phases add :mod:`fsrs_scheduler` (Phase 2) here.
"""

from .knowledge_tracing import (
    DEFAULT_KT_PARAMS,
    KTParams,
    KTState,
    KnowledgeTracer,
)

__all__ = [
    "DEFAULT_KT_PARAMS",
    "KTParams",
    "KTState",
    "KnowledgeTracer",
]
