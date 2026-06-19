"""Tests for PersonalTutor's domain framework and plugin discovery.

Run with ``python -m pytest personal_tutor/tests`` (pytest is pulled in via
DeepTutor's dev extras; install with ``uv pip install -e '.[dev]'`` if not
present). These tests deliberately avoid importing DeepTutor's runtime so
they stay fast and runnable in a minimal CI environment — only the
plugin-discovery test touches DeepTutor, and it is marked so it can be skipped
when DeepTutor is not installed.
"""
