"""
HubSpot CRM via MCP (Model Context Protocol).

Connects to the official HubSpot MCP server subprocess:
  npx @hubspot/mcp-server --access-token <HUBSPOT_ACCESS_TOKEN>

Exposes the same async interface as hubspot_client.py so the adapter
layer can swap transports without changing any business logic.

Requirements:
  pip install mcp>=1.0.0
  Node.js + npx installed (for @hubspot/mcp-server)
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from agent.integrations.langfuse_client import log_trace

load_dotenv()

# ---------------------------------------------------------------------------
# Tool names exposed by @hubspot/mcp-server (npm)
# ---------------------------------------------------------------------------

_TOOL_SEARCH_CONTACTS = "search_contacts"
_TOOL_CREATE_CONTACT = "create_contact"
_TOOL_UPDATE_CONTACT = "update_contact"
_TOOL_CREATE_DEAL = "create_deal"
_TOOL_ASSOCIATE = "associate_records"

# Stage mappings shared with REST client
STAGE_TO_HS_STATUS: dict[str, str] = {
    "outbound_sent": "NEW",
    "email_opened": "OPEN",
    "replied": "CONNECTED",
    "call_booked": "IN_PROGRESS",
    "proposal_sent": "OPEN_DEAL",
}
STAGE_ORDER = list(STAGE_TO_HS_STATUS.keys())


def _access_token() -> str:
    return os.getenv("HUBSPOT_ACCESS_TOKEN", "")


# ---------------------------------------------------------------------------
# Core MCP transport
# ---------------------------------------------------------------------------

async def _call_mcp_tool(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """
    Spawn the HubSpot MCP server subprocess, initialise a session, call one
    tool, then tear down.

    Each call is self-contained so no global state is needed.  For production
    traffic add a persistent session that lives for the FastAPI lifespan event.
    """
    try:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
    except ImportError as exc:
        raise RuntimeError(
            "mcp package missing — run: pip install 'mcp>=1.0.0'"
        ) from exc

    token = _access_token()
    if not token:
        raise ValueError(
            "HUBSPOT_ACCESS_TOKEN is not set; required by HubSpot MCP server"
        )

    server_params = StdioServerParameters(
        command="npx",
        args=["--yes", "@hubspot/mcp-server", "--access-token", token],
        env=None,
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments=arguments)

    # MCP returns a list of Content objects; we want the first text item
    if result.content:
        raw = result.content[0]
        text = getattr(raw, "text", None) or str(raw)
        try:
            return json.loads(text)
        except (json.JSONDecodeError, TypeError):
            return {"raw": text}
    return {}


# ---------------------------------------------------------------------------
# Public interface — mirrors hubspot_client.py
# ---------------------------------------------------------------------------

async def create_or_update_contact(properties: dict[str, Any]) -> dict[str, Any]:
    """Create a new contact or update an existing one by email via MCP."""
    email = properties.get("email", "")
    existing = await get_contact_by_email(email)

    if existing:
        contact_id = existing["id"]
        result = await _call_mcp_tool(
            _TOOL_UPDATE_CONTACT,
            {
                "contactId": contact_id,
                "properties": _sanitise(properties),
            },
        )
        result["operation"] = "updated"
        log_trace("hubspot_mcp_contact_updated", {"email": email, "contact_id": contact_id})
        return result

    result = await _call_mcp_tool(
        _TOOL_CREATE_CONTACT,
        {"properties": _sanitise(properties)},
    )
    result["operation"] = "created"
    log_trace("hubspot_mcp_contact_created", {"email": email})
    return result


async def get_contact_by_email(email: str) -> dict[str, Any] | None:
    """Look up a HubSpot contact by email via MCP search."""
    result = await _call_mcp_tool(
        _TOOL_SEARCH_CONTACTS,
        {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "email", "operator": "EQ", "value": email}
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
        },
    )
    results = result.get("results", [])
    return results[0] if results else None


async def update_contact_stage(email: str, stage: str) -> dict[str, Any]:
    """Advance a contact's lifecycle stage via MCP."""
    if stage not in STAGE_ORDER:
        return {"status": "error", "error": f"Unknown stage: {stage}"}

    hs_status = STAGE_TO_HS_STATUS[stage]
    contact = await get_contact_by_email(email)

    if not contact:
        result = await _call_mcp_tool(
            _TOOL_CREATE_CONTACT,
            {
                "properties": _sanitise(
                    {
                        "email": email,
                        "lifecyclestage": "lead",
                        "hs_lead_status": hs_status,
                        "enrichment_timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
            },
        )
        log_trace(
            "hubspot_mcp_stage_contact_created",
            {"email": email, "stage": stage, "hs_status": hs_status},
        )
        return result

    contact_id = contact["id"]
    result = await _call_mcp_tool(
        _TOOL_UPDATE_CONTACT,
        {
            "contactId": contact_id,
            "properties": _sanitise(
                {
                    "hs_lead_status": hs_status,
                    "enrichment_timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ),
        },
    )
    log_trace(
        "hubspot_mcp_stage_updated",
        {"email": email, "contact_id": contact_id, "stage": stage, "hs_status": hs_status},
    )
    return result


async def create_deal(
    contact_email: str,
    company: str,
    segment: str,
    acv_estimate: int,
) -> dict[str, Any]:
    """Create a HubSpot deal and associate it with the contact via MCP."""
    deal = await _call_mcp_tool(
        _TOOL_CREATE_DEAL,
        {
            "properties": {
                "dealname": f"{company} — {segment.replace('_', ' ').title()} Discovery",
                "dealstage": "appointmentscheduled",
                "pipeline": "default",
                "amount": str(acv_estimate),
                "closedate": _close_date_ms(90),
            }
        },
    )

    deal_id = deal.get("id")
    if deal_id:
        contact = await get_contact_by_email(contact_email)
        if contact:
            await _call_mcp_tool(
                _TOOL_ASSOCIATE,
                {
                    "fromObjectType": "deals",
                    "toObjectType": "contacts",
                    "fromObjectId": deal_id,
                    "toObjectId": contact["id"],
                    "associationType": "deal_to_contact",
                },
            )

    log_trace(
        "hubspot_mcp_deal_created",
        {
            "deal_id": deal_id,
            "company": company,
            "segment": segment,
            "acv_estimate": acv_estimate,
            "contact_email": contact_email,
        },
    )
    return deal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise(props: dict[str, Any]) -> dict[str, Any]:
    """HubSpot requires all property values to be strings."""
    return {k: str(v) if v is not None else "" for k, v in props.items()}


def _close_date_ms(days: int) -> str:
    """Return close date N days from now in millisecond epoch (HubSpot format)."""
    return str(int((time.time() + days * 86400) * 1000))
