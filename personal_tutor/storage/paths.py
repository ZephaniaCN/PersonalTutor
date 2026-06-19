"""Workspace path helpers for PersonalTutor.

Resolves a private sub-directory under DeepTutor's workspace root via
:class:`~deeptutor.services.path_service.PathService`, so PersonalTutor's data
is co-located with (and inherits the per-user isolation of) the rest of the
user's data — no separate DB or mount point to manage.
"""

from __future__ import annotations

from pathlib import Path


def _workspace_root() -> Path:
    """Return DeepTutor's workspace root, falling back to CWD if unavailable.

    The try/except keeps PersonalTutor importable (and unit-testable) even
    when DeepTutor's path service has not been initialized — e.g. in a pure
    unit test or a CLI smoke run outside ``deeptutor serve``.
    """
    try:
        from deeptutor.services.path_service import get_path_service

        return Path(get_path_service().get_workspace_dir())
    except Exception:
        return Path.cwd() / "data"


def personal_root() -> Path:
    """PersonalTutor's private directory under the workspace root."""
    root = _workspace_root() / "personal_tutor"
    root.mkdir(parents=True, exist_ok=True)
    return root


def profile_path(domain_id: str) -> Path:
    """Path to the learning-profile JSON for *domain_id*."""
    return personal_root() / f"profile_{domain_id}.json"


def diagnostic_path(domain_id: str) -> Path:
    """Path to the latest diagnostic result for *domain_id*."""
    return personal_root() / f"diagnostic_{domain_id}.json"


def exam_path(exam_id: str) -> Path:
    """Path to an exam record."""
    exams = personal_root() / "exams"
    exams.mkdir(parents=True, exist_ok=True)
    return exams / f"{exam_id}.json"


__all__ = ["personal_root", "profile_path", "diagnostic_path", "exam_path"]
