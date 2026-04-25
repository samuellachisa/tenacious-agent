# Channel Orchestration

## Overview

The Channel Orchestrator (`agent/core/channel_orchestrator.py`) is a central state machine that manages when to use email, SMS, CRM updates, and Cal.com bookings based on prospect lifecycle stage.

## Problem

Before the orchestrator, channel logic was scattered across handlers:
- `sms_client.py` independently checked warm lead status
- `qualify_prospect.py` decided when to send Cal.com links
- `main.py` email handler made CRM update decisions
- No single source of truth for channel eligibility

This led to:
- Inconsistent channel gating (SMS sent to cold leads)
- Duplicate validation logic across modules
- Hard to audit channel usage
- Difficult to enforce new channel policies

## Solution

Centralized state machine that:
1. Defines valid prospect stages and transitions
2. Enforces channel eligibility rules per stage
3. Recommends next actions based on engagement signals
4. Logs all transitions for observability

## Prospect Lifecycle

```
new → outbound_sent → email_opened → replied → qualified → scheduled → call_booked
  ↓         ↓              ↓            ↓          ↓           ↓            ↓
  └─────────┴──────────────┴────────────┴──────────┴───────────┴────────────→ disqualified
```

### Stage Definitions

| Stage | Description | Entry Condition |
|-------|-------------|-----------------|
| `new` | Fresh prospect, no outreach yet | Initial state |
| `outbound_sent` | Initial email sent | Email sent successfully |
| `email_opened` | Prospect opened email (warm lead) | Email open event |
| `replied` | Prospect replied to email | Email reply received |
| `qualified` | Prospect meets ICP criteria | Qualification logic passed |
| `scheduled` | Discovery call scheduled | Cal.com booking confirmed |
| `call_booked` | Call completed, deal in pipeline | Call occurred |
| `disqualified` | Prospect rejected or opted out | Hard disqualifier matched |

## Channel Eligibility Rules

### Email
- Available: All stages except `disqualified`
- Use case: Primary outreach channel

### SMS
- Available: `email_opened`, `replied`, `qualified`, `scheduled`, `call_booked`
- Requirement: Warm lead (prospect has engaged with email)
- Use case: Scheduling reminders, urgent follow-ups

### Cal.com
- Available: `qualified`, `scheduled`, `call_booked`
- Requirement: Prospect has been qualified
- Use case: Discovery call booking

### CRM
- Available: All stages
- Use case: Stage updates, task creation, notes

## Usage

### 1. Check Channel Eligibility

```python
from agent.core.channel_orchestrator import Channel, ChannelOrchestrator, ProspectStage

orchestrator = container.channel_orchestrator

# Check if SMS is allowed for this prospect
eligibility = orchestrator.check_channel_eligibility(
    channel=Channel.SMS,
    current_stage=ProspectStage.EMAIL_OPENED,
)

if eligibility.eligible:
    # Send SMS
    await sms_gateway.send_sms(...)
else:
    # Log rejection
    print(f"SMS rejected: {eligibility.reason}")
```

### 2. Transition Prospect Stage

```python
# Prospect replied to email - transition to replied stage
transition = orchestrator.transition_stage(
    from_stage=ProspectStage.OUTBOUND_SENT,
    to_stage=ProspectStage.REPLIED,
    company="Acme Corp",
)

if transition.success:
    # Update CRM
    await crm.update_contact_stage(email, "replied")
    
    # Check newly available channels
    if Channel.SMS in transition.allowed_channels:
        print("SMS now available - prospect is warm lead")
else:
    print(f"Invalid transition: {transition.reason}")
```

### 3. Get Next Action Recommendation

```python
# Prospect opened email - what should we do next?
next_action = orchestrator.get_next_action(
    current_stage=ProspectStage.OUTBOUND_SENT,
    engagement_signal="email_opened",
    company="Acme Corp",
)

print(f"Recommended action: {next_action['action']}")
print(f"Next stage: {next_action['next_stage']}")
print(f"Available channels: {next_action['channels']}")

# Execute recommended action
if next_action["action"] == "send_followup_email":
    await email_gateway.send_email(...)
```

## State Transition Rules

### Valid Transitions

| From Stage | To Stage | Trigger |
|------------|----------|---------|
| `new` | `outbound_sent` | Email sent |
| `outbound_sent` | `email_opened` | Email opened |
| `outbound_sent` | `replied` | Email replied (skip email_opened) |
| `email_opened` | `replied` | Email replied |
| `replied` | `qualified` | Qualification passed |
| `qualified` | `scheduled` | Cal.com booking |
| `scheduled` | `call_booked` | Call completed |
| Any stage | `disqualified` | Hard disqualifier or opt-out |

### Invalid Transitions

- Backward transitions (e.g., `qualified` → `replied`)
- Skip-stage transitions (except `outbound_sent` → `replied`)
- Transitions from terminal states (`disqualified`, `call_booked`)

## Integration Points

### 1. Email Reply Handler (`agent/main.py`)

```python
from agent.core.channel_orchestrator import ProspectStage

async def handle_email_reply(from_email: str, company: str):
    # Get current stage from CRM
    contact = await crm.get_contact_by_email(from_email)
    current_stage = ProspectStage(contact["stage"])
    
    # Get next action
    next_action = orchestrator.get_next_action(
        current_stage=current_stage,
        engagement_signal="email_replied",
        company=company,
    )
    
    # Execute action
    if next_action["action"] == "qualify_prospect":
        qualification = qualify_prospect.execute(enrichment)
        
        if qualification.qualified:
            # Transition to qualified
            transition = orchestrator.transition_stage(
                from_stage=current_stage,
                to_stage=ProspectStage.QUALIFIED,
                company=company,
            )
            
            if transition.success:
                await crm.update_contact_stage(from_email, "qualified")
                
                # Check if Cal.com is now available
                if Channel.CALCOM in transition.allowed_channels:
                    await email_gateway.send_calcom_link(from_email)
```

