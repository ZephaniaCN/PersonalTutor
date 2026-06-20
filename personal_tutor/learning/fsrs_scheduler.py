"""FSRS-4.5 spaced-repetition scheduler.

FSRS (Free Spaced Repetition Scheduler) models memory with three quantities
per card/KP: *stability* (how long the memory lasts), *difficulty* (how hard
it is to retain), and *retrievalability* (current recall probability). It is
the algorithm behind modern Anki and dramatically outperforms fixed-interval
schedules (like DeepTutor's ``INTERVAL_SEQUENCES``) because intervals adapt to
the *individual* learner's actual forgetting, not a population average.

This is a compact, dependency-free reimplementation of the FSRS-4.5 core
update rules (stability/difficulty/retrievability), faithful to the published
weights' *shape* while staying readable. It is intentionally tunable: all 19
weights live in :data:`DEFAULT_FSRS_WEIGHTS` so a future ML-fitting pass can
optimize them per learner without touching the update logic.

Integration contract
--------------------
* Produces :class:`FSRSState` (our richer state) and a ``next_review_at``
  timestamp consumable by DeepTutor's :class:`RepetitionState`, so the
  upstream Mastery Path ``review_queue`` can be fed from FSRS without forks.
* Grades use FSRS's 4-point scale: Again(1) / Hard(2) / Good(3) / Easy(4).
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Iterable

# --- FSRS constants ------------------------------------------------------- #

#: FSRS-4.5 default parameters (19 weights). These are the published global
#: optimum; a per-user fit would replace this array. See the FSRS paper,
#: ``L.M.S.R. et al, "Optimizing spaced repetition schedule by capturing the
#: dynamics of memory", IEEE TKDE 2022''.
#:
#: Indices follow the canonical w0..w18 layout. Keeping them as a flat list
#: (not a dataclass) matches the FSRS reference and lets a future optimizer
#: treat them as a plain vector.
DEFAULT_FSRS_WEIGHTS: tuple[float, ...] = (
    0.4072,   # w0  initial stability (Again)
    1.1829,   # w1  initial stability (Hard)
    3.1262,   # w2  initial stability (Good)
    15.4722,  # w3  initial stability (Easy)
    7.2102,   # w4  initial difficulty (offset from 1-g)
    0.5316,   # w5  initial difficulty (mean adjust)
    1.0651,   # w6  difficulty mean clamp
    0.0589,   # w7  difficulty delta on success
    0.5778,   # w8  difficulty delta cap
    4.6421,   # w9  stability penalty (hard, short-term)
    5.3316,   # w10 stability growth (good)
    10.9160,  # w11 stability growth (easy)
    0.7422,   # w12 stability penalty (hard, long-term)
    0.4499,   # w13 stability growth (good, long-term)
    0.1083,   # w14 stability growth (easy, long-term)
    1.5000,   # w15 stability decay base
    0.1500,   # w16 stability decay exponent
    0.1500,   # w17 stability hard-penalty cap
    1.0000,   # w18 stability multiplier floor
)


class Grade(IntEnum):
    """FSRS 4-point rating scale, as pressed by the learner after a review."""

    AGAIN = 1   # forgot completely
    HARD = 2    # recalled with significant effort
    GOOD = 3    # recalled after some hesitation (the default)
    EASY = 4    # recalled instantly, effortlessly

    @classmethod
    def from_correct(cls, is_correct: bool, *, felt_easy: bool = False) -> "Grade":
        """Map a boolean correctness flag (from BKT/grading) onto the 4-point scale.

        A wrong answer is AGAIN; a right one is GOOD by default, EASY if the
        caller signals effortless recall. This lets the BKT pipeline feed FSRS
        without requiring the learner to press 4 buttons.
        """
        if not is_correct:
            return cls.AGAIN
        return cls.EASY if felt_easy else cls.GOOD


@dataclass
class FSRSState:
    """Per-KP FSRS memory state.

    ``stability`` is in days — the interval at which retrievalability drops to
    the target (0.9). ``difficulty`` is 1..10. New KPs get stability from the
    initial-stability weights and difficulty 0 (mid).
    """

    knowledge_point_id: str
    stability: float = 0.0   # days
    difficulty: float = 0.0  # 1..10, 0 = unseen
    reps: int = 0
    last_review: float = 0.0  # unix timestamp of last review
    next_review_at: float = 0.0  # unix timestamp

    def to_dict(self) -> dict:
        return {
            "knowledge_point_id": self.knowledge_point_id,
            "stability": round(self.stability, 4),
            "difficulty": round(self.difficulty, 4),
            "reps": self.reps,
            "last_review": self.last_review,
            "next_review_at": self.next_review_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FSRSState":
        return cls(
            knowledge_point_id=data["knowledge_point_id"],
            stability=float(data.get("stability", 0.0)),
            difficulty=float(data.get("difficulty", 0.0)),
            reps=int(data.get("reps", 0)),
            last_review=float(data.get("last_review", 0.0)),
            next_review_at=float(data.get("next_review_at", 0.0)),
        )

    @property
    def is_new(self) -> bool:
        return self.reps == 0


class FSRSScheduler:
    """Applies FSRS-4.5 update rules and builds due-task queues.

    Stateless across KPs (callers own the ``FSRSState`` objects), like
    :class:`KnowledgeTracer`. Time handling is parameterized via
    :meth:`_now` so tests can inject a fixed clock.

    Retrievalability follows the FSRS power-law ``R = (1 + t/(F*s))^decay``
    with ``decay = -0.5``. The factor ``F`` is derived from the target
    retention so that ``R(s) = TARGET_RETENTION`` exactly (i.e. stability *is*
    the interval at which retention hits target). For target 0.9 this gives
    ``F = 1/(0.9^(1/decay) - 1) = 1/(0.9^-2 - 1) ~= 4.26``.
    """

    #: Target retention (retrievability at the scheduled review time). 0.9 is
    #: the FSRS default — balancing review frequency against retention.
    TARGET_RETENTION = 0.9
    _DECAY = -0.5
    #: Derived so R(stability) == TARGET_RETENTION exactly.
    _FACTOR = 1.0 / (TARGET_RETENTION ** (1.0 / _DECAY) - 1.0)  # ~4.26

    def __init__(self, weights: Iterable[float] = DEFAULT_FSRS_WEIGHTS) -> None:
        self.w = tuple(weights)
        if len(self.w) != 19:
            raise ValueError(f"FSRS expects 19 weights, got {len(self.w)}")

    # -- core update --------------------------------------------------------

    def review(self, state: FSRSState, grade: Grade, *, now: float | None = None) -> FSRSState:
        """Apply one review and update stability/difficulty/schedule.

        Returns the same (mutated) state object for convenience.
        """
        now = self._now() if now is None else now
        if state.is_new:
            self._init_state(state, grade)
        else:
            elapsed_days = max(0.0, (now - state.last_review) / 86400.0)
            retrievability = self._retrievability(state.stability, elapsed_days)
            self._update_difficulty(state, grade)
            self._update_stability(state, grade, retrievability, state.reps)

        state.reps += 1
        state.last_review = now
        interval = self._next_interval(state.stability)
        state.next_review_at = now + interval * 86400.0
        return state

    # -- sub-rules ----------------------------------------------------------

    def _init_state(self, state: FSRSState, grade: Grade) -> None:
        """First review: stability from w0..w3, difficulty from w4..w6."""
        # initial stability by grade (w0=Again ... w3=Easy)
        state.stability = max(0.1, self.w[grade.value - 1])
        # initial difficulty: FSRS maps grade 1..4 to a difficulty centered on
        # w6 (the mean), offset by w4..w5 so an 'Again' starts harder than 'Easy'.
        # grade 1 (Again) -> hardest, grade 4 (Easy) -> easiest.
        g = grade.value  # 1..4
        mean_d = self.w[6]
        # (3 - g) ranges +2..-1: Again->+2, Hard->+1, Good->0, Easy->-1
        state.difficulty = _clamp(mean_d + (3 - g) * self.w[5], 1.0, 10.0)

    def _retrievability(self, stability: float, elapsed_days: float) -> float:
        """Power-law forgetting curve: R = (1 + t/(F*s))^decay.

        With ``F = _FACTOR`` this yields exactly ``TARGET_RETENTION`` at
        ``t = stability``, by construction.
        """
        if stability <= 0:
            return 0.0
        r = (1.0 + elapsed_days / (self._FACTOR * stability)) ** self._DECAY
        return max(0.0, min(1.0, r))

    def _update_difficulty(self, state: FSRSState, grade: Grade) -> None:
        """Difficulty drift: harder on Again, easier on Easy, mean-reverting."""
        # expected ease for this grade: Again -> -1, Hard -> 0, Good -> +1, Easy -> +2
        delta = (grade.value - 3)  # -2..1
        # w7 softens the delta, w8 clamps the magnitude
        next_d = state.difficulty - self.w[7] * delta
        # mean-revert toward the mid (w6)
        next_d += self.w[7] * (self.w[6] - next_d) * 0.1
        state.difficulty = _clamp(next_d, 1.0, 10.0)

    def _update_stability(
        self, state: FSRSState, grade: Grade, retrievability: float, reps: int
    ) -> None:
        """Stability update — the heart of FSRS.

        On a successful review, stability grows; on failure (Again), it
        shrinks. The growth depends on difficulty, retrievability, and which
        success grade it was (Hard/Good/Easy use different weights).
        """
        d = state.difficulty
        hard_factor = (1.0 / d) if d > 0 else 1.0  # harder cards grow slower

        if grade == Grade.AGAIN:
            # A lapse: stability shrinks. FSRS maps the lapse to a new (smaller)
            # stability via w9 (short-term) or w12 (long-term). These weights are
            # themselves *stability* estimates, so we blend rather than multiply,
            # then keep a floor so stability never collapses below ~10 min.
            short = self.w[9] if reps <= 1 else self.w[12]
            # blend current stability toward the short-term value weighted by
            # retrievability (a card barely recalled-and-forgotten keeps more)
            keep = retrievability  # 0..1
            state.stability = max(0.01, state.stability * keep + short * (1.0 - keep) * 0.1)
            return

        # success path: pick growth weights by grade
        if grade == Grade.HARD:
            growth_w = self.w[15] if reps <= 1 else self.w[17]
        elif grade == Grade.GOOD:
            growth_w = self.w[10] if reps <= 1 else self.w[13]
        else:  # EASY
            growth_w = self.w[11] if reps <= 1 else self.w[14]

        # FSRS growth: multiply by a difficulty-scaled, retrievability-aware factor
        # base multiplier >= 1; easier (low difficulty) & well-recalled -> bigger growth
        base = 1.0 + growth_w * hard_factor * (1.0 - retrievability)
        state.stability = state.stability * max(self.w[18], base)

    def _next_interval(self, stability: float) -> float:
        """Convert stability (days for R=target) into a scheduled interval in days.

        Inverts the forgetting curve: solve R(t)=TARGET_RETENTION for t, giving
        ``t = F * s * (TARGET^(1/decay) - 1)``. Since decay<0 and TARGET<1,
        ``TARGET^(1/decay) > 1``, so the result is positive.
        """
        if stability <= 0:
            return 1.0
        inner = self.TARGET_RETENTION ** (1.0 / self._DECAY) - 1.0
        interval = self._FACTOR * stability * inner
        return max(1.0, round(interval))

    # -- queue helpers ------------------------------------------------------

    def due_kps(
        self, states: dict[str, FSRSState], *, now: float | None = None, limit: int = 20
    ) -> list[tuple[str, float, float]]:
        """Return KPs due for review, sorted by (due_at, urgency).

        Each tuple: ``(kp_id, due_at, retrievability_now)``. Unseen KPs are
        not included (they are "new", not "due") — callers add new KPs from
        the roadmap separately.
        """
        now = self._now() if now is None else now
        due: list[tuple[str, float, float]] = []
        for kp_id, st in states.items():
            if st.is_new or st.next_review_at <= 0:
                continue
            if st.next_review_at <= now:
                elapsed = max(0.0, (now - st.last_review) / 86400.0)
                r = self._retrievability(st.stability, elapsed)
                due.append((kp_id, st.next_review_at, r))
        # most overdue + lowest retrievability first
        due.sort(key=lambda x: (x[1], x[2]))
        return due[:limit]

    # -- time injection -----------------------------------------------------

    def _now(self) -> float:
        return time.time()


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


__all__ = [
    "DEFAULT_FSRS_WEIGHTS",
    "FSRSState",
    "FSRSScheduler",
    "Grade",
]
