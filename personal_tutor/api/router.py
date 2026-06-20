"""PersonalTutor REST router.

Thin facade over :mod:`personal_tutor.domains`, :mod:`personal_tutor.learning`,
and :mod:`personal_tutor.capabilities.diagnostic` so the real logic stays
testable without HTTP.

Endpoints
---------
* ``GET  /api/v1/personal/health``                         — liveness + version
* ``GET  /api/v1/personal/domains``                        — list registered domains
* ``GET  /api/v1/personal/domains/{id}``                   — domain knowledge graph
* ``GET  /api/v1/personal/profile/{domain_id}``            — read learning profile
* ``PUT  /api/v1/personal/profile/{domain_id}``            — write learning profile
* ``POST /api/v1/personal/profile/{domain_id}/rebuild``    — recompute profile from BKT
* ``POST /api/v1/personal/diagnostics/{id}/start``         — prepare diagnostic questions
* ``POST /api/v1/personal/diagnostics/{id}/grade``         — grade answers, update BKT + profile
* ``GET  /api/v1/personal/weakness/{domain_id}``           — lowest-mastery knowledge points
* ``GET  /api/v1/personal/review/{domain_id}/queue``       — FSRS due-review queue
* ``POST /api/v1/personal/review/{domain_id}/submit``      — record reviews, reschedule (FSRS+BKT)
* ``POST /api/v1/personal/roadmaps/{domain_id}/generate``  — generate personalized roadmap
* ``GET  /api/v1/personal/roadmaps/{domain_id}``           — read stored roadmap
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from personal_tutor import __version__ as pt_version
from personal_tutor import MIN_DEEPTUTOR_VERSION
from personal_tutor.capabilities.diagnostic.diagnostic import (
    grade_diagnostic,
    prepare_diagnostic,
)
from personal_tutor.capabilities.roadmap_planner.planner import (
    load_roadmap,
    plan_roadmap,
)
from personal_tutor.domains import get_registry
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.learning.fsrs_scheduler import Grade
from personal_tutor.learning.kt_store import KTStore
from personal_tutor.learning.profile_builder import build_profile, write_profile
from personal_tutor.learning.review_store import ReviewStore
from personal_tutor.storage import json_store
from personal_tutor.storage.paths import diagnostic_path, profile_path

router = APIRouter()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _require_domain(domain_id: str):
    try:
        return get_registry().require(domain_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


def _serialize_graph(spec) -> dict[str, Any]:
    """Render a domain's knowledge graph for the frontend."""
    graph = spec.knowledge_graph()
    return {
        "domain_id": spec.domain_id,
        "name": spec.name,
        "description": spec.description,
        "modules": [
            {"id": mid, "name": graph.modules.get(mid) and mid or mid}
            for mid in graph.module_order
        ],
        "module_names": {
            mid: [graph.get(kp).name for kp in kps if graph.get(kp)]
            for mid, kps in graph.modules.items()
        },
        "knowledge_points": [
            {
                "id": kp.id,
                "name": kp.name,
                "summary": kp.summary,
                "type": kp.type,
                "module_id": kp.module_id,
                "prerequisites": list(kp.prerequisites),
                "tags": list(kp.tags),
            }
            for kp in graph.all_points()
        ],
        "topological_order": graph.topological_order(),
    }


# --------------------------------------------------------------------------- #
# Health
# --------------------------------------------------------------------------- #

@router.get("/health")
async def health() -> dict[str, Any]:
    """Liveness probe + version metadata for the frontend."""
    return {
        "ok": True,
        "personal_tutor_version": pt_version,
        "min_deeptutor_version": MIN_DEEPTUTOR_VERSION,
        "domains": get_registry().ids(),
    }


# --------------------------------------------------------------------------- #
# Domains
# --------------------------------------------------------------------------- #

@router.get("/domains")
async def list_domains() -> list[dict[str, Any]]:
    """List all registered learning domains with a knowledge-point count."""
    out: list[dict[str, Any]] = []
    for spec in get_registry().all():
        graph = spec.knowledge_graph()
        out.append(
            {
                "domain_id": spec.domain_id,
                "name": spec.name,
                "description": spec.description,
                "knowledge_point_count": len(graph.all_points()),
            }
        )
    return out


@router.get("/domains/{domain_id}")
async def get_domain(domain_id: str) -> dict[str, Any]:
    """Return a domain's full knowledge graph (modules + points + topo order)."""
    spec = _require_domain(domain_id)
    return _serialize_graph(spec)


