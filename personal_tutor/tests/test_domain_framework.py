"""Unit tests for the domain extension framework (no DeepTutor deps).

These exercise the pure-Python pieces a domain author interacts with:
KnowledgeGraph DAG operations, the registry singleton, and the programming
domain's spec loading from its bundled YAML.
"""

from __future__ import annotations

import pytest

from personal_tutor.domains import (
    DomainRegistry,
    KnowledgeGraph,
    KnowledgePoint,
    get_registry,
    register,
    reset_registry,
)


# --------------------------------------------------------------------------- #
# KnowledgeGraph
# --------------------------------------------------------------------------- #

def _kp(kp_id: str, prereqs=()) -> KnowledgePoint:
    return KnowledgePoint(id=kp_id, name=kp_id, module_id="m", prerequisites=prereqs)


def test_topological_order_respects_prerequisites():
    """Prerequisites must always precede their dependents in topo order."""
    g = KnowledgeGraph()
    g.add_module("m")
    g.add_point(_kp("b", prereqs=("a",)))
    g.add_point(_kp("c", prereqs=("b",)))
    g.add_point(_kp("a"))
    order = g.topological_order()
    assert order.index("a") < order.index("b") < order.index("c")


def test_topological_order_detects_cycle():
    """A cyclic graph must raise — a roadmap can't be planned on a cycle."""
    g = KnowledgeGraph()
    g.add_module("m")
    g.add_point(_kp("x", prereqs=("y",)))
    g.add_point(_kp("y", prereqs=("x",)))
    with pytest.raises(ValueError, match="cycle"):
        g.topological_order()


def test_add_point_dedupes_within_module():
    g = KnowledgeGraph()
    g.add_module("m")
    g.add_point(_kp("a"))
    g.add_point(_kp("a"))  # duplicate id
    assert g.modules["m"] == ["a"]
    assert len(g.all_points()) == 1


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #

class _FakeDomain:
    """Minimal duck-typed spec for registry tests (avoids ABC boilerplate)."""
    domain_id = "fake"
    name = "Fake"


def test_registry_register_and_lookup():
    reg = DomainRegistry()
    reg.register(_FakeDomain())
    assert reg.get("fake") is not None
    assert "fake" in reg.ids()
    assert len(reg.all()) == 1


def test_registry_require_raises_on_unknown():
    reg = DomainRegistry()
    with pytest.raises(KeyError, match="Unknown domain"):
        reg.require("nope")


def test_registry_rejects_empty_id():
    class _Empty:
        domain_id = ""
        name = "Empty"
    reg = DomainRegistry()
    with pytest.raises(ValueError, match="domain_id"):
        reg.register(_Empty())


def test_default_registry_autoregisters_programming():
    """The process-wide registry must always know about `programming`."""
    # reset_registry returns a fresh registry with built-ins already loaded.
    reg = reset_registry()
    assert "programming" in reg.ids()
    # And get_registry (a separate fresh singleton) must also have it.
    assert "programming" in get_registry().ids()


# --------------------------------------------------------------------------- #
# Programming domain spec (loads bundled YAML)
# --------------------------------------------------------------------------- #

def test_programming_domain_loads_graph():
    from personal_tutor.domains.programming.spec import ProgrammingDomain

    spec = ProgrammingDomain()
    graph = spec.knowledge_graph()
    # The seed graph has a fixed shape; guard against silent truncation.
    assert len(graph.all_points()) >= 15, "seed graph should be non-trivial"
    # Topo order must be acyclic.
    assert len(graph.topological_order()) == len(graph.all_points())


def test_programming_diagnostic_blueprint_samples_modules():
    from personal_tutor.domains.programming.spec import ProgrammingDomain

    spec = ProgrammingDomain()
    bp = spec.diagnostic_blueprint()
    assert bp.questions_per_module >= 1
    assert "ds.hashtable" in bp.must_include


def test_programming_rubric_covers_code_and_concept():
    from personal_tutor.domains.base import QuestionType
    from personal_tutor.domains.programming.spec import ProgrammingDomain

    spec = ProgrammingDomain()
    code_rubric = spec.rubric_for(QuestionType.CODE)
    assert code_rubric is not None and code_rubric.pass_threshold == 1.0
    concept_rubric = spec.rubric_for(QuestionType.CONCEPT)
    assert concept_rubric is not None
