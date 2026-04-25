"""Langfuse adapter implementing Observability port."""

from __future__ import annotations

from typing import Any

from agent.domain.ports.observability import Observability
from agent.integrations import langfuse_client


class LangfuseAdapter(Observability):
    """Adapter for Langfuse observability."""
    
    def log_trace(self, event: str, data: dict[str, Any]) -> None:
        """Log a trace event."""
        langfuse_client.log_trace(event, data)
