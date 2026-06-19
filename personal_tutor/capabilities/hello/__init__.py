"""Hello capability — smoke test for the PersonalTutor plugin injection.

This capability is intentionally dependency-free: it emits a short report and
finishes. Its sole purpose is to prove that the
``deeptutor.plugins.loader`` -> :mod:`personal_tutor.plugins` chain correctly
registers a capability the upstream CLI can dispatch to via
``deeptutor run personal_hello``.

It also doubles as a live reference implementation for:

* how to emit structured stream events (STAGE / CONTENT / RESULT);
* how to read the active :mod:`personal_tutor.domains` registry so future
  capabilities have a template for domain-aware behaviour.
"""
