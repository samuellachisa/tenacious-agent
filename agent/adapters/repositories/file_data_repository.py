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
        crunchbase_path: str = "data/crunchbase-companies.csv",
        layoffs_path: str = "data/layoffs.csv",
    ):
        self.crunchbase_path = Path(crunchbase_path)
        self.layoffs_path = Path(layoffs_path)
    
    def get_firmographics(self, company_name: str) -> Firmographics:
        """Get company firmographic data from Crunchbase CSV."""
        try:
            with open(self.crunchbase_path, newline="", encoding="utf-8") as fh:
                records: list[dict] = list(csv.DictReader(fh))
        except FileNotFoundError:
            records = []

        normalised = company_name.strip().lower()
        for record in records:
            if record.get("name", "").strip().lower() == normalised:
                founded_raw = record.get("founded_date", "")
                founded_year = None
                if founded_raw:
                    try:
                        founded_year = int(str(founded_raw)[:4])
                    except ValueError:
                        pass

                employee_count_raw = record.get("num_employees", "0")
                try:
                    emp_count = int(employee_count_raw)
                except (ValueError, TypeError):
                    emp_count = 0

                return Firmographics(
                    name=record.get("name", company_name),
                    industry=record.get("industries", "Unknown"),
                    country=record.get("country_code", "Unknown"),
                    city=record.get("city", record.get("region", "Unknown")),
                    employee_count=emp_count,
                    founded_year=founded_year,
                    description=record.get("about", record.get("short_description", "")),
                    website=record.get("website", record.get("homepage_url", "")),
                    total_funding_usd=0,
                    linkedin_url="",
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
        """Get recent funding event from Crunchbase CSV."""
        try:
            with open(self.crunchbase_path, newline="", encoding="utf-8") as fh:
                records: list[dict] = list(csv.DictReader(fh))
        except FileNotFoundError:
            return None

        normalised = company_name.strip().lower()
        for record in records:
            if record.get("name", "").strip().lower() == normalised:
                funding_raw = record.get("funding_rounds_list", record.get("funding_rounds", ""))
                if not funding_raw or funding_raw in ("null", "", "[]"):
                    return None
                try:
                    import json as _json
                    rounds = _json.loads(funding_raw)
                    if not isinstance(rounds, list) or not rounds:
                        return None
                    latest = rounds[0]
                    last_funding_type = latest.get("investment_type", "")
                    last_funding_at = latest.get("announced_on", "")
                    total_usd = sum(
                        r.get("money_raised", {}).get("value_usd", 0) or 0
                        for r in rounds if isinstance(r, dict)
                    )
                except Exception:
                    return None

                if not last_funding_at:
                    return None

                # Parse date
                try:
                    funding_date = datetime.fromisoformat(last_funding_at.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    try:
                        funding_date = datetime.strptime(last_funding_at[:10], "%Y-%m-%d").replace(
                            tzinfo=timezone.utc
                        )
                    except (ValueError, AttributeError):
                        return None

                now = datetime.now(timezone.utc)
                recency_days = (now - funding_date).days

                # Only return if within 180 days
                if recency_days > 180:
                    return None

                return FundingEvent(
                    round_type=last_funding_type,
                    amount_usd=float(total_usd),
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
        """Leadership change not available in CSV — always returns None."""
        return None
    
    async def get_job_signals(self, company_name: str, website: str) -> JobSignals:
        """Job signals not available in CSV — return empty defaults."""
        return JobSignals(
            total_open_roles=0,
            engineering_roles=0,
            ai_ml_roles=0,
            senior_roles=0,
        )

    def get_crunchbase_companies(self) -> list[dict]:
        """Return all rows from the Crunchbase CSV as a list of dicts."""
        try:
            with open(self.crunchbase_path, newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
        except FileNotFoundError:
            return []
