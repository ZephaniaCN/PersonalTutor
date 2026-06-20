"""Exam records store + formal assessment engine.

An exam differs from the adaptive quiz in three ways (mirroring how real exams
differ from homework):

1. **One-shot**: all questions are generated up front from a blueprint, and the
   learner submits all answers at once (no per-question feedback that would
   leak info).
2. **Timed**: a deadline is set; submissions after it are flagged late.
3. **Reported**: produces a score report (per-KP breakdown, comparison to last
   exam, top weak points) rather than just updating state.

Grading reuses :mod:`personal_tutor.llm.chains.grader` so the same quality bar
applies. After grading, BKT/FSRS/profile are updated just like a quiz — an exam
is also learning evidence, not only measurement.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any

from personal_tutor.capabilities.diagnostic.diagnostic import _sample_plan
from personal_tutor.domains import get_registry
from personal_tutor.domains.base import Difficulty
from personal_tutor.llm.chains.grader import DEFAULT_THRESHOLD, grade_answer
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.learning.fsrs_scheduler import Grade as FSRSGrade
from personal_tutor.learning.kt_store import KTStore
from personal_tutor.learning.profile_builder import write_profile
from personal_tutor.learning.review_store import ReviewStore
from personal_tutor.storage import json_store
from personal_tutor.storage.paths import exam_path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _now_ts() -> float:
    return time.time()


async def start_exam(
    domain_id: str,
    *,
    num_questions: int = 10,
    duration_minutes: int = 30,
    difficulty: str | None = None,
    title: str | None = None,
) -> dict[str, Any]:
    """Generate a fixed exam paper and open it for submission.

    Samples KPs (broadly, like the diagnostic) and generates one question per
    KP. The expected answers stay server-side; the client receives only the
    questions. A deadline is recorded from *duration_minutes*.
    """
    spec = get_registry().require(domain_id)
    graph = spec.knowledge_graph()
    plan = _sample_plan(domain_id)[:num_questions]

    # If a fixed difficulty is requested, honor it; else scale by prior mastery.
    fixed_diff = Difficulty(difficulty) if difficulty else None
    kt_store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    states = kt_store.get_all()

    questions: list[dict[str, Any]] = []
    for item in plan:
        kp = graph.get(item["knowledge_point_id"])
        if kp is None:
            continue
        diff = fixed_diff or Difficulty.from_mastery(tracer.mastery_of(states.get(kp.id), kp.id))
        for gen in spec.generators_for(kp):
            produced = await gen.generate(kp, difficulty=diff, count=1)
            for q in produced:
                questions.append(q)
            break

    exam_id = f"exam_{uuid.uuid4().hex[:12]}"
    started = _now_ts()
    record = {
        "exam_id": exam_id,
        "domain_id": domain_id,
        "title": title or f"{spec.name} 评估 — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
        "status": "open",
        "started_at": started,
        "started_at_iso": _now_iso(),
        "deadline": started + duration_minutes * 60.0,
        "duration_minutes": duration_minutes,
        "num_questions": len(questions),
        "questions": questions,
        # expected answers kept here, server-side; stripped from the "paper" view.
    }
    json_store.write_json(exam_path(exam_id), record)
    return record


async def submit_exam(
    exam_id: str,
    answers: list[dict[str, Any]],
    *,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Grade an exam submission and produce the score report.

    Each answer: ``{knowledge_point_id, user_answer}``. Late submissions are
    graded but flagged. After grading, BKT/FSRS/profile are updated.
    """
    record = json_store.read_json(exam_path(exam_id), default=None)
    if not isinstance(record, dict):
        raise KeyError(f"exam {exam_id!r} not found")
    if record.get("status") == "graded":
        raise ValueError(f"exam {exam_id!r} already graded")

    domain_id = record["domain_id"]
    spec = get_registry().require(domain_id)
    questions = {q["knowledge_point_id"]: q for q in record.get("questions", [])}
    submitted_ts = _now_ts()
    is_late = submitted_ts > record.get("deadline", float("inf"))

    # Grade each answer.
    per_kp: list[dict[str, Any]] = []
    correct = 0
    bkt_outcomes: dict[str, bool] = {}
    for ans in answers:
        kp_id = ans.get("knowledge_point_id")
        user_answer = ans.get("user_answer", "")
        q = questions.get(kp_id, {})
        rubric = spec.rubric_for(_qtype(q))
        verdict = await grade_answer(
            knowledge_point_id=kp_id,
            question=q.get("question", ""),
            reference_answer=q.get("expected_answer") or q.get("correct_answer", ""),
            learner_answer=user_answer,
            rubric=(rubric.criteria if rubric else "覆盖核心概念"),
            threshold=threshold,
        )
        if verdict.is_correct:
            correct += 1
        bkt_outcomes[kp_id] = verdict.is_correct
        per_kp.append(
            {
                "knowledge_point_id": kp_id,
                "verdict": verdict.to_dict(),
                "user_answer": user_answer,
                "expected_answer": q.get("expected_answer") or q.get("correct_answer", ""),
            }
        )

    # Update BKT + FSRS + profile (an exam is learning evidence too).
    kt_store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    states = tracer.update_many(kt_store.get_all(), bkt_outcomes)
    kt_store.upsert_many(states.values())
    kt_store.save()

    review_store = ReviewStore(domain_id)
    fsrs_states = review_store.get_all()
    for kp_id, ok in bkt_outcomes.items():
        st = fsrs_states.get(kp_id) or review_store.get(kp_id)
        review_store.scheduler.review(st, FSRSGrade.GOOD if ok else FSRSGrade.AGAIN)
        fsrs_states[kp_id] = st
    review_store.save()

    profile = write_profile(domain_id, kt_store, tracer, note=f"exam {exam_id}")

    total = len(answers) or 1
    report = {
        "exam_id": exam_id,
        "domain_id": domain_id,
        "title": record.get("title"),
        "status": "graded",
        "submitted_at_iso": _now_iso(),
        "late": is_late,
        "score": {"correct": correct, "total": len(answers), "pct": round(correct / total, 4)},
        "per_kp": per_kp,
        "weak_points": profile["weak_points"][:5],
        "profile_summary": profile["summary"],
    }
    # Persist the graded record (replace the open one).
    record.update(report)
    record["status"] = "graded"
    json_store.write_json(exam_path(exam_id), record)
    return report


def get_exam_report(exam_id: str) -> dict[str, Any]:
    """Return the stored exam record (open or graded)."""
    record = json_store.read_json(exam_path(exam_id), default=None)
    if not isinstance(record, dict):
        raise KeyError(f"exam {exam_id!r} not found")
    return record


def _qtype(question: dict[str, Any]):
    from personal_tutor.domains.base import QuestionType

    try:
        return QuestionType(question.get("question_type", "concept"))
    except ValueError:
        return QuestionType.CONCEPT


__all__ = ["start_exam", "submit_exam", "get_exam_report"]
