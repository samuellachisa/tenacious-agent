"""
Signal enrichment pipeline for Tenacious Agent.
Aggregates firmographic, funding, layoff, job-post, and leadership signals
into a unified brief that feeds the ICP qualifier.
"""

from __future__ import annotations

import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from agent.langfuse_client import log_trace

load_dotenv()

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

def _crunchbase_path() -> Path:
    return Path(os.getenv("CRUNCHBASE_DATA_PATH", "data/crunchbase_sample.json"))


def _layoffs_path() -> Path:
    return Path(os.getenv("LAYOFFS_DATA_PATH", "data/layoffs.csv"))


def _briefs_dir() -> Path:
    p = Path("data/briefs")
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------------------
# Firmographics
# ---------------------------------------------------------------------------

def get_crunchbase_firmographics(company_name: str) -> dict[str, Any]:
    """
    Load firmographic data from the local Crunchbase sample JSON.

    Returns a dict with: name, industry, country, city, employee_count,
    founded_year, description, website, total_funding_usd,
    last_funding_type, last_funding_at.
    Falls back to empty defaults if the company is not found.
    """
    path = _crunchbase_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
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

            return {
                "name": record.get("name", company_name),
                "industry": record.get("category_list", "Unknown"),
                "country": record.get("country_code", "Unknown"),
                "city": record.get("city", "Unknown"),
                "employee_count": record.get("employee_count", 0),
                "founded_year": founded_year,
                "description": record.get("short_description", ""),
                "website": record.get("homepage_url", ""),
                "total_funding_usd": record.get("total_funding_usd", 0),
                "last_funding_type": record.get("last_funding_type", ""),
                "last_funding_at": record.get("last_funding_at", ""),
                "linkedin_url": record.get("linkedin_url", ""),
                "cto_name": record.get("cto_name", ""),
                "cto_tenure_days": record.get("cto_tenure_days"),
                "open_roles_raw": record.get("open_roles", []),
                "recent_news": record.get("recent_news", ""),
            }

    # Company not found — return minimal defaults
    return {
        "name": company_name,
        "industry": "Unknown",
        "country": "Unknown",
        "city": "Unknown",
        "employee_count": 0,
        "founded_year": None,
        "description": "",
        "website": "",
        "total_funding_usd": 0,
        "last_funding_type": "",
        "last_funding_at": "",
        "linkedin_url": "",
        "cto_name": "",
        "cto_tenure_days": None,
        "open_roles_raw": [],
        "recent_news": "",
    }


# ---------------------------------------------------------------------------
# Funding signal
# ---------------------------------------------------------------------------

