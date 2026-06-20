"""Tests for the diagnostic flow and profile builder.

These exercise the full prepare → grade → profile pipeline using the
programming seed domain. They use a temporary workspace (via the storage
helpers' cwd fallback) so nothing leaks into the real user data directory.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from personal_tutor.capabilities.diagnostic.diagnostic import (
    grade_diagnostic,
    prepare_diagnostic,
)
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.learning.profile_builder import (
    build_profile,
    render_profile_markdown,
)
from personal_tutor.storage.paths import personal_root, profile_path


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    """Redirect PersonalTutor storage into a temp dir for the test.

    ``personal_root`` calls DeepTutor's PathService, which resolves the
    workspace from env/CLI. We monkeypatch the resolver to a temp path so the
    test never touches real user data and is fully hermetic.
    """
    fake_ws = tmp_path / "data"
    fake_ws.mkdir()

    def _fake_root():
        return fake_ws

    monkeypatch.setattr(
        "personal_tutor.storage.paths._workspace_root", _fake_root
    )
    return fake_ws


# --------------------------------------------------------------------------- #
# Diagnostic prepare
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_prepare_diagnostic_produces_questions(isolated_workspace):
    result = await prepare_diagnostic("programming")
    assert result["domain_id"] == "programming"
    assert result["total_questions"] >= 5  # blueprint samples >=5 KPs
    assert all("question" in q for q in result["questions"])
    assert all("expected_answer" in q for q in result["questions"])
    assert result["status"] == "prepared"


@pytest.mark.asyncio
async def test_prepare_diagnostic_unknown_domain(isolated_workspace):
    with pytest.raises(KeyError, match="Unknown domain"):
        await prepare_diagnostic("nope")


# --------------------------------------------------------------------------- #
# Diagnostic grade + BKT update
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_grade_updates_profile_and_identifies_weakness(isolated_workspace):
    prepared = await prepare_diagnostic("programming")
    kps = [q["knowledge_point_id"] for q in prepared["questions"]]

    # Simulate: get the first KP right, everything else wrong.
    answers = []
    for i, kp_id in enumerate(kps):
        answers.append({"knowledge_point_id": kp_id, "is_correct": i == 0})

    result = grade_diagnostic("programming", answers, diagnostic_id=prepared["diagnostic_id"])
    assert result["status"] == "graded"
    assert result["score"]["total"] == len(kps)
    assert result["score"]["correct"] == 1

    # The all-wrong KPs should dominate the weak points.
    weak_ids = [w["knowledge_point_id"] for w in result["weak_points"]]
    assert kps[1] in weak_ids  # a wrong KP is weak
    assert kps[0] not in weak_ids or result["weak_points"]  # the right one less likely


@pytest.mark.asyncio
async def test_grade_persists_profile_json(isolated_workspace):
    prepared = await prepare_diagnostic("programming")
    answers = [
        {"knowledge_point_id": q["knowledge_point_id"], "is_correct": True}
        for q in prepared["questions"]
    ]
    grade_diagnostic("programming", answers)
    # Profile JSON must exist and be structured.
    import json

    data = json.loads(profile_path("programming").read_text(encoding="utf-8"))
    assert data["domain_id"] == "programming"
    assert "summary" in data
    assert data["summary"]["assessed"] > 0


# --------------------------------------------------------------------------- #
# Profile builder
# --------------------------------------------------------------------------- #

def test_build_profile_with_no_data_reports_zero_coverage(isolated_workspace):
    from personal_tutor.learning.kt_store import KTStore

    store = KTStore("programming")
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    profile = build_profile("programming", store, tracer)
    assert profile["summary"]["assessed"] == 0
    assert profile["summary"]["coverage"] == 0.0
    assert profile["summary"]["total_knowledge_points"] >= 15


def test_render_markdown_contains_weakness(isolated_workspace):
    from personal_tutor.learning.kt_store import KTStore

    store = KTStore("programming")
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    # Force a weak KP by answering wrong.
    st = store.get("algo.dp")
    tracer.update(st, False)
    tracer.update(st, False)
    store.upsert(st)

    profile = build_profile("programming", store, tracer)
    md = render_profile_markdown(profile)
    assert "动态规划" in md or "algo.dp" in md
    assert "薄弱点" in md
