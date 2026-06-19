"""PersonalTutor HTTP API surface.

A single FastAPI :class:`~fastapi.APIRouter` (``router``) exposing the
PersonalTutor endpoints. It is mounted onto the DeepTutor app via
``patches/002-mount-personal-tutor-router.patch`` (a 3-line include in
``deeptutor/api/main.py``) so the upstream tree stays otherwise untouched.

Endpoint groups
---------------
* ``GET  /api/v1/personal/domains``               — list registered domains
* ``GET  /api/v1/personal/domains/{id}``          — domain knowledge graph
* ``GET  /api/v1/personal/profile/{domain_id}``   — read learning profile
* ``PUT  /api/v1/personal/profile/{domain_id}``   — write learning profile
* ``POST /api/v1/personal/diagnostics/{id}/start``— begin entry diagnostic
* ``GET  /api/v1/personal/health``                — liveness + version
"""
