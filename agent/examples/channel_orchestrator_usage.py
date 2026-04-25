"""
Example: Using ChannelOrchestrator in email reply handler.

This demonstrates how to centralize channel logic using the orchestrator
instead of scattering eligibility checks across handlers.
"""

from agent.core.channel_orchestrator import (
    Channel,
    ChannelOrchestrator,
    ProspectStage,
)
from agent.domain.ports.observability import Observability


async def handle_email_reply_with_orchestrator(
    from_email: str,
    company: str,
    message_body: str,
    orchestrator: ChannelOrchestrator,
    crm_adapter,
    email_gateway,
    sms_gateway,
    calcom_gateway,
    obs: Observability,
) -> dict:
    """
    Handle email reply using orchestrator for channel decisions.
    
    Before: Each handler independently checked warm lead status, qualification, etc.
    After: Orchestrator provides single source of truth for channel eligibility.
    """
    
    # 1. Get current stage from CRM
    contact = await crm_adapter.get_contact_by_email(from_email)
    current_stage = ProspectStage(contact.get("stage", "new"))
    
    obs.log_trace("email_reply_received", {
        "from": from_email,
        "company": company,
        "current_stage": current_stage.value,
    })
    
    # 2. Determine next action based on reply
    next_action = orchestrator.get_next_action(
        current_stage=current_stage,
        engagement_signal="email_replied",
        company=company,
    )
    
    obs.log_trace("orchestrator_recommendation", next_action)
    
    # 3. Execute recommended action
    if next_action["action"] == "qualify_prospect":
        # Prospect replied - qualify them
        from agent.domain.use_cases.qualify_prospect import QualifyProspect
        
        enrichment = await crm_adapter.get_enrichment(from_email)
        qualifier = QualifyProspect(obs)
        qualification = qualifier.execute(enrichment)
        
        if qualification.qualified:
            # Update CRM to qualified stage
            await crm_adapter.update_contact_stage(from_email, "qualified")
            
            # Check if Cal.com is now eligible
            calcom_check = orchestrator.check_channel_eligibility(
                Channel.CALCOM,
                ProspectStage.QUALIFIED,
            )
            
            if calcom_check.eligible:
                # Send Cal.com link via email
                await email_gateway.send_email(
                    to=from_email,
                    subject=f"Let's schedule a call - {company}",
                    body=f"Thanks for your interest! Here's my calendar: https://cal.com/tenacious/discovery",
                )
                
                # Check if SMS is eligible for reminder
                sms_check = orchestrator.check_channel_eligibility(
                    Channel.SMS,
                    ProspectStage.QUALIFIED,
                )
                
                if sms_check.eligible and contact.get("phone"):
                    # Send SMS reminder (orchestrator confirmed warm lead)
                    await sms_gateway.send_sms(
                        to_number=contact["phone"],
                        message=f"Hi {contact['first_name']}, I just sent you a calendar link. Looking forward to connecting!",
                        contact_email=from_email,  # For audit trail
                    )
                    
                    obs.log_trace("sms_sent_after_qualification", {
                        "company": company,
                        "reason": sms_check.reason,
                    })
            
            return {
                "status": "qualified",
                "next_stage": "qualified",
                "channels_used": ["email", "sms"] if contact.get("phone") else ["email"],
            }
        else:
            # Not qualified - update CRM and stop
            await crm_adapter.update_contact_stage(from_email, "disqualified")
            
            return {
                "status": "disqualified",
                "reason": qualification.reason,
            }
    
    elif next_action["action"] == "maintain":
        # No valid transition - just acknowledge reply
        await email_gateway.send_email(
            to=from_email,
            subject=f"Re: {company}",
            body="Thanks for your message. I'll review and get back to you shortly.",
        )
        
        return {
            "status": "acknowledged",
            "next_stage": current_stage.value,
        }
    
    return {
        "status": "processed",
        "action": next_action["action"],
    }


