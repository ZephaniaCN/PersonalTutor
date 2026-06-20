"""Aggregate BKT state into a learner profile.

This is the bridge between the numeric BKT engine and the human/LLM-facing
"who is this learner" picture. It produces two artifacts from the same data:

1. A **structured profile** (``learning_profile.json``) — machine-readable,
   consumed by the frontend and the roadmap planner. Per-KP mastery,
   weak points, coverage, and a coarse level label.
2. A **Memory L3 ``profile`` markdown** — human/LLM-readable, mirrored into
   DeepTutor's Memory system so DeepTutor's own capabilities (chat, mastery
   path) automatically pick up the learner's strengths/weaknesses. This is
   the "single source of truth" benefit: configure PersonalTutor, and every
   DeepTutor turn knows your level too.

The dual-write is intentional: structured JSON for our tools, markdown for
DeepTutor's Memory (which is markdown-native by design).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from personal_tutor.domains import KnowledgePoint, get_registry
from personal_tutor.learning.knowledge_tracing import KTState, KnowledgeTracer
from personal_tutor.learning.kt_store import KTStore
from personal_tutor.storage import json_store
from personal_tutor.storage.paths import profile_path

#: Mastery thresholds for the coarse level labels. Tuned so that "beginner"
#: means "mostly unseen or <40%", "proficient" means "consistently >70%".
_LEVELS = [
    (0.0, "未入门"),
    (0.4, "入门"),
    (0.7, "熟练"),
    (0.85, "精通"),
]


def _level_for(mastery: float) -> str:
    for threshold, label in reversed(_LEVELS):
        if mastery >= threshold:
            return label
    return _LEVELS[0][1]


def _kp_meta(domain_id: str) -> dict[str, KnowledgePoint]:
    """Name lookup for KPs in a domain (for readable profile output)."""
    try:
        graph = get_registry().require(domain_id).knowledge_graph()
        return {kp.id: kp for kp in graph.all_points()}
    except Exception:
        return {}


def build_profile(
    domain_id: str,
    store: KTStore,
    tracer: KnowledgeTracer,
    *,
    note: str | None = None,
) -> dict[str, Any]:
    """Build the structured learner profile for *domain_id*.

    Reads all KT states from *store*, scores every KP in the domain's graph
    (unseen KPs count as the prior), and returns a dict ready to persist.
    """
    states = store.get_all()
    meta = _kp_meta(domain_id)
    all_ids = list(meta.keys()) or list(states.keys())

    rows: list[dict[str, Any]] = []
    mastered = 0
    mastery_sum = 0.0
    for kp_id in all_ids:
        st = states.get(kp_id)
        mastery = tracer.mastery_of(st, kp_id)
        mastery_sum += mastery
        if mastery >= 0.7:
            mastered += 1
        kp = meta.get(kp_id)
        rows.append(
            {
                "knowledge_point_id": kp_id,
                "name": kp.name if kp else kp_id,
                "module_id": kp.module_id if kp else "",
                "mastery": round(mastery, 4),
                "level": _level_for(mastery),
                "attempts": st.attempts if st else 0,
                "correct": st.correct if st else 0,
            }
        )

    # Sort: weakest first — the most actionable view for a learner.
    rows.sort(key=lambda r: (r["mastery"], -r["attempts"]))

    coverage = len(states) / len(all_ids) if all_ids else 0.0
    avg_mastery = mastery_sum / len(all_ids) if all_ids else 0.0

    return {
        "domain_id": domain_id,
        "version": 1,
        "generated_at": _now(),
        "summary": {
            "total_knowledge_points": len(all_ids),
            "assessed": len(states),
            "coverage": round(coverage, 4),
            "average_mastery": round(avg_mastery, 4),
            "mastered": mastered,
            "overall_level": _level_for(avg_mastery),
        },
        "weak_points": [r for r in rows if r["mastery"] < 0.5][:10],
        "knowledge_points": rows,
        "note": note,
    }


def render_profile_markdown(profile: dict[str, Any]) -> str:
    """Render the structured profile as Memory-L3-friendly markdown.

    DeepTutor's Memory L3 ``profile`` slot is markdown with natural-language
    claims; this produces a compact, claim-rich summary an LLM can ground on.
    """
    s = profile.get("summary", {})
    lines = [
        f"# Learner Profile — {profile.get('domain_id', 'unknown')}",
        "",
        f"- 整体水平: **{s.get('overall_level', '?')}** "
        f"(平均掌握度 {s.get('average_mastery', 0):.2f})",
        f"- 已评估知识点: {s.get('assessed', 0)}/{s.get('total_knowledge_points', 0)} "
        f"(覆盖率 {s.get('coverage', 0):.0%})",
        f"- 已掌握(≥0.7): {s.get('mastered', 0)} 个",
        "",
    ]
    weak = profile.get("weak_points", [])
    if weak:
        lines.append("## 当前薄弱点(优先复习)")
        for w in weak[:5]:
            lines.append(
                f"- **{w.get('name', w.get('knowledge_point_id'))}**: "
                f"掌握度 {w.get('mastery', 0):.2f} ({w.get('level', '?')}), "
                f"历史 {w.get('correct', 0)}/{w.get('attempts', 0)} 正确"
            )
    else:
        lines.append("_尚无明显薄弱点(未评估或已掌握)。_")
    return "\n".join(lines)


def write_profile(
    domain_id: str,
    store: KTStore,
    tracer: KnowledgeTracer,
    *,
    note: str | None = None,
    mirror_to_memory: bool = True,
) -> dict[str, Any]:
    """Build, persist, and (optionally) mirror the profile.

    Returns the structured profile dict. When ``mirror_to_memory`` is True,
    also pushes a markdown rendering into DeepTutor Memory L3 ``profile`` so
    DeepTutor's native capabilities pick up the learner's state. Memory write
    failures are swallowed (logged) so a profile write never fails just
    because Memory is unavailable.
    """
    profile = build_profile(domain_id, store, tracer, note=note)
    json_store.write_json(profile_path(domain_id), profile)

    if mirror_to_memory:
        _mirror_to_memory(render_profile_markdown(profile))

    return profile


def _mirror_to_memory(markdown: str) -> None:
    """Best-effort write into DeepTutor Memory L3 ``profile``.

    Uses the public REST surface when a server is reachable, else falls back
    to writing the file directly under the Memory directory. Both paths are
    best-effort: PersonalTutor's structured profile is the source of truth;
    Memory is a convenience mirror.
    """
    try:
        # Direct file write — simplest and works in-process. The Memory L3
        # layout is <workspace>/memory/L3/profile.md (see deeptutor services).
        from personal_tutor.storage.paths import _workspace_root

        l3_dir = _workspace_root() / "memory" / "L3"
        l3_dir.mkdir(parents=True, exist_ok=True)
        (l3_dir / "profile.md").write_text(markdown, encoding="utf-8")
    except Exception:
        # Mirroring is opportunistic; never fail the profile write on it.
        import logging

        logging.getLogger(__name__).debug(
            "Could not mirror profile to Memory L3", exc_info=True
        )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


__all__ = [
    "build_profile",
    "render_profile_markdown",
    "write_profile",
]
