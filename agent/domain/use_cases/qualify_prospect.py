"""Qualify prospect use case - pure business logic."""

from __future__ import annotations

from agent.domain.entities.prospect import Enrichment, Qualification
from agent.domain.ports.observability import Observability

# Hard disqualifier keywords
DISQUALIFIER_KEYWORDS = {
    "consulting", "staffing", "recruiting", "outsourcing",
    "headhunting", "talent acquisition", "executive search",
    "managed services", "bpo", "business process outsourcing",
}

# ACV estimates per segment
SEGMENT_ACV = {
    "recently_funded": 85_000,
    "cost_restructuring": 60_000,
    "leadership_transition": 75_000,
    "capability_gap": 95_000,
}

SEGMENT_DISPLAY_NAMES = {
    "recently_funded": "Recently Funded (Series A/B)",
    "cost_restructuring": "Cost Restructuring (Post-Layoff)",
    "leadership_transition": "Leadership Transition (New CTO/VP Eng)",
    "capability_gap": "Capability Gap (AI Maturity ≥ 6)",
}


class QualifyProspect:
    """Use case for qualifying prospects into ICP segments."""
    
    def __init__(self, observability: Observability):
        self.obs = observability
    
    def execute(self, enrichment: Enrichment) -> Qualification:
        """Execute qualification logic."""
        company = enrichment.company_name
        
        # Hard disqualification check
        combined_text = f"{enrichment.firmographics.industry} {enrichment.firmographics.description}".lower()
        for kw in DISQUALIFIER_KEYWORDS:
            if kw in combined_text:
                result = Qualification(
                    qualified=False,
                    segment="",
                    segment_name="Disqualified",
                    confidence=0.0,
                    acv_estimate=0,
                    pitch_language="",
                    reason=f"Hard disqualifier matched: '{kw}' found in industry/description.",
                    manual_review=False,
                )
                self.obs.log_trace("qualifier_disqualified", {"company": company, "reason": result.reason})
                return result
        
        # Check for mixed signals (funding + layoff)
        if enrichment.funding_event and enrichment.layoff_signal:
            if enrichment.funding_event.is_recent and enrichment.layoff_signal.is_significant:
                result = self._handle_mixed_signal(enrichment)
                self.obs.log_trace("qualifier_mixed_signal", {"company": company, **result.to_dict()})
                return result
        
        # Segment priority: recently_funded > leadership_transition > cost_restructuring > capability_gap
        
        # Segment 1: Recently funded
        if enrichment.funding_event and enrichment.funding_event.is_recent:
            result = self._qualify_recently_funded(enrichment)
            self.obs.log_trace("qualifier_result", {"company": company, **result.to_dict()})
            return result
        
        # Segment 2: Leadership transition
        if enrichment.leadership_change and enrichment.leadership_change.is_new:
            result = self._qualify_leadership_transition(enrichment)
            self.obs.log_trace("qualifier_result", {"company": company, **result.to_dict()})
            return result
        
        # Segment 3: Cost restructuring
        if enrichment.layoff_signal and enrichment.layoff_signal.is_significant:
            # Mid-market gate: 50-1000 employees
            if 50 <= enrichment.firmographics.employee_count <= 1000:
                result = self._qualify_cost_restructuring(enrichment)
                self.obs.log_trace("qualifier_result", {"company": company, **result.to_dict()})
                return result
        
        # Segment 4: Capability gap (AI maturity >= 6)
        if enrichment.ai_maturity.is_mature:
            result = self._qualify_capability_gap(enrichment)
            self.obs.log_trace("qualifier_result", {"company": company, **result.to_dict()})
            return result
        
        # Not qualified
        result = Qualification(
            qualified=False,
            segment="",
            segment_name="Not Qualified",
            confidence=0.0,
            acv_estimate=0,
            pitch_language="",
            reason=(
                f"No qualifying ICP signals detected. "
                f"Funding: {enrichment.funding_event is not None}, "
                f"Layoff: {enrichment.layoff_signal is not None}, "
                f"Leadership: {enrichment.leadership_change is not None}, "
                f"AI maturity: {enrichment.ai_maturity.score}"
            ),
            manual_review=False,
        )
        self.obs.log_trace("qualifier_not_qualified", {"company": company, **result.to_dict()})
        return result
    
    def _handle_mixed_signal(self, enrichment: Enrichment) -> Qualification:
        """Handle funding + layoff mixed signal."""
        segment = "recently_funded"
        confidence = 0.55  # Reduced for mixed signal
        
        pitch = self._build_pitch(segment, enrichment)
        
        return Qualification(
            qualified=True,
            segment=segment,
            segment_name=SEGMENT_DISPLAY_NAMES[segment],
            confidence=confidence,
            acv_estimate=SEGMENT_ACV[segment],
            pitch_language=pitch,
            reason=(
                f"Mixed signal: {enrichment.funding_event.round_type} "
                f"({enrichment.funding_event.recency_days} days ago) AND layoff of "
                f"{enrichment.layoff_signal.total_laid_off} people "
                f"({enrichment.layoff_signal.recency_days} days ago). "
                "Defaulting to recently_funded — flagged for manual review."
            ),
            manual_review=True,
        )
    
    def _qualify_recently_funded(self, enrichment: Enrichment) -> Qualification:
        """Qualify as recently funded segment."""
        segment = "recently_funded"
        funding = enrichment.funding_event
        
        # Confidence based on recency
        if funding.recency_days <= 60:
            confidence = 0.95
        elif funding.recency_days <= 120:
            confidence = 0.85
        else:
            confidence = 0.75
        
        pitch = self._build_pitch(segment, enrichment)
        
        return Qualification(
            qualified=True,
            segment=segment,
            segment_name=SEGMENT_DISPLAY_NAMES[segment],
            confidence=confidence,
            acv_estimate=SEGMENT_ACV[segment],
            pitch_language=pitch,
            reason=(
                f"{funding.round_type.replace('_', ' ').title()} funding detected: "
                f"${funding.amount_usd:,.0f} — {funding.recency_days} days ago. "
                "Company is in active growth phase with capital to deploy on talent."
            ),
            manual_review=False,
        )
    
    def _qualify_leadership_transition(self, enrichment: Enrichment) -> Qualification:
        """Qualify as leadership transition segment."""
        segment = "leadership_transition"
        leadership = enrichment.leadership_change
        
        # Confidence based on tenure
        if leadership.tenure_days <= 30:
            confidence = 0.90
        elif leadership.tenure_days <= 60:
            confidence = 0.80
        else:
            confidence = 0.70
        
        pitch = self._build_pitch(segment, enrichment)
        
        return Qualification(
            qualified=True,
            segment=segment,
            segment_name=SEGMENT_DISPLAY_NAMES[segment],
            confidence=confidence,
            acv_estimate=SEGMENT_ACV[segment],
            pitch_language=pitch,
            reason=(
                f"New {leadership.role} ({leadership.name}) "
                f"joined {leadership.tenure_days} days ago. "
                "New technical leadership typically drives vendor and team restructuring."
            ),
            manual_review=False,
        )
    
    def _qualify_cost_restructuring(self, enrichment: Enrichment) -> Qualification:
        """Qualify as cost restructuring segment."""
        segment = "cost_restructuring"
        layoff = enrichment.layoff_signal
        
        # Confidence based on layoff size and recency
        confidence = 0.70
        if layoff.percentage >= 15:
            confidence += 0.10
        if layoff.recency_days <= 90:
            confidence += 0.10
        confidence = min(confidence, 0.95)
        
        pitch = self._build_pitch(segment, enrichment)
        
        return Qualification(
            qualified=True,
            segment=segment,
            segment_name=SEGMENT_DISPLAY_NAMES[segment],
            confidence=confidence,
            acv_estimate=SEGMENT_ACV[segment],
            pitch_language=pitch,
            reason=(
                f"Post-layoff mid-market: {layoff.total_laid_off} headcount reduction "
                f"({layoff.percentage:.1f}%) — {layoff.recency_days} days ago. "
                "Company is optimising cost structure — outsourced talent is a natural fit."
            ),
            manual_review=False,
        )
    
    def _qualify_capability_gap(self, enrichment: Enrichment) -> Qualification:
        """Qualify as capability gap segment."""
        segment = "capability_gap"
        ai = enrichment.ai_maturity
        
        # Confidence based on AI maturity score and hiring
        confidence = 0.60 + (ai.score / 10 * 0.20)
        if enrichment.job_signals.ai_ml_roles >= 3:
            confidence += 0.10
        confidence = min(confidence, 0.95)
        
        pitch = self._build_pitch(segment, enrichment)
        
        return Qualification(
            qualified=True,
            segment=segment,
            segment_name=SEGMENT_DISPLAY_NAMES[segment],
            confidence=confidence,
            acv_estimate=SEGMENT_ACV[segment],
            pitch_language=pitch,
            reason=(
                f"AI maturity score {ai.score}/10. "
                "Company shows meaningful AI adoption signals but lacks the talent "
                "depth to execute at scale — outsourced AI/ML talent is a direct fit."
            ),
            manual_review=False,
        )
    
    def _build_pitch(self, segment: str, enrichment: Enrichment) -> str:
        """Build segment-specific pitch language."""
        company = enrichment.company_name
        
        if segment == "recently_funded":
            return (
                f"I noticed {company} recently closed a funding round. "
                f"Congrats on the momentum. As you scale your engineering team, "
                f"Tenacious Consulting can place senior engineers and AI/ML specialists "
                f"directly within your team — typically within 2 weeks. "
                f"Would you have 20 minutes this week for a quick discovery call?"
            )
        
        elif segment == "leadership_transition":
            leader = enrichment.leadership_change
            return (
                f"I saw {leader.name} recently joined {company} as {leader.role}. "
                f"New technical leadership often brings fresh vendor and team evaluations. "
                f"Tenacious Consulting specializes in placing senior engineers who can "
                f"hit the ground running. Would you have 20 minutes for a quick call?"
            )
        
        elif segment == "cost_restructuring":
            return (
                f"I understand {company} recently went through a restructuring. "
                f"Many mid-market companies in similar situations find that outsourced "
                f"senior talent offers the flexibility and cost efficiency they need. "
                f"Tenacious Consulting can place engineers within 2 weeks. "
                f"Would you have 20 minutes to explore this?"
            )
        
        elif segment == "capability_gap":
            return (
                f"I noticed {company} is building AI/ML capabilities. "
                f"Tenacious Consulting specializes in placing senior AI/ML engineers "
                f"who can accelerate your roadmap. We typically place within 2 weeks. "
                f"Would you have 20 minutes for a discovery call?"
            )
        
        return ""
