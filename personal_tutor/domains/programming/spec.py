"""Programming algorithms :class:`DomainSpec`.

Loads its knowledge graph from the bundled ``knowledge_graph.yaml`` so the
domain content stays declarative and editable without touching Python. A
placeholder :class:`ProgrammingQuestionGenerator` is wired in so the spec is
fully functional end-to-end; it will be replaced by an LLM-backed generator
in :mod:`personal_tutor.llm.chains` once the orchestration layer lands.
"""

from __future__ import annotations

from functools import lru_cache
from importlib import resources
from typing import Any

import yaml

from personal_tutor.domains.base import (
    DiagnosticBlueprint,
    Difficulty,
    DomainSpec,
    KnowledgeGraph,
    KnowledgePoint,
    QuestionGenerator,
    QuestionType,
    Rubric,
)


def _load_graph_yaml() -> dict[str, Any]:
    """Read the bundled knowledge graph YAML via importlib.resources.

    Using ``files()`` keeps this robust to whether ``personal_tutor`` is run
    from source, installed editable, or packed in a wheel — matching how
    DeepTutor ships its own packaged data.
    """
    pkg_files = resources.files("personal_tutor.domains.programming")
    yaml_text = (pkg_files / "knowledge_graph.yaml").read_text(encoding="utf-8")
    return yaml.safe_load(yaml_text)


def _build_graph(data: dict[str, Any]) -> KnowledgeGraph:
    """Translate the YAML structure into a :class:`KnowledgeGraph`."""
    graph = KnowledgeGraph()
    # Modules first, so ordering is respected even if points arrive unordered.
    modules = data.get("modules", [])
    modules_sorted = sorted(modules, key=lambda m: m.get("order", 0))
    for mod in modules_sorted:
        graph.add_module(mod["id"], name=mod.get("name", ""), order=None)
    for raw in data.get("knowledge_points", []):
        graph.add_point(
            KnowledgePoint(
                id=raw["id"],
                name=raw.get("name", raw["id"]),
                summary=raw.get("summary", ""),
                type=raw.get("type", "concept"),
                module_id=raw.get("module_id", ""),
                prerequisites=tuple(raw.get("prerequisites", []) or []),
                tags=tuple(raw.get("tags", []) or []),
            )
        )
    return graph


class ProgrammingQuestionGenerator(QuestionGenerator):
    """Placeholder generator producing templated CONCEPT questions.

    The real generator (LLM-backed, producing fresh LeetCode-style prompts)
    lives in :mod:`personal_tutor.llm.chains` and will be injected here. This
    placeholder guarantees the domain is usable end-to-end today: a quiz can
    run, the question bank can be populated, and the assessment loop is
    exercised without any API key configured.
    """

    question_type = QuestionType.CONCEPT

    async def generate(
        self,
        kp: KnowledgePoint,
        *,
        difficulty: Difficulty,
        count: int = 1,
    ) -> list[dict[str, Any]]:
        questions: list[dict[str, Any]] = []
        for _ in range(count):
            questions.append(
                {
                    "question_id": f"{kp.id}-concept-{difficulty.value}",
                    "knowledge_point_id": kp.id,
                    "question_type": self.question_type.value,
                    "question": (
                        f"请简要说明「{kp.name}」的核心概念"
                        + (f"：{kp.summary}" if kp.summary else "")
                        + f"(难度: {difficulty.value})"
                    ),
                    "difficulty": difficulty.value,
                    "correct_answer": kp.summary or kp.name,
                    "explanation": (
                        "参考答案应覆盖核心定义、典型应用与常见陷阱。"
                        "LLM 接入后将由模型生成更精准的参考答案与判分。"
                    ),
                    "options": [],
                }
            )
        return questions


class ProgrammingDomain(DomainSpec):
    """Concrete spec for the programming algorithms domain."""

    domain_id = "programming"
    name = "编程算法"
    description = "数据结构、经典算法与复杂度分析,覆盖 LeetCode 中等难度核心题型。"

    @lru_cache(maxsize=1)
    def _graph(self) -> KnowledgeGraph:
        return _build_graph(_load_graph_yaml())

    def knowledge_graph(self) -> KnowledgeGraph:
        # lru_cache is on a private method so each instance shares the cache
        # without the public method needing to be hashable.
        return self._graph()

    def diagnostic_blueprint(self) -> DiagnosticBlueprint:
        return DiagnosticBlueprint(
            questions_per_module=3,
            default_difficulty=Difficulty.MEDIUM_EASY,
            must_include=("ds.hashtable", "algo.dp", "analysis.big_o"),
        )

    def generators_for(self, kp: KnowledgePoint) -> list[QuestionGenerator]:
        return [ProgrammingQuestionGenerator()]

    def rubric_for(self, question_type: QuestionType) -> Rubric | None:
        if question_type == QuestionType.CODE:
            return Rubric(
                question_type=question_type,
                criteria="代码须通过全部测试用例,且时空复杂度达标。",
                test_case_ids=(),
                pass_threshold=1.0,
            )
        return Rubric(
            question_type=question_type,
            criteria="答案须准确覆盖概念定义、典型应用与至少一个易错点。",
            pass_threshold=0.7,
        )


__all__ = ["ProgrammingDomain", "ProgrammingQuestionGenerator"]
