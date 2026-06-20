"""Unit tests for the BKT knowledge-tracing engine.

Pure-math tests — no DeepTutor, no I/O. These pin the Bayesian update
behavior so a future refactor of the engine can't silently change the
pedagogy.
"""

from __future__ import annotations

import pytest

from personal_tutor.learning.knowledge_tracing import (
    DEFAULT_KT_PARAMS,
    KTParams,
    KTState,
    KnowledgeTracer,
    log_likelihood,
)


# --------------------------------------------------------------------------- #
# Parameter validation
# --------------------------------------------------------------------------- #

def test_kt_params_rejects_out_of_range():
    with pytest.raises(ValueError, match="out of range"):
        KTParams(p_known=1.5)
    with pytest.raises(ValueError, match="out of range"):
        KTParams(p_slip=0.0)  # clamped away from 0


def test_kt_params_rejects_guess_plus_slip_ge_one():
    """guess + slip >= 1 makes the model non-identifiable — must reject."""
    with pytest.raises(ValueError, match="p_guess.*p_slip"):
        KTParams(p_guess=0.6, p_slip=0.5)


def test_default_params_are_valid():
    p = DEFAULT_KT_PARAMS
    assert 0 < p.p_known < 1
    assert p.p_guess + p.p_slip < 1


# --------------------------------------------------------------------------- #
# Bayesian update behavior
# --------------------------------------------------------------------------- #

def test_correct_answer_raises_mastery():
    tracer = KnowledgeTracer()
    st = KTState(knowledge_point_id="x")
    prior = st.p_known
    tracer.update(st, True)
    assert st.p_known > prior
    assert st.attempts == 1
    assert st.correct == 1


def test_wrong_answer_lowers_mastery():
    tracer = KnowledgeTracer()
    st = KTState(knowledge_point_id="x")
    prior = st.p_known
    tracer.update(st, False)
    assert st.p_known < prior
    assert st.correct == 0


def test_mastery_converges_high_with_streak_of_correct():
    """Many correct answers should drive P(known) near 1 (within clamp)."""
    tracer = KnowledgeTracer()
    st = KTState(knowledge_point_id="x")
    for _ in range(10):
        tracer.update(st, True)
    assert st.p_known > 0.95


def test_mastery_converges_low_with_streak_of_wrong():
    """Many wrong answers drive P(known) toward the transit floor.

    Note: BKT can't reach 0 — the transit parameter means a learner may have
    *learned* from a wrong attempt, so the floor is ~p_transit/(1+p_transit).
    With default transit=0.1 that's ~0.09; we assert it gets well below the
    prior (0.5) and close to the floor.
    """
    tracer = KnowledgeTracer()
    st = KTState(knowledge_point_id="x")
    for _ in range(10):
        tracer.update(st, False)
    assert st.p_known < 0.15


def test_update_is_markovian_in_p_known():
    """The next posterior depends only on current p_known + observation,
    not on history. Two states with equal p_known AND equal attempts==0
    (so both use the prior) update identically."""
    tracer = KnowledgeTracer()
    a = KTState(knowledge_point_id="a", p_known=0.6, attempts=0)
    b = KTState(knowledge_point_id="b", p_known=0.6, attempts=0)
    tracer.update(a, True)
    tracer.update(b, True)
    assert abs(a.p_known - b.p_known) < 1e-9


def test_update_many_applies_all_outcomes():
    tracer = KnowledgeTracer()
    states = {
        "a": KTState(knowledge_point_id="a"),
        "b": KTState(knowledge_point_id="b"),
    }
    out = tracer.update_many(states, {"a": True, "b": False})
    assert out["a"].p_known > 0.5
    assert out["b"].p_known < 0.5


def test_weakest_returns_lowest_mastery_first():
    tracer = KnowledgeTracer()
    states = {
        "strong": KTState(knowledge_point_id="strong", p_known=0.9),
        "weak": KTState(knowledge_point_id="weak", p_known=0.2),
        "mid": KTState(knowledge_point_id="mid", p_known=0.5),
    }
    weakest = tracer.weakest(states, limit=2)
    assert weakest[0][0] == "weak"
    assert weakest[1][0] == "mid"


def test_weakest_includes_unseen_as_prior():
    tracer = KnowledgeTracer()
    states = {"seen": KTState(knowledge_point_id="seen", p_known=0.9)}
    weakest = tracer.weakest(states, all_kp_ids=iter(["seen", "unseen"]), limit=5)
    ids = [kp_id for kp_id, _ in weakest]
    assert "unseen" in ids
    # unseen should be scored at the prior (0.5), lower than the seen 0.9
    unseen_score = next(s for k, s in weakest if k == "unseen")
    assert abs(unseen_score - 0.5) < 1e-9


# --------------------------------------------------------------------------- #
# Serialization round-trip
# --------------------------------------------------------------------------- #

def test_state_roundtrip():
    st = KTState(knowledge_point_id="x", p_known=0.77, attempts=4, correct=3)
    st.history = [True, False, True, True]
    st.last_updated = "2026-01-01T00:00:00+00:00"
    rebuilt = KTState.from_dict(st.to_dict())
    assert rebuilt.knowledge_point_id == "x"
    assert rebuilt.p_known == 0.77
    assert rebuilt.attempts == 4
    assert rebuilt.correct == 3
    assert rebuilt.history == [True, False, True, True]


# --------------------------------------------------------------------------- #
# Log-likelihood (model sanity)
# --------------------------------------------------------------------------- #

def test_log_likelihood_positive_for_consistent_sequence():
    """A fully-correct sequence should be more likely under low-slip params
    than under high-slip params."""
    seq = [True, True, True, True]
    ll_good = log_likelihood(KTParams(p_slip=0.05, p_guess=0.25), seq)
    ll_bad = log_likelihood(KTParams(p_slip=0.4, p_guess=0.25), seq)
    assert ll_good > ll_bad
