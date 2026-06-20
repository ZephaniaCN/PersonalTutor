# PersonalTutor

A personalized AI tutoring layer built **on top of** [DeepTutor](https://github.com/HKUDS/DeepTutor).
PersonalTutor adds domain-aware personalized learning — a learner profile,
diagnostic assessment, adaptive roadmaps, spaced-repetition review, and
quizzes/exams — while keeping the upstream DeepTutor tree essentially unmodified
so upstream updates can be absorbed continuously.

> **Status:** Phase 0 (infrastructure) complete. Domain framework, plugin
> injection, REST surface, and the programming-algorithms seed domain are live.
> BKT knowledge tracing, FSRS scheduling, and the exam engine land in phases 1–4.

---

## Why a separate layer?

DeepTutor is an excellent *general* tutor, but a truly personal growth system
needs three things it only partially provides:

| Need | DeepTutor | PersonalTutor adds |
|------|-----------|--------------------|
| Fine-grained weakness tracking | Memory L3 `profile` (soft claims) | Per-knowledge-point **BKT** tracing |
| Precise review scheduling | Mastery Path spaced review (fixed intervals) | **FSRS-4.5** card-level scheduler |
| Formal assessment | `deep_question` (practice-oriented) | Timed **exam engine** + score reports |
| New learning fields | Hardcoded capabilities | **Domain plugin registry** (add fields without code changes) |

PersonalTutor fills these gaps as an isolated package that DeepTutor discovers
through its reserved plugin hook — no upstream files are patched beyond two
single-line build/API includes (see `patches/`).

---

## Architecture

```
┌─────────────────────────── DeepTutor (upstream, ~unmodified) ───────────────────────────┐
│  deeptutor/                core runtime, capability protocol, FastAPI app, Memory, RAG   │
│      ↑                                                                                   │
│      │ reserved plugin hook: `deeptutor.plugins.loader` (a shim that re-exports ↓)       │
└──────┼──────────────────────────────────────────────────────────────────────────────────┘
       │
┌──────┴──────────────────────── PersonalTutor (this extension) ──────────────────────────┐
│  personal_tutor/                                                                         │
│    plugins.py        ← capability discovery (manifests → BaseCapability)                 │
│    domains/          ← DomainSpec + KnowledgeGraph + registry (the extensibility core)   │
│       programming/      ↳ seed domain: 20 KPs across data structures / algorithms        │
│    capabilities/     ← BaseCapability impls (hello ✓, diagnostic/todo, quiz/todo…)       │
│    llm/              ← LLM client reusing DeepTutor's model_catalog.json (no 2nd key)    │
│    api/router.py     ← REST mounted at /api/v1/personal                                   │
│    storage/          ← JSON store under DeepTutor's per-user workspace                   │
│    tests/            ← domain unit tests + upstream compatibility contract               │
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

**The two patches** (in `patches/`, re-applied after every upstream rebase):
1. `001-personal-tutor-package-include.patch` — adds `personal_tutor*` to
   setuptools discovery so `pip install -e .` installs it (and it's importable
   from any CWD, not just the project root).
2. `002-mount-personal-tutor-router.patch` — mounts the PersonalTutor router
   at `/api/v1/personal` on the FastAPI app (best-effort; failure degrades
   gracefully).

---

## Quick start

```bash
# 1. Clone (this is a fork of HKUDS/DeepTutor with personal_tutor/ added)
cd PersonalTutor

# 2. Create a Python 3.11 env and install (editable, picks up both packages)
uv venv --python 3.11 .venv
source .venv/bin/activate
uv pip install -e .
uv pip install pytest pytest-asyncio   # for the tests

# 3. Verify the plugin injection end-to-end
deeptutor run personal_hello "smoke test"
# → "PersonalTutor v0.1.0 is online ... Registered learning domains: 编程算法 (20 KPs)"

# 4. Verify the REST surface
deeptutor serve --port 8001 &
curl http://localhost:8001/api/v1/personal/health
curl http://localhost:8001/api/v1/personal/domains
curl -X POST http://localhost:8001/api/v1/personal/diagnostics/programming/start

# 5. Run the test suite (domain logic + upstream compatibility contract)
python -m pytest personal_tutor/tests/ -v
```

To actually chat with DeepTutor's LLM features, configure a model in
`data/user/settings/model_catalog.json` (or via the web Settings UI after
`deeptutor start`). PersonalTutor reuses this same config — it stores no API
keys of its own.

---

## Adding a new learning domain

A domain is a declarative spec; no capability or core code needs to change.

1. Create `personal_tutor/domains/<your_domain>/` with a `knowledge_graph.yaml`
   (copy `programming/knowledge_graph.yaml` as a template).
2. Implement a `DomainSpec` subclass (see
   `personal_tutor/domains/programming/spec.py`).
3. Register it in `personal_tutor/domains/registry.py::_autoregister_builtin_domains`.
4. It now appears in `GET /api/v1/personal/domains` and is usable by every
   capability.

Future domains on the roadmap: large-language-models, photography, art
appreciation, narratology, writing, economics.

---

## Adding a new capability

1. Create `personal_tutor/capabilities/<name>/capability.py` with a
   `BaseCapability` subclass (use `hello/capability.py` as the minimal template).
2. Register a `PersonalCapabilitySpec` in `personal_tutor/plugins.py::_install_defaults`.
3. The upstream registry discovers it automatically — `deeptutor run <name>`
   works with no further changes.

---

## Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| **0 — Infrastructure** | Env, plugin injection, domain framework, REST, programming seed domain | ✅ Done |
| **1 — Diagnostic + profile** | Entry diagnostic capability, BKT knowledge tracing, profile builder | ✅ Done |
| **2 — Roadmap + FSRS** | Personalized roadmap generation, FSRS-4.5 scheduler, Mastery Path sync | ✅ Done |
| **3 — Quiz + exam** | Adaptive quiz (BKT-driven), timed exam engine, LLM grading, score reports | ✅ Done |
| **4 — Frontend** | Next.js dashboard: overview, diagnostic, profile, roadmap, practice, exam | ✅ Done |

---

## Syncing with upstream DeepTutor

```bash
git remote add upstream https://github.com/HKUDS/DeepTutor.git
git fetch upstream
git rebase upstream/dev
# Resolve conflicts only in patches/ (single-line includes), then:
git am --abort 2>/dev/null; git am patches/*.patch   # re-apply if needed
python -m pytest personal_tutor/tests/test_compatibility.py -v
```

The compatibility test suite is the gate: it fails loudly if an upstream
change breaks the plugin discovery contract, the router mount, the version
minimum, or the packaged-YAML resolution.
