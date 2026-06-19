"""PersonalTutor REST router.

Phase-0 scope: enough surface area to drive the Next.js frontend (domains,
knowledge graph, profile read/write, diagnostic start) without depending on
the not-yet-built BKT engine or FSRS scheduler. Each endpoint is a thin facade
over :mod:`personal_tutor.domains` and :mod:`personal_tutor.storage` so the
real logic stays testable without HTTP.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from personal_tutor import __version__ as pt_version
from personal_tutor import MIN_DEEPTUTOR_VERSION
from personal_tutor.domains import get_registry
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

    Phase 0 returns the blueprint and the sampled knowledge-point plan (which
    KPs will be tested). Actual question generation + grading lands with the
    diagnostic capability in phase 2; this endpoint gives the frontend
    something to render a "diagnostic setup" screen immediately.
    """
    spec = _require_domain(domain_id)
    bp = spec.diagnostic_blueprint()
    graph = spec.knowledge_graph()

    # Sample: take the must-include KPs plus ``questions_per_module`` per module.
    plan: list[dict[str, Any]] = []
    for must in bp.must_include:
        kp = graph.get(must)
        if kp:
            plan.append({"knowledge_point_id": kp.id, "name": kp.name})
    for module_id in graph.module_order:
        kps = [graph.get(k) for k in graph.modules.get(module_id, []) if graph.get(k)]
        for kp in kps[: bp.questions_per_module]:
            if kp and all(p["knowledge_point_id"] != kp.id for p in plan):
                plan.append({"knowledge_point_id": kp.id, "name": kp.name})

    result = {
        "domain_id": domain_id,
        "blueprint": {
            "questions_per_module": bp.questions_per_module,
            "default_difficulty": bp.default_difficulty.value,
            "must_include": list(bp.must_include),
        },
        "question_plan": plan,
        "total_questions": len(plan),
    }
    json_store.write_json(diagnostic_path(domain_id), result)
    return result


__all__ = ["router"]
