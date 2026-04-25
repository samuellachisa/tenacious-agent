"""Domain entities for prospect enrichment and qualification."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class FundingEvent:
    """Represents a funding round."""
    round_type: str
    amount_usd: float
    date: datetime | None
    recency_days: int
    
    @property
    def is_recent(self) -> bool:
        """Funding within last 180 days."""
        return self.recency_days <= 180


@dataclass
class LayoffSignal:
    """Represents a layoff event."""
    company_name: str
    date: datetime | None
    percentage: float
    total_laid_off: int
    recency_days: int
    
    @property
    def is_significant(self) -> bool:
        """Layoff >= 10% or >= 50 people."""
        return self.percentage >= 10.0 or self.total_laid_off >= 50


@dataclass
class LeadershipChange:
    """Represents a CTO or leadership transition."""
    role: str
    name: str
    tenure_days: int
    
    @property
    def is_new(self) -> bool:
        """Tenure < 90 days."""
        return self.tenure_days < 90


@dataclass
class AIMaturity:
    """AI/ML maturity assessment."""
    score: int  # 0-10
    has_ml_team: bool
    has_data_platform: bool
    has_ai_products: bool
    
    @property
    def is_mature(self) -> bool:
        """Score >= 6."""
        return self.score >= 6


@dataclass
class JobSignals:
    """Hiring signals from job postings."""
    total_open_roles: int
    engineering_roles: int
    ai_ml_roles: int
    senior_roles: int
    
    @property
    def is_hiring_aggressively(self) -> bool:
        """10+ engineering roles."""
        return self.engineering_roles >= 10


@dataclass
class Firmographics:
    """Company firmographic data."""
    name: str
    industry: str
    country: str
    city: str
    employee_count: int
    founded_year: int | None
    description: str
    website: str
    total_funding_usd: float
    linkedin_url: str
    
    @property
    def is_enterprise(self) -> bool:
        """500+ employees."""
        return self.employee_count >= 500
    
    @property
    def is_well_funded(self) -> bool:
        """$10M+ total funding."""
        return self.total_funding_usd >= 10_000_000


@dataclass
class Enrichment:
    """Complete enrichment data for a prospect."""
    company_name: str
    firmographics: Firmographics
    funding_event: FundingEvent | None
    layoff_signal: LayoffSignal | None
    leadership_change: LeadershipChange | None
    ai_maturity: AIMaturity
    job_signals: JobSignals
    enriched_at: datetime
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for backward compatibility."""
        return {
            "company": self.company_name,
            "firmographics": {
                "name": self.firmographics.name,
                "industry": self.firmographics.industry,
                "country": self.firmographics.country,
                "city": self.firmographics.city,
                "employee_count": self.firmographics.employee_count,
                "founded_year": self.firmographics.founded_year,
                "description": self.firmographics.description,
                "website": self.firmographics.website,
                "total_funding_usd": self.firmographics.total_funding_usd,
                "linkedin_url": self.firmographics.linkedin_url,
            },
            "funding_event": {
                "round_type": self.funding_event.round_type,
                "amount_usd": self.funding_event.amount_usd,
                "date": self.funding_event.date.isoformat() if self.funding_event.date else None,
                "recency_days": self.funding_event.recency_days,
            } if self.funding_event else None,
            "layoff_signal": {
                "company_name": self.layoff_signal.company_name,
                "date": self.layoff_signal.date.isoformat() if self.layoff_signal.date else None,
                "percentage": self.layoff_signal.percentage,
                "total_laid_off": self.layoff_signal.total_laid_off,
                "recency_days": self.layoff_signal.recency_days,
            } if self.layoff_signal else None,
            "leadership_change": {
                "role": self.leadership_change.role,
                "name": self.leadership_change.name,
                "tenure_days": self.leadership_change.tenure_days,
            } if self.leadership_change else None,
            "ai_maturity": {
                "score": self.ai_maturity.score,
                "has_ml_team": self.ai_maturity.has_ml_team,
                "has_data_platform": self.ai_maturity.has_data_platform,
                "has_ai_products": self.ai_maturity.has_ai_products,
            },
            "job_signals": {
                "total_open_roles": self.job_signals.total_open_roles,
                "engineering_roles": self.job_signals.engineering_roles,
                "ai_ml_roles": self.job_signals.ai_ml_roles,
                "senior_roles": self.job_signals.senior_roles,
            },
            "enriched_at": self.enriched_at.isoformat(),
        }


@dataclass
class Qualification:
    """Prospect qualification result."""
    qualified: bool
    segment: str  # recently_funded, cost_restructuring, leadership_transition, capability_gap
    segment_name: str
    confidence: float  # 0.0-1.0
    acv_estimate: int
    pitch_language: str
    reason: str
    manual_review: bool = False
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for backward compatibility."""
        return {
            "qualified": self.qualified,
            "segment": self.segment,
            "segment_name": self.segment_name,
            "confidence": self.confidence,
            "acv_estimate": self.acv_estimate,
            "pitch_language": self.pitch_language,
            "reason": self.reason,
            "manual_review": self.manual_review,
        }


@dataclass
class Contact:
    """CRM contact representation."""
    email: str
    first_name: str
    last_name: str
    company: str
    phone: str | None
    stage: str  # new, outbound_sent, email_opened, replied, qualified, scheduled, call_booked
    properties: dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_warm_lead(self) -> bool:
        """Check if contact is warm (replied or engaged)."""
        warm_stages = {"replied", "qualified", "scheduled", "call_booked", "email_opened"}
        return self.stage in warm_stages
