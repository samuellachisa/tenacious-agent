"""
MailerSend email client with kill-switch support.
When TENACIOUS_OUTBOUND_ENABLED=false or OUTBOUND_ENABLED=false, all sends are routed to a local sink.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx

from agent.env_utils import outbound_enabled
from agent.langfuse_client import log_trace

MAILERSEND_API_URL = "https://api.mailersend.com/v1/email"


def _outbound_enabled() -> bool:
    return outbound_enabled()


async def send_email(
    to_email: str,
    subject: str,
    text: str,
    html: str,
    reply_to: str | None = None,
) -> dict[str, Any]:
    """
    Send a transactional email via MailerSend.

    Kill switch: when OUTBOUND_ENABLED=false the message is routed to a
    local sink — logged to Langfuse and printed to stdout.  No HTTP call
    is made.

    Returns a dict with keys: status, message_id (or sink), to, subject.
    """
    from_email = os.getenv("MAILERSEND_FROM_EMAIL", "outbound@tenacious.consulting")
    from_name = os.getenv("MAILERSEND_FROM_NAME", "Tenacious Consulting")
    api_key = os.getenv("MAILERSEND_API_KEY", "")

    payload: dict[str, Any] = {
        "from": {"email": from_email, "name": from_name},
        "to": [{"email": to_email}],
        "subject": subject,
        "text": text,
        "html": html,
    }
    if reply_to:
        payload["reply_to"] = {"email": reply_to}

    if not _outbound_enabled():
        sink_result = {
            "status": "sink",
            "message_id": None,
            "to": to_email,
            "subject": subject,
            "sink_reason": "OUTBOUND_ENABLED=false",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(f"[SINK] Email to={to_email} subject='{subject}' (outbound disabled)")
        log_trace(
            "email_sink",
            {
                "to": to_email,
                "subject": subject,
                "reason": "OUTBOUND_ENABLED=false",
            },
        )
        return sink_result

    # Live send
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                MAILERSEND_API_URL, json=payload, headers=headers
            )
            response.raise_for_status()
            message_id = response.headers.get("X-Message-Id", "unknown")
            result = {
                "status": "sent",
                "message_id": message_id,
                "to": to_email,
                "subject": subject,
                "http_status": response.status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            log_trace("email_sent", result)
            return result

    except httpx.HTTPStatusError as exc:
        error_result = {
            "status": "error",
            "message_id": None,
            "to": to_email,
            "subject": subject,
            "error": str(exc),
            "http_status": exc.response.status_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        log_trace("email_error", error_result)
        return error_result

    except Exception as exc:
        error_result = {
            "status": "error",
            "message_id": None,
            "to": to_email,
            "subject": subject,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        log_trace("email_error", error_result)
        return error_result