# --------------------------------------------------------------------------- #
# Profile (learning档案) — read/write the structured profile JSON
# --------------------------------------------------------------------------- #

class ProfileUpdate(BaseModel):
    """Partial update to a learning profile.

    The frontend posts the whole profile object; we persist it verbatim. As
    the BKT engine lands, richer schema validation will be added here.
    """

    profile: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


@router.get("/profile/{domain_id}")
async def get_profile(domain_id: str) -> dict[str, Any]:
    """Read the stored learning profile for a domain (empty if none yet)."""
    _require_domain(domain_id)
    data = json_store.read_json(profile_path(domain_id), default=None)
    if data is None:
        return {"domain_id": domain_id, "profile": {}, "initialized": False}
    return {"domain_id": domain_id, **data, "initialized": True}


@router.put("/profile/{domain_id}")
async def put_profile(domain_id: str, body: ProfileUpdate) -> dict[str, Any]:
    """Write (or replace) the learning profile for a domain."""
    _require_domain(domain_id)
    payload = {"domain_id": domain_id, "profile": body.profile, "note": body.note}
    json_store.write_json(profile_path(domain_id), payload)
    return {"ok": True, "domain_id": domain_id}


# --------------------------------------------------------------------------- #
# Diagnostic — phase-0: return the blueprint + a sampled question plan
# --------------------------------------------------------------------------- #

@router.post("/diagnostics/{domain_id}/start")
async def start_diagnostic(domain_id: str) -> dict[str, Any]:
    """Start an entry diagnostic for a domain.

    Samples the knowledge graph per the domain's blueprint, generates one
    question per sampled KP (placeholder generator today, LLM-backed once a
    model is configured), and returns the full question set. Each question
    carries an ``expected_answer`` for deterministic grading.

    Submit answers with :meth:`grade_diagnostic_answers`.
    """
    _require_domain(domain_id)
    return await prepare_diagnostic(domain_id)


class AnswerItem(BaseModel):
    """One graded answer from the client.

    ``is_correct`` is computed client-side (against expected_answer, or via an
    LLM grade for open questions) — same convention as DeepTutor's quiz-results.
    """

    knowledge_point_id: str
    is_correct: bool
    question_id: str | None = None
    user_answer: str | None = None


class GradeRequest(BaseModel):
    answers: list[AnswerItem]
    diagnostic_id: str | None = None


@router.post("/diagnostics/{domain_id}/grade")
async def grade_diagnostic_answers(
    domain_id: str, body: GradeRequest
) -> dict[str, Any]:
    """Grade diagnostic answers, update BKT state, and rebuild the profile.

    Returns the score, updated profile summary, and top weak points so the
    client can render the baseline report in one round trip.
    """
    _require_domain(domain_id)
    return grade_diagnostic(
        domain_id,
        [a.model_dump() for a in body.answers],
        diagnostic_id=body.diagnostic_id,
    )


# --------------------------------------------------------------------------- #
# Weakness / profile queries
# --------------------------------------------------------------------------- #

@router.get("/weakness/{domain_id}")
async def get_weakness(domain_id: str, limit: int = 10) -> dict[str, Any]:
    """Return the lowest-mastery knowledge points for a domain.

    Reads the current BKT state and scores every KP in the domain's graph
    (unseen KPs count as the prior). Useful for "what should I study next".
    """
    spec = _require_domain(domain_id)
    graph = spec.knowledge_graph()
    store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    states = store.get_all()

    scored: list[dict[str, Any]] = []
    for kp in graph.all_points():
        st = states.get(kp.id)
        mastery = tracer.mastery_of(st, kp.id)
        scored.append(
            {
                "knowledge_point_id": kp.id,
                "name": kp.name,
                "module_id": kp.module_id,
                "mastery": round(mastery, 4),
                "attempts": st.attempts if st else 0,
                "correct": st.correct if st else 0,
            }
        )
    scored.sort(key=lambda r: (r["mastery"], -r["attempts"]))
    return {"domain_id": domain_id, "weak_points": scored[:limit], "total": len(scored)}


@router.post("/profile/{domain_id}/rebuild")
async def rebuild_profile(domain_id: str) -> dict[str, Any]:
    """Recompute and persist the profile from current BKT state.

    Call this after any out-of-band BKT update (e.g. practice answers recorded
    directly) to refresh the profile + Memory L3 mirror.
    """
    _require_domain(domain_id)
    store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    return write_profile(domain_id, store, tracer, note="Rebuilt via API")


