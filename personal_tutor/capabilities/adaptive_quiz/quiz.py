"""Adaptive quiz coordinator — the practice loop.

Two-phase, client-driven (like the diagnostic), but adaptive:

* **next**: pick the weakest knowledge point the learner hasn't exhausted
  recently, choose a difficulty from its current mastery (low → easy, high →
  hard), generate a question, and return it. The expected_answer is kept
  server-side for grading.
* **grade**: grade the learner's answer (LLM if configured, else keyword
  overlap), update BKT + FSRS state, and rebuild the profile so the next
  ``next`` call sees the new mastery.

This closes the practice loop: each answer sharpens the estimate of what the
learner knows, which steers the next question. Compared to a fixed quiz, this
spends the learner's time where it matters most.
"""

from __future__ import annotations

import time
from typing import Any

from personal_tutor.domains import get_registry
from personal_tutor.domains.base import Difficulty
from personal_tutor.llm.chains.grader import DEFAULT_THRESHOLD, grade_answer
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.learning.fsrs_scheduler import Grade as FSRSGrade
from personal_tutor.learning.kt_store import KTStore
from personal_tutor.learning.profile_builder import write_profile
from personal_tutor.learning.review_store import ReviewStore

#: Don't re-quiz the same KP within this window (seconds) so a session spreads
#: across topics. ~10 min.
_RECENT_COOLDOWN = 600.0


async def next_question(domain_id: str, *, exclude: list[str] | None = None) -> dict[str, Any]:
    """Pick the next adaptive question for the learner.

    Selection: lowest-mastery KP that isn't in *exclude* and wasn't quizzed in
    the last cooldown window. Difficulty scales with mastery via the domain's
    :class:`Difficulty.from_mastery`.
    """
    spec = get_registry().require(domain_id)
    graph = spec.knowledge_graph()
    kt_store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    states = kt_store.get_all()

    exclude_set = set(exclude or [])
    now = time.time()

    # Score every KP, filter exclusions + recent.
    scored: list[tuple[str, float]] = []
    for kp in graph.all_points():
        if kp.id in exclude_set:
            continue
        st = states.get(kp.id)
        # Cooldown: skip KPs quizzed very recently (has FSRS state w/ recent review).
        if st and st.last_updated:
            continue
        scored.append((kp.id, tracer.mastery_of(st, kp.id)))

    if not scored:
        # Everything excluded/recent — fall back to absolute weakest ignoring cooldown.
        scored = [
            (kp.id, tracer.mastery_of(states.get(kp.id), kp.id))
            for kp in graph.all_points()
            if kp.id not in exclude_set
        ] or [(kp.id, tracer.mastery_of(states.get(kp.id), kp.id)) for kp in graph.all_points()]

    scored.sort(key=lambda kv: kv[1])
    kp_id, mastery = scored[0]
    kp = graph.get(kp_id)
    difficulty = Difficulty.from_mastery(mastery)

    # Generate via the domain's generators.
    question: dict[str, Any] | None = None
    for gen in spec.generators_for(kp):
        produced = await gen.generate(kp, difficulty=difficulty, count=1)
        if produced:
            question = produced[0]
            break

    if question is None:
        return {"domain_id": domain_id, "error": "no generator produced a question"}

    # Mark the KT state as recently quizzed (cooldown via last_updated timestamp).
    st = kt_store.get(kp_id)
    # Store a sentinel ISO-ish marker; grade() will overwrite with the real outcome.
    st.last_updated = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now))
    kt_store.upsert(st)
    kt_store.save()

    return {
        "domain_id": domain_id,
        "knowledge_point_id": kp_id,
        "kp_name": kp.name,
        "mastery": round(mastery, 4),
        "difficulty": difficulty.value,
        "rationale": f"当前掌握度 {mastery:.0%},聚焦最薄弱知识点",
        "question": question,
    }


async def grade_one(
    domain_id: str,
    *,
    knowledge_point_id: str,
    user_answer: str,
    question: dict[str, Any] | None = None,
    threshold: float = DEFAULT_THRESHOLD,
) -> dict[str, Any]:
    """Grade a single adaptive answer and update all learner state.

    *question* (the full question dict incl. expected_answer) may be passed by
    the client; if absent we look up expected_answer from the placeholder. The
    BKT outcome and an FSRS review (Good/Again) are applied so both mastery
    estimation and the review schedule reflect this attempt.
    """
    spec = get_registry().require(domain_id)
    graph = spec.knowledge_graph()
    kp = graph.get(knowledge_point_id)
    if kp is None:
        return {"error": f"unknown knowledge point {knowledge_point_id!r}"}

    expected = (question or {}).get("expected_answer") or (question or {}).get("correct_answer") or kp.summary
    question_text = (question or {}).get("question", f"请说明「{kp.name}」")

    verdict = await grade_answer(
        knowledge_point_id=knowledge_point_id,
        question=question_text,
        reference_answer=expected,
        learner_answer=user_answer,
        rubric=(spec.rubric_for(_qtype(question)) or "").criteria if spec.rubric_for(_qtype(question)) else "覆盖核心概念",
        threshold=threshold,
    )

    # Update BKT.
    kt_store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    st_bkt = kt_store.get(knowledge_point_id)
    tracer.update(st_bkt, verdict.is_correct)
    kt_store.upsert(st_bkt)
    kt_store.save()

    # Update FSRS (treating correct=Good, wrong=Again).
    review_store = ReviewStore(domain_id)
    st_fsrs = review_store.get(knowledge_point_id)
    grade = FSRSGrade.GOOD if verdict.is_correct else FSRSGrade.AGAIN
    review_store.scheduler.review(st_fsrs, grade)
    review_store.upsert(st_fsrs)
    review_store.save()

    # Rebuild profile (cheap; single domain) so /weakness reflects this attempt.
    write_profile(domain_id, kt_store, tracer, note="adaptive quiz update")

    return {
        "domain_id": domain_id,
        "knowledge_point_id": knowledge_point_id,
        "verdict": verdict.to_dict(),
        "new_mastery": round(st_bkt.p_known, 4),
        "expected_answer": expected,
        "explanation": (question or {}).get("explanation", ""),
    }


def _qtype(question: dict[str, Any] | None):
    from personal_tutor.domains.base import QuestionType

    raw = (question or {}).get("question_type", "concept")
    try:
        return QuestionType(raw)
    except ValueError:
        return QuestionType.CONCEPT


__all__ = ["next_question", "grade_one"]
