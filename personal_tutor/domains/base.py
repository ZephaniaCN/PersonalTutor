"""Abstract building blocks for a learning domain.

These types are deliberately framework-agnostic (pure dataclasses + ABCs, no
LLM/DeepTutor imports) so a domain can be authored, unit-tested, and serialized
without pulling in the full runtime. Capabilities in
:mod:`personal_tutor.capabilities` bind these specs to the DeepTutor
capability protocol and the LLM orchestration layer.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class QuestionType(str, Enum):
    """The kinds of questions a domain can produce.

    Mirrors the shape DeepTutor's ``deep_question`` capability already emits
    so questions can flow into the upstream Question Bank without translation.
    """

    CONCEPT = "concept"           # short-answer / multiple-choice on theory
    ANALYSIS = "analysis"         # e.g. complexity analysis, trade-off reasoning
    CODE = "code"                 # implementation, judged against test cases
    DEBUG = "debug"               # find/fix a bug in given code
    OPEN = "open"                 # free-form, LLM-graded against a rubric


class Difficulty(str, Enum):
    """5-point difficulty scale. Strings keep payloads JSON-friendly."""

    EASY = "easy"
    MEDIUM_EASY = "medium-easy"
    MEDIUM = "medium"
    MEDIUM_HARD = "medium-hard"
    HARD = "hard"

    @classmethod
    def from_mastery(cls, mastery: float) -> "Difficulty":
        """Pick a difficulty from a 0..1 mastery estimate.

        Low mastery -> easy (scaffolding); high mastery -> hard (challenge).
        This is the default adaptive-difficulty rule; a domain may override
        ``QuestionGenerator.difficulty_for`` for finer control.
        """
        if mastery < 0.2:
            return cls.EASY
        if mastery < 0.4:
            return cls.MEDIUM_EASY
        if mastery < 0.6:
            return cls.MEDIUM
        if mastery < 0.8:
            return cls.MEDIUM_HARD
        return cls.HARD


@dataclass(frozen=True)
class KnowledgePoint:
    """A single atomic skill/concept inside a domain.

    ``id`` is globally unique within the domain (e.g.
    ``algo.dp.knapsack_01``). ``prerequisites`` reference other KP ids the
    learner is expected to know first — the roadmap planner walks this DAG.
    """

    id: str
    name: str
    summary: str = ""
    type: str = "concept"  # memory | concept | procedure | design (mirrors DeepTutor)
    module_id: str = ""
    prerequisites: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


@dataclass
class KnowledgeGraph:
    """A DAG of knowledge points grouped into ordered modules.

    The graph is append-only by construction: builders (see
    :mod:`personal_tutor.domains.programming.spec`) add points and modules,
    then ``freeze`` is called by the registry. Query helpers do the
    topological work the roadmap planner needs.
    """

    points: dict[str, KnowledgePoint] = field(default_factory=dict)
    modules: dict[str, list[str]] = field(default_factory=dict)  # module_id -> [kp_id]
    module_order: list[str] = field(default_factory=list)

    # -- mutation (domain authoring) ----------------------------------------

    def add_module(self, module_id: str, name: str = "", order: int | None = None) -> None:
        if module_id in self.modules:
            return
        self.modules[module_id] = []
        if order is None:
            self.module_order.append(module_id)
        else:
            self.module_order.insert(order, module_id)

    def add_point(self, point: KnowledgePoint) -> None:
        self.points[point.id] = point
        if not point.module_id:
            return
        bucket = self.modules.setdefault(point.module_id, [])
        if point.id not in bucket:
            bucket.append(point.id)

    # -- queries (used by capabilities) -------------------------------------

    def all_points(self) -> list[KnowledgePoint]:
        return list(self.points.values())

    def get(self, kp_id: str) -> KnowledgePoint | None:
        return self.points.get(kp_id)

    def prerequisites_of(self, kp_id: str) -> list[str]:
        kp = self.points.get(kp_id)
        return list(kp.prerequisites) if kp else []

    def topological_order(self) -> list[str]:
        """Return KP ids in dependency order (prereqs first).

        Uses Kahn's algorithm; raises :class:`ValueError` on cycles, since a
        learning graph must be acyclic for a roadmap to make sense.
        """
        indeg: dict[str, int] = {kp_id: 0 for kp_id in self.points}
        adj: dict[str, list[str]] = {kp_id: [] for kp_id in self.points}
        for kp in self.points.values():
            for pre in kp.prerequisites:
                if pre in self.points:
                    adj[pre].append(kp.id)
                    indeg[kp.id] += 1
        queue = [kp_id for kp_id, d in indeg.items() if d == 0]
        order: list[str] = []
        while queue:
            node = queue.pop(0)
            order.append(node)
            for nxt in adj[node]:
                indeg[nxt] -= 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(self.points):
            unresolved = [k for k, d in indeg.items() if d > 0]
            raise ValueError(f"Knowledge graph has a cycle through: {unresolved}")
        return order


@dataclass(frozen=True)
class DiagnosticBlueprint:
    """How to sample the knowledge graph for an entry diagnostic.

    A diagnostic is a broad, shallow sweep that establishes a baseline before
    a roadmap is planned. ``questions_per_module`` controls breadth; together
    with the number of modules it bounds total question count.
    """

    questions_per_module: int = 2
    default_difficulty: Difficulty = Difficulty.MEDIUM_EASY
    # KPs tagged here are always included even if not sampled.
    must_include: tuple[str, ...] = ()


@dataclass
class Rubric:
    """How to judge an answer for a question type in this domain."""

    question_type: QuestionType
    # For CODE questions: list of test-case ids to run (empty = LLM-graded).
    # For CONCEPT/OPEN: grading criteria prompt fragment handed to the LLM.
    criteria: str = ""
    test_case_ids: tuple[str, ...] = ()
    pass_threshold: float = 0.7


class QuestionGenerator(ABC):
    """Produces questions for a knowledge point.

    The default implementation is an LLM-backed generator (lives in
    :mod:`personal_tutor.llm.chains`); domains may ship hand-authored
    question banks that implement this interface directly (no LLM call).
    """

    question_type: QuestionType = QuestionType.CONCEPT

    @abstractmethod
    async def generate(
        self,
        kp: KnowledgePoint,
        *,
        difficulty: Difficulty,
        count: int = 1,
    ) -> list[dict[str, Any]]:
        """Return ``count`` question dicts.

        Each dict is shaped to match the upstream Question Bank entry so it
        can be persisted unchanged. Minimum keys: ``question_id``,
        ``knowledge_point_id``, ``question_type``, ``question``,
        ``options`` (optional), ``difficulty``, ``correct_answer``,
        ``explanation``.
        """
        raise NotImplementedError

    def difficulty_for(self, mastery: float) -> Difficulty:
        """Default adaptive-difficulty mapping; override for custom rules."""
        return Difficulty.from_mastery(mastery)


class DomainSpec(ABC):
    """Declarative description of one learning domain.

    Subclasses populate the attributes (typically from a bundled YAML/JSON
    spec) and provide the question generators + rubrics. The registry calls
    :meth:`load` lazily so heavy resources (LLM clients, big question banks)
    are only created when the domain is actually used.
    """

    #: Globally unique id, e.g. ``"programming"``. Used in API paths and storage keys.
    domain_id: str
    #: Human-readable name, e.g. ``"编程算法"``.
    name: str
    #: Short one-line description for listings.
    description: str = ""

    @abstractmethod
    def knowledge_graph(self) -> KnowledgeGraph:
        """Return the domain's knowledge graph (built once, cached by caller)."""
        raise NotImplementedError

    @abstractmethod
    def diagnostic_blueprint(self) -> DiagnosticBlueprint:
        """Return the blueprint for the entry diagnostic."""
        raise NotImplementedError

    def generators_for(self, kp: KnowledgePoint) -> list[QuestionGenerator]:
        """Return the generators that can produce questions for *kp*.

        Default: no generators. Domains override to map KPs/types to their
        question sources (hand-authored bank, LLM chain, or a mix).
        """
        return []

    def rubric_for(self, question_type: QuestionType) -> Rubric | None:
        """Return the grading rubric for *question_type*, or ``None``."""
        return None

    def mastery_threshold(self, kp: KnowledgePoint) -> float:
        """Per-KP mastery threshold (0..1). Defaults to 0.7 like DeepTutor."""
        return 0.7


__all__ = [
    "Difficulty",
    "DiagnosticBlueprint",
    "DomainSpec",
    "KnowledgeGraph",
    "KnowledgePoint",
    "QuestionGenerator",
    "QuestionType",
    "Rubric",
]
