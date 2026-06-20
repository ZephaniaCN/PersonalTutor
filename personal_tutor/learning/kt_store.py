"""Persistence for BKT knowledge-tracing state.

Stores a domain's worth of ``KTState`` objects in a single JSON file under
DeepTutor's workspace, so knowledge-tracing data inherits the same per-user
isolation (``data/users/<uid>/`` in multi-user mode) as everything else.

File layout::

    <workspace>/personal_tutor/kt_<domain_id>.json
        { "domain_id": "...", "version": 1, "states": { kp_id: KTState.to_dict() } }

Writes are atomic (tmp + rename) and process-locked, mirroring
``deeptutor/learning/storage.py``'s discipline.
"""

from __future__ import annotations

import threading
from typing import Iterable

from personal_tutor.learning.knowledge_tracing import DEFAULT_KT_PARAMS, KTParams, KTState
from personal_tutor.storage import json_store
from personal_tutor.storage.paths import personal_root

_VERSION = 1


def _kt_path(domain_id: str):
    return personal_root() / f"kt_{domain_id}.json"


class KTStore:
    """JSON-backed store of ``KTState`` for one domain.

    Holds an in-memory cache loaded lazily on first access; callers should
    call :meth:`save` after a batch of updates. Thread-safe via a module-level
    lock shared with :mod:`json_store`'s write path.
    """

    def __init__(self, domain_id: str, params: KTParams = DEFAULT_KT_PARAMS) -> None:
        self.domain_id = domain_id
        self.params = params
        self._cache: dict[str, KTState] | None = None
        self._lock = threading.Lock()

    # -- load / save -------------------------------------------------------

    def load(self) -> dict[str, KTState]:
        """Lazily load and cache the domain's KT states."""
        if self._cache is not None:
            return self._cache
        with self._lock:
            if self._cache is None:
                data = json_store.read_json(_kt_path(self.domain_id), default=None)
                states: dict[str, KTState] = {}
                if isinstance(data, dict):
                    for raw in (data.get("states") or {}).values():
                        st = KTState.from_dict(raw)
                        states[st.knowledge_point_id] = st
                self._cache = states
            return self._cache

    def save(self) -> None:
        """Persist the cached states atomically. No-op if never loaded."""
        if self._cache is None:
            return
        payload = {
            "domain_id": self.domain_id,
            "version": _VERSION,
            "states": {kp_id: st.to_dict() for kp_id, st in self._cache.items()},
        }
        json_store.write_json(_kt_path(self.domain_id), payload)

    # -- access ------------------------------------------------------------

    def get(self, kp_id: str) -> KTState:
        """Return the state for *kp_id*, creating a fresh prior if unseen."""
        states = self.load()
        st = states.get(kp_id)
        if st is None:
            st = KTState(knowledge_point_id=kp_id, p_known=self.params.p_known)
            states[kp_id] = st
        return st

    def get_all(self) -> dict[str, KTState]:
        return self.load()

    def upsert(self, state: KTState) -> None:
        states = self.load()
        states[state.knowledge_point_id] = state

    def upsert_many(self, states: Iterable[KTState]) -> None:
        cache = self.load()
        for st in states:
            cache[st.knowledge_point_id] = st


__all__ = ["KTStore"]
