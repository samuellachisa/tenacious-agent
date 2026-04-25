"""
Cal.com REST API client — availability lookup and booking.
Uses Cal.com API v2. Falls back to +2 days 10am UTC if unavailable.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import load_dotenv

from agent.integrations.langfuse_client import log_trace

load_dotenv()


def _calcom_base() -> str:
    return os.getenv("CALCOM_API_URL", "https://api.cal.com/v2")


def _api_key() -> str:
    return os.getenv("CALCOM_API_KEY", "")


def _event_type_id() -> str:
    return os.getenv("CALCOM_EVENT_TYPE_ID", "")


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_api_key()}",
        "cal-api-version": "2024-08-13",
        "Content-Type": "application/json",
    }


def _fallback_slot() -> str:
    now = datetime.now(timezone.utc)
    candidate = now + timedelta(days=2)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate.replace(hour=10, minute=0, second=0, microsecond=0).isoformat()


async def find_available_slot(days_ahead: int = 7) -> str | None:
    """Return the first available slot from Cal.com v2, or fallback."""
    event_type_id = _event_type_id()
    if not event_type_id:
        fallback = _fallback_slot()
        log_trace("calcom_slot_fallback", {"reason": "CALCOM_EVENT_TYPE_ID not set", "slot": fallback})
        return fallback

    date_from = datetime.now(timezone.utc)
    date_to = date_from + timedelta(days=days_ahead)

    params = {
        "eventTypeId": event_type_id,
        "startTime": date_from.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "endTime": date_to.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timeZone": "UTC",
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{_calcom_base()}/slots/available",
                headers=_headers(),
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            # v2 returns {"status": "success", "data": {"slots": {"2026-04-24": [{"time": "..."}]}}}
            slots_by_day: dict = data.get("data", {}).get("slots", {})
            for _day, day_slots in sorted(slots_by_day.items()):
                if day_slots:
                    slot_time = day_slots[0].get("time", "")
                    if slot_time:
                        log_trace("calcom_slot_found", {"slot": slot_time, "event_type_id": event_type_id})
                        return slot_time

        fallback = _fallback_slot()
        log_trace("calcom_slot_fallback", {"reason": "no slots in window", "slot": fallback})
        return fallback

    except Exception as exc:
        fallback = _fallback_slot()
        log_trace("calcom_slot_fallback", {"reason": str(exc), "slot": fallback})
        return fallback


async def book_discovery_call(
    name: str,
    email: str,
    slot: str,
    timezone: str = "UTC",
) -> dict[str, Any]:
    """Book a discovery call via Cal.com API v2."""
    event_type_id = _event_type_id()

    payload = {
        "eventTypeId": int(event_type_id) if event_type_id else 0,
        "start": slot,
        "attendee": {
            "name": name,
            "email": email,
            "timeZone": timezone,
            "language": "en",
        },
        "metadata": {"source": "tenacious-agent"},
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"{_calcom_base()}/bookings",
                headers=_headers(),
                json=payload,
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
                    "booking_id": booking_data.get("data", {}).get("id"),
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
        log_trace("calcom_booking_error", {"name": name, "email": email, "slot": slot, "error": exc.response.text})
        return error_result

    except Exception as exc:
        error_result = {"status": "error", "slot": slot, "booking": None, "error": str(exc)}
        log_trace("calcom_booking_error", {"name": name, "email": email, "slot": slot, "error": str(exc)})
        return error_result