# --------------------------------------------------------------------------- #
# Review queue (FSRS)
# --------------------------------------------------------------------------- #

@router.get("/review/{domain_id}/queue")
async def get_review_queue(domain_id: str, limit: int = 20) -> dict[str, Any]:
    """Return the FSRS due-review queue for a domain.

    Sorted by (due_at, retrievability) — most overdue / most forgotten first.
    Each item carries KP metadata so the frontend can render a review screen.
    """
    _require_domain(domain_id)
    store = ReviewStore(domain_id)
    due = store.due(limit=limit)
    return {"domain_id": domain_id, "due_count": len(due), "items": due}


class ReviewSubmission(BaseModel):
    """One FSRS review result. ``grade`` is 1=Again 2=Hard 3=Good 4=Easy."""

    knowledge_point_id: str
    grade: int = Field(ge=1, le=4, description="1=Again, 2=Hard, 3=Good, 4=Easy")
    # Optional: also record into BKT (correctness derived from grade).
    update_bkt: bool = True


class ReviewBatch(BaseModel):
    reviews: list[ReviewSubmission]
    sync_mastery_path: bool = False


@router.post("/review/{domain_id}/submit")
async def submit_reviews(domain_id: str, body: ReviewBatch) -> dict[str, Any]:
    """Record FSRS reviews and reschedule.

    Applies each grade through the FSRS scheduler, persists the new intervals,
    optionally mirrors them into BKT state + DeepTutor's Mastery Path
    review_queue (so the upstream /learning dashboard stays in sync).
    """
    _require_domain(domain_id)
    store = ReviewStore(domain_id)

    # Apply FSRS updates.
    fsrs_states = store.get_all()
    bkt_outcomes: dict[str, bool] = {}
    for r in body.reviews:
        st = fsrs_states.get(r.knowledge_point_id)
        if st is None:
            st = store.get(r.knowledge_point_id)
            fsrs_states[r.knowledge_point_id] = st
        store.scheduler.review(st, Grade(r.grade))
        if r.update_bkt:
            # Again(1)/Hard(2) count as "incorrect" for BKT; Good/Easy as correct.
            bkt_outcomes[r.knowledge_point_id] = r.grade >= 3
    store.save()

    # Optionally also update BKT (keeps mastery in lockstep with recall).
    bkt_summary = None
    if bkt_outcomes:
        from personal_tutor.learning.kt_store import KTStore

        kt = KTStore(domain_id)
        tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
        states = kt.get_all()
        tracer.update_many(states, bkt_outcomes)
        kt.upsert_many(states.values())
        kt.save()
        bkt_summary = "updated"

    synced = False
    if body.sync_mastery_path:
        synced = store.sync_to_mastery_path()

    due = store.due(limit=20)
    return {
        "ok": True,
        "domain_id": domain_id,
        "processed": len(body.reviews),
        "bkt": bkt_summary,
        "mastery_path_synced": synced,
        "remaining_due": len(due),
    }


# --------------------------------------------------------------------------- #
# Roadmap
# --------------------------------------------------------------------------- #

class RoadmapRequest(BaseModel):
    goal: str | None = None
    max_objectives: int = Field(default=50, ge=1, le=200)


@router.post("/roadmaps/{domain_id}/generate")
async def generate_roadmap(domain_id: str, body: RoadmapRequest | None = None) -> dict[str, Any]:
    """Generate (or regenerate) a personalized roadmap from the current profile.

    Reads BKT mastery, respects the knowledge-graph topology, and front-loads
    weak points. Persists to ``roadmap_<domain>.json``.
    """
    _require_domain(domain_id)
    goal = body.goal if body else None
    max_obj = body.max_objectives if body else 50
    return plan_roadmap(domain_id, goal=goal, max_objectives=max_obj)


@router.get("/roadmaps/{domain_id}")
async def get_roadmap(domain_id: str) -> dict[str, Any]:
    """Return the stored roadmap (404 if not yet generated)."""
    _require_domain(domain_id)
    rm = load_roadmap(domain_id)
    if rm is None:
        raise HTTPException(
            status_code=404,
            detail=f"No roadmap for {domain_id!r}. POST /roadmaps/{domain_id}/generate first.",
        )
    return rm


__all__ = ["router"]