def get_funding_event(
    company_name: str, firmographics: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Check whether the company has a Series A/B/seed funding event in the
    last 180 days.

    Returns a dict with: type, date, days_ago, total_funding_usd, in_window
    or None if no qualifying event is found.
    """
    funding_type = firmographics.get("last_funding_type", "").lower()
    funding_date_str = firmographics.get("last_funding_at", "")

    qualifying_types = {"series_a", "series_b", "seed", "series_c"}
    if funding_type not in qualifying_types:
        return None

    if not funding_date_str:
        return None

    try:
        funding_date = datetime.strptime(funding_date_str[:10], "%Y-%m-%d").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        return None

    now = datetime.now(timezone.utc)
    days_ago = (now - funding_date).days
    in_window = days_ago <= 180

    return {
        "type": funding_type,
        "date": funding_date_str,
        "days_ago": days_ago,
        "total_funding_usd": firmographics.get("total_funding_usd", 0),
        "in_window": in_window,
    }


# ---------------------------------------------------------------------------
# Layoff signal
# ---------------------------------------------------------------------------

def get_layoff_signal(company_name: str) -> dict[str, Any] | None:
    """
    Check the layoffs CSV for a recent layoff event (last 120 days).

    Returns a dict with: date, days_ago, headcount, percentage, in_window
    or None if no event is found.
    """
    path = _layoffs_path()
    normalised = company_name.strip().lower()

    try:
        with open(path, newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                if row.get("Company", "").strip().lower() != normalised:
                    continue

                date_str = row.get("Date", "")
                try:
                    event_date = datetime.strptime(date_str[:10], "%Y-%m-%d").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    continue

                now = datetime.now(timezone.utc)
                days_ago = (now - event_date).days
                in_window = days_ago <= 120

                return {
                    "date": date_str,
                    "days_ago": days_ago,
                    "headcount": _safe_int(row.get("Laid_Off_Count", "0")),
                    "percentage": _safe_float(row.get("Percentage", "0")),
                    "in_window": in_window,
                    "source": row.get("Source", ""),
                    "stage": row.get("Stage", ""),
                    "country": row.get("Country", ""),
                }
    except FileNotFoundError:
        pass

    return None


# ---------------------------------------------------------------------------
# Job post signals (Playwright scrape + firmographic inference)
# ---------------------------------------------------------------------------

async def get_job_post_signals(
    company_name: str, firmographics: dict[str, Any]
) -> dict[str, Any]:
    """
    Derive job-post signals from the Crunchbase open_roles list and attempt
    a lightweight Playwright scrape of the company's careers page.

    Returns: open_roles (int), ai_roles (list), velocity (str),
             source (str), confidence (str).
    """
    open_roles_raw: list[str] = firmographics.get("open_roles_raw", [])

    ai_keywords = {
        "ai", "ml", "machine learning", "artificial intelligence",
        "llm", "nlp", "data scientist", "deep learning", "mlops",
        "ai platform", "ai engineer", "ai product", "ai compliance",
        "ml researcher", "ai lead",
    }

    ai_roles = [
        role for role in open_roles_raw
        if any(kw in role.lower() for kw in ai_keywords)
    ]

    open_count = len(open_roles_raw)
    source = "crunchbase_sample"
    confidence = "medium"

    # Attempt Playwright scrape for richer signal
    scraped_roles = await _scrape_careers_page(
        firmographics.get("website", ""), company_name
    )
    if scraped_roles:
        open_roles_raw = list(set(open_roles_raw + scraped_roles))
        ai_roles = [
            role for role in open_roles_raw
            if any(kw in role.lower() for kw in ai_keywords)
        ]
        open_count = len(open_roles_raw)
        source = "playwright_scrape"
        confidence = "high"

    # Velocity heuristic
    if open_count >= 10:
        velocity = "high"
    elif open_count >= 5:
        velocity = "medium"
    elif open_count >= 1:
        velocity = "low"
    else:
        velocity = "none"

    return {
        "open_roles": open_count,
        "ai_roles": ai_roles,
        "velocity": velocity,
        "source": source,
        "confidence": confidence,
    }


async def _scrape_careers_page(website: str, company_name: str) -> list[str]:
    """
    Attempt a Playwright scrape of the company's /careers or /jobs page.
    Returns a list of role title strings, or empty list on failure.
    """
    if not website:
        return []

    careers_urls = [
        website.rstrip("/") + "/careers",
        website.rstrip("/") + "/jobs",
    ]

    try:
        from playwright.async_api import async_playwright  # type: ignore

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            page = await browser.new_page()

            for url in careers_urls:
                try:
                    await page.goto(url, timeout=8000, wait_until="domcontentloaded")
                    # Extract text from common job listing selectors
                    selectors = [
                        "h2", "h3", ".job-title", ".position-title",
                        "[data-testid='job-title']", ".role-name",
                    ]
                    roles: list[str] = []
                    for sel in selectors:
                        elements = await page.query_selector_all(sel)
                        for el in elements[:20]:
                            text = (await el.inner_text()).strip()
                            if text and len(text) < 100:
                                roles.append(text)
                    if roles:
                        await browser.close()
                        return roles[:30]
                except Exception:
                    continue

            await browser.close()
    except Exception:
        pass

    return []


# ---------------------------------------------------------------------------
# Leadership change signal
# ---------------------------------------------------------------------------

def get_leadership_change(
    company_name: str, firmographics: dict[str, Any]
) -> dict[str, Any] | None:
    """
    Detect a new CTO or VP Engineering in the last 90 days using
    firmographic data (cto_tenure_days field from Crunchbase sample).

    Returns a dict with: role, name, tenure_days, in_window
    or None if no qualifying change is detected.
    """
    cto_name = firmographics.get("cto_name", "")
    tenure_days = firmographics.get("cto_tenure_days")

    if not cto_name or tenure_days is None:
        return None

    in_window = tenure_days <= 90

    return {
        "role": "CTO",
        "name": cto_name,
        "tenure_days": tenure_days,
        "in_window": in_window,
    }


# ---------------------------------------------------------------------------
# AI maturity scoring
# ---------------------------------------------------------------------------

def score_ai_maturity(
    job_signals: dict[str, Any], firmographics: dict[str, Any]
) -> dict[str, Any]:
    """
    Score AI maturity 0-3 with per-signal justification.

    Scoring bands:
      0 = no signal
      1 = weak (low-weight signals only)
      2 = moderate (medium-weight signals present)
      3 = strong (high-weight signals present)

    Signal weights:
      HIGH:   AI-adjacent roles (ML Engineer, AI Platform Lead, etc.)
              Named AI leadership (CTO with AI background)
      MEDIUM: GitHub AI activity (inferred from description keywords)
              Executive commentary on AI (recent_news mentions AI)
      LOW:    ML stack keywords in description
              Strategic communications (website/description mentions AI)
    """
    score = 0
    justification: list[str] = []
    confidence_votes: list[str] = []

    ai_roles: list[str] = job_signals.get("ai_roles", [])
    open_roles: int = job_signals.get("open_roles", 0)
    description: str = firmographics.get("description", "").lower()
    industry: str = firmographics.get("industry", "").lower()
    recent_news: str = firmographics.get("recent_news", "").lower()
    cto_name: str = firmographics.get("cto_name", "")
    cto_tenure: int | None = firmographics.get("cto_tenure_days")

    # HIGH weight: AI-adjacent open roles
    if len(ai_roles) >= 3:
        score += 2
        justification.append(
            f"HIGH: {len(ai_roles)} AI-adjacent open roles detected: "
            + ", ".join(ai_roles[:3])
        )
        confidence_votes.append("high")
    elif len(ai_roles) >= 1:
        score += 1
        justification.append(
            f"HIGH: {len(ai_roles)} AI-adjacent role(s) detected: "
            + ", ".join(ai_roles[:2])
        )
        confidence_votes.append("medium")

    # HIGH weight: Named AI leadership (CTO tenure < 90 days suggests new hire)
    if cto_name and cto_tenure is not None and cto_tenure <= 90:
        score += 1
        justification.append(
            f"HIGH: New CTO '{cto_name}' joined {cto_tenure} days ago — "
            "likely mandate to modernise tech stack."
        )
        confidence_votes.append("high")

    # MEDIUM weight: AI/ML keywords in industry classification
    ai_industry_keywords = {"artificial intelligence", "machine learning", "ai", "ml"}
    if any(kw in industry for kw in ai_industry_keywords):
        score += 1
        justification.append(
            f"MEDIUM: Industry classification contains AI/ML signal: '{industry}'"
        )
        confidence_votes.append("medium")

    # MEDIUM weight: Executive commentary in recent news
    if any(kw in recent_news for kw in ["ai", "machine learning", "llm", "automation"]):
        score += 1
        justification.append(
            "MEDIUM: Recent news mentions AI/ML/automation — executive commentary signal."
        )
        confidence_votes.append("medium")

    # LOW weight: ML stack keywords in description
    ml_stack_keywords = [
        "mlops", "pipeline", "data infrastructure", "model", "inference",
        "vector", "embedding", "neural", "deep learning",
    ]
    if any(kw in description for kw in ml_stack_keywords):
        justification.append(
            "LOW: Product description contains ML stack keywords."
        )
        confidence_votes.append("low")

    # LOW weight: Strategic AI communications in description
    if any(kw in description for kw in ["ai-powered", "ai powered", "artificial intelligence"]):
        justification.append(
            "LOW: Description explicitly references AI-powered capabilities."
        )
        confidence_votes.append("low")

    # Cap score at 3
    score = min(score, 3)

    # Derive confidence from votes
    if confidence_votes.count("high") >= 2:
        confidence = "high"
    elif "high" in confidence_votes or confidence_votes.count("medium") >= 2:
        confidence = "medium"
    elif confidence_votes:
        confidence = "low"
    else:
        confidence = "low"

    if not justification:
        justification.append("No AI maturity signals detected.")

    return {
        "score": score,
        "confidence": confidence,
        "justification": justification,
    }


# ---------------------------------------------------------------------------
# Competitor gap brief
# ---------------------------------------------------------------------------

def build_competitor_gap_brief(
    company_name: str,
    firmographics: dict[str, Any],
    ai_maturity: dict[str, Any],
) -> dict[str, Any]:
    """
    Build a competitive gap brief by comparing the prospect's AI maturity
    against sector peers from the Crunchbase sample.

    Returns: sector, peers_analyzed, company_score, sector_median,
             top_quartile_score, peer_scores, gaps, confidence.
    """
    path = _crunchbase_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            all_records: list[dict] = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        all_records = []

    company_industry = firmographics.get("industry", "").lower()
    company_score = ai_maturity.get("score", 0)

    # Find sector peers (same broad industry, different company)
    peers: list[dict] = []
    for record in all_records:
        if record.get("name", "").strip().lower() == company_name.strip().lower():
            continue
        rec_industry = record.get("category_list", "").lower()
        # Broad sector match: share at least one category keyword
        company_cats = set(company_industry.replace("|", " ").split())
        rec_cats = set(rec_industry.replace("|", " ").split())
        if company_cats & rec_cats:
            peers.append(record)

    # If no sector peers, use all other companies
    if not peers:
        peers = [
            r for r in all_records
            if r.get("name", "").strip().lower() != company_name.strip().lower()
        ]

    # Score each peer's AI maturity using available signals
    peer_scores: list[dict] = []
    for peer in peers[:10]:
        peer_firmographics = {
            "industry": peer.get("category_list", ""),
            "description": peer.get("short_description", "").lower(),
            "recent_news": peer.get("recent_news", "").lower(),
            "cto_name": peer.get("cto_name", ""),
            "cto_tenure_days": peer.get("cto_tenure_days"),
            "open_roles_raw": peer.get("open_roles", []),
        }
        peer_job_signals = {
            "open_roles": len(peer.get("open_roles", [])),
            "ai_roles": [
                r for r in peer.get("open_roles", [])
                if any(
                    kw in r.lower()
                    for kw in {"ai", "ml", "machine learning", "data scientist", "mlops"}
                )
            ],
        }
        peer_maturity = score_ai_maturity(peer_job_signals, peer_firmographics)
        peer_scores.append(
            {
                "name": peer.get("name", "Unknown"),
                "score": peer_maturity["score"],
                "confidence": peer_maturity["confidence"],
            }
        )

    scores_only = [p["score"] for p in peer_scores]
    sector_median = _median(scores_only) if scores_only else 0.0
    top_quartile = _percentile(scores_only, 75) if scores_only else 0.0

    # Identify gaps vs top quartile
    gaps: list[str] = []
    if company_score < top_quartile:
        gap_delta = top_quartile - company_score
        if gap_delta >= 2:
            gaps.append(
                f"Significant AI capability gap: top-quartile peers score "
                f"{top_quartile:.1f} vs your {company_score} — "
                "opportunity to accelerate AI adoption with dedicated ML talent."
            )
        if gap_delta >= 1:
            gaps.append(
                "Peers in the top quartile are actively hiring AI/ML engineers "
                "and building internal AI platforms — risk of competitive displacement."
            )
        if company_score <= 1:
            gaps.append(
                "No dedicated AI leadership role detected — top-quartile peers "
                "have named AI leads driving product differentiation."
            )

    if not gaps:
        gaps.append(
            "Company AI maturity is at or above sector top quartile — "
            "focus pitch on scaling existing AI capabilities."
        )

    # Confidence based on peer sample size
    if len(peer_scores) >= 5:
        brief_confidence = "high"
    elif len(peer_scores) >= 2:
        brief_confidence = "medium"
    else:
        brief_confidence = "low"

    return {
        "sector": firmographics.get("industry", "Unknown"),
        "peers_analyzed": len(peer_scores),
        "company_score": company_score,
        "sector_median": round(sector_median, 2),
        "top_quartile_score": round(top_quartile, 2),
        "peer_scores": peer_scores,
        "gaps": gaps,
        "confidence": brief_confidence,
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

async def run_enrichment_pipeline(company_name: str) -> dict[str, Any]:
    """
    Run the complete signal enrichment pipeline for a company.

    Steps:
      1. Firmographics (Crunchbase)
      2. Funding event signal
      3. Layoff signal
      4. Job post signals (Playwright + firmographic)
      5. Leadership change signal
      6. AI maturity score
      7. Competitor gap brief
      8. Merge into hiring_signal_brief
      9. Save to data/briefs/{company}_brief.json
      10. Log pipeline latency to Langfuse

    Returns the complete brief dict.
    """
    start_ts = time.monotonic()

    log_trace("enrichment_pipeline_start", {"company": company_name})

    # Step 1: Firmographics
    firmographics = get_crunchbase_firmographics(company_name)
    log_trace("enrichment_firmographics", {"company": company_name, "firmographics": firmographics})

    # Step 2: Funding event
    funding_event = get_funding_event(company_name, firmographics)
    log_trace("enrichment_funding", {"company": company_name, "funding_event": funding_event})

    # Step 3: Layoff signal
    layoff_signal = get_layoff_signal(company_name)
    log_trace("enrichment_layoff", {"company": company_name, "layoff_signal": layoff_signal})

    # Step 4: Job post signals
    job_signals = await get_job_post_signals(company_name, firmographics)
    log_trace("enrichment_job_signals", {"company": company_name, "job_signals": job_signals})

    # Step 5: Leadership change
    leadership_change = get_leadership_change(company_name, firmographics)
    log_trace("enrichment_leadership", {"company": company_name, "leadership_change": leadership_change})

    # Step 6: AI maturity
    ai_maturity = score_ai_maturity(job_signals, firmographics)
    log_trace("enrichment_ai_maturity", {"company": company_name, "ai_maturity": ai_maturity})

    # Step 7: Competitor gap brief
    competitor_gap = build_competitor_gap_brief(company_name, firmographics, ai_maturity)
    log_trace("enrichment_competitor_gap", {"company": company_name, "competitor_gap": competitor_gap})

    # Step 8: Assemble brief
    elapsed_ms = round((time.monotonic() - start_ts) * 1000, 1)

    brief: dict[str, Any] = {
        "company": company_name,
        "enriched_at": datetime.now(timezone.utc).isoformat(),
        "pipeline_latency_ms": elapsed_ms,
        "firmographics": firmographics,
        "funding_event": funding_event,
        "layoff_signal": layoff_signal,
        "job_signals": job_signals,
        "leadership_change": leadership_change,
        "ai_maturity": ai_maturity,
        "competitor_gap": competitor_gap,
        "hiring_signal_brief": _build_hiring_signal_brief(
            firmographics, funding_event, layoff_signal,
            job_signals, leadership_change, ai_maturity,
        ),
    }

    # Step 9: Persist brief
    safe_name = company_name.lower().replace(" ", "_").replace("/", "_")
    brief_path = _briefs_dir() / f"{safe_name}_brief.json"
    with open(brief_path, "w", encoding="utf-8") as fh:
        json.dump(brief, fh, indent=2, default=str)

    # Step 10: Log latency
    log_trace(
        "enrichment_pipeline_complete",
        {
            "company": company_name,
            "pipeline_latency_ms": elapsed_ms,
            "brief_path": str(brief_path),
            "ai_maturity_score": ai_maturity.get("score"),
            "funding_in_window": funding_event.get("in_window") if funding_event else False,
            "layoff_in_window": layoff_signal.get("in_window") if layoff_signal else False,
        },
    )

    return brief


def _build_hiring_signal_brief(
    firmographics: dict,
    funding_event: dict | None,
    layoff_signal: dict | None,
    job_signals: dict,
    leadership_change: dict | None,
    ai_maturity: dict,
) -> dict[str, Any]:
    """Merge all signals into a concise hiring signal brief."""
    signals: list[str] = []

    if funding_event and funding_event.get("in_window"):
        signals.append(
            f"Recent {funding_event['type'].replace('_', ' ').title()} "
            f"(${funding_event['total_funding_usd']:,}) — "
            f"{funding_event['days_ago']} days ago"
        )

    if layoff_signal and layoff_signal.get("in_window"):
        signals.append(
            f"Workforce reduction: {layoff_signal['headcount']} headcount "
            f"({layoff_signal['percentage']}%) — {layoff_signal['days_ago']} days ago"
        )

    if leadership_change and leadership_change.get("in_window"):
        signals.append(
            f"New {leadership_change['role']}: {leadership_change['name']} "
            f"({leadership_change['tenure_days']} days tenure)"
        )

    open_roles = job_signals.get("open_roles", 0)
    ai_roles = job_signals.get("ai_roles", [])
    if open_roles > 0:
        signals.append(
            f"{open_roles} open roles detected"
            + (f", including {len(ai_roles)} AI/ML roles" if ai_roles else "")
        )

    return {
        "summary_signals": signals,
        "ai_maturity_score": ai_maturity.get("score", 0),
        "ai_maturity_confidence": ai_maturity.get("confidence", "low"),
        "ai_maturity_justification": ai_maturity.get("justification", []),
        "employee_count": firmographics.get("employee_count", 0),
        "industry": firmographics.get("industry", "Unknown"),
        "country": firmographics.get("country", "Unknown"),
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _safe_int(value: str) -> int:
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return 0


def _safe_float(value: str) -> float:
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


def _median(values: list[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 0:
        return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return float(sorted_vals[mid])


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = (pct / 100) * (len(sorted_vals) - 1)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_vals) - 1)
    frac = idx - lower
    return sorted_vals[lower] + frac * (sorted_vals[upper] - sorted_vals[lower])
