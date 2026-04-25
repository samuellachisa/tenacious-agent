"""Email gateway port for sending emails."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class EmailGateway(ABC):
    """Port for email operations."""
    
    @abstractmethod
    async def send_email(
        self,
        to_email: str,
        subject: str,
        text: str,
        html: str,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send an email."""
        pass
