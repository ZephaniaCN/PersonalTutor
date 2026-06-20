"""Entry diagnostic capability.

The diagnostic establishes a learner's baseline across a whole domain before
any roadmap is planned. It:

1. samples knowledge points per the domain's diagnostic blueprint,
2. generates one question per sampled KP (placeholder generator today,
   LLM-backed generator once configured),
3. returns the question set for the client to administer,
4. accepts graded answers, updates BKT state, and rebuilds the profile.

Because administration (showing questions, collecting answers) happens on the
client, the capability exposes two distinct operations rather than one turn:
``prepare`` (produce questions) and ``grade`` (consume answers). Both are also
reachable via REST (:mod:`personal_tutor.api.router`) so a web UI can drive
the flow without the CLI.
"""
