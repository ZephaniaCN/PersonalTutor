"""Tiny atomic JSON store.

Mirrors the write discipline of :mod:`deeptutor.learning.storage` (write to a
sibling temp file, then ``os.replace`` for atomicity) but stays dependency-
free so any PersonalTutor module can use it without pulling DeepTutor.
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

_lock = threading.Lock()


def read_json(path: Path, default: Any = None) -> Any:
    """Read and parse *path*; return *default* if missing or invalid."""
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, data: Any) -> None:
    """Atomically write *data* as UTF-8 JSON.

    Uses a process-wide lock plus a tmp-file+rename so concurrent writes within
    one process never produce a truncated file. Cross-process safety relies on
    ``os.replace`` being atomic on POSIX/Windows for same-filesystem renames.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2, default=str)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with _lock:
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)


__all__ = ["read_json", "write_json"]
