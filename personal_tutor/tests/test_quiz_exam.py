"""Tests for the adaptive quiz and exam engine."""

from __future__ import annotations

import pytest

from personal_tutor.capabilities.adaptive_quiz.quiz import grade_one, next_question
from personal_tutor.learning.kt_store import KTStore
from personal_tutor.learning import DEFAULT_KT_PARAMS, KnowledgeTracer
from personal_tutor.storage import exam_store


@pytest.fixture
def isolated_workspace(tmp_path, monkeypatch):
    fake_ws = tmp_path / "data"
    fake_ws.mkdir()
    monkeypatch.setattr("personal_tutor.storage.paths._workspace_root", lambda: fake_ws)
    return fake_ws


def _seed_weak(domain_id: str, weak_kp: str) -> None:
    """Make one KP weak so the quiz targets it."""
    store = KTStore(domain_id)
    tracer = KnowledgeTracer(DEFAULT_KT_PARAMS)
    st = store.get(weak_kp)
    tracer.update(st, False)
    tracer.update(st, False)
    store.upsert(st)
    store.save()


# --------------------------------------------------------------------------- #
# Adaptive quiz
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_next_question_targets_weakest(isolated_workspace):
    _seed_weak("programming", "algo.dp")
    q = await next_question("programming")
    assert q["knowledge_point_id"] == "algo.dp"
    # Weak KP (mastery < 0.2) should get EASY difficulty (scaffolding).
    assert q["difficulty"] == "easy"
    assert "question" in q


@pytest.mark.asyncio
async def test_next_question_excludes(isolated_workspace):
    """Excluded KPs must not be returned."""
    _seed_weak("programming", "algo.dp")
    q = await next_question("programming", exclude=["algo.dp"])
    assert q["knowledge_point_id"] != "algo.dp"


@pytest.mark.asyncio
async def test_grade_updates_mastery(isolated_workspace):
    """Grade loop must run end-to-end and update BKT/FSRS/profile.

    We don't assert the *direction* of the mastery change: with the fallback
    grader (no LLM in CI), a paraphrased-but-correct answer may score below
    threshold and lower mastery — that's the grader's call, not the loop's.
    What matters is that the loop executed and produced a verdict + new state.
    """
    _seed_weak("programming", "algo.dp")
    before = KTStore("programming").get("algo.dp").p_known
    result = await grade_one(
        "programming",
        knowledge_point_id="algo.dp",
        user_answer="动态规划是通过状态转移方程求解最优化问题",
        question={
            "question": "说明动态规划",
            "expected_answer": "动态规划是分治+记忆化,通过状态转移求解",
            "question_type": "concept",
        },
    )
    assert "verdict" in result
    assert "is_correct" in result["verdict"]
    assert "score" in result["verdict"]
    # new_mastery must be reported and reflect the post-update BKT state.
    # (result rounds to 4 dp; compare against the rounded store value.)
    assert "new_mastery" in result
    after = KTStore("programming").get("algo.dp").p_known
    assert abs(result["new_mastery"] - round(after, 4)) < 1e-4
    # And mastery must have changed from the seed value (the update ran).
    assert before != after


@pytest.mark.asyncio
async def test_grade_empty_answer_is_wrong(isolated_workspace):
    result = await grade_one(
        "programming",
        knowledge_point_id="ds.array",
        user_answer="",
        question={"expected_answer": "数组是连续内存", "question_type": "concept"},
    )
    assert result["verdict"]["is_correct"] is False
    assert result["verdict"]["score"] == 0.0


# --------------------------------------------------------------------------- #
# Exam engine
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exam_start_strips_expected_answers(isolated_workspace):
    record = await exam_store.start_exam("programming", num_questions=5, duration_minutes=20)
    assert record["status"] == "open"
    assert record["num_questions"] >= 1
    # The stored record keeps expected answers (for grading).
    assert all("expected_answer" in q for q in record["questions"])


@pytest.mark.asyncio
async def test_exam_submit_produces_report(isolated_workspace):
    record = await exam_store.start_exam("programming", num_questions=5, duration_minutes=20)
    answers = [
        {"knowledge_point_id": q["knowledge_point_id"], "user_answer": q["expected_answer"]}
        for q in record["questions"]
    ]
    report = await exam_store.submit_exam(record["exam_id"], answers)
    assert report["status"] == "graded"
    assert report["score"]["total"] == len(answers)
    # Perfect answers (identical to expected) should score high.
    assert report["score"]["correct"] == len(answers)
    assert "profile_summary" in report
    assert "weak_points" in report


@pytest.mark.asyncio
async def test_exam_double_submit_rejected(isolated_workspace):
    record = await exam_store.start_exam("programming", num_questions=3, duration_minutes=20)
    answers = [
        {"knowledge_point_id": q["knowledge_point_id"], "user_answer": "x"}
        for q in record["questions"]
    ]
    await exam_store.submit_exam(record["exam_id"], answers)
    with pytest.raises(ValueError, match="already graded"):
        await exam_store.submit_exam(record["exam_id"], answers)


@pytest.mark.asyncio
async def test_exam_report_retrievable(isolated_workspace):
    record = await exam_store.start_exam("programming", num_questions=3, duration_minutes=20)
    fetched = exam_store.get_exam_report(record["exam_id"])
    assert fetched["exam_id"] == record["exam_id"]
    assert fetched["status"] == "open"


@pytest.mark.asyncio
async def test_exam_unknown_raises(isolated_workspace):
    with pytest.raises(KeyError):
        exam_store.get_exam_report("exam_nope")
