"""SMS adapter implementing SMSGateway port."""

from __future__ import annotations

from typing import Any

from agent.domain.ports.sms_gateway import SMSGateway
from agent.integrations import sms_client


class SMSAdapter(SMSGateway):
    """Adapter for Africa's Talking SMS service."""
    
    async def send_sms(
        self,
        to_number: str,
        message: str,
        contact_email: str | None = None,
        skip_warm_check: bool = False,
    ) -> dict[str, Any]:
        """Send an SMS message."""
        return await sms_client.send_sms(
            to_number=to_number,
            message=message,
            contact_email=contact_email,
            skip_warm_check=skip_warm_check,
        )
    
    async def send_scheduling_sms(
        self,
        to_number: str,
        prospect_name: str,
        slot: str,
        contact_email: str,
    ) -> dict[str, Any]:
        """Send a scheduling confirmation SMS."""
        return await sms_client.send_scheduling_sms(
            to_number=to_number,
            prospect_name=prospect_name,
            slot=slot,
            contact_email=contact_email,
        )
