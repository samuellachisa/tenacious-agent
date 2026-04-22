"""
Tenacious Agent — FastAPI application entry point.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr

load_dotenv()

app = FastAPI(
    title="Tenacious Agent",
    description="B2B lead generation and conversion system for Tenacious Consulting",
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class ProspectRequest(BaseModel):
    company_name: str
    contact_email: str
    contact_first_name: str
    contact_last_name: str
    phone_number: str | None = None
    timezone: str = "UTC"


class EmailReplyWebhook(BaseModel):
    from_email: str
    from_name: str | None = None
    company_name: str | None = None
    message_preview: str | None = None
    phone_number: str | None = None


class EmailEventWebhook(BaseModel):
    type: str
    email: str | None = None
    message_id: str | None = None
    timestamp: str | None = None


class SmsWebhook(BaseModel):
    from_number: str
    to_number: str | None = None
    text: str
    date: str | None = None


class CalWebhook(BaseModel):
    triggerEvent: str
    payload: dict[str, Any]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health_check() -> dict[str, Any]:
    """Health check — returns service status and kill-switch state."""
    return {
        "status": "ok",
        "outbound_enabled": os.getenv("OUTBOUND_ENABLED", "false").lower() == "true",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "service": "tenacious-agent",
        "version": "1.0.0",
    }


@app.post("/webhook/email")
async def webhook_email(
    event: EmailEventWebhook,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle MailerSend delivery events: opened, clicked, delivered.
    Updates HubSpot contact stage accordingly.
    """
    from agent.langfuse_client import log_trace

    stage_map = {
        "opened": "email_opened",
        "clicked": "email_opened",
        "delivered": "outbound_sent",
    }

    event_type = event.type.lower()
    stage = stage_map.get(event_type)

    log_trace(
        "webhook_email_event",
        {
            "event_type": event_type,
            "email": event.email,
            "message_id": event.message_id,
            "mapped_stage": stage,
        },
    )

    if stage and event.email:
        background_tasks.add_task(_update_stage_bg, event.email, stage)

    return {
        "received": True,
        "event_type": event_type,
        "stage_update": stage,
        "email": event.email,
    }


