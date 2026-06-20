"""``personal_quiz`` capability — CLI entry that fetches one adaptive question.

Grading happens through REST (``POST /api/v1/personal/quiz/{domain_id}/grade``)
because the answer comes from the client. This capability exists so the CLI
flow mirrors the diagnostic one and the plugin list shows PersonalTutor's
full surface.
"""

from __future__ import annotations

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus

from personal_tutor import __version__ as pt_version
from personal_tutor.capabilities.adaptive_quiz.quiz import next_question


class AdaptiveQuizCapability(BaseCapability):
    """Fetch the next adaptive question for a domain."""

    manifest = CapabilityManifest(
        name="personal_quiz",
        description=(
            "PersonalTutor adaptive quiz. Picks the learner's weakest knowledge "
            "point, scales difficulty to current mastery, and emits one question. "
            "Grade the answer via POST /api/v1/personal/quiz/{domain_id}/grade."
        ),
        stages=["selecting", "responding"],
        tools_used=[],
        cli_aliases=["pquiz"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        domain_id = (getattr(context, "user_message", "") or "").strip() or "programming"

        async with stream.stage("selecting", source=self.manifest.name):
            await stream.content(
                f"Selecting the next question for `{domain_id}` based on your profile...",
                source=self.manifest.name,
                stage="selecting",
            )

        result = await next_question(domain_id)

        async with stream.stage("responding", source=self.manifest.name):
            q = result.get("question", {})
            lines = [
                f"# Adaptive Question — {result.get('kp_name', result.get('knowledge_point_id'))}",
                "",
                f"- Knowledge point: `{result.get('knowledge_point_id')}`",
                f"- Current mastery: **{result.get('mastery', 0):.0%}**",
                f"- Difficulty: {result.get('difficulty')}",
                f"- Rationale: {result.get('rationale')}",
                "",
                "## Question",
                q.get("question", "(no question generated)"),
            ]
            await stream.content("\n".join(lines), source=self.manifest.name, stage="responding")

        await stream.result(
            {
                "capability": self.manifest.name,
                "version": pt_version,
                "knowledge_point_id": result.get("knowledge_point_id"),
                "difficulty": result.get("difficulty"),
                "question": q,
            },
            source=self.manifest.name,
        )


__all__ = ["AdaptiveQuizCapability"]
