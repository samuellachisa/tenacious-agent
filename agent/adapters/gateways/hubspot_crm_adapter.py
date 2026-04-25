"""HubSpot CRM adapter implementing CRMRepository port."""

from __future__ import annotations

from typing import Any

from agent.domain.entities.prospect import Contact
from agent.domain.ports.crm_repository import CRMRepository
from agent.integrations import hubspot_client


class HubSpotCRMAdapter(CRMRepository):
    """Adapter for HubSpot CRM."""
    
    async def get_contact(self, email: str) -> Contact | None:
        """Get contact by email."""
        result = await hubspot_client.get_contact_by_email(email)
        if not result:
            return None
        
        props = result.get("properties", {})
        return Contact(
            email=props.get("email", email),
            first_name=props.get("firstname", ""),
            last_name=props.get("lastname", ""),
            company=props.get("company", ""),
            phone=props.get("phone"),
            stage=props.get("hs_lead_status", "new"),
            properties=props,
        )
    
    async def create_or_update_contact(self, properties: dict[str, Any]) -> None:
        """Create or update a contact."""
        await hubspot_client.create_or_update_contact(properties)
    
    async def update_stage(self, email: str, stage: str) -> None:
        """Update contact lifecycle stage."""
        await hubspot_client.update_contact_stage(email, stage)
    
    async def create_deal(
        self,
        contact_email: str,
        company: str,
        segment: str,
        acv_estimate: int,
    ) -> None:
        """Create a deal in the CRM."""
        await hubspot_client.create_deal(
            contact_email=contact_email,
            company=company,
            segment=segment,
            acv_estimate=acv_estimate,
        )
