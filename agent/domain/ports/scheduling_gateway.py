"""Scheduling gateway port for calendar operations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SchedulingGateway(ABC):
    """Port for scheduling operations."""
    
    @abstractmethod
    async def find_available_slot(self, days_ahead: int = 7) -> str | None:
        """Find an available calendar slot."""
        pass
    
    @abstractmethod
    async def book_discovery_call(
        self,
        name: str,
        email: str,
        slot: str,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """Book a discovery call."""
        pass
