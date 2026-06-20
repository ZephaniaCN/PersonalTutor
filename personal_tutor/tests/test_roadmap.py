"""Tests for the roadmap planner."""

from __future__ import annotations

import pytest

from personal_tutor.capabilities.roadmap_planner.planner import (
    ACQUIRED_THRESHOLD,
    load_roadmap,
    plan_roadmap,
)
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.learning.kt_store import KTStore


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    fake_ws = tmp_path / "data"
    fake_ws.mkdir()
    monkeypatch.setattr("personal_tutor.storage.paths._workspace_root", lambda: fake_ws)
    return fake_ws


def _seed_mastery(domain_id: str, outcomes: dict[str, list[bool]]) -> None:
    """Seed BKT mastery by replaying outcomes through the store."""
    store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    for kp_id, oks in outcomes.items():
        st = store.get(kp_id)
        for ok in oks:
            tracer.update(st, ok)
        store.upsert(st)
    store.save()


# --------------------------------------------------------------------------- #
# Empty profile
# --------------------------------------------------------------------------- #

def test_plan_from_empty_profile_includes_all(isolated_workspace):
    rm = plan_roadmap("programming")
    assert rm["summary"]["acquired"] == 0
    assert rm["summary"]["remaining"] == rm["summary"]["total_knowledge_points"]
    assert len(rm["objectives"]) == rm["summary"]["total_knowledge_points"]


def test_plan_respects_topological_order(isolated_workspace):
    """Every objective's prerequisites must appear earlier in the plan."""
    rm = plan_roadmap("programming")
    seen: set[str] = set()
    for obj in rm["objectives"]:
        for pre in obj["prerequisites"]:
            assert pre in seen, (
                f"{obj['knowledge_point_id']} scheduled before prereq {pre}"
            )
        seen.add(obj["knowledge_point_id"])


# --------------------------------------------------------------------------- #
# Weakness front-loading
# --------------------------------------------------------------------------- #

def test_weak_points_are_front_loaded(isolated_workspace):
    _seed_mastery(
        "programming",
        {
            "ds.array": [True, True],       # strong
            "ds.hashtable": [True, True],   # strong
            "analysis.big_o": [True, True], # strong
            "algo.dp": [False, False],      # very weak
        },
    )
    rm = plan_roadmap("programming")
    # algo.dp must come before the midpoint of the plan
    positions = {o["knowledge_point_id"]: o["order"] for o in rm["objectives"]}
    assert "algo.dp" in positions
    assert positions["algo.dp"] <= len(rm["objectives"]) // 2
    # and its rationale must flag it as weak
    dp_obj = next(o for o in rm["objectives"] if o["knowledge_point_id"] == "algo.dp")
    assert "薄弱" in dp_obj["rationale"]


def test_acquired_kps_are_skipped(isolated_workspace):
    _seed_mastery(
        "programming",
        {"ds.array": [True, True, True, True, True]},  # driven well above threshold
    )
    rm = plan_roadmap("programming")
    acquired_ids = {a["knowledge_point_id"] for a in rm["acquired"]}
    objective_ids = {o["knowledge_point_id"] for o in rm["objectives"]}
    # A KP that's acquired should not also be an active objective.
    # (ds.array may or may not cross ACQUIRED_THRESHOLD depending on BKT path;
    # if it did, it's in acquired and not in objectives.)
    assert not (acquired_ids & objective_ids), "acquired KP appears as objective"


# --------------------------------------------------------------------------- #
# Persistence
# --------------------------------------------------------------------------- #

def test_plan_is_persisted_and_loadable(isolated_workspace):
    rm = plan_roadmap("programming", goal="test goal")
    loaded = load_roadmap("programming")
    assert loaded is not None
    assert loaded["goal"] == "test goal"
    assert loaded["domain_id"] == rm["domain_id"]


def test_load_returns_none_when_not_generated(isolated_workspace):
    assert load_roadmap("programming") is None


def test_prereq_unmet_kp_waits(isolated_workspace):
    """A KP whose prereq is unmastered must be scheduled after that prereq."""
    _seed_mastery("programming", {"algo.dp": [True, True]})  # dp strong-ish, knapsack unseen
    rm = plan_roadmap("programming")
    positions = {o["knowledge_point_id"]: o["order"] for o in rm["objectives"]}
    # algo.dp_knapsack depends on algo.dp; dp must come first.
    if "algo.dp_knapsack" in positions and "algo.dp" in positions:
        assert positions["algo.dp"] < positions["algo.dp_knapsack"]
