"""Data repository port for accessing enrichment data sources."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from agent.domain.entities.prospect import (
    Firmographics,
    FundingEvent,
    LayoffSignal,
    LeadershipChange,
    JobSignals,
)


class DataRepository(ABC):
    """Port for accessing enrichment data sources."""
    
    @abstractmethod
    def get_firmographics(self, company_name: str) -> Firmographics:
        """Get company firmographic data."""
        pass
    
    @abstractmethod
    def get_funding_event(self, company_name: str, firmographics: Firmographics) -> FundingEvent | None:
        """Get recent funding event if any."""
        pass
    
    @abstractmethod
    def get_layoff_signal(self, company_name: str) -> LayoffSignal | None:
        """Get layoff signal if any."""
        pass
    
    @abstractmethod
    def get_leadership_change(self, company_name: str, firmographics: Firmographics) -> LeadershipChange | None:
        """Get leadership transition if any."""
        pass
    
    @abstractmethod
    async def get_job_signals(self, company_name: str, website: str) -> JobSignals:
        """Get hiring signals from job postings."""
        pass
