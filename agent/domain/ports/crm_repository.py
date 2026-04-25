"""CRM repository port for contact management."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent.domain.entities.prospect import Contact


class CRMRepository(ABC):
    """Port for CRM operations."""
    
    @abstractmethod
    async def get_contact(self, email: str) -> Contact | None:
        """Get contact by email."""
        pass
    
    @abstractmethod
    async def create_or_update_contact(self, properties: dict[str, Any]) -> None:
        """Create or update a contact."""
        pass
    
    @abstractmethod
    async def update_stage(self, email: str, stage: str) -> None:
        """Update contact lifecycle stage."""
        pass
    
    @abstractmethod
    async def create_deal(
        self,
        contact_email: str,
        company: str,
        segment: str,
        acv_estimate: int,
    ) -> None:
        """Create a deal in the CRM."""
        pass
