"""Persistence + Mastery-Path sync for FSRS review state.

Mirrors :mod:`kt_store` in shape: JSON-backed, workspace-scoped, atomic writes.
On top of plain persistence it adds :meth:`sync_to_mastery_path`, which writes
FSRS-derived ``next_review_at`` timestamps back into DeepTutor's
:class:`LearningProgress.review_queue` so the upstream Mastery Path dashboard
shows the *same* schedule PersonalTutor computes — without forking upstream.

If a LearningProgress file for the domain exists (created by a DeepTutor
mastery_path session), we update its review_queue in place; otherwise we just
keep the FSRS state file for our own review endpoint. Either way PersonalTutor's
review queue is authoritative and self-sufficient.
"""

from __future__ import annotations

import logging
from typing import Any

from personal_tutor.learning.fsrs_scheduler import DEFAULT_FSRS_WEIGHTS, FSRSState, FSRSScheduler
from personal_tutor.storage import json_store
from personal_tutor.storage.paths import personal_root

log = logging.getLogger(__name__)
_VERSION = 1


def _review_path(domain_id: str):
    return personal_root() / f"fsrs_{domain_id}.json"


class ReviewStore:
    """JSON-backed FSRS state store for one domain.

    Same lazy-cache + atomic-save discipline as :class:`KTStore`.
    """

    def __init__(self, domain_id: str) -> None:
        self.domain_id = domain_id
        self.scheduler = FSRSScheduler(DEFAULT_FSRS_WEIGHTS)
        self._cache: dict[str, FSRSState] | None = None

    def load(self) -> dict[str, FSRSState]:
        if self._cache is not None:
            return self._cache
        data = json_store.read_json(_review_path(self.domain_id), default=None)
        states: dict[str, FSRSState] = {}
        if isinstance(data, dict):
            for raw in (data.get("states") or {}).values():
                st = FSRSState.from_dict(raw)
                states[st.knowledge_point_id] = st
        self._cache = states
        return states

    def save(self) -> None:
        if self._cache is None:
            return
        payload = {
            "domain_id": self.domain_id,
            "version": _VERSION,
            "states": {kp_id: st.to_dict() for kp_id, st in self._cache.items()},
        }
        json_store.write_json(_review_path(self.domain_id), payload)

    # -- access ------------------------------------------------------------

    def get(self, kp_id: str) -> FSRSState:
        states = self.load()
        st = states.get(kp_id)
        if st is None:
            st = FSRSState(knowledge_point_id=kp_id)
            states[kp_id] = st
        return st

    def get_all(self) -> dict[str, FSRSState]:
        return self.load()

    def upsert(self, state: FSRSState) -> None:
        self.load()[state.knowledge_point_id] = state

    def upsert_many(self, states: dict[str, FSRSState]) -> None:
        cache = self.load()
        cache.update(states)

    # -- due queue ---------------------------------------------------------

    def due(self, *, now: float | None = None, limit: int = 20) -> list[dict[str, Any]]:
        """Return due review items enriched with KP metadata for display."""
        from personal_tutor.domains import get_registry

        states = self.get_all()
        due = self.scheduler.due_kps(states, now=now, limit=limit)
        # Also include new (unseen) KPs from the roadmap that are ready to learn.
        try:
            graph = get_registry().require(self.domain_id).knowledge_graph()
            meta = {kp.id: kp for kp in graph.all_points()}
        except Exception:
            meta = {}

        out: list[dict[str, Any]] = []
        for kp_id, due_at, retrievability in due:
            kp = meta.get(kp_id)
            out.append(
                {
                    "knowledge_point_id": kp_id,
                    "name": kp.name if kp else kp_id,
                    "module_id": kp.module_id if kp else "",
                    "due_at": due_at,
                    "retrievability": round(retrievability, 4),
                    "kind": "review",
                }
            )
        return out

    # -- Mastery Path sync -------------------------------------------------

    def sync_to_mastery_path(self, book_id: str | None = None) -> bool:
        """Best-effort sync of FSRS intervals into DeepTutor's review_queue.

        Looks for a ``learning/<book_id>.json`` LearningProgress file under the
        workspace and updates each KP's ``RepetitionState.next_review_at`` from
        the corresponding FSRS state. Returns True if a file was updated.

        This keeps the upstream ``/learning`` dashboard consistent with
        PersonalTutor's schedule. Failures (no progress file, parse errors)
        are logged and swallowed — PersonalTutor's own review endpoint is the
        source of truth either way.
        """
        try:
            from personal_tutor.storage.paths import _workspace_root

            learn_dir = _workspace_root() / "workspace" / "learning"
            if not learn_dir.exists():
                return False
            states = self.get_all()
            updated_any = False
            for progress_file in learn_dir.glob("*.json"):
                progress = json_store.read_json(progress_file, default=None)
                if not isinstance(progress, dict):
                    continue
                if book_id and progress.get("book_id") != book_id:
                    continue
                changed = _patch_review_queue(progress, states)
                if changed:
                    json_store.write_json(progress_file, progress)
                    updated_any = True
                    log.info("Synced FSRS review times into %s", progress_file.name)
            return updated_any
        except Exception:
            log.debug("Mastery Path sync skipped", exc_info=True)
            return False


def _patch_review_queue(progress: dict, fsrs_states: dict[str, FSRSState]) -> bool:
    """Update LearningProgress.review_queue / repetition_states from FSRS.

    Returns True if the progress dict was modified. We only touch
    ``next_review_at`` (and add missing entries) — upstream gating logic and
    mastery_levels stay intact.
    """
    changed = False
    rep_states: dict[str, Any] = progress.setdefault("repetition_states", {})
    review_queue: list[dict] = progress.setdefault("review_queue", [])

    # Build an index of existing review_queue entries by kp_id for in-place update.
    queue_by_kp = {q.get("knowledge_point_id"): q for q in review_queue if isinstance(q, dict)}

    for kp_id, fsrs in fsrs_states.items():
        if fsrs.is_new or fsrs.next_review_at <= 0:
            continue
        ts = fsrs.next_review_at
        # Update RepetitionState.next_review_at
        rs = rep_states.get(kp_id)
        if isinstance(rs, dict):
            if rs.get("next_review_at") != ts:
                rs["next_review_at"] = ts
                changed = True
        else:
            rep_states[kp_id] = {
                "interval_index": 0,
                "consecutive_correct": 0,
                "consecutive_wrong": 0,
                "next_review_at": ts,
            }
            changed = True
        # Update or add review_queue entry
        entry = queue_by_kp.get(kp_id)
        if entry is None:
            review_queue.append(
                {
                    "id": f"review_{kp_id}",
                    "knowledge_point_id": kp_id,
                    "due_at": ts,
                    "priority": 3,
                }
            )
            changed = True
        elif entry.get("due_at") != ts:
            entry["due_at"] = ts
            changed = True
    return changed


__all__ = ["ReviewStore"]
