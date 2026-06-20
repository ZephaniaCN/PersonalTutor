"""Roadmap generation algorithm.

The planner merges two signals:

* **Weakness** — KPs the learner scores low on (from BKT) jump the queue.
* **Topology** — a KP's prerequisites must appear earlier in the plan (you
  can't learn 0-1 knapsack DP before you know what DP is).

Algorithm (priority-respecting topological sort):
1. Compute an effective priority for each KP = f(mastery): lower mastery =>
   higher priority, but never above a KP whose prereqs are unmet.
2. Repeatedly pick, among KPs whose prereqs are all *either mastered or
   already scheduled*, the one with the highest priority (lowest mastery).

This guarantees a valid learning order while front-loading the learner's
weaknesses — exactly what a human tutor would recommend.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from personal_tutor.domains import get_registry
from personal_tutor.domains.base import KnowledgeGraph
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.learning.kt_store import KTStore
from personal_tutor.storage import json_store
from personal_tutor.storage.paths import personal_root

#: Mastery above which a KP is considered "already acquired" and skipped in
#: the active plan (it may still appear as a satisfied prerequisite).
ACQUIRED_THRESHOLD = 0.7


@dataclass
class Objective:
    """One step in a roadmap."""

    order: int
    knowledge_point_id: str
    name: str
    module_id: str
    mastery: float
    rationale: str  # why this KP is here at this position
    prerequisites: list[str] = field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _roadmap_path(domain_id: str):
    return personal_root() / f"roadmap_{domain_id}.json"


def plan_roadmap(
    domain_id: str,
    *,
    goal: str | None = None,
    max_objectives: int = 50,
) -> dict[str, Any]:
    """Build a personalized roadmap for *domain_id*.

    Reads the current BKT mastery (empty profile => starts from scratch) and
    the domain knowledge graph, then produces an ordered objective list. The
    result is persisted to ``roadmap_<domain>.json``.
    """
    spec = get_registry().require(domain_id)
    graph = spec.knowledge_graph()
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    store = KTStore(domain_id)
    states = store.get_all()

    mastery: dict[str, float] = {
        kp_id: tracer.mastery_of(states.get(kp_id), kp_id) for kp_id in graph.points
    }

    objectives = _priority_topo_sort(graph, mastery)
    # Cap and number the active objectives.
    active = [o for o in objectives if mastery.get(o.knowledge_point_id, 0.0) < ACQUIRED_THRESHOLD]
    skipped = [o for o in objectives if o not in active]
    active = active[:max_objectives]
    for i, obj in enumerate(active, 1):
        obj.order = i

    roadmap = {
        "domain_id": domain_id,
        "domain_name": spec.name,
        "goal": goal or f"系统掌握「{spec.name}」全部核心知识点",
        "version": 1,
        "generated_at": _now(),
        "summary": {
            "total_knowledge_points": len(graph.points),
            "acquired": len(skipped),
            "remaining": len(active),
            "average_mastery": round(sum(mastery.values()) / len(mastery), 4) if mastery else 0.0,
        },
        "objectives": [o.__dict__ for o in active],
        "acquired": [
            {
                "knowledge_point_id": o.knowledge_point_id,
                "name": o.name,
                "mastery": round(o.mastery, 4),
            }
            for o in skipped
        ],
    }
    json_store.write_json(_roadmap_path(domain_id), roadmap)
    return roadmap


def _priority_topo_sort(graph: KnowledgeGraph, mastery: dict[str, float]) -> list[Objective]:
    """Topological sort that breaks ties by lowest mastery first.

    A KP becomes schedulable only once all its prerequisites are *either*
    already mastered (mastery >= ACQUIRED_THRESHOLD) or already placed in the
    plan. Among schedulable KPs we always pick the weakest — closing gaps
    before piling on new material.
    """
    scheduled: set[str] = set()
    result: list[Objective] = []

    def is_mastered(kp_id: str) -> bool:
        return mastery.get(kp_id, 0.0) >= ACQUIRED_THRESHOLD

    def prereqs_satisfied(kp_id: str) -> bool:
        return all(
            is_mastered(pre) or pre in scheduled
            for pre in graph.prerequisites_of(kp_id)
        )

    remaining = set(graph.points)
    order_counter = 0

    while remaining:
        # Candidates: schedulable (prereqs ok) and not yet placed.
        candidates = [kp_id for kp_id in remaining if prereqs_satisfied(kp_id)]
        if not candidates:
            # Cycle / unsatisfiable prereqs: place remaining in raw topo order
            # so we never deadlock. (graph.topological_order raises on real
            # cycles; we already validated the graph is a DAG at load time.)
            candidates = list(remaining)

        # Pick the weakest (lowest mastery); ties broken by KP id for stability.
        candidates.sort(key=lambda k: (mastery.get(k, 0.0), k))
        chosen = candidates[0]
        remaining.discard(chosen)
        scheduled.add(chosen)

        kp = graph.get(chosen)
        pres = graph.prerequisites_of(chosen)
        # Rationale explains *why now* — useful for the learner & for LLM narration.
        weak = mastery.get(chosen, 0.0) < 0.5
        if weak:
            rationale = "薄弱知识点,优先攻克"
        elif not pres:
            rationale = "无前置依赖的基础知识点"
        elif all(is_mastered(p) for p in pres):
            rationale = "前置知识点已掌握,可以学习"
        else:
            rationale = "前置知识点已在计划中,顺序学习"
        order_counter += 1
        result.append(
            Objective(
                order=order_counter,
                knowledge_point_id=chosen,
                name=kp.name if kp else chosen,
                module_id=kp.module_id if kp else "",
                mastery=mastery.get(chosen, 0.0),
                rationale=rationale,
                prerequisites=list(pres),
            )
        )
    return result


def load_roadmap(domain_id: str) -> dict[str, Any] | None:
    """Return the stored roadmap, or None if not yet generated."""
    return json_store.read_json(_roadmap_path(domain_id), default=None)


__all__ = ["Objective", "plan_roadmap", "load_roadmap", "ACQUIRED_THRESHOLD"]