async def handle_cal_booking_with_orchestrator(
    email: str,
    company: str,
    slot: str,
    orchestrator: ChannelOrchestrator,
    crm_adapter,
    sms_gateway,
    obs: Observability,
) -> dict:
    """
    Handle Cal.com booking using orchestrator for SMS eligibility.
    
    Before: SMS client independently checked warm lead status.
    After: Orchestrator validates stage transition and channel eligibility.
    """
    
    # 1. Get current stage
    contact = await crm_adapter.get_contact_by_email(email)
    current_stage = ProspectStage(contact.get("stage", "qualified"))
    
    # 2. Attempt transition to scheduled
    transition = orchestrator.transition_stage(
        from_stage=current_stage,
        to_stage=ProspectStage.SCHEDULED,
        company=company,
    )
    
    if not transition.success:
        obs.log_trace("invalid_booking_transition", {
            "company": company,
            "from_stage": current_stage.value,
            "reason": transition.reason,
        })
        return {
            "status": "error",
            "reason": transition.reason,
        }
    
    # 3. Update CRM
    await crm_adapter.update_contact_stage(email, "scheduled")
    await crm_adapter.create_task(
        email=email,
        title=f"Discovery call scheduled - {company}",
        due_date=slot,
    )
    
    # 4. Check SMS eligibility
    sms_check = orchestrator.check_channel_eligibility(
        Channel.SMS,
        ProspectStage.SCHEDULED,
    )
    
    if sms_check.eligible and contact.get("phone"):
        # Send SMS confirmation
        await sms_gateway.send_sms(
            to_number=contact["phone"],
            message=f"Hi {contact['first_name']}, your call with Tenacious is confirmed for {slot}. Looking forward to it!",
            contact_email=email,
        )
        
        obs.log_trace("sms_booking_confirmation", {
            "company": company,
            "slot": slot,
            "reason": sms_check.reason,
        })
        
        return {
            "status": "scheduled",
            "sms_sent": True,
            "channels_used": ["crm", "sms"],
        }
    
    return {
        "status": "scheduled",
        "sms_sent": False,
        "channels_used": ["crm"],
        "sms_skip_reason": sms_check.reason if not sms_check.eligible else "No phone number",
    }


async def handle_email_opened_with_orchestrator(
    email: str,
    company: str,
    orchestrator: ChannelOrchestrator,
    crm_adapter,
    obs: Observability,
) -> dict:
    """
    Handle email open event using orchestrator.
    
    Email open transitions prospect from cold to warm lead.
    """
    
    # 1. Get current stage
    contact = await crm_adapter.get_contact_by_email(email)
    current_stage = ProspectStage(contact.get("stage", "outbound_sent"))
    
    # 2. Attempt transition to email_opened
    transition = orchestrator.transition_stage(
        from_stage=current_stage,
        to_stage=ProspectStage.EMAIL_OPENED,
        company=company,
    )
    
    if transition.success:
        # Update CRM
        await crm_adapter.update_contact_stage(email, "email_opened")
        
        obs.log_trace("prospect_now_warm", {
            "company": company,
            "from_stage": current_stage.value,
            "to_stage": "email_opened",
            "sms_now_eligible": Channel.SMS in transition.allowed_channels,
        })
        
        return {
            "status": "warm_lead",
            "stage": "email_opened",
            "sms_eligible": Channel.SMS in transition.allowed_channels,
        }
    
    return {
        "status": "no_change",
        "reason": transition.reason,
    }


# Example: Checking channel eligibility before action
async def send_message_with_channel_check(
    email: str,
    company: str,
    channel: Channel,
    orchestrator: ChannelOrchestrator,
    crm_adapter,
    obs: Observability,
) -> dict:
    """
    Generic message sender that checks channel eligibility first.
    """
    
    # Get current stage
    contact = await crm_adapter.get_contact_by_email(email)
    current_stage = ProspectStage(contact.get("stage", "new"))
    
    # Check eligibility
    eligibility = orchestrator.check_channel_eligibility(channel, current_stage)
    
    if not eligibility.eligible:
        obs.log_trace("channel_rejected", {
            "company": company,
            "channel": channel.value,
            "stage": current_stage.value,
            "reason": eligibility.reason,
        })
        
        return {
            "status": "rejected",
            "channel": channel.value,
            "reason": eligibility.reason,
        }
    
    obs.log_trace("channel_approved", {
        "company": company,
        "channel": channel.value,
        "stage": current_stage.value,
    })
    
    return {
        "status": "approved",
        "channel": channel.value,
        "reason": eligibility.reason,
    }
