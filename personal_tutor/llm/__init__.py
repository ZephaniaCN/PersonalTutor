"""LLM orchestration layer for PersonalTutor.

Reuses DeepTutor's resolved LLM configuration (``data/user/settings/model_catalog.json``)
as the single source of API keys and endpoints — PersonalTutor never stores
its own credentials. Thin wrappers (:mod:`personal_tutor.llm.client`) expose
an OpenAI-compatible async client plus helpers tailored to the tutoring
workflows (question generation, grading, roadmap planning).
"""
