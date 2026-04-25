"""Dependency injection container - wires up clean architecture."""

from __future__ import annotations

import os

from agent.adapters.gateways.calcom_adapter import CalComAdapter
from agent.adapters.gateways.hubspot_crm_adapter import HubSpotCRMAdapter
from agent.adapters.gateways.mailersend_adapter import MailerSendAdapter
from agent.adapters.gateways.sms_adapter import SMSAdapter
from agent.adapters.observability.langfuse_adapter import LangfuseAdapter
from agent.adapters.repositories.file_data_repository import FileDataRepository
from agent.domain.use_cases.enrich_prospect import EnrichProspect
from agent.domain.use_cases.qualify_prospect import QualifyProspect


class Container:
    """Dependency injection container."""
    
    def __init__(self):
        # Infrastructure adapters (outer layer)
        self._observability = LangfuseAdapter()
        self._data_repo = FileDataRepository(
            crunchbase_path=os.getenv("CRUNCHBASE_DATA_PATH", "data/crunchbase_sample.json"),
            layoffs_path=os.getenv("LAYOFFS_DATA_PATH", "data/layoffs.csv"),
        )
        self._crm = HubSpotCRMAdapter()
        self._email = MailerSendAdapter()
        self._sms = SMSAdapter()
        self._scheduling = CalComAdapter()
        
        # Use cases (application layer) - inject dependencies
        self._enrich_prospect = EnrichProspect(
            data_repo=self._data_repo,
            observability=self._observability,
        )
        self._qualify_prospect = QualifyProspect(
            observability=self._observability,
        )
    
    @property
    def enrich_prospect(self) -> EnrichProspect:
        """Get enrich prospect use case."""
        return self._enrich_prospect
    
    @property
    def qualify_prospect(self) -> QualifyProspect:
        """Get qualify prospect use case."""
        return self._qualify_prospect
    
    @property
    def crm(self) -> HubSpotCRMAdapter:
        """Get CRM repository."""
        return self._crm
    
    @property
    def email(self) -> MailerSendAdapter:
        """Get email gateway."""
        return self._email
    
    @property
    def sms(self) -> SMSAdapter:
        """Get SMS gateway."""
        return self._sms
    
    @property
    def scheduling(self) -> CalComAdapter:
        """Get scheduling gateway."""
        return self._scheduling
    
    @property
    def observability(self) -> LangfuseAdapter:
        """Get observability."""
        return self._observability


# Global container instance
container = Container()
