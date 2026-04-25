"""MailerSend adapter implementing EmailGateway port."""

from __future__ import annotations

from typing import Any

from agent.domain.ports.email_gateway import EmailGateway
from agent.integrations import mailersend_client


class MailerSendAdapter(EmailGateway):
    """Adapter for MailerSend email service."""
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        text: str,
        html: str,
        reply_to: str | None = None,
    ) -> dict[str, Any]:
        """Send an email."""
        return await mailersend_client.send_email(
            to_email=to_email,
            subject=subject,
            text=text,
            html=html,
            reply_to=reply_to,
        )
