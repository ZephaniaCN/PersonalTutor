"""``personal_diagnostic`` capability — CLI/REPL entry to the diagnostic.

When invoked via ``deeptutor run personal_diagnostic "<domain_id>"``, this
prepares a diagnostic question set and streams it as content. Grading happens
through the REST endpoint (or a future ``--grade`` flag) because answers must
come from the client.

Kept intentionally thin: all logic lives in :mod:`diagnostic.diagnostic` so
the REST layer and the capability share one implementation.
"""

from __future__ import annotations

import asyncio
import json

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus

from personal_tutor import __version__ as pt_version
from personal_tutor.capabilities.diagnostic.diagnostic import prepare_diagnostic


class DiagnosticCapability(BaseCapability):
    """Prepares an entry diagnostic for a domain and streams the question set."""

    manifest = CapabilityManifest(
        name="personal_diagnostic",
        description=(
            "PersonalTutor entry diagnostic. Sample a domain's knowledge graph, "
            "generate one question per sampled knowledge point, and emit the "
            "question set as structured content. Submit answers via the "
            "POST /api/v1/personal/diagnostics/{domain_id}/grade endpoint."
        ),
        stages=["preparing", "responding"],
        tools_used=[],
        cli_aliases=["pdiag"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        # The user message is expected to be the domain_id (e.g. "programming").
        domain_id = (getattr(context, "user_message", "") or "").strip() or "programming"

        async with stream.stage("preparing", source=self.manifest.name):
            await stream.content(
                f"Preparing entry diagnostic for domain `{domain_id}`...",
                source=self.manifest.name,
                stage="preparing",
            )

        result = await prepare_diagnostic(domain_id)

        async with stream.stage("responding", source=self.manifest.name):
            lines = [
                f"# Entry Diagnostic — {domain_id}",
                "",
                f"- Questions: **{result['total_questions']}**",
                f"- Diagnostic id: `{result['diagnostic_id']}`",
                f"- Default difficulty: {result['blueprint']['default_difficulty']}",
                "",
                "## Questions",
            ]
            for i, q in enumerate(result["questions"], 1):
                lines.append(f"### Q{i}: {q.get('knowledge_point_id', '?')}")
                lines.append(q.get("question", ""))
                if q.get("options"):
                    lines.append("Options: " + " / ".join(q["options"]))
                lines.append("")

            await stream.content("\n".join(lines), source=self.manifest.name, stage="responding")

        await stream.result(
            {
                "capability": self.manifest.name,
                "version": pt_version,
                "diagnostic_id": result["diagnostic_id"],
                "total_questions": result["total_questions"],
                "questions": result["questions"],
            },
            source=self.manifest.name,
        )


__all__ = ["DiagnosticCapability"]
