"""
Job post history storage and retrieval for hiring velocity calculation.

Stores daily snapshots of job post counts to enable 60-day delta computation.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _get_snapshots_dir() -> Path:
    """Get the directory for job post snapshots."""
    base = Path(os.getenv("JOB_SNAPSHOTS_PATH", "data/job_snapshots"))
    base.mkdir(parents=True, exist_ok=True)
    return base


def _get_company_snapshot_path(company_domain: str) -> Path:
    """Get the snapshot directory for a specific company."""
    snapshots_dir = _get_snapshots_dir()
    # Sanitize domain for filesystem
    safe_domain = company_domain.lower().replace(".", "_").replace("/", "_")
    company_dir = snapshots_dir / safe_domain
    company_dir.mkdir(parents=True, exist_ok=True)
    return company_dir


def store_job_snapshot(
    company_domain: str,
    open_roles_count: int,
    ai_roles_count: int,
    source: str,
    timestamp: datetime | None = None,
) -> Path:
    """
    Store a snapshot of job post counts for a company.
    
    Args:
        company_domain: Company domain (e.g., "dataflow.tech")
        open_roles_count: Total number of open roles
        ai_roles_count: Number of AI/ML roles
        source: Data source (e.g., "playwright_scrape", "crunchbase_sample")
        timestamp: Snapshot timestamp (defaults to now)
    
    Returns:
        Path to the stored snapshot file
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)
    
    company_dir = _get_company_snapshot_path(company_domain)
    
    # Use date as filename: YYYY-MM-DD.json
    date_str = timestamp.strftime("%Y-%m-%d")
    snapshot_path = company_dir / f"{date_str}.json"
    
    snapshot_data = {
        "company_domain": company_domain,
        "date": date_str,
        "timestamp": timestamp.isoformat(),
        "open_roles_count": open_roles_count,
        "ai_roles_count": ai_roles_count,
        "source": source,
    }
    
    with open(snapshot_path, "w", encoding="utf-8") as fh:
        json.dump(snapshot_data, fh, indent=2)
    
    return snapshot_path


def get_historical_snapshot(
    company_domain: str,
    days_ago: int = 60,
    reference_date: datetime | None = None,
) -> dict[str, Any] | None:
    """
    Retrieve a historical job post snapshot from N days ago.
    
    Args:
        company_domain: Company domain (e.g., "dataflow.tech")
        days_ago: Number of days to look back (default: 60)
        reference_date: Reference date for lookback (defaults to now)
    
    Returns:
        Snapshot dict with open_roles_count, ai_roles_count, source, timestamp
        or None if no snapshot exists for that date
    """
    if reference_date is None:
        reference_date = datetime.now(timezone.utc)
    
    target_date = reference_date - timedelta(days=days_ago)
    company_dir = _get_company_snapshot_path(company_domain)
    
    # Try exact date first
    date_str = target_date.strftime("%Y-%m-%d")
    snapshot_path = company_dir / f"{date_str}.json"
    
    if snapshot_path.exists():
        with open(snapshot_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    
    # If exact date not found, search for nearest snapshot within ±7 days
    for offset in range(1, 8):
        # Try earlier dates first
        for delta in [-offset, offset]:
            alt_date = target_date + timedelta(days=delta)
            alt_date_str = alt_date.strftime("%Y-%m-%d")
            alt_path = company_dir / f"{alt_date_str}.json"
            
            if alt_path.exists():
                with open(alt_path, "r", encoding="utf-8") as fh:
                    return json.load(fh)
    
    # No snapshot found within ±7 days
    return None


def get_all_snapshots(company_domain: str) -> list[dict[str, Any]]:
    """
    Get all historical snapshots for a company, sorted by date (oldest first).
    
    Args:
        company_domain: Company domain (e.g., "dataflow.tech")
    
    Returns:
        List of snapshot dicts sorted by date
    """
    company_dir = _get_company_snapshot_path(company_domain)
    
    snapshots = []
    for snapshot_file in sorted(company_dir.glob("*.json")):
        try:
            with open(snapshot_file, "r", encoding="utf-8") as fh:
                snapshots.append(json.load(fh))
        except (json.JSONDecodeError, IOError):
            continue
    
    return snapshots


def cleanup_old_snapshots(company_domain: str, keep_days: int = 90) -> int:
    """
    Delete snapshots older than keep_days to prevent unbounded storage growth.
    
    Args:
        company_domain: Company domain (e.g., "dataflow.tech")
        keep_days: Number of days of history to retain (default: 90)
    
    Returns:
        Number of snapshots deleted
    """
    company_dir = _get_company_snapshot_path(company_domain)
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=keep_days)
    
    deleted_count = 0
    for snapshot_file in company_dir.glob("*.json"):
        try:
            # Parse date from filename (YYYY-MM-DD.json)
            date_str = snapshot_file.stem
            snapshot_date = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            
            if snapshot_date < cutoff_date:
                snapshot_file.unlink()
                deleted_count += 1
        except (ValueError, OSError):
            continue
    
    return deleted_count
