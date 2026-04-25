# Signal Metadata Implementation Summary

## Overview

This document summarizes the implementation of explicit robots.txt/public-page checks in the scraper and the addition of source, timestamp, and confidence metadata to all signals in the enrichment pipeline.

## Changes Implemented

### 1. Robots.txt Compliance in Web Scraper

**File:** `agent/core/enrichment.py`

**New Function:** `_check_robots_txt(website: str, path: str) -> bool`
- Fetches and parses robots.txt for each domain
- Checks if the target path is allowed for our user agent
- Returns True if allowed, False if disallowed
- Fails open (allows scraping) if robots.txt is unavailable

**Updated Function:** `_scrape_careers_page(website: str, company_name: str) -> list[str]`
- Checks robots.txt before accessing any page
- Only scrapes paths that are explicitly allowed
- Sets identifiable user agent: `TenaciousBot/1.0`
- Verifies pages are publicly accessible (checks HTTP status codes)
- Gracefully falls back to Crunchbase data if scraping is disallowed

**Dependencies Added:**
- `aiohttp==3.11.11` (for async HTTP requests to fetch robots.txt)

### 2. Signal Metadata Enhancement

All signal functions now return explicit metadata fields:

#### Funding Event (`get_funding_event`)
```python
{
    # ... existing fields ...
    "source": "crunchbase",
    "timestamp": "2026-04-25T10:30:00Z",
    "confidence": 1.0
}
```

#### Layoff Signal (`get_layoff_signal`)
```python
{
    # ... existing fields ...
    "source": "https://layoffs.fyi/..." or "layoffs.fyi",
    "timestamp": "2026-04-25T10:30:00Z",
    "confidence": 0.9
}
```

#### Job Signals (`get_job_post_signals`)
```python
{
    # ... existing fields ...
    "source": "playwright_scrape" or "crunchbase_sample",
    "timestamp": "2026-04-25T10:30:00Z",
    "confidence": 0.9
}
```

#### Leadership Change (`get_leadership_change`)
```python
{
    # ... existing fields ...
    "source": "crunchbase",
    "timestamp": "2026-04-25T10:30:00Z",
    "confidence": 0.9
}
```

#### AI Maturity (`score_ai_maturity`)
```python
{
    # ... existing fields ...
    "source": "ai_maturity_config",
    "timestamp": "2026-04-25T10:30:00Z",
    "confidence": 0.85
}
```

### 3. Hiring Signal Brief Enhancement

**File:** `agent/core/enrichment.py`

**Updated Function:** `_build_hiring_signal_brief(...) -> dict[str, Any]`

The hiring signal brief now includes a structured `signals` array where each signal carries:
- `type`: Signal type identifier (funding, layoff, leadership, job_signals)
- `summary`: Human-readable description
- `source`: Data source identifier
- `timestamp`: ISO 8601 timestamp when collected
- `confidence`: Confidence score (0.0-1.0)

Additionally includes AI maturity metadata:
- `ai_maturity_source`: "ai_maturity_config"
- `ai_maturity_timestamp`: ISO 8601 timestamp

**Backward Compatibility:**
- Maintains `summary_signals` array (list of strings) for existing consumers
- New consumers should use the structured `signals` array

Example output:
```json
{
  "signals": [
    {
      "type": "funding",
      "summary": "Recent Series B ($15,000,000) — 45 days ago",
      "source": "crunchbase",
      "timestamp": "2026-04-25T10:30:00Z",
      "confidence": 1.0
    },
    {
      "type": "job_signals",
      "summary": "12 open roles detected, including 3 AI/ML roles",
      "source": "playwright_scrape",
      "timestamp": "2026-04-25T10:30:15Z",
      "confidence": 0.9
    }
  ],
  "summary_signals": [
    "Recent Series B ($15,000,000) — 45 days ago",
    "12 open roles detected, including 3 AI/ML roles"
  ],
  "ai_maturity_source": "ai_maturity_config",
  "ai_maturity_timestamp": "2026-04-25T10:30:20Z",
  "overall_confidence": 0.82,
  "confidence_breakdown": {
    "funding": 1.0,
    "layoff": 0.0,
    "job_signals": 0.9,
    "leadership": 0.0,
    "ai_maturity": 0.85
  }
}
```

### 4. Schema Updates

**File:** `schemas/enrichment_output.schema.json`

Updated JSON schema to include:
- `source` field for all signal types
- `timestamp` field for all signal types
- `signals` array in hiring_signal_brief with structured metadata
- `ai_maturity_source` and `ai_maturity_timestamp` fields

### 5. Documentation Updates

**New File:** `docs/SCRAPING_POLICY.md`
- Comprehensive documentation of ethical scraping practices
- Technical implementation details
- Opt-out mechanisms for website administrators
- Future enhancement roadmap

**Updated File:** `docs/ENRICHMENT_SCHEMA.md`
- Added metadata field descriptions to all signal sections
- Updated hiring signal brief documentation
- Added scraping policy notes to job signals section

### 6. Testing

**New File:** `test_signal_metadata.py`
- Validates that all signals carry source, timestamp, and confidence
- Tests each signal function independently
- Verifies hiring signal brief structure
- Provides clear output for debugging

## Benefits

1. **Transparency:** Every signal now explicitly states its data source and collection time
2. **Auditability:** Timestamps enable tracking signal freshness and debugging stale data
3. **Ethical Compliance:** Robots.txt checks ensure respectful web scraping
4. **Confidence Tracking:** Explicit confidence scores enable better downstream decision-making
5. **Backward Compatibility:** Existing consumers continue to work with `summary_signals`

## Usage Example

```python
from agent.core.enrichment import run_enrichment_pipeline

# Run enrichment
brief = await run_enrichment_pipeline("Company Name")

# Access structured signals with metadata
for signal in brief["hiring_signal_brief"]["signals"]:
    print(f"Signal: {signal['type']}")
    print(f"  Source: {signal['source']}")
    print(f"  Timestamp: {signal['timestamp']}")
    print(f"  Confidence: {signal['confidence']}")
    print(f"  Summary: {signal['summary']}")
```

## Migration Guide

For downstream consumers:

1. **No Breaking Changes:** Existing code using `summary_signals` continues to work
2. **Recommended Migration:** Switch to using the structured `signals` array for richer metadata
3. **New Fields:** Access `ai_maturity_source` and `ai_maturity_timestamp` for AI maturity metadata

## Testing

Run the test script to verify implementation:

```bash
cd agent
python ../test_signal_metadata.py
```

Expected output:
```
=== Testing DataFlow Technologies ===

✓ Funding Event:
  - Source: crunchbase
  - Timestamp: 2026-04-25T10:30:00Z
  - Confidence: 1.0

✓ Job Signals:
  - Source: playwright_scrape
  - Timestamp: 2026-04-25T10:30:15Z
  - Confidence: 0.9

...

✓ All signals carry source, timestamp, and confidence metadata!
```

## References

- Implementation: `agent/core/enrichment.py`
- Schema: `schemas/enrichment_output.schema.json`
- Documentation: `docs/ENRICHMENT_SCHEMA.md`
- Scraping Policy: `docs/SCRAPING_POLICY.md`
- Test: `test_signal_metadata.py`
