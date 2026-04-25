"""Observability port for logging and tracing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class Observability(ABC):
    """Port for observability operations."""
    
    @abstractmethod
    def log_trace(self, event: str, data: dict[str, Any]) -> None:
        """Log a trace event."""
        pass
