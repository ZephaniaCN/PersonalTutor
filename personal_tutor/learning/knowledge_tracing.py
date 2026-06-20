"""Bayesian Knowledge Tracing (BKT) — per-knowledge-point mastery estimation.

BKT models a learner's knowledge of each skill as a *latent* binary state
(known / not-known) and updates the probability of "known" after every
answered question using Bayes' rule. Four parameters govern the dynamics:

* ``p_known``   (init / prior)  — P(known before first attempt)
* ``p_transit`` (learn)         — P(not-known → known) after a practice step
* ``p_slip``    (slip)          — P(wrong answer | known)
* ``p_guess``   (guess)         — P(right answer | not-known)

This is the classic Corbett & Anderson (1995) model. It is the "richer model"
that DeepTutor's ``deeptutor/learning/mastery.py::compute_mastery`` docstring
explicitly invites as a drop-in replacement — except PersonalTutor keeps it
stateful (per-KP persistent state) rather than recomputing from a raw
correctness list each time, which lets it carry confidence and history forward.

Design choices
--------------
* Pure functions over a small ``KTState`` dataclass — trivially testable, no
  globals, no I/O.
* Parameters are per-KT-unit (caller can pass per-skill tuned values); a
  sensible global default is provided.
* Numerical safety: probabilities are clamped to ``[EPS, 1-EPS]`` to avoid
  0/0 in the posterior — a well-known BKT footgun.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from typing import Iterator

# Avoid 0/0 and absorbing states. Corbett & Anderson's original work and most
# BKT toolkits clamp; 1e-3 is loose enough to be numerically stable without
# distorting the posterior meaningfully.
_EPS = 1e-3


@dataclass(frozen=True)
class KTParams:
    """The four BKT parameters for one knowledge unit.

    Frozen so a params object can be shared across many updates safely and
    used as a dict key if needed. Values are clamped on construction.
    """

    p_known: float = 0.5
    p_transit: float = 0.1
    p_slip: float = 0.1
    p_guess: float = 0.25

    def __post_init__(self) -> None:
        for name, val in (
            ("p_known", self.p_known),
            ("p_transit", self.p_transit),
            ("p_slip", self.p_slip),
            ("p_guess", self.p_guess),
        ):
            if not (_EPS <= val <= 1.0 - _EPS):
                raise ValueError(
                    f"KTParams.{name}={val} out of range [{_EPS}, {1 - _EPS}]"
                )
        # guess + slip > 1 makes the model non-identifiable (a known learner
        # becomes less likely to be right than a not-known one). Reject it so
        # misconfigured domains fail loudly rather than producing nonsense.
        if self.p_guess + self.p_slip >= 1.0:
            raise ValueError(
                f"p_guess({self.p_guess}) + p_slip({self.p_slip}) >= 1.0; "
                "BKT requires p_guess + p_slip < 1"
            )


#: Conservative defaults suitable when a domain has no tuned parameters.
#: Prior is 50/50 (agnostic); transit is low (one attempt rarely fully teaches
#: a skill); slip is low (known learners usually answer right); guess is high
#: enough for 4-option multiple choice.
DEFAULT_KT_PARAMS = KTParams(p_known=0.5, p_transit=0.1, p_slip=0.1, p_guess=0.25)


@dataclass
class KTState:
    """Mutable BKT state for a single knowledge point.

    ``p_known`` is the posterior P(known | history) carried forward across
    updates; ``attempts`` and ``correct`` are kept for auditability and for
    fallback recency-based scoring. Serialize via :meth:`to_dict`.
    """

    knowledge_point_id: str
    p_known: float = DEFAULT_KT_PARAMS.p_known
    attempts: int = 0
    correct: int = 0
    # Rolling correctness list (chronological). Capped to last 50 to bound
    # memory; full history is rarely needed since BKT is Markovian in p_known.
    history: list[bool] = field(default_factory=list)
    last_updated: str = ""  # ISO timestamp; left as str to avoid datetime dep here

    @property
    def mastery(self) -> float:
        """P(known) as a 0..1 mastery score — directly comparable to DeepTutor's."""
        return self.p_known

    def record(self, is_correct: bool, *, timestamp: str = "") -> None:
        self.history.append(is_correct)
        if len(self.history) > 50:
            self.history = self.history[-50:]
        self.attempts += 1
        if is_correct:
            self.correct += 1
        if timestamp:
            self.last_updated = timestamp

    def to_dict(self) -> dict:
        return {
            "knowledge_point_id": self.knowledge_point_id,
            "p_known": round(self.p_known, 6),
            "attempts": self.attempts,
            "correct": self.correct,
            "history": self.history,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "KTState":
        return cls(
            knowledge_point_id=data["knowledge_point_id"],
            p_known=float(data.get("p_known", DEFAULT_KT_PARAMS.p_known)),
            attempts=int(data.get("attempts", 0)),
            correct=int(data.get("correct", 0)),
            history=list(data.get("history", [])),
            last_updated=str(data.get("last_updated", "")),
        )


class KnowledgeTracer:
    """Applies BKT updates to a set of knowledge points.

    The tracer is stateless across KP ids — callers own the ``KTState``
    objects (typically loaded/saved by :mod:`kt_store`). The tracer just
    applies the math. This separation makes the engine trivial to unit test
    and lets the store handle persistence/locking independently.
    """

    def __init__(self, params: KTParams = DEFAULT_KT_PARAMS) -> None:
        self.params = params

    # -- core Bayes update -------------------------------------------------

    def update(self, state: KTState, is_correct: bool, *, timestamp: str = "") -> KTState:
        """Apply one observation and return the updated state.

        Standard BKT two-step: (1) posterior update given the observation,
        (2) transition (the learner may have learned from the attempt).
        """
        p = _clamp(self.params.p_known if state.attempts == 0 else state.p_known)
        slip = self.params.p_slip
        guess = self.params.p_guess
        transit = self.params.p_transit

        # Step 1 — P(known | observation)
        if is_correct:
            # P(correct) = p_known*(1-slip) + (1-p_known)*guess
            p_correct = p * (1 - slip) + (1 - p) * guess
            posterior = (p * (1 - slip)) / p_correct
        else:
            # P(wrong) = p_known*slip + (1-p_known)*(1-guess)
            p_wrong = p * slip + (1 - p) * (1 - guess)
            posterior = (p * slip) / p_wrong

        # Step 2 — transition: even if not known, the practice step may teach it
        posterior = posterior + (1 - posterior) * transit
        posterior = _clamp(posterior)

        state.p_known = posterior
        state.record(is_correct, timestamp=timestamp)
        return state

    # -- batch + convenience ----------------------------------------------

    def update_many(
        self, states: dict[str, KTState], outcomes: dict[str, bool]
    ) -> dict[str, KTState]:
        """Apply multiple KP observations at once (e.g. a graded diagnostic)."""
        updated: dict[str, KTState] = dict(states)
        for kp_id, is_correct in outcomes.items():
            st = updated.get(kp_id)
            if st is None:
                st = KTState(knowledge_point_id=kp_id)
                updated[kp_id] = st
            self.update(st, is_correct)
        return updated

    def mastery_of(self, state: KTState | None, kp_id: str) -> float:
        """Return P(known) for a KP, or the prior if unseen."""
        if state is None:
            return self.params.p_known
        return state.p_known

    def weakest(
        self,
        states: dict[str, KTState],
        *,
        all_kp_ids: Iterator[str] | None = None,
        limit: int = 5,
    ) -> list[tuple[str, float]]:
        """Return the ``limit`` lowest-mastery KPs (unseen KPs counted as prior)."""
        scored: list[tuple[str, float]] = []
        ids = list(all_kp_ids) if all_kp_ids is not None else list(states.keys())
        for kp_id in ids:
            scored.append((kp_id, self.mastery_of(states.get(kp_id), kp_id)))
        scored.sort(key=lambda kv: kv[1])
        return scored[:limit]


def _clamp(p: float) -> float:
    """Clamp a probability into [EPS, 1-EPS] to avoid degenerate posteriors."""
    return max(_EPS, min(1.0 - _EPS, p))


def log_likelihood(
    params: KTParams, correctness: list[bool], prior: float | None = None
) -> float:
    """Log-likelihood of an observed sequence under *params*.

    Useful for parameter fitting / model comparison. Uses the forward
    algorithm over the hidden known/not-known state. Kept here next to the
    update so the math lives in one place.
    """
    p = params.p_known if prior is None else prior
    total = 0.0
    for c in correctness:
        p_obs = p * (1 - params.p_slip) + (1 - p) * params.p_guess
        p_obs_wrong = p * params.p_slip + (1 - p) * (1 - params.p_guess)
        prob = p_obs if c else p_obs_wrong
        total += math.log(_clamp(prob))
        # forward update of P(known) after this observation + transition
        posterior = (p * (1 - params.p_slip)) / p_obs if c else (p * params.p_slip) / p_obs_wrong
        p = _clamp(posterior + (1 - _clamp(posterior)) * params.p_transit)
    return total


__all__ = [
    "DEFAULT_KT_PARAMS",
    "KTParams",
    "KTState",
    "KnowledgeTracer",
    "log_likelihood",
]
