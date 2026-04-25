"""
HubSpot CRM client — contacts and deals. FIXED VERSION.
All calls use Bearer token from HUBSPOT_ACCESS_TOKEN.
All calls are logged to Langfuse.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

from agent.integrations.langfuse_client import log_trace

load_dotenv()

# Internal stage → valid HubSpot hs_lead_status values
STAGE_TO_HS_STATUS = {
    "outbound_sent": "NEW",
    "email_opened": "OPEN",
    "replied": "CONNECTED",
    "call_booked": "IN_PROGRESS",
    "proposal_sent": "OPEN_DEAL",
}

STAGE_ORDER = list(STAGE_TO_HS_STATUS.keys())


def _hubspot_base() -> str:
    return os.getenv("HUBSPOT_API_URL", "https://api.hubapi.com")


def _headers() -> dict[str, str]:
    token = os.getenv("HUBSPOT_ACCESS_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


async def create_or_update_contact(properties: dict[str, Any]) -> dict[str, Any]:
    """
    Create a new HubSpot contact or update an existing one by email.
    Required fields: email, firstname, lastname, company.
    Optional enrichment fields: icp_segment, ai_maturity_score,
    enrichment_timestamp, lifecyclestage, hs_lead_status.
    """
    email = properties.get("email", "")
    existing = await get_contact_by_email(email)

    if existing:
        contact_id = existing["id"]
        result = await update_contact(contact_id, properties)
        result["operation"] = "updated"
        log_trace(
            "hubspot_contact_updated",
            {"email": email, "contact_id": contact_id},
        )
        return result

    result = await create_contact(properties)
    result["operation"] = "created"
    log_trace(
        "hubspot_contact_created",
        {"email": email},
    )
    return result


async def create_contact(properties: dict[str, Any]) -> dict[str, Any]:
    """Create a new HubSpot contact."""
    payload = {"properties": _sanitise_properties(properties)}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_hubspot_base()}/crm/v3/objects/contacts",
                json=payload,
                headers=_headers(),
            )
            response.raise_for_status()
            data = response.json()
            log_trace(
                "hubspot_create_contact_success",
                {"contact_id": data.get("id"), "email": properties.get("email")},
            )
            return data

    except httpx.HTTPStatusError as exc:
        error = {
            "status": "error",
            "error": exc.response.text,
            "http_status": exc.response.status_code,
        }
        log_trace("hubspot_create_contact_error", error)
        return error

    except Exception as exc:
        error = {"status": "error", "error": str(exc)}
        log_trace("hubspot_create_contact_error", error)
        return error


async def update_contact(
    contact_id: str, properties: dict[str, Any]
) -> dict[str, Any]:
    """Update an existing HubSpot contact by ID."""
    payload = {"properties": _sanitise_properties(properties)}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.patch(
                f"{_hubspot_base()}/crm/v3/objects/contacts/{contact_id}",
                json=payload,
                headers=_headers(),
            )
            response.raise_for_status()
            data = response.json()
            log_trace(
                "hubspot_update_contact_success",
                {"contact_id": contact_id},
            )
            return data

    except httpx.HTTPStatusError as exc:
        error = {
            "status": "error",
            "contact_id": contact_id,
            "error": exc.response.text,
            "http_status": exc.response.status_code,
        }
        log_trace("hubspot_update_contact_error", error)
        return error

    except Exception as exc:
        error = {"status": "error", "contact_id": contact_id, "error": str(exc)}
        log_trace("hubspot_update_contact_error", error)
        return error


async def get_contact_by_email(email: str) -> dict[str, Any] | None:
    """
    Look up a HubSpot contact by email address.
    Returns the contact dict or None if not found.
    """
    params = {
        "filterGroups": [
            {
                "filters": [
                    {
                        "propertyName": "email",
                        "operator": "EQ",
                        "value": email,
                    }
                ]
            }
        ],
        "properties": [
            "email",
            "firstname",
            "lastname",
            "company",
            "lifecyclestage",
            "hs_lead_status",
            "icp_segment",
            "ai_maturity_score",
            "enrichment_timestamp",
        ],
        "limit": 1,
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_hubspot_base()}/crm/v3/objects/contacts/search",
                json=params,
                headers=_headers(),
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            if results:
                return results[0]
            return None

    except Exception as exc:
        log_trace("hubspot_get_contact_error", {"email": email, "error": str(exc)})
        return None


async def update_contact_stage(email: str, stage: str) -> dict[str, Any]:
    """
    Advance a contact lifecycle stage.
    Valid internal stages:
      outbound_sent → email_opened → replied → call_booked → proposal_sent
    These are mapped to valid HubSpot hs_lead_status values.
    """
    if stage not in STAGE_ORDER:
        return {"status": "error", "error": f"Unknown stage: {stage}"}

    hs_status = STAGE_TO_HS_STATUS[stage]

    contact = await get_contact_by_email(email)
    if not contact:
        # Create minimal contact if not found
        contact = await create_contact(
            {
                "email": email,
                "lifecyclestage": "lead",
                "hs_lead_status": hs_status,
                "enrichment_timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        log_trace(
            "hubspot_stage_contact_created",
            {"email": email, "stage": stage, "hs_status": hs_status},
        )
        return contact

    contact_id = contact["id"]
    result = await update_contact(
        contact_id,
        {
            "hs_lead_status": hs_status,
            "enrichment_timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
    log_trace(
        "hubspot_stage_updated",
        {
            "email": email,
            "contact_id": contact_id,
            "stage": stage,
            "hs_status": hs_status,
        },
    )
    return result


async def create_deal(
    contact_email: str,
    company: str,
    segment: str,
    acv_estimate: int,
) -> dict[str, Any]:
    """
    Create a HubSpot deal linked to a contact.
    Deal stage is set to appointmentscheduled (discovery call booked).
    """
    deal_payload = {
        "properties": {
            "dealname": f"{company} — {segment.replace('_', ' ').title()} Discovery",
            "dealstage": "appointmentscheduled",
            "pipeline": "default",
            "amount": str(acv_estimate),
            "closedate": _close_date_90_days(),
        }
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            deal_response = await client.post(
                f"{_hubspot_base()}/crm/v3/objects/deals",
                json=deal_payload,
                headers=_headers(),
            )
            deal_response.raise_for_status()
            deal = deal_response.json()
            deal_id = deal["id"]

            # Associate deal with contact
            contact = await get_contact_by_email(contact_email)
            if contact:
                contact_id = contact["id"]
                assoc_payload = {
                    "inputs": [
                        {
                            "from": {"id": deal_id},
                            "to": {"id": contact_id},
                            "type": "deal_to_contact",
                        }
                    ]
                }
                await client.post(
                    f"{_hubspot_base()}/crm/v3/associations/deals/contacts/batch/create",
                    json=assoc_payload,
                    headers=_headers(),
                )

            log_trace(
                "hubspot_deal_created",
                {
                    "deal_id": deal_id,
                    "company": company,
                    "segment": segment,
                    "acv_estimate": acv_estimate,
                    "contact_email": contact_email,
                },
            )
            return deal

    except httpx.HTTPStatusError as exc:
        error = {
            "status": "error",
            "error": exc.response.text,
            "http_status": exc.response.status_code,
        }
        log_trace("hubspot_deal_error", error)
        return error

    except Exception as exc:
        error = {"status": "error", "error": str(exc)}
        log_trace("hubspot_deal_error", error)
        return error


async def setup_custom_properties() -> None:
    """
    Create custom contact and deal properties required by the pipeline.
    Run this once before using the CRM client.
    Safe to run multiple times — skips already-existing properties.
    """
    contact_props = [
        {
            "name": "icp_segment",
            "label": "ICP Segment",
            "type": "string",
            "fieldType": "text",
            "groupName": "contactinformation",
        },
        {
            "name": "ai_maturity_score",
            "label": "AI Maturity Score",
            "type": "string",
            "fieldType": "text",
            "groupName": "contactinformation",
        },
        {
            "name": "enrichment_timestamp",
            "label": "Enrichment Timestamp",
            "type": "string",
            "fieldType": "text",
            "groupName": "contactinformation",
        },
    ]

    deal_props = [
        {
            "name": "icp_segment",
            "label": "ICP Segment",
            "type": "string",
            "fieldType": "text",
            "groupName": "dealinformation",
        },
    ]

    async with httpx.AsyncClient(timeout=15.0) as client:
        for prop in contact_props:
            r = await client.post(
                f"{_hubspot_base()}/crm/v3/properties/contacts",
                headers=_headers(),
                json=prop,
            )
            if r.status_code in (200, 201):
                print(f"[HUBSPOT SETUP] Created contact property: {prop['name']}")
            elif r.status_code == 409:
                print(f"[HUBSPOT SETUP] Already exists: {prop['name']}")
            else:
                print(f"[HUBSPOT SETUP] Error {prop['name']}: {r.status_code}")

        for prop in deal_props:
            r = await client.post(
                f"{_hubspot_base()}/crm/v3/properties/deals",
                headers=_headers(),
                json=prop,
            )
            if r.status_code in (200, 201):
                print(f"[HUBSPOT SETUP] Created deal property: {prop['name']}")
            elif r.status_code == 409:
                print(f"[HUBSPOT SETUP] Already exists: {prop['name']}")
            else:
                print(f"[HUBSPOT SETUP] Error {prop['name']}: {r.status_code}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise_properties(props: dict[str, Any]) -> dict[str, Any]:
    """Convert all property values to strings as HubSpot requires."""
    return {k: str(v) if v is not None else "" for k, v in props.items()}


def _close_date_90_days() -> str:
    """Return close date 90 days from now in milliseconds epoch (HubSpot format)."""
    import time
    return str(int((time.time() + 90 * 86400) * 1000))


# ---------------------------------------------------------------------------
# Run setup when executed directly
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    asyncio.run(setup_custom_properties())