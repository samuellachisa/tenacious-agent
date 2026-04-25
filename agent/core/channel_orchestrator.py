"""
Channel Orchestrator - Central state machine for managing channel transitions.

This module coordinates when to use email, SMS, CRM updates, and Cal.com bookings
based on prospect state and engagement signals. It prevents scattered channel logic
across handlers and enforces consistent transition rules.

State Machine:
    new → outbound_sent → email_opened → replied → qualified → scheduled → call_booked

Channel Rules:
    - Email: Available at all stages
    - SMS: Only for warm leads (email_opened, replied, qualified, scheduled, call_booked)
    - Cal.com: Only after qualification (qualified, scheduled, call_booked)
    - CRM: Updated at every state transition

Design Principles:
    1. Single source of truth for channel eligibility
    2. Explicit state transitions with validation
    3. Fail-closed: reject invalid transitions
    4. Observable: log all transitions and rejections
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

from agent.domain.ports.observability import Observability


class ProspectStage(str, Enum):
    """Valid prospect lifecycle stages."""
    NEW = "new"
    OUTBOUND_SENT = "outbound_sent"
    EMAIL_OPENED = "email_opened"
    REPLIED = "replied"
    QUALIFIED = "qualified"
    SCHEDULED = "scheduled"
    CALL_BOOKED = "call_booked"
    DISQUALIFIED = "disqualified"


class Channel(str, Enum):
    """Available communication channels."""
    EMAIL = "email"
    SMS = "sms"
    CALCOM = "calcom"
    CRM = "crm"


@dataclass
class ChannelEligibility:
    """Result of channel eligibility check."""
    eligible: bool
    channel: Channel
    stage: ProspectStage
    reason: str


@dataclass
class StateTransition:
    """Result of state transition attempt."""
    success: bool
    from_stage: ProspectStage
    to_stage: ProspectStage
    reason: str
    allowed_channels: list[Channel]


# Warm lead stages (SMS eligible)
WARM_LEAD_STAGES = {
    ProspectStage.EMAIL_OPENED,
    ProspectStage.REPLIED,
    ProspectStage.QUALIFIED,
    ProspectStage.SCHEDULED,
    ProspectStage.CALL_BOOKED,
}

# Qualified stages (Cal.com eligible)
QUALIFIED_STAGES = {
    ProspectStage.QUALIFIED,
    ProspectStage.SCHEDULED,
    ProspectStage.CALL_BOOKED,
}

# Valid state transitions (from_stage → to_stage)
VALID_TRANSITIONS = {
    ProspectStage.NEW: {ProspectStage.OUTBOUND_SENT, ProspectStage.DISQUALIFIED},
    ProspectStage.OUTBOUND_SENT: {ProspectStage.EMAIL_OPENED, ProspectStage.REPLIED, ProspectStage.DISQUALIFIED},
    ProspectStage.EMAIL_OPENED: {ProspectStage.REPLIED, ProspectStage.DISQUALIFIED},
    ProspectStage.REPLIED: {ProspectStage.QUALIFIED, ProspectStage.DISQUALIFIED},
    ProspectStage.QUALIFIED: {ProspectStage.SCHEDULED, ProspectStage.DISQUALIFIED},
    ProspectStage.SCHEDULED: {ProspectStage.CALL_BOOKED, ProspectStage.DISQUALIFIED},
    ProspectStage.CALL_BOOKED: {ProspectStage.DISQUALIFIED},  # Terminal state
    ProspectStage.DISQUALIFIED: set(),  # Terminal state
}


class ChannelOrchestrator:
    """Orchestrates channel selection and state transitions."""
    
    def __init__(self, observability: Observability):
        self.obs = observability
    
    def check_channel_eligibility(
        self,
        channel: Channel,
        current_stage: ProspectStage,
    ) -> ChannelEligibility:
        """
        Check if a channel is eligible for the current prospect stage.
        
        Args:
            channel: The channel to check (email, sms, calcom, crm)
            current_stage: Current prospect lifecycle stage
        
        Returns:
            ChannelEligibility with eligibility status and reason
        """
        if channel == Channel.EMAIL:
            # Email always available (except disqualified)
            if current_stage == ProspectStage.DISQUALIFIED:
                return ChannelEligibility(
                    eligible=False,
                    channel=channel,
                    stage=current_stage,
                    reason="Prospect is disqualified - no outreach allowed",
                )
            return ChannelEligibility(
                eligible=True,
                channel=channel,
                stage=current_stage,
                reason="Email available at all active stages",
            )
        
        elif channel == Channel.SMS:
            # SMS only for warm leads
            if current_stage in WARM_LEAD_STAGES:
                return ChannelEligibility(
                    eligible=True,
                    channel=channel,
                    stage=current_stage,
                    reason=f"Warm lead stage '{current_stage.value}' - SMS eligible",
                )
            return ChannelEligibility(
                eligible=False,
                channel=channel,
                stage=current_stage,
                reason=f"Cold lead stage '{current_stage.value}' - SMS requires warm lead (email_opened, replied, qualified, scheduled, call_booked)",
            )
        
        elif channel == Channel.CALCOM:
            # Cal.com only after qualification
            if current_stage in QUALIFIED_STAGES:
                return ChannelEligibility(
                    eligible=True,
                    channel=channel,
                    stage=current_stage,
                    reason=f"Qualified stage '{current_stage.value}' - Cal.com eligible",
                )
            return ChannelEligibility(
                eligible=False,
                channel=channel,
                stage=current_stage,
                reason=f"Stage '{current_stage.value}' - Cal.com requires qualification (qualified, scheduled, call_booked)",
            )
        
        elif channel == Channel.CRM:
            # CRM always available
            return ChannelEligibility(
                eligible=True,
                channel=channel,
                stage=current_stage,
                reason="CRM updates available at all stages",
            )
        
        # Unknown channel
        return ChannelEligibility(
            eligible=False,
            channel=channel,
            stage=current_stage,
            reason=f"Unknown channel: {channel}",
        )
    
    def transition_stage(
        self,
        from_stage: ProspectStage,
        to_stage: ProspectStage,
        company: str,
    ) -> StateTransition:
        """
        Attempt to transition prospect from one stage to another.
        
        Args:
            from_stage: Current stage
            to_stage: Desired next stage
            company: Company name (for logging)
        
        Returns:
            StateTransition with success status and allowed channels
        """
        # Validate transition
        allowed_next_stages = VALID_TRANSITIONS.get(from_stage, set())
        
        if to_stage not in allowed_next_stages:
            result = StateTransition(
                success=False,
                from_stage=from_stage,
                to_stage=to_stage,
                reason=f"Invalid transition: {from_stage.value} → {to_stage.value}. Allowed: {[s.value for s in allowed_next_stages]}",
                allowed_channels=[],
            )
            self.obs.log_trace("channel_orchestrator_invalid_transition", {
                "company": company,
                "from_stage": from_stage.value,
                "to_stage": to_stage.value,
                "reason": result.reason,
            })
            return result
        
        # Determine allowed channels for new stage
        allowed_channels = [Channel.EMAIL, Channel.CRM]  # Always available
        
        if to_stage in WARM_LEAD_STAGES:
            allowed_channels.append(Channel.SMS)
        
        if to_stage in QUALIFIED_STAGES:
            allowed_channels.append(Channel.CALCOM)
        
        result = StateTransition(
            success=True,
            from_stage=from_stage,
            to_stage=to_stage,
            reason=f"Valid transition: {from_stage.value} → {to_stage.value}",
            allowed_channels=allowed_channels,
        )
        
        self.obs.log_trace("channel_orchestrator_transition", {
            "company": company,
            "from_stage": from_stage.value,
            "to_stage": to_stage.value,
            "allowed_channels": [c.value for c in allowed_channels],
        })
        
        return result
    
    def get_next_action(
        self,
        current_stage: ProspectStage,
        engagement_signal: Literal["email_opened", "email_replied", "qualified", "scheduled"] | None,
        company: str,
    ) -> dict:
        """
        Recommend next action based on current stage and engagement signal.
        
        Args:
            current_stage: Current prospect stage
            engagement_signal: Latest engagement signal (if any)
            company: Company name (for logging)
        
        Returns:
            Dict with recommended action, channels, and next stage
        """
        # Map engagement signal to next stage
        next_stage = current_stage
        
        if engagement_signal == "email_opened" and current_stage == ProspectStage.OUTBOUND_SENT:
            next_stage = ProspectStage.EMAIL_OPENED
        elif engagement_signal == "email_replied" and current_stage in {ProspectStage.OUTBOUND_SENT, ProspectStage.EMAIL_OPENED}:
            next_stage = ProspectStage.REPLIED
        elif engagement_signal == "qualified" and current_stage == ProspectStage.REPLIED:
            next_stage = ProspectStage.QUALIFIED
        elif engagement_signal == "scheduled" and current_stage == ProspectStage.QUALIFIED:
            next_stage = ProspectStage.SCHEDULED
        
        # Attempt transition
        transition = self.transition_stage(current_stage, next_stage, company)
        
        if not transition.success:
            # No valid transition - maintain current stage
            return {
                "action": "maintain",
                "current_stage": current_stage.value,
                "next_stage": current_stage.value,
                "channels": [Channel.EMAIL.value, Channel.CRM.value],
                "reason": "No engagement signal or invalid transition",
            }
        
        # Recommend action based on new stage
        action_map = {
            ProspectStage.OUTBOUND_SENT: "send_initial_email",
            ProspectStage.EMAIL_OPENED: "send_followup_email",
            ProspectStage.REPLIED: "qualify_prospect",
            ProspectStage.QUALIFIED: "send_calcom_link",
            ProspectStage.SCHEDULED: "send_sms_reminder",
            ProspectStage.CALL_BOOKED: "prepare_discovery_brief",
        }
        
        action = action_map.get(next_stage, "update_crm")
        
        result = {
            "action": action,
            "current_stage": current_stage.value,
            "next_stage": next_stage.value,
            "channels": [c.value for c in transition.allowed_channels],
            "reason": transition.reason,
        }
        
        self.obs.log_trace("channel_orchestrator_next_action", {
            "company": company,
            **result,
        })
        
        return result
