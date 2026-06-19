"""Storage layer for PersonalTutor.

All persistence rides on DeepTutor's :class:`~deeptutor.services.path_service.PathService`
so data lives under the same per-user workspace (``data/users/<uid>/`` in
multi-user mode, ``data/`` otherwise). We add a single sub-directory
``personal_tutor/`` under the workspace to keep PersonalTutor's files grouped
and easy to inspect/back up.

Each store is JSON-backed (atomic write via tmp+rename, matching
:mod:`deeptutor.learning.storage`). A SQLite store can be layered in later
when query patterns demand it; the file format is designed to migrate cleanly.
"""
