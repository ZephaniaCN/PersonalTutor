"""LLM answer grader.

Grades free-form learner answers against a reference answer + rubric using the
DeepTutor-configured LLM. Returns a structured verdict (is_correct + score +
rationale) so it can feed straight into the BKT update.

Two-tier design:
* **LLM path** — when a model is configured, asks the LLM to grade on a 0..1
  scale with JSON output, grounded by the rubric. This handles open/concept/
  analysis questions where exact-match is hopeless.
* **Fallback path** — keyword overlap (Jaccard on token sets) against the
  reference answer. Crude but deterministic and key-free; good enough for the
  placeholder generator's simple concept questions and for unit tests.

The caller picks the threshold (default 0.7) for "correct".
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from personal_tutor.llm import client as llm_client

log = logging.getLogger(__name__)

#: Default correctness threshold — matches DeepTutor's mastery pass_threshold.
DEFAULT_THRESHOLD = 0.7

_SYSTEM = (
    "You are a strict but fair examiner. Grade the learner's answer against the "
    "reference answer using the rubric. Respond ONLY with compact JSON."
)

_USER_TEMPLATE = """\
知识点: {kp}
题目: {question}
参考答案: {reference}
评分标准: {rubric}
学习者答案: {answer}

按以下 JSON 格式评分(不要输出任何其它内容):
{{"score": 0.0到1.0, "is_correct": true或false, "rationale": "一句话理由"}}

判定要点: 核心概念正确得分; 遗漏关键点扣分; 概念性错误判 0.3 以下. \
score >= {threshold} 时 is_correct = true."""


@dataclass
class GradeVerdict:
    """Structured grading result."""

    is_correct: bool
    score: float
    rationale: str
    method: str  # "llm" | "fallback"

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_correct": self.is_correct,
            "score": round(self.score, 4),
            "rationale": self.rationale,
            "method": self.method,
        }


async def grade_answer(
    *,
    knowledge_point_id: str,
    question: str,
    reference_answer: str,
    learner_answer: str,
    rubric: str = "答案须准确覆盖概念定义、典型应用与至少一个易错点。",
    threshold: float = DEFAULT_THRESHOLD,
) -> GradeVerdict:
    """Grade one answer, preferring LLM, falling back to keyword overlap.

    Never raises — a broken LLM call yields a fallback verdict so the quiz loop
    keeps moving. Callers that need strict LLM grading can check ``method``.
    """
    if not learner_answer.strip():
        return GradeVerdict(False, 0.0, "未作答", "fallback")

    try:
        verdict = await _grade_with_llm(
            knowledge_point_id=knowledge_point_id,
            question=question,
            reference_answer=reference_answer,
            learner_answer=learner_answer,
            rubric=rubric,
            threshold=threshold,
        )
        if verdict is not None:
            return verdict
    except Exception as exc:  # noqa: BLE001
        # LLM configured but unusable (no key / network / parse error), or any
        # other failure — fall back so the quiz loop never breaks on a flaky
        # model. Logged at debug for visibility.
        log.debug("LLM grading unavailable (%s), using fallback", exc)

    score = _fallback_score(reference_answer, learner_answer)
    return GradeVerdict(
        is_correct=score >= threshold,
        score=score,
        rationale=f"关键词重合度 {score:.0%}(无 LLM 时的回退判定)",
        method="fallback",
    )


async def _grade_with_llm(
    *,
    knowledge_point_id: str,
    question: str,
    reference_answer: str,
    learner_answer: str,
    rubric: str,
    threshold: float,
) -> GradeVerdict | None:
    """Call the LLM and parse the JSON verdict. Returns None if unavailable."""
    if llm_client.resolve_model() is None:
        return None  # no LLM configured — let the caller fall back

    prompt = _USER_TEMPLATE.format(
        kp=knowledge_point_id,
        question=question,
        reference=reference_answer,
        rubric=rubric,
        answer=learner_answer,
        threshold=threshold,
    )
    raw = await llm_client.chat(
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": prompt},
        ],
        temperature=0.0,
        max_tokens=200,
        response_format={"type": "json_object"},
    )
    return _parse_verdict(raw, threshold)


def _parse_verdict(raw: str, threshold: float) -> GradeVerdict | None:
    """Parse the LLM's JSON response robustly (tolerate code fences / prose)."""
    if not raw:
        return None
    # Strip markdown code fences if present.
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to find the first {...} block.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    score = float(data.get("score", 0.0))
    score = max(0.0, min(1.0, score))
    is_correct = bool(data.get("is_correct", score >= threshold))
    rationale = str(data.get("rationale", "")).strip() or "LLM 判定"
    return GradeVerdict(is_correct=is_correct, score=score, rationale=rationale, method="llm")


def _fallback_score(reference: str, answer: str) -> float:
    """Jaccard similarity over CJK-aware token bigrams.

    Plain word splitting is useless for Chinese (no spaces), so we tokenize by
    character bigrams — works acceptably for short reference answers and is
    fully deterministic. For English, falls back to whitespace tokens.
    """
    ref_tokens = _tokenize(reference)
    ans_tokens = _tokenize(answer)
    if not ref_tokens:
        return 0.0
    if not ans_tokens:
        return 0.0
    intersection = len(ref_tokens & ans_tokens)
    union = len(ref_tokens | ans_tokens)
    return intersection / union if union else 0.0


def _tokenize(text: str) -> set[str]:
    """CJK-aware tokenization: char-bigrams for CJK, words for Latin."""
    text = text.strip().lower()
    # If the text is mostly CJK, use character bigrams.
    cjk = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    if cjk >= len(text) * 0.3 and len(text) >= 2:
        return {text[i : i + 2] for i in range(len(text) - 1)}
    # Latin: word tokens.
    return {w for w in re.split(r"\W+", text) if len(w) >= 2}


__all__ = ["DEFAULT_THRESHOLD", "GradeVerdict", "grade_answer"]
