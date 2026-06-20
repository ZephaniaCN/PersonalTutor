"""LLM-backed chains for PersonalTutor.

Each module is one workflow (grading, question generation, roadmap narration).
All chains reuse :mod:`personal_tutor.llm.client` (which reads DeepTutor's
model_catalog) so there's a single source of API keys, and all degrade
gracefully to deterministic fallbacks when no LLM is configured — keeping
PersonalTutor fully functional in offline / no-key environments.
"""
