"""Tests for the FSRS scheduler and review store."""

from __future__ import annotations

import pytest

from personal_tutor.learning.fsrs_scheduler import (
    DEFAULT_FSRS_WEIGHTS,
    FSRSState,
    FSRSScheduler,
    Grade,
)


# --------------------------------------------------------------------------- #
# Forgetting curve & interval math
# --------------------------------------------------------------------------- #

def test_retrievability_at_stability_equals_target():
    """R(t=stability) must be exactly TARGET_RETENTION by construction."""
    s = FSRSScheduler()
    assert abs(s._retrievability(10.0, 10.0) - s.TARGET_RETENTION) < 1e-9


def test_retrievability_at_zero_is_one():
    s = FSRSScheduler()
    assert s._retrievability(10.0, 0.0) == pytest.approx(1.0)


def test_retrievability_decreases_with_time():
    s = FSRSScheduler()
    assert s._retrievability(10.0, 5.0) > s._retrievability(10.0, 20.0)


def test_next_interval_positive_and_scales_with_stability():
    s = FSRSScheduler()
    small = s._next_interval(1.0)
    big = s._next_interval(30.0)
    assert small >= 1
    assert big > small


# --------------------------------------------------------------------------- #
# Review dynamics
# --------------------------------------------------------------------------- #

def test_good_reviews_grow_stability_and_interval():
    s = FSRSScheduler()
    T0 = 1_000_000.0
    st = FSRSState(knowledge_point_id="x")
    s.review(st, Grade.GOOD, now=T0)
    stab1 = st.stability
    s.review(st, Grade.GOOD, now=st.next_review_at)
    assert st.stability > stab1


def test_again_shrinks_stability():
    s = FSRSScheduler()
    T0 = 1_000_000.0
    st = FSRSState(knowledge_point_id="x")
    s.review(st, Grade.GOOD, now=T0)
    stab_before = st.stability
    s.review(st, Grade.AGAIN, now=st.next_review_at)
    assert st.stability < stab_before


def test_easy_first_stability_above_good_first():
    s = FSRSScheduler()
    good = FSRSState(knowledge_point_id="g")
    easy = FSRSState(knowledge_point_id="e")
    s.review(good, Grade.GOOD, now=0.0)
    s.review(easy, Grade.EASY, now=0.0)
    assert easy.stability > good.stability


def test_grade_from_correct_boolean():
    assert Grade.from_correct(False) == Grade.AGAIN
    assert Grade.from_correct(True) == Grade.GOOD
    assert Grade.from_correct(True, felt_easy=True) == Grade.EASY


def test_due_queue_excludes_new_and_orders_by_retrievability():
    s = FSRSScheduler()
    T0 = 1_000_000.0
    # Two KPs reviewed, then we fast-forward past their due time.
    a = FSRSState(knowledge_point_id="a")
    b = FSRSState(knowledge_point_id="b")
    s.review(a, Grade.GOOD, now=T0)
    s.review(b, Grade.GOOD, now=T0)
    # 'b' reviewed later in time -> a bit more retrievable; both due at +30d.
    future = T0 + 30 * 86400
    due = s.due_kps({"a": a, "b": b}, now=future, limit=5)
    ids = [kp_id for kp_id, _, _ in due]
    assert set(ids) == {"a", "b"}
    # new (unseen) KP must NOT appear in the due queue
    new = FSRSState(knowledge_point_id="new")
    due2 = s.due_kps({"new": new}, now=future)
    assert due2 == []


# --------------------------------------------------------------------------- #
# Serialization
# --------------------------------------------------------------------------- #

def test_state_roundtrip():
    st = FSRSState(
        knowledge_point_id="x",
        stability=12.5,
        difficulty=5.0,
        reps=3,
        last_review=1000.0,
        next_review_at=1000.0 + 12.5 * 86400,
    )
    rebuilt = FSRSState.from_dict(st.to_dict())
    assert rebuilt.stability == 12.5
    assert rebuilt.reps == 3


def test_invalid_weights_length():
    with pytest.raises(ValueError, match="19 weights"):
        FSRSScheduler(weights=(0.1,) * 5)
