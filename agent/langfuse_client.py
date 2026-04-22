"""
Langfuse observability client — singleton wrapper.
Every pipeline event is traced here. Errors are non-blocking.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_langfuse_instance = None


def get_langfuse():
    """Return a singleton Langfuse instance, initialised lazily."""
    global _langfuse_instance
    if _langfuse_instance is not None:
        return _langfuse_instance

    try:
        from langfuse import Langfuse  # type: ignore

        _langfuse_instance = Langfuse(
            public_key=os.getenv("LANGFUSE_PUBLIC_KEY", ""),
            secret_key=os.getenv("LANGFUSE_SECRET_KEY", ""),
            host=os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com"),
        )
    except Exception as exc:  # pragma: no cover
        print(f"[Langfuse] init error (non-fatal): {exc}")
        _langfuse_instance = _NoopLangfuse()

    return _langfuse_instance


def log_trace(event_name: str, metadata: dict[str, Any]) -> None:
    """
    Create a Langfuse trace for a pipeline event.
    Non-blocking — exceptions are printed but never raised.
    """
    try:
        lf = get_langfuse()
        enriched = {
            **metadata,
            "logged_at": datetime.now(timezone.utc).isoformat(),
            "service": "tenacious-agent",
        }
        trace = lf.trace(name=event_name, metadata=enriched)
        trace.update(output=enriched)
    except Exception as exc:  # pragma: no cover
        print(f"[Langfuse] log_trace error (non-fatal): {exc}")


def log_llm_call(
    prompt: str,
    response: str,
    model: str,
    cost_usd: float,
) -> None:
    """
    Log an LLM generation to Langfuse for cost attribution.
    Non-blocking — exceptions are printed but never raised.
    """
    try:
        lf = get_langfuse()
        trace = lf.trace(
            name="llm_call",
            metadata={
                "model": model,
                "cost_usd": cost_usd,
                "logged_at": datetime.now(timezone.utc).isoformat(),
                "service": "tenacious-agent",
            },
        )
        trace.generation(
            name="llm_generation",
            model=model,
            input=prompt,
            output=response,
            usage={
                "total_cost": cost_usd,
            },
        )
    except Exception as exc:  # pragma: no cover
        print(f"[Langfuse] log_llm_call error (non-fatal): {exc}")


class _NoopLangfuse:
    """Fallback no-op when Langfuse credentials are missing or SDK fails."""

    def trace(self, **kwargs):
        return _NoopTrace()

    def flush(self):
        pass


class _NoopTrace:
    def update(self, **kwargs):
        pass

    def generation(self, **kwargs):
        pass

    def span(self, **kwargs):
        return self
