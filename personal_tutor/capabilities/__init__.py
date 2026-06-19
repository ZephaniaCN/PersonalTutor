"""PersonalTutor capabilities package.

Each subpackage implements one :class:`deeptutor.core.capability_protocol.BaseCapability`
that PersonalTutor exposes to DeepTutor through the plugin discovery hook
(:mod:`personal_tutor.plugins`). Capabilities are intentionally thin: the
intelligence lives in :mod:`personal_tutor.learning` (pure, testable engine)
and the LLM orchestration in :mod:`personal_tutor.llm`.
"""
