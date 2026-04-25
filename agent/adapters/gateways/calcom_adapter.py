"""Cal.com adapter implementing SchedulingGateway port."""

from __future__ import annotations

from typing import Any

from agent.domain.ports.scheduling_gateway import SchedulingGateway
from agent.integrations import calcom_client


class CalComAdapter(SchedulingGateway):
    """Adapter for Cal.com scheduling service."""
    
    async def find_available_slot(self, days_ahead: int = 7) -> str | None:
        """Find an available calendar slot."""
        return await calcom_client.find_available_slot(days_ahead=days_ahead)
    
    async def book_discovery_call(
        self,
        name: str,
        email: str,
        slot: str,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        """Book a discovery call."""
        return await calcom_client.book_discovery_call(
            name=name,
            email=email,
            slot=slot,
            timezone=timezone,
        )
