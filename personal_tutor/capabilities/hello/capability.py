"""``personal_hello`` capability implementation."""

from __future__ import annotations

from deeptutor.core.capability_protocol import BaseCapability, CapabilityManifest
from deeptutor.core.context import UnifiedContext
from deeptutor.core.stream_bus import StreamBus

from personal_tutor import __version__ as pt_version
from personal_tutor import MIN_DEEPTUTOR_VERSION
from personal_tutor.domains import get_registry


def _build_report(user_message: str) -> str:
    """Compose a short diagnostic report.

    Importing :mod:`personal_tutor.domains` here (not at module top) keeps the
    capability instantiable even if a domain registry implementation raises —
    the ``try`` below degrades gracefully.
    """
    lines = [
        f"# PersonalTutor v{pt_version} is online",
        "",
        f"- Min DeepTutor version: {MIN_DEEPTUTOR_VERSION}",
    ]
    if user_message:
        lines.append(f"- Echo: {user_message}")
    try:
        domains = get_registry().all()
        if domains:
            lines.append("")
            lines.append("## Registered learning domains")
            for d in domains:
                # knowledge_graph() is a method (lazy build); call it once.
                kp_count = len(d.knowledge_graph().all_points())
                lines.append(f"- **{d.name}** (`{d.domain_id}`) — {kp_count} knowledge points")
        else:
            lines.append("- Domains: (none registered yet)")
    except Exception as exc:  # pragma: no cover - defensive
        lines.append(f"- Domains: registry unavailable ({exc!r})")
    return "\n".join(lines)


class HelloCapability(BaseCapability):
    """A trivial capability that verifies plugin injection end-to-end."""

    manifest = CapabilityManifest(
        name="personal_hello",
        description=(
            "PersonalTutor smoke-test capability. Emits a status report and "
            "confirms the plugin discovery chain (deeptutor.plugins.loader -> "
            "personal_tutor.plugins) is wired up."
        ),
        stages=["responding"],
        tools_used=[],
        cli_aliases=["phello"],
    )

    async def run(self, context: UnifiedContext, stream: StreamBus) -> None:
        async with stream.stage("responding", source=self.manifest.name):
            report = _build_report(getattr(context, "user_message", "") or "")
            await stream.content(report, source=self.manifest.name, stage="responding")
        await stream.result(
            {
                "capability": self.manifest.name,
                "version": pt_version,
                "ok": True,
            },
            source=self.manifest.name,
        )


__all__ = ["HelloCapability"]
