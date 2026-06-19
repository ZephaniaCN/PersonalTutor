"""PersonalTutor — a personalized AI tutoring layer on top of DeepTutor.

PersonalTutor is an **isolated extension package** that adds domain-aware
personalized learning (learning profile, diagnostic assessment, adaptive
roadmaps, spaced-repetition review, and quizzes/exams) to an *unmodified*
upstream DeepTutor runtime.

Design contract
---------------
* This package only touches DeepTutor through its **public extension points**:
    - the reserved ``deeptutor.plugins.loader`` discovery hook
      (see ``deeptutor/plugins/loader.py``, a thin shim that re-exports from
      :mod:`personal_tutor.plugins`);
    - the documented REST/WebSocket API of ``deeptutor serve``;
    - the public capability protocol ``deeptutor.core.capability_protocol``;
    - the storage path service ``deeptutor.services.path_service``.
* It never patches ``BUILTIN_CAPABILITY_CLASSES`` or other upstream files, so
  an upstream ``git rebase`` stays conflict-free outside ``deeptutor/plugins/``.

Compatibility
-------------
``MIN_DEEPTUTOR_VERSION`` pins the lowest upstream release this layer was
authored and tested against. Bump it only after re-validating against a newer
upstream ``dev``.
"""

from __future__ import annotations

__version__ = "0.1.0"

#: Lowest upstream DeepTutor release this extension is known to work with.
#: Bump only after re-running ``tests/test_compatibility.py``.
MIN_DEEPTUTOR_VERSION = "1.4.9"

__all__ = ["__version__", "MIN_DEEPTUTOR_VERSION"]
