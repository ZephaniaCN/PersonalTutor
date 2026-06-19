# PersonalTutor package

An isolated extension layer that adds domain-aware personalized learning
(profile, diagnostic, adaptive roadmap, spaced review, quizzes/exams) on top
of an **unmodified** DeepTutor runtime.

PersonalTutor reuses DeepTutor's LLM configuration (single source of API keys),
storage layer (`PathService`), and capability protocol. It is discovered by
upstream through the reserved `deeptutor.plugins.loader` hook, so no upstream
file is patched.

See `PERSONAL_TUTOR.md` at the repository root for the full architecture.
