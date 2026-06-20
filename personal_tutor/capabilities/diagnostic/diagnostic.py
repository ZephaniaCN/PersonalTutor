"""Diagnostic coordinator — prepare questions and grade answers.

Kept framework-agnostic (no DeepTutor capability imports here) so it can be
unit-tested directly and reused by both the REST layer and the capability
wrapper in ``capability.py``. The BKT update + profile rebuild happens here so
the logic has exactly one implementation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from personal_tutor.domains import get_registry
from personal_tutor.domains.base import Difficulty
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.learning.kt_store import KTStore
from personal_tutor.learning.profile_builder import write_profile
from personal_tutor.storage import json_store
from personal_tutor.storage.paths import diagnostic_path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sample_plan(domain_id: str) -> list[dict[str, str]]:
    """Pick KPs to test, honoring the blueprint's must-include + per-module quota."""
    spec = get_registry().require(domain_id)
    bp = spec.diagnostic_blueprint()
    graph = spec.knowledge_graph()

    plan: list[dict[str, str]] = []
    seen: set[str] = set()

    for must in bp.must_include:
        kp = graph.get(must)
        if kp and kp.id not in seen:
            plan.append({"knowledge_point_id": kp.id, "name": kp.name})
            seen.add(kp.id)

    for module_id in graph.module_order:
        for kp_id in graph.modules.get(module_id, []):
            kp = graph.get(kp_id)
            if not kp or kp.id in seen:
                continue
            plan.append({"knowledge_point_id": kp.id, "name": kp.name})
            seen.add(kp.id)
            # stop adding from this module once the per-module quota is hit
            module_count = sum(1 for p in plan if graph.get(p["knowledge_point_id"]) and graph.get(p["knowledge_point_id"]).module_id == module_id)
            if module_count >= bp.questions_per_module:
                break

    return plan


async def prepare_diagnostic(domain_id: str) -> dict[str, Any]:
    """Produce the diagnostic question set for *domain_id*.

    Generates one question per sampled KP via the domain's generators. Each
    question carries an ``expected_answer`` so grading is deterministic and
    server-side (the client never sees the answer until grading).
    """
    spec = get_registry().require(domain_id)
    bp = spec.diagnostic_blueprint()
    graph = spec.knowledge_graph()
    plan = _sample_plan(domain_id)
    difficulty = Difficulty.from_mastery(0.0) if False else bp.default_difficulty

    questions: list[dict[str, Any]] = []
    for item in plan:
        kp = graph.get(item["knowledge_point_id"])
        if kp is None:
            continue
        # Use the first generator that yields for this KP.
        for gen in spec.generators_for(kp):
            produced = await gen.generate(kp, difficulty=difficulty, count=1)
            for q in produced:
                questions.append(q)
            break

    diagnostic_id = f"diag_{uuid.uuid4().hex[:12]}"
    result = {
        "diagnostic_id": diagnostic_id,
        "domain_id": domain_id,
        "created_at": _now(),
        "blueprint": {
            "questions_per_module": bp.questions_per_module,
            "default_difficulty": bp.default_difficulty.value,
            "must_include": list(bp.must_include),
        },
        "questions": questions,
        "total_questions": len(questions),
        "status": "prepared",
    }
    json_store.write_json(diagnostic_path(domain_id), result)
    return result


def grade_diagnostic(
    domain_id: str,
    answers: list[dict[str, Any]],
    *,
    diagnostic_id: str | None = None,
) -> dict[str, Any]:
    """Grade diagnostic answers, update BKT, and rebuild the profile.

    Each answer dict carries ``knowledge_point_id`` and ``is_correct`` (the
    client computes correctness against the question's expected_answer, or an
    LLM grades open answers). We trust the client's correctness flag here —
    same convention as DeepTutor's ``POST /sessions/{id}/quiz-results``.

    Returns the updated profile so callers get the result of the baseline in
    one round trip.
    """
    spec = get_registry().require(domain_id)
    store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)

    outcomes: dict[str, bool] = {}
    correct_count = 0
    for ans in answers:
        kp_id = ans.get("knowledge_point_id")
        if not kp_id:
            continue
        is_correct = bool(ans.get("is_correct", False))
        outcomes[kp_id] = is_correct
        if is_correct:
            correct_count += 1

    # Apply BKT updates through the tracer, then persist.
    states = store.get_all()
    states = tracer.update_many(states, outcomes)
    store.upsert_many(states.values())
    store.save()

    # Rebuild + persist the profile (also mirrors to Memory L3).
    profile = write_profile(
        domain_id,
        store,
        tracer,
        note=f"Updated by diagnostic {diagnostic_id or '(inline)'}",
    )

    total = len(answers) or 1
    return {
        "diagnostic_id": diagnostic_id,
        "domain_id": domain_id,
        "graded_at": _now(),
        "score": {"correct": correct_count, "total": len(answers), "pct": round(correct_count / total, 4)},
        "profile_summary": profile["summary"],
        "weak_points": profile["weak_points"][:5],
        "status": "graded",
    }


__all__ = ["prepare_diagnostic", "grade_diagnostic"]
