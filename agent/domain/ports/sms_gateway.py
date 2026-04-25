"""SMS gateway port for sending SMS messages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class SMSGateway(ABC):
    """Port for SMS operations."""
    
    @abstractmethod
    async def send_sms(
        self,
        to_number: str,
        message: str,
        contact_email: str | None = None,
        skip_warm_check: bool = False,
    ) -> dict[str, Any]:
        """Send an SMS message."""
        pass
    
    @abstractmethod
    async def send_scheduling_sms(
        self,
        to_number: str,
        prospect_name: str,
        slot: str,
        contact_email: str,
    ) -> dict[str, Any]:
        """Send a scheduling confirmation SMS."""
        pass
