"""
Africa's Talking SMS client — sandbox mode, warm leads only.

WARM LEAD POLICY:
-----------------
SMS is ONLY sent to prospects who have:
  1. Replied to an email (stage: replied, qualified, scheduled, or booked)
  2. Been validated as warm via is_warm_lead() check

This enforces channel gating: cold prospects receive email only, warm leads
receive SMS for scheduling confirmations.

Kill switch: TENACIOUS_OUTBOUND_ENABLED=false or OUTBOUND_ENABLED=false routes all SMS to sink.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx

from agent.utils.env_utils import outbound_enabled
from agent.integrations.langfuse_client import log_trace

# Stages that qualify as "warm lead" for SMS eligibility
WARM_LEAD_STAGES = {"replied", "qualified", "scheduled", "call_booked", "email_opened"}


def _outbound_enabled() -> bool:
    return outbound_enabled()


async def is_warm_lead(email_or_phone: str) -> bool:
    """
    Check if a contact is a warm lead (eligible for SMS).
    
    A warm lead has:
    - Replied to email (stage: replied or later)
    - OR opened/clicked an email (stage: email_opened)
    
    Returns True if contact is warm, False otherwise.
    """
    from agent.integrations.hubspot_client import get_contact_by_email
    
    try:
        # Try to fetch contact from HubSpot
        contact = await get_contact_by_email(email_or_phone)
        if not contact:
            log_trace("warm_lead_check_failed", {
                "identifier": email_or_phone,
                "reason": "contact_not_found",
            })
            return False
        
        stage = contact.get("properties", {}).get("hs_lead_status", "")
        is_warm = stage in WARM_LEAD_STAGES
        
        log_trace("warm_lead_check", {
            "identifier": email_or_phone,
            "stage": stage,
            "is_warm": is_warm,
        })
        
        return is_warm
        
    except Exception as exc:
        log_trace("warm_lead_check_error", {
            "identifier": email_or_phone,
            "error": str(exc),
        })
        # Fail closed: if we can't verify, don't send SMS
        return False


async def send_sms(
    to_number: str,
    message: str,
    contact_email: str | None = None,
    skip_warm_check: bool = False,
) -> dict[str, Any]:
    """
    Send an SMS via Africa's Talking sandbox.
    
    WARM LEAD ENFORCEMENT:
    ----------------------
    By default, validates that the contact is a warm lead before sending.
    Set skip_warm_check=True to bypass (use only for testing or admin messages).
    
    Args:
        to_number: E.164 phone number e.g. +254712345678
        message: SMS body (max 160 chars recommended)
        contact_email: Email to validate warm lead status (required unless skip_warm_check=True)
        skip_warm_check: Bypass warm lead validation (use sparingly)
    
    Kill switch: when OUTBOUND_ENABLED=false the message is routed to sink.
    """
    # Warm lead validation
    if not skip_warm_check:
        if not contact_email:
            log_trace("sms_rejected_no_email", {"to": to_number})
            return {
                "status": "rejected",
                "to": to_number,
                "reason": "contact_email required for warm lead validation",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        
        if not await is_warm_lead(contact_email):
            log_trace("sms_rejected_cold_lead", {
                "to": to_number,
                "email": contact_email,
            })
            return {
                "status": "rejected",
                "to": to_number,
                "reason": "contact is not a warm lead (must reply to email first)",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
    
    if not _outbound_enabled():
        print(f"[SINK] SMS to={to_number} message='{message[:60]}...' (outbound disabled)")
        log_trace("sms_sink", {
            "to": to_number,
            "message_preview": message[:120],
            "reason": "OUTBOUND_ENABLED=false",
        })
        return {
            "status": "sink",
            "to": to_number,
            "message": message,
            "sink_reason": "OUTBOUND_ENABLED=false",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    username = os.getenv("AT_USERNAME", "sandbox")
    api_key = os.getenv("AT_API_KEY", "")
    shortcode = os.getenv("AT_SHORTCODE", "")
    is_sandbox = username == "sandbox"

    # AT sandbox uses HTTP not HTTPS
    # AT production uses HTTPS
    # Allow override via env for testing or alternative endpoints
    url = os.getenv(
        "AT_API_URL",
        "https://api.sandbox.africastalking.com/version1/messaging"
        if is_sandbox
        else "https://api.africastalking.com/version1/messaging"
    )

    # Build payload — do NOT include from/shortcode for sandbox
    # AT sandbox rejects shortcode unless it is registered exactly
    data: dict[str, str] = {
        "username": username,
        "to": to_number,
        "message": message,
    }
    if shortcode and not is_sandbox:
        # Only include shortcode for production
        data["from"] = shortcode

    headers = {
        "apiKey": api_key,
        "Accept": "application/json",
        "Content-Type": "application/x-www-form-urlencoded",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0, verify=False) as client:
            response = await client.post(url, data=data, headers=headers)

            # AT returns 201 for success
            if response.status_code in (200, 201):
                print(f"[SMS] Sent to {to_number} — {response.status_code}")
                log_trace("sms_sent", {
                    "to": to_number,
                    "status": response.status_code,
                    "response": response.text[:200],
                })
                return {
                    "status": "sent",
                    "to": to_number,
                    "at_response": response.json(),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            else:
                print(f"[SMS ERROR] AT returned {response.status_code}: {response.text[:500]}")
                print(f"[SMS DEBUG] payload sent: {data}")
                log_trace("sms_error", {
                    "to": to_number,
                    "status": response.status_code,
                    "response": response.text[:200],
                })
                return {
                    "status": "error",
                    "to": to_number,
                    "error": f"AT error {response.status_code}: {response.text}",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

    except httpx.TimeoutException:
        print(f"[SMS ERROR] Timeout sending to {to_number}")
        log_trace("sms_error", {"to": to_number, "error": "timeout"})
        return {
            "status": "error",
            "to": to_number,
            "error": "Request timed out",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as exc:
        print(f"[SMS ERROR] {exc}")
        log_trace("sms_error", {"to": to_number, "error": str(exc)})
        return {
            "status": "error",
            "to": to_number,
            "error": str(exc),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def send_scheduling_sms(
    to_number: str,
    prospect_name: str,
    slot: str,
    contact_email: str,
) -> dict[str, Any]:
    """
    Send a discovery call scheduling confirmation SMS to a warm lead.
    
    WARM LEAD ENFORCEMENT:
    ----------------------
    Automatically validates that contact_email corresponds to a warm lead
    before sending. This is the primary SMS use case.

    Args:
        to_number: E.164 phone number e.g. +254712345678
        prospect_name: First name of the prospect
        slot: ISO 8601 datetime string for the booked slot
        contact_email: Email address for warm lead validation
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

    result = await send_sms(
        to_number=to_number,
        message=message,
        contact_email=contact_email,
        skip_warm_check=False,  # Enforce warm lead check
    )
    result["slot"] = slot
    result["prospect_name"] = prospect_name
    log_trace("scheduling_sms", {
        "to": to_number,
        "prospect_name": prospect_name,
        "slot": slot,
        "status": result.get("status"),
    })
    return result


