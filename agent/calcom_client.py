"""
Cal.com REST API client — availability lookup and booking.
Falls back to +2 days 10am UTC if the API is unavailable.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

from agent.langfuse_client import log_trace

load_dotenv()


def _base_url() -> str:
    return os.getenv("CALCOM_BASE_URL", "https://api.cal.com/v1").rstrip("/")


def _api_key() -> str:
    return os.getenv("CALCOM_API_KEY", "")


def _event_type_id() -> str:
    return os.getenv("CALCOM_EVENT_TYPE_ID", "")


def _fallback_slot() -> str:
    """Return a fallback slot: next business day at 10:00 UTC."""
    now = datetime.now(timezone.utc)
    candidate = now + timedelta(days=2)
    # Skip weekends
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    slot = candidate.replace(hour=10, minute=0, second=0, microsecond=0)
    return slot.isoformat()


async def find_available_slot(days_ahead: int = 7) -> str | None:
    """
    Query Cal.com availability and return the first open ISO datetime slot.
    Falls back to +2 days 10am UTC if the API is unavailable or returns no slots.
    """
    event_type_id = _event_type_id()
    if not event_type_id:
        fallback = _fallback_slot()
        log_trace(
            "calcom_slot_fallback",
            {"reason": "CALCOM_EVENT_TYPE_ID not set", "slot": fallback},
        )
        return fallback

    date_from = datetime.now(timezone.utc)
    date_to = date_from + timedelta(days=days_ahead)

    params = {
        "apiKey": _api_key(),
        "eventTypeId": event_type_id,
        "startTime": date_from.isoformat(),
        "endTime": date_to.isoformat(),
        "timeZone": "UTC",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{_base_url()}/availability",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            # Cal.com v1 returns {"busy": [...], "timeZone": "...", "slots": {...}}
            slots_by_day: dict = data.get("slots", {})
            for _day, day_slots in sorted(slots_by_day.items()):
                if day_slots:
                    first_slot = day_slots[0]
                    slot_time = first_slot.get("time", "")
                    if slot_time:
                        log_trace(
                            "calcom_slot_found",
                            {"slot": slot_time, "event_type_id": event_type_id},
                        )
                        return slot_time

            # No slots found in window — use fallback
            fallback = _fallback_slot()
            log_trace(
                "calcom_slot_fallback",
                {"reason": "no slots in availability window", "slot": fallback},
            )
            return fallback

    except Exception as exc:
        fallback = _fallback_slot()
        log_trace(
            "calcom_slot_fallback",
            {"reason": str(exc), "slot": fallback},
        )
        return fallback


async def book_discovery_call(
    name: str,
    email: str,
    slot: str,
    timezone: str = "UTC",
) -> dict[str, Any]:
    """
    Book a discovery call on Cal.com.

    Args:
        name: Prospect's full name
        email: Prospect's email address
        slot: ISO 8601 datetime string for the desired slot
        timezone: Prospect's timezone string (default UTC)

    Returns:
        dict with keys: status, slot, booking (raw Cal.com response or error)
    """
    event_type_id = _event_type_id()

    payload = {
        "eventTypeId": int(event_type_id) if event_type_id else 0,
        "start": slot,
        "timeZone": timezone,
        "responses": {
            "name": name,
            "email": email,
            "notes": "Discovery call booked via Tenacious Agent outbound pipeline.",
        },
        "metadata": {
            "source": "tenacious-agent",
        },
        "language": "en",
    }

    params = {"apiKey": _api_key()}

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_base_url()}/bookings",
                json=payload,
                params=params,
            )
            response.raise_for_status()
            booking_data = response.json()

            result = {
                "status": "booked",
                "slot": slot,
                "booking": booking_data,
            }
            log_trace(
                "calcom_booking_created",
                {
                    "name": name,
                    "email": email,
                    "slot": slot,
                    "booking_id": booking_data.get("id"),
                    "event_type_id": event_type_id,
                },
            )
            return result

    except httpx.HTTPStatusError as exc:
        error_result = {
            "status": "error",
            "slot": slot,
            "booking": None,
            "error": exc.response.text,
            "http_status": exc.response.status_code,
        }
        log_trace(
            "calcom_booking_error",
            {"name": name, "email": email, "slot": slot, "error": exc.response.text},
        )
        return error_result

    except Exception as exc:
        error_result = {
            "status": "error",
            "slot": slot,
            "booking": None,
            "error": str(exc),
        }
        log_trace(
            "calcom_booking_error",
            {"name": name, "email": email, "slot": slot, "error": str(exc)},
        )
        return error_result
