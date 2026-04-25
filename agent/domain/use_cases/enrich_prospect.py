"""Enrich prospect use case - pure business logic."""

from __future__ import annotations

from datetime import datetime, timezone

from agent.domain.entities.prospect import Enrichment, AIMaturity
from agent.domain.ports.data_repository import DataRepository
from agent.domain.ports.observability import Observability


class EnrichProspect:
    """Use case for enriching prospect data."""
    
    def __init__(
        self,
        data_repo: DataRepository,
        observability: Observability,
    ):
        self.data = data_repo
        self.obs = observability
    
    async def execute(self, company_name: str) -> Enrichment:
        """Execute enrichment pipeline."""
        self.obs.log_trace("enrichment_start", {"company": company_name})
        
        # Step 1: Firmographics
        firmographics = self.data.get_firmographics(company_name)
        
        # Step 2: Funding event
        funding_event = self.data.get_funding_event(company_name, firmographics)
        
        # Step 3: Layoff signal
        layoff_signal = self.data.get_layoff_signal(company_name)
        
        # Step 4: Leadership change
        leadership_change = self.data.get_leadership_change(company_name, firmographics)
        
        # Step 5: Job signals
        job_signals = await self.data.get_job_signals(company_name, firmographics.website)
        
        # Step 6: AI maturity (business logic)
        ai_maturity = self._score_ai_maturity(
            firmographics.description,
            job_signals.ai_ml_roles,
        )
        
        enrichment = Enrichment(
            company_name=company_name,
            firmographics=firmographics,
            funding_event=funding_event,
            layoff_signal=layoff_signal,
            leadership_change=leadership_change,
            ai_maturity=ai_maturity,
            job_signals=job_signals,
            enriched_at=datetime.now(timezone.utc),
        )
        
        self.obs.log_trace("enrichment_complete", {
            "company": company_name,
            "has_funding": funding_event is not None,
            "has_layoff": layoff_signal is not None,
            "has_leadership_change": leadership_change is not None,
            "ai_maturity_score": ai_maturity.score,
        })
        
        return enrichment
    
    def _score_ai_maturity(self, description: str, ai_ml_roles: int) -> AIMaturity:
        """Score AI/ML maturity based on description and hiring."""
        desc_lower = description.lower()
        
        # Check for AI/ML indicators
        has_ml_team = any(kw in desc_lower for kw in [
            "machine learning", "artificial intelligence", "deep learning",
            "ml engineer", "data scientist", "ai research"
        ])
        
        has_data_platform = any(kw in desc_lower for kw in [
            "data platform", "data infrastructure", "big data",
            "data pipeline", "analytics platform"
        ])
        
        has_ai_products = any(kw in desc_lower for kw in [
            "ai-powered", "ml-driven", "intelligent", "predictive",
            "recommendation engine", "personalization"
        ])
        
        # Calculate score
        score = 0
        if has_ml_team:
            score += 3
        if has_data_platform:
            score += 2
        if has_ai_products:
            score += 3
        if ai_ml_roles >= 5:
            score += 2
        elif ai_ml_roles >= 2:
            score += 1
        
        return AIMaturity(
            score=min(score, 10),
            has_ml_team=has_ml_team,
            has_data_platform=has_data_platform,
            has_ai_products=has_ai_products,
        )
