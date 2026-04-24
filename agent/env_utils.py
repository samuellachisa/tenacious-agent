"""
Shared environment helpers for Tenacious Agent.

This module centralizes outbound gate behavior for both the policy-preferred
`TENACIOUS_OUTBOUND_ENABLED` flag and the legacy `OUTBOUND_ENABLED` alias.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()

PREFERRED_FLAG = "TENACIOUS_OUTBOUND_ENABLED"
LEGACY_FLAG = "OUTBOUND_ENABLED"


def get_outbound_flag_value() -> str | None:
    value = os.getenv(PREFERRED_FLAG)
    if value is not None:
        return value
    return os.getenv(LEGACY_FLAG)


def outbound_enabled() -> bool:
    value = get_outbound_flag_value()
    return str(value or "false").strip().lower() == "true"


def outbound_flag_name() -> str:
    if os.getenv(PREFERRED_FLAG) is not None:
        return PREFERRED_FLAG
    return LEGACY_FLAG
