"""
Example: Extending email behavior via event handlers.

This demonstrates how to hook into email events without modifying
the core mailersend_client.py logic.
"""

from typing import Any

from agent.integrations.mailersend_client import register_email_event_handler


async def analytics_tracker(event_type: str, data: dict[str, Any]) -> None:
    """Track email metrics to analytics platform."""
    if event_type == "sent":
        print(f"[ANALYTICS] Email sent to {data['to']}")
        # await analytics_client.track("email_sent", data)
    elif event_type == "error":
        print(f"[ANALYTICS] Email failed: {data.get('error')}")
        # await analytics_client.track("email_failed", data)


async def slack_notifier(event_type: str, data: dict[str, Any]) -> None:
    """Send Slack notifications for important email events."""
    if event_type == "error" and data.get("http_status") == 429:
        print(f"[SLACK] Rate limit hit for {data['to']}")
        # await slack_client.send_alert("Rate limit exceeded", data)


# Register handlers at application startup
def setup_email_handlers() -> None:
    """Call this during app initialization."""
    register_email_event_handler(analytics_tracker)
    register_email_event_handler(slack_notifier)
