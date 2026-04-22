"""
Africa's Talking SMS client — sandbox mode, warm leads only.
Kill switch: OUTBOUND_ENABLED=false routes all SMS to sink.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from agent.langfuse_client import log_trace

load_dotenv()


def _outbound_enabled() -> bool:
    return os.getenv("OUTBOUND_ENABLED", "false").lower() == "true"


def _get_sms_service():
    """Initialise Africa's Talking SDK and return the SMS service."""
    import africastalking  # type: ignore

    username = os.getenv("AT_USERNAME", "sandbox")
    api_key = os.getenv("AT_API_KEY", "")
    africastalking.initialize(username, api_key)
    return africastalking.SMS


async def send_sms(to_number: str, message: str) -> dict[str, Any]:
    """
    Send an SMS via Africa's Talking sandbox.

    Only called for warm leads (prospects who have already replied by email).
    Kill switch: when OUTBOUND_ENABLED=false the message is routed to sink.
    """
    shortcode = os.getenv("AT_SHORTCODE", "15629")

    if not _outbound_enabled():
        sink_result = {
            "status": "sink",
            "to": to_number,
            "message": message,
            "sink_reason": "OUTBOUND_ENABLED=false",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        print(f"[SINK] SMS to={to_number} message='{message[:60]}...' (outbound disabled)")
        log_trace(
            "sms_sink",
            {
                "to": to_number,
                "message_preview": message[:120],
                "reason": "OUTBOUND_ENABLED=false",
            },
        )
        return sink_result

    try:
        sms = _get_sms_service()
        response = sms.send(message, [to_number], shortcode)
        result = {
            "status": "sent",
            "to": to_number,
            "at_response": response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        log_trace("sms_sent", {"to": to_number, "response": str(response)})
        return result

    except Exception as exc:
        error_result = {
            "status": "error",
            "to": to_number,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        log_trace("sms_error", {"to": to_number, "error": str(exc)})
        return error_result


async def send_scheduling_sms(
    to_number: str,
    prospect_name: str,
    slot: str,
) -> dict[str, Any]:
    """
    Send a discovery call scheduling confirmation SMS to a warm lead.

    Args:
        to_number: E.164 phone number, e.g. +254712345678
        prospect_name: First name of the prospect
        slot: ISO 8601 datetime string for the booked slot

    Returns:
        dict with status, to, slot, and AT response or sink info
    """
    try:
        from datetime import datetime as dt

        slot_dt = dt.fromisoformat(slot.replace("Z", "+00:00"))
        friendly_time = slot_dt.strftime("%A %b %d at %I:%M %p UTC")
    except Exception:
        friendly_time = slot

    message = (
        f"Hi {prospect_name}, your discovery call with Tenacious Consulting "
        f"is confirmed for {friendly_time}. "
        f"A calendar invite has been sent to your email. "
        f"Reply STOP to opt out."
    )

    result = await send_sms(to_number, message)
    result["slot"] = slot
    result["prospect_name"] = prospect_name
    log_trace(
        "scheduling_sms",
        {
            "to": to_number,
            "prospect_name": prospect_name,
            "slot": slot,
            "status": result.get("status"),
        },
    )
    return result