@app.post("/webhook/email/reply")
async def webhook_email_reply(
    reply: EmailReplyWebhook,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Simulate an inbound email reply — triggers the full qualification pipeline.

    Steps:
    1. Update HubSpot contact stage to 'replied'
    2. Run enrichment if company_name provided
    3. Qualify prospect
    4. If qualified: find Cal.com slot + book discovery call
    5. Send confirmation email (kill-switch aware)
    6. Log all steps to Langfuse
    """
    from agent.langfuse_client import log_trace

    log_trace(
        "webhook_email_reply_received",
        {
            "from_email": reply.from_email,
            "from_name": reply.from_name,
            "company_name": reply.company_name,
        },
    )

    background_tasks.add_task(
        _handle_reply_pipeline,
        reply.from_email,
        reply.from_name or "",
        reply.company_name or "",
        reply.phone_number,
        reply.message_preview or "",
    )

    return {
        "received": True,
        "from_email": reply.from_email,
        "pipeline": "queued",
    }


@app.post("/webhook/sms")
async def webhook_sms(
    sms: SmsWebhook,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle Africa's Talking inbound SMS for warm lead scheduling.
    Parses scheduling intent and responds with confirmation.
    """
    from agent.langfuse_client import log_trace

    log_trace(
        "webhook_sms_received",
        {
            "from_number": sms.from_number,
            "text_preview": sms.text[:100],
        },
    )

    background_tasks.add_task(
        _handle_sms_scheduling,
        sms.from_number,
        sms.text,
    )

    return {
        "received": True,
        "from_number": sms.from_number,
        "action": "scheduling_queued",
    }


@app.post("/webhook/cal")
async def webhook_cal(
    event: CalWebhook,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Handle Cal.com BOOKING_CREATED event.
    Updates HubSpot contact stage to 'call_booked' and creates a deal.
    """
    from agent.langfuse_client import log_trace

    log_trace(
        "webhook_cal_received",
        {
            "trigger_event": event.triggerEvent,
            "payload_keys": list(event.payload.keys()),
        },
    )

    if event.triggerEvent == "BOOKING_CREATED":
        background_tasks.add_task(_handle_cal_booking, event.payload)

    return {
        "received": True,
        "trigger_event": event.triggerEvent,
        "action": "booking_processing_queued",
    }


@app.post("/prospect")
async def prospect_endpoint(
    req: ProspectRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """
    Trigger the full enrichment + qualification + outbound pipeline for one company.

    Steps:
    1. Run enrichment pipeline
    2. Qualify prospect into ICP segment
    3. Create/update HubSpot contact with enrichment fields
    4. Send outbound email via MailerSend (kill-switch aware)
    5. Log every step to Langfuse
    """
    from agent.langfuse_client import log_trace

    log_trace(
        "prospect_endpoint_triggered",
        {
            "company_name": req.company_name,
            "contact_email": req.contact_email,
        },
    )

    background_tasks.add_task(
        _run_prospect_pipeline,
        req.company_name,
        req.contact_email,
        req.contact_first_name,
        req.contact_last_name,
        req.phone_number,
        req.timezone,
    )

    return {
        "status": "pipeline_queued",
        "company_name": req.company_name,
        "contact_email": req.contact_email,
        "message": "Enrichment and outbound pipeline started in background.",
    }


# ---------------------------------------------------------------------------
# Background task implementations
# ---------------------------------------------------------------------------

async def _run_prospect_pipeline(
    company_name: str,
    contact_email: str,
    first_name: str,
    last_name: str,
    phone_number: str | None,
    tz: str,
) -> None:
    """Full prospect pipeline: enrich → qualify → CRM → email."""
    from agent.enrichment import run_enrichment_pipeline
    from agent.hubspot_client import create_or_update_contact, update_contact_stage
    from agent.langfuse_client import log_trace
    from agent.mailersend_client import send_email
    from agent.qualifier import qualify_prospect

    # Step 1: Enrichment
    log_trace("pipeline_step", {"step": "enrichment_start", "company": company_name})
    enrichment = await run_enrichment_pipeline(company_name)

    # Step 2: Qualification
    log_trace("pipeline_step", {"step": "qualification_start", "company": company_name})
    qualification = qualify_prospect(enrichment)

    # Step 3: HubSpot contact
    log_trace("pipeline_step", {"step": "hubspot_upsert", "company": company_name})
    ai_maturity = enrichment.get("ai_maturity", {})
    hubspot_props = {
        "email": contact_email,
        "firstname": first_name,
        "lastname": last_name,
        "company": company_name,
        "icp_segment": qualification.get("segment") or "not_qualified",
        "ai_maturity_score": str(ai_maturity.get("score", 0)),
        "enrichment_timestamp": enrichment.get("enriched_at", ""),
        "lifecyclestage": "lead",
        "hs_lead_status": "outbound_sent" if qualification.get("qualified") else "not_qualified",
    }
    if phone_number:
        hubspot_props["phone"] = phone_number

    await create_or_update_contact(hubspot_props)

    if not qualification.get("qualified"):
        log_trace(
            "pipeline_not_qualified",
            {"company": company_name, "reason": qualification.get("reason")},
        )
        return

    # Step 4: Send outbound email
    log_trace("pipeline_step", {"step": "email_send", "company": company_name})
    subject = _build_email_subject(qualification, company_name)
    pitch = qualification.get("pitch_language", "")
    text_body = _build_email_text(first_name, company_name, pitch, qualification)
    html_body = _build_email_html(first_name, company_name, pitch, qualification)

    email_result = await send_email(
        to_email=contact_email,
        subject=subject,
        text=text_body,
        html=html_body,
        reply_to=os.getenv("MAILERSEND_FROM_EMAIL", "outbound@tenacious.consulting"),
    )

    log_trace(
        "pipeline_complete",
        {
            "company": company_name,
            "segment": qualification.get("segment"),
            "confidence": qualification.get("confidence"),
            "acv_estimate": qualification.get("acv_estimate"),
            "email_status": email_result.get("status"),
            "manual_review": qualification.get("manual_review", False),
        },
    )


async def _handle_reply_pipeline(
    from_email: str,
    from_name: str,
    company_name: str,
    phone_number: str | None,
    message_preview: str,
) -> None:
    """Reply pipeline: stage update → enrich → qualify → book call → confirm."""
    from agent.calcom_client import book_discovery_call, find_available_slot
    from agent.hubspot_client import create_or_update_contact, update_contact_stage
    from agent.langfuse_client import log_trace
    from agent.mailersend_client import send_email
    from agent.qualifier import qualify_prospect

    # Step 1: Update stage to replied
    log_trace("reply_pipeline_step", {"step": "stage_update", "email": from_email})
    await update_contact_stage(from_email, "replied")

    # Step 2: Enrichment (if company known)
    enrichment: dict[str, Any] = {}
    if company_name:
        from agent.enrichment import run_enrichment_pipeline

        log_trace("reply_pipeline_step", {"step": "enrichment", "company": company_name})
        enrichment = await run_enrichment_pipeline(company_name)
    else:
        enrichment = {"company": from_email.split("@")[-1].split(".")[0]}

    # Step 3: Qualify
    log_trace("reply_pipeline_step", {"step": "qualification", "email": from_email})
    qualification = qualify_prospect(enrichment)

    if not qualification.get("qualified"):
        log_trace(
            "reply_pipeline_not_qualified",
            {"email": from_email, "reason": qualification.get("reason")},
        )
        return

    # Step 4: Find Cal.com slot + book
    log_trace("reply_pipeline_step", {"step": "cal_booking", "email": from_email})
    slot = await find_available_slot(days_ahead=7)
    if not slot:
        log_trace("reply_pipeline_no_slot", {"email": from_email})
        return

    name_parts = from_name.split(" ", 1) if from_name else ["", ""]
    first_name = name_parts[0] or "there"

    booking = await book_discovery_call(
        name=from_name or from_email,
        email=from_email,
        slot=slot,
        timezone="UTC",
    )

    # Step 5: Update HubSpot stage to call_booked
    await update_contact_stage(from_email, "call_booked")

    # Step 6: Send confirmation email
    log_trace("reply_pipeline_step", {"step": "confirmation_email", "email": from_email})
    slot_friendly = _format_slot(slot)
    confirm_text = (
        f"Hi {first_name},\n\n"
        f"Thanks for getting back to us. Your discovery call with Tenacious Consulting "
        f"is confirmed for {slot_friendly}.\n\n"
        f"We'll send a calendar invite to {from_email} shortly.\n\n"
        f"Looking forward to speaking with you.\n\n"
        f"Best,\nTenacious Consulting Team"
    )
    confirm_html = (
        f"<p>Hi {first_name},</p>"
        f"<p>Thanks for getting back to us. Your discovery call with "
        f"<strong>Tenacious Consulting</strong> is confirmed for "
        f"<strong>{slot_friendly}</strong>.</p>"
        f"<p>We'll send a calendar invite to {from_email} shortly.</p>"
        f"<p>Looking forward to speaking with you.</p>"
        f"<p>Best,<br>Tenacious Consulting Team</p>"
    )

    await send_email(
        to_email=from_email,
        subject="Your Discovery Call is Confirmed — Tenacious Consulting",
        text=confirm_text,
        html=confirm_html,
    )

    # Step 7: SMS if phone available (warm lead)
    if phone_number:
        from agent.sms_client import send_scheduling_sms

        await send_scheduling_sms(
            to_number=phone_number,
            prospect_name=first_name,
            slot=slot,
        )

    log_trace(
        "reply_pipeline_complete",
        {
            "email": from_email,
            "company": company_name,
            "slot": slot,
            "booking_status": booking.get("status"),
            "segment": qualification.get("segment"),
        },
    )


async def _handle_sms_scheduling(from_number: str, text: str) -> None:
    """Handle inbound SMS — parse scheduling intent and respond."""
    from agent.langfuse_client import log_trace
    from agent.sms_client import send_sms

    text_lower = text.lower()
    log_trace("sms_scheduling_received", {"from": from_number, "text": text[:100]})

    # Parse scheduling keywords
    if any(kw in text_lower for kw in ["schedule", "book", "call", "meeting", "yes", "confirm"]):
        from agent.calcom_client import find_available_slot

        slot = await find_available_slot(days_ahead=5)
        slot_friendly = _format_slot(slot) if slot else "soon"

        response_msg = (
            f"Great! Your discovery call with Tenacious Consulting is being scheduled "
            f"for {slot_friendly}. You'll receive a calendar invite by email shortly."
        )
        log_trace("sms_scheduling_intent_matched", {"from": from_number, "slot": slot})
    elif any(kw in text_lower for kw in ["stop", "unsubscribe", "opt out", "remove"]):
        response_msg = (
            "You've been unsubscribed from Tenacious Consulting SMS. "
            "Reply START to re-subscribe."
        )
        log_trace("sms_opt_out", {"from": from_number})
    else:
        response_msg = (
            "Hi, this is Tenacious Consulting. Reply SCHEDULE to book a discovery call "
            "or STOP to opt out."
        )
        log_trace("sms_unrecognised", {"from": from_number, "text": text[:100]})

    await send_sms(from_number, response_msg)


async def _handle_cal_booking(payload: dict[str, Any]) -> None:
    """Process Cal.com BOOKING_CREATED — update HubSpot contact and create deal."""
    from agent.hubspot_client import create_deal, update_contact_stage
    from agent.langfuse_client import log_trace

    attendees = payload.get("attendees", [])
    if not attendees:
        log_trace("cal_booking_no_attendees", {"payload_keys": list(payload.keys())})
        return

    attendee = attendees[0]
    email = attendee.get("email", "")
    name = attendee.get("name", "")
    company = payload.get("title", "").replace("Discovery Call", "").strip(" —-")

    if not email:
        log_trace("cal_booking_no_email", {"payload": payload})
        return

    # Update HubSpot stage
    await update_contact_stage(email, "call_booked")

    # Create deal
    slot = payload.get("startTime", "")
    await create_deal(
        contact_email=email,
        company=company or name,
        segment="discovery_call",
        acv_estimate=75_000,
    )

    log_trace(
        "cal_booking_processed",
        {
            "email": email,
            "name": name,
            "company": company,
            "slot": slot,
        },
    )


async def _update_stage_bg(email: str, stage: str) -> None:
    """Background task wrapper for HubSpot stage update."""
    from agent.hubspot_client import update_contact_stage

    await update_contact_stage(email, stage)


# ---------------------------------------------------------------------------
# Email content builders
# ---------------------------------------------------------------------------

def _build_email_subject(qualification: dict, company_name: str) -> str:
    segment = qualification.get("segment", "")
    subject_map = {
        "recently_funded": f"Scaling {company_name}'s engineering team post-funding",
        "cost_restructuring": f"Flexible engineering talent for {company_name}",
        "leadership_transition": f"Quick-start engineering support for {company_name}",
        "capability_gap": f"AI/ML talent for {company_name}'s roadmap",
    }
    return subject_map.get(segment, f"Engineering talent partnership — {company_name}")


def _build_email_text(
    first_name: str,
    company_name: str,
    pitch: str,
    qualification: dict,
) -> str:
    segment_name = qualification.get("segment_name", "")
    acv = qualification.get("acv_estimate", 0)
    return (
        f"Hi {first_name},\n\n"
        f"{pitch}\n\n"
        f"Tenacious Consulting places senior engineers and AI/ML specialists "
        f"directly within your team — typically within 2 weeks.\n\n"
        f"Would you have 20 minutes this week for a quick discovery call?\n\n"
        f"Best,\nTenacious Consulting Team\n\n"
        f"---\n"
        f"Segment: {segment_name} | Est. ACV: ${acv:,}\n"
        f"Unsubscribe: reply with UNSUBSCRIBE"
    )


def _build_email_html(
    first_name: str,
    company_name: str,
    pitch: str,
    qualification: dict,
) -> str:
    pitch_html = pitch.replace("\n\n", "</p><p>").replace("\n", "<br>")
    return (
        f"<p>Hi {first_name},</p>"
        f"<p>{pitch_html}</p>"
        f"<p>Tenacious Consulting places senior engineers and AI/ML specialists "
        f"directly within your team — typically within 2 weeks.</p>"
        f"<p>Would you have 20 minutes this week for a quick discovery call?</p>"
        f"<p>Best,<br><strong>Tenacious Consulting Team</strong></p>"
        f"<hr><small>To unsubscribe, reply with UNSUBSCRIBE.</small>"
    )


def _format_slot(slot: str | None) -> str:
    if not slot:
        return "a time to be confirmed"
    try:
        dt = datetime.fromisoformat(slot.replace("Z", "+00:00"))
        return dt.strftime("%A, %B %d at %I:%M %p UTC")
    except Exception:
        return slot
