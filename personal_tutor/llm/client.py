"""LLM client — bridges PersonalTutor to DeepTutor's model configuration.

The cardinal rule here: **never read API keys ourselves**. We call DeepTutor's
:func:`deeptutor.services.llm.config.get_llm_config`, which resolves the active
model/catalog from ``data/user/settings/model_catalog.json`` (or a scoped
override set by a partner/capability). That keeps a single source of truth —
change the model once in DeepTutor Settings and every PersonalTutor chain
follows.

When DeepTutor is not installed or not configured, the helpers degrade
gracefully so capabilities can still emit a clear "configure LLM in DeepTutor
Settings" message instead of crashing at import time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ResolvedModel:
    """A snapshot of the LLM config PersonalTutor will call.

    Mirrors the subset of DeepTutor's ``LLMConfig`` that an OpenAI-compatible
    client needs. Kept as a plain dataclass so it can be passed around and
    logged without leaking the full config object.
    """

    model: str
    api_key: str
    base_url: str | None
    binding: str = "openai"

    @property
    def is_configured(self) -> bool:
        return bool(self.model and self.api_key)


def resolve_model() -> ResolvedModel | None:
    """Resolve the active model from DeepTutor's config.

    Returns ``None`` (rather than raising) when DeepTutor is unconfigured so
    callers can fall back to placeholder behaviour during demos/tests.
    """
    try:
        from deeptutor.services.llm.config import get_llm_config
    except Exception as exc:  # pragma: no cover - DeepTutor not importable
        logger.debug("DeepTutor LLM config unavailable: %r", exc)
        return None
    try:
        cfg = get_llm_config()
    except Exception as exc:
        logger.debug("DeepTutor LLM config not resolved: %r", exc)
        return None
    return ResolvedModel(
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.effective_url or cfg.base_url,
        binding=cfg.binding,
    )


def build_async_client():
    """Return an OpenAI-compatible ``AsyncOpenAI`` client.

    Uses DeepTutor's resolved config so there is exactly one place (DeepTutor
    Settings → Catalog) that owns the API key. Raises a clear
    :class:`RuntimeError` with remediation guidance when no model is set.
    """
    model = resolve_model()
    if model is None or not model.is_configured:
        raise RuntimeError(
            "No LLM configured. Open DeepTutor Settings → Catalog, set an "
            "active model + API key, then retry. PersonalTutor reuses "
            "DeepTutor's model_catalog.json and stores no keys of its own."
        )
    from openai import AsyncOpenAI  # DeepTutor already depends on `openai`

    kwargs: dict[str, Any] = {"api_key": model.api_key}
    if model.base_url:
        kwargs["base_url"] = model.base_url
    return AsyncOpenAI(**kwargs), model


async def chat(
    messages: list[dict[str, str]],
    *,
    temperature: float = 0.4,
    max_tokens: int = 1024,
    response_format: dict[str, str] | None = None,
) -> str:
    """One-shot chat completion against the DeepTutor-configured model.

    Thin convenience wrapper so call sites (chains, capabilities) don't each
    reconstruct a client. Returns the assistant message text.
    """
    client, model = build_async_client()
    try:
        kwargs: dict[str, Any] = {
            "model": model.model,
            "messages": messages,
            "temperature": temperature,
        }
        # Newer OpenAI models require max_completion_tokens; mirror DeepTutor's
        # helper to stay compatible across model families.
        try:
            from deeptutor.services.llm.config import get_token_limit_kwargs

            kwargs.update(get_token_limit_kwargs(model.model, max_tokens))
        except Exception:  # pragma: no cover - fall back to max_tokens
            kwargs["max_tokens"] = max_tokens
        if response_format is not None:
            kwargs["response_format"] = response_format
        resp = await client.chat.completions.create(**kwargs)
        return (resp.choices[0].message.content or "").strip()
    finally:
        await client.close()


__all__ = ["ResolvedModel", "resolve_model", "build_async_client", "chat"]
