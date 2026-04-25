"""File-based data repository implementation."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agent.domain.entities.prospect import (
    Firmographics,
    FundingEvent,
    LayoffSignal,
    LeadershipChange,
    JobSignals,
)
from agent.domain.ports.data_repository import DataRepository


class FileDataRepository(DataRepository):
    """File-based implementation of data repository."""
    
    def __init__(
        self,
        crunchbase_path: str = "data/crunchbase_sample.json",
        layoffs_path: str = "data/layoffs.csv",
    ):
        self.crunchbase_path = Path(crunchbase_path)
        self.layoffs_path = Path(layoffs_path)
    
    def get_firmographics(self, company_name: str) -> Firmographics:
        """Get company firmographic data from Crunchbase file."""
        try:
            with open(self.crunchbase_path, "r", encoding="utf-8") as fh:
                records: list[dict] = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            records = []
        
        normalised = company_name.strip().lower()
        for record in records:
            if record.get("name", "").strip().lower() == normalised:
                founded_raw = record.get("founded_on", "")
                founded_year = None
                if founded_raw:
                    try:
                        founded_year = int(founded_raw[:4])
                    except ValueError:
                        pass
                
                return Firmographics(
                    name=record.get("name", company_name),
                    industry=record.get("category_list", "Unknown"),
                    country=record.get("country_code", "Unknown"),
                    city=record.get("city", "Unknown"),
                    employee_count=record.get("employee_count", 0),
                    founded_year=founded_year,
                    description=record.get("short_description", ""),
                    website=record.get("homepage_url", ""),
                    total_funding_usd=record.get("total_funding_usd", 0),
                    linkedin_url=record.get("linkedin_url", ""),
                )
        
        # Company not found - return defaults
        return Firmographics(
            name=company_name,
            industry="Unknown",
            country="Unknown",
            city="Unknown",
            employee_count=0,
            founded_year=None,
            description="",
            website="",
            total_funding_usd=0,
            linkedin_url="",
        )
    
    def get_funding_event(
        self,
        company_name: str,
        firmographics: Firmographics,
    ) -> FundingEvent | None:
        """Get recent funding event from Crunchbase data."""
        try:
            with open(self.crunchbase_path, "r", encoding="utf-8") as fh:
                records: list[dict] = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        
        normalised = company_name.strip().lower()
        for record in records:
            if record.get("name", "").strip().lower() == normalised:
                last_funding_type = record.get("last_funding_type", "")
                last_funding_at = record.get("last_funding_at", "")
                
                if not last_funding_type or not last_funding_at:
                    return None
                
                # Parse date
                try:
                    funding_date = datetime.fromisoformat(last_funding_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    return None
                
                now = datetime.now(timezone.utc)
                recency_days = (now - funding_date).days
                
                # Only return if within 180 days
                if recency_days > 180:
                    return None
                
                return FundingEvent(
                    round_type=last_funding_type,
                    amount_usd=record.get("total_funding_usd", 0),
                    date=funding_date,
                    recency_days=recency_days,
                )
        
        return None
    
    def get_layoff_signal(self, company_name: str) -> LayoffSignal | None:
        """Get layoff signal from CSV file."""
        try:
            with open(self.layoffs_path, "r", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
        except (FileNotFoundError, csv.Error):
            return None
        
        normalised = company_name.strip().lower()
        for row in rows:
            if row.get("company", "").strip().lower() == normalised:
                date_str = row.get("date", "")
                try:
                    layoff_date = datetime.fromisoformat(date_str)
                except (ValueError, AttributeError):
                    layoff_date = None
                
                now = datetime.now(timezone.utc)
                recency_days = (now - layoff_date).days if layoff_date else 999
                
                # Only return if within 180 days
                if recency_days > 180:
                    return None
                
                try:
                    percentage = float(row.get("percentage", "0"))
                    total_laid_off = int(row.get("total_laid_off", "0"))
                except (ValueError, TypeError):
                    percentage = 0.0
                    total_laid_off = 0
                
                return LayoffSignal(
                    company_name=row.get("company", company_name),
                    date=layoff_date,
                    percentage=percentage,
                    total_laid_off=total_laid_off,
                    recency_days=recency_days,
                )
        
        return None
    
    def get_leadership_change(
        self,
        company_name: str,
        firmographics: Firmographics,
    ) -> LeadershipChange | None:
        """Get leadership change from Crunchbase data."""
        try:
            with open(self.crunchbase_path, "r", encoding="utf-8") as fh:
                records: list[dict] = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return None
        
        normalised = company_name.strip().lower()
        for record in records:
            if record.get("name", "").strip().lower() == normalised:
                cto_name = record.get("cto_name", "")
                cto_tenure_days = record.get("cto_tenure_days")
                
                if not cto_name or cto_tenure_days is None:
                    return None
                
                try:
                    tenure = int(cto_tenure_days)
                except (ValueError, TypeError):
                    return None
                
                # Only return if tenure < 90 days
                if tenure >= 90:
                    return None
                
                return LeadershipChange(
                    role="CTO",
                    name=cto_name,
                    tenure_days=tenure,
                )
        
        return None
    
    async def get_job_signals(self, company_name: str, website: str) -> JobSignals:
        """Get hiring signals from job postings."""
        # For now, extract from Crunchbase data
        # In production, this would scrape careers pages
        try:
            with open(self.crunchbase_path, "r", encoding="utf-8") as fh:
                records: list[dict] = json.load(fh)
        except (FileNotFoundError, json.JSONDecodeError):
            return JobSignals(
                total_open_roles=0,
                engineering_roles=0,
                ai_ml_roles=0,
                senior_roles=0,
            )
        
        normalised = company_name.strip().lower()
        for record in records:
            if record.get("name", "").strip().lower() == normalised:
                open_roles = record.get("open_roles", [])
                
                engineering_roles = sum(
                    1 for role in open_roles
                    if any(kw in role.lower() for kw in ["engineer", "developer", "architect", "technical"])
                )
                
                ai_ml_roles = sum(
                    1 for role in open_roles
                    if any(kw in role.lower() for kw in ["ai", "ml", "machine learning", "data scientist"])
                )
                
                senior_roles = sum(
                    1 for role in open_roles
                    if any(kw in role.lower() for kw in ["senior", "lead", "principal", "staff"])
                )
                
                return JobSignals(
                    total_open_roles=len(open_roles),
                    engineering_roles=engineering_roles,
                    ai_ml_roles=ai_ml_roles,
                    senior_roles=senior_roles,
                )
        
        return JobSignals(
            total_open_roles=0,
            engineering_roles=0,
            ai_ml_roles=0,
            senior_roles=0,
        )