### 2. SMS Gateway (`agent/integrations/sms_client.py`)

```python
async def send_sms(to_number: str, message: str, contact_email: str):
    # Get current stage
    contact = await crm.get_contact_by_email(contact_email)
    current_stage = ProspectStage(contact["stage"])
    
    # Check SMS eligibility
    eligibility = orchestrator.check_channel_eligibility(
        channel=Channel.SMS,
        current_stage=current_stage,
    )
    
    if not eligibility.eligible:
        obs.log_trace("sms_rejected", {
            "to": to_number,
            "stage": current_stage.value,
            "reason": eligibility.reason,
        })
        return {"status": "rejected", "reason": eligibility.reason}
    
    # Send SMS
    result = await sms_client.send(to_number, message)
    return result
```

### 3. Cal.com Booking (`agent/integrations/calcom_client.py`)

```python
async def book_call(email: str, slot: str, company: str):
    # Get current stage
    contact = await crm.get_contact_by_email(email)
    current_stage = ProspectStage(contact["stage"])
    
    # Check Cal.com eligibility
    eligibility = orchestrator.check_channel_eligibility(
        channel=Channel.CALCOM,
        current_stage=current_stage,
    )
    
    if not eligibility.eligible:
        return {"status": "rejected", "reason": eligibility.reason}
    
    # Transition to scheduled
    transition = orchestrator.transition_stage(
        from_stage=current_stage,
        to_stage=ProspectStage.SCHEDULED,
        company=company,
    )
    
    if transition.success:
        await crm.update_contact_stage(email, "scheduled")
        
        # Check if SMS reminder is available
        if Channel.SMS in transition.allowed_channels and contact.get("phone"):
            await sms_gateway.send_sms(
                to_number=contact["phone"],
                message=f"Call confirmed for {slot}",
                contact_email=email,
            )
```

## Observability

All orchestrator actions are logged to Langfuse:

### Trace Events

1. `channel_orchestrator_transition` - Valid stage transition
   ```json
   {
     "company": "Acme Corp",
     "from_stage": "replied",
     "to_stage": "qualified",
     "allowed_channels": ["email", "sms", "calcom", "crm"]
   }
   ```

2. `channel_orchestrator_invalid_transition` - Rejected transition
   ```json
   {
     "company": "Acme Corp",
     "from_stage": "qualified",
     "to_stage": "replied",
     "reason": "Invalid transition: qualified → replied. Allowed: ['scheduled', 'disqualified']"
   }
   ```

3. `channel_orchestrator_next_action` - Action recommendation
   ```json
   {
     "company": "Acme Corp",
     "action": "send_calcom_link",
     "current_stage": "replied",
     "next_stage": "qualified",
     "channels": ["email", "sms", "calcom", "crm"]
   }
   ```

## Testing

See `eval/test_channel_orchestrator.md` for comprehensive test specification.

Key test scenarios:
- Channel eligibility at each stage
- Valid and invalid state transitions
- Next action recommendations
- Terminal state enforcement
- Fast-track transitions (skip stages)

## Benefits

1. **Single source of truth**: All channel logic in one place
2. **Fail-closed**: Invalid transitions rejected by default
3. **Observable**: All transitions logged for audit
4. **Testable**: State machine logic isolated and unit-testable
5. **Extensible**: Easy to add new channels or stages
6. **Consistent**: Same rules enforced across all handlers

## Migration Guide

### Before (Scattered Logic)

```python
# In sms_client.py
if contact["stage"] in ["replied", "qualified", "scheduled"]:
    await send_sms(...)

# In qualify_prospect.py
if qualification.qualified:
    await send_calcom_link(...)

# In main.py
if contact["stage"] == "replied":
    await qualify_prospect(...)
```

### After (Orchestrated)

```python
# In sms_client.py
eligibility = orchestrator.check_channel_eligibility(Channel.SMS, current_stage)
if eligibility.eligible:
    await send_sms(...)

# In qualify_prospect.py
transition = orchestrator.transition_stage(from_stage, ProspectStage.QUALIFIED, company)
if transition.success and Channel.CALCOM in transition.allowed_channels:
    await send_calcom_link(...)

# In main.py
next_action = orchestrator.get_next_action(current_stage, "email_replied", company)
if next_action["action"] == "qualify_prospect":
    await qualify_prospect(...)
```

## Future Enhancements

1. **Multi-channel campaigns**: Coordinate email + SMS sequences
2. **Channel preferences**: Respect prospect's preferred channel
3. **Rate limiting**: Enforce max messages per channel per day
4. **A/B testing**: Test different channel strategies per segment
5. **Channel analytics**: Track conversion rates by channel and stage
6. **Escalation paths**: Auto-escalate to human when stuck in stage
7. **Time-based transitions**: Auto-disqualify if no reply after N days

## References

- Implementation: `agent/core/channel_orchestrator.py`
- Tests: `eval/test_channel_orchestrator.md`
- Usage examples: `agent/examples/channel_orchestrator_usage.py`
- SMS policy: `agent/integrations/SMS_POLICY.md`
- Container: `agent/container.py`