async def handle_inbound_sms(from_number: str, message: str) -> dict[str, Any]:
    """
    Handle an inbound SMS from a warm lead.
    Routes to scheduling flow if message indicates interest.
    Returns action taken.
    """
    message_lower = message.lower().strip()

    scheduling_keywords = [
        "yes", "confirm", "schedule", "book", "available",
        "call", "meeting", "talk", "interested", "sure", "ok", "okay"
    ]
    opt_out_keywords = ["stop", "unsubscribe", "cancel", "no", "quit"]

    log_trace("sms_inbound_received", {
        "from": from_number,
        "message_preview": message[:100],
    })

    if any(kw in message_lower for kw in opt_out_keywords):
        print(f"[SMS] Opt-out received from {from_number}")
        log_trace("sms_opt_out", {"from": from_number})
        return {"action": "opt_out", "from": from_number}

    if any(kw in message_lower for kw in scheduling_keywords):
        print(f"[SMS] Scheduling intent detected from {from_number}")
        log_trace("sms_scheduling_intent", {
            "from": from_number,
            "message": message,
        })
        return {"action": "scheduling_triggered", "from": from_number}

    log_trace("sms_inbound_no_action", {"from": from_number})
    return {"action": "no_match", "from": from_number}


# ---------------------------------------------------------------------------
# Quick test when run directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    async def test():
        print("=" * 50)
        print("Testing SMS client")
        print("=" * 50)

        # Test sink mode
        print("\n1. Testing sink mode (OUTBOUND_ENABLED=false)...")
        os.environ["OUTBOUND_ENABLED"] = "false"
        result = await send_sms(
            to_number="+254700000000",
            message="Test message from Tenacious",
            skip_warm_check=True,  # Skip for testing
        )
        print(f"   Result: {result['status']} — {result.get('sink_reason', '')}")

        # Test outbound mode
        print("\n2. Testing outbound mode (OUTBOUND_ENABLED=true)...")
        os.environ["OUTBOUND_ENABLED"] = "true"
        result = await send_sms(
            to_number="+254700000000",
            message="Test message from Tenacious agent",
            skip_warm_check=True,  # Skip for testing
        )
        print(f"   Result: {result['status']}")
        if result["status"] == "error":
            print(f"   Error: {result['error']}")

        # Test scheduling SMS
        print("\n3. Testing scheduling SMS...")
        os.environ["OUTBOUND_ENABLED"] = "false"
        result = await send_scheduling_sms(
            to_number="+254700000000",
            prospect_name="Alex",
            slot="2026-04-25T10:00:00Z",
            contact_email="test@example.com",
        )
        print(f"   Result: {result['status']}")

        # Test inbound handling
        print("\n4. Testing inbound SMS handling...")
        result = await handle_inbound_sms("+254700000000", "Yes I want to book a call")
        print(f"   Action: {result['action']}")

        result = await handle_inbound_sms("+254700000000", "STOP")
        print(f"   Action: {result['action']}")

        print("\nDone.")

    asyncio.run(test())