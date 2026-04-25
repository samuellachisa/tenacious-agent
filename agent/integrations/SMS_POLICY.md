# SMS Channel Policy

## Warm Lead Enforcement

SMS is a privileged channel reserved exclusively for warm leads. This policy ensures compliance with best practices and prevents spam.

### What is a Warm Lead?

A contact qualifies as a warm lead when they have:

1. **Replied to an email** (stage: `replied`, `qualified`, `scheduled`, `call_booked`)
2. **Engaged with email** (stage: `email_opened` - opened or clicked)

### Stage Validation

The `is_warm_lead()` function checks HubSpot contact stage against:

```python
WARM_LEAD_STAGES = {
    "replied",
    "qualified", 
    "scheduled",
    "call_booked",
    "email_opened"
}
```

### Enforcement Mechanism

All SMS sends go through `send_sms()` which:

1. Requires `contact_email` parameter (unless `skip_warm_check=True`)
2. Calls `is_warm_lead(contact_email)` to validate stage
3. Rejects with `status: "rejected"` if contact is cold
4. Logs rejection reason to Langfuse for audit trail

### Usage Examples

#### Correct: Scheduling SMS (warm lead)

```python
from agent.integrations.sms_client import send_scheduling_sms

# Automatically validates warm lead status
await send_scheduling_sms(
    to_number="+254712345678",
    prospect_name="Alex",
    slot="2026-04-25T10:00:00Z",
    contact_email="alex@company.com",  # Required for validation
)
```

#### Correct: Manual SMS with validation

```python
from agent.integrations.sms_client import send_sms

result = await send_sms(
    to_number="+254712345678",
    message="Your call is confirmed",
    contact_email="alex@company.com",  # Validates warm lead
)

if result["status"] == "rejected":
    print(f"SMS blocked: {result['reason']}")
```

#### Incorrect: Bypassing validation (avoid)

```python
# Only use skip_warm_check for testing or admin messages
result = await send_sms(
    to_number="+254712345678",
    message="Test message",
    skip_warm_check=True,  # ⚠️ Bypasses warm lead check
)
```

### Integration with Pipeline

The reply pipeline automatically enforces warm lead policy:

```python
# In _handle_reply_pipeline()
if phone_number:
    # SMS only sent if contact has replied (warm lead)
    await send_scheduling_sms(
        to_number=phone_number,
        prospect_name=first_name,
        slot=slot,
        contact_email=from_email,  # Validated against HubSpot
    )
```

### Fail-Closed Design

If warm lead validation fails (HubSpot unreachable, contact not found):
- Function returns `False` (not warm)
- SMS is rejected
- Error logged to Langfuse

This prevents accidental SMS to cold leads during system issues.

### Audit Trail

All warm lead checks are logged:

```python
log_trace("warm_lead_check", {
    "identifier": email,
    "stage": "replied",
    "is_warm": True,
})

log_trace("sms_rejected_cold_lead", {
    "to": phone_number,
    "email": email,
})
```

## Channel Gating Summary

| Contact Stage | Email | SMS |
|--------------|-------|-----|
| new | ✅ | ❌ |
| outbound_sent | ✅ | ❌ |
| email_opened | ✅ | ✅ |
| replied | ✅ | ✅ |
| qualified | ✅ | ✅ |
| scheduled | ✅ | ✅ |
| call_booked | ✅ | ✅ |

This ensures cold outreach stays in email, while SMS is reserved for engaged prospects.
