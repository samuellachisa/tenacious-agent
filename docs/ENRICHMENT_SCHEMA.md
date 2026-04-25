# Enrichment Pipeline Output Schema

## Overview

The enrichment pipeline (`run_enrichment_pipeline()`) produces a standardized JSON artifact with confidence scoring across all signals. This document describes the output schema for downstream consumers (qualifier, outreach composer, CRM sync).

All signals now carry explicit metadata:
- `source`: Data source identifier (e.g., "crunchbase", "playwright_scrape", "layoffs.fyi")
- `timestamp`: ISO 8601 timestamp when the signal was collected
- `confidence`: Numeric confidence score from 0.0 to 1.0

## Confidence Scoring Standard

All signals use a **numeric confidence score from 0.0 to 1.0**:

| Range | Interpretation | Usage Guidance |
|-------|---------------|----------------|
| 0.9-1.0 | High confidence | Assert facts directly in outreach |
| 0.7-0.8 | Medium-high confidence | Use with light hedging ("appears to", "signals suggest") |
| 0.5-0.6 | Medium confidence | Ask rather than assert ("Are you...?") |
| 0.3-0.4 | Low confidence | Avoid specific claims, use generic language |
| 0.0-0.2 | Very low/no signal | Do not reference in outreach |

## Output Structure

```json
{
  "company": "string",
  "enriched_at": "ISO 8601 datetime",
  "pipeline_latency_ms": "number",
  "firmographics": { /* Crunchbase data */ },
  "funding_event": { /* or null */ },
  "layoff_signal": { /* or null */ },
  "job_signals": { /* required */ },
  "leadership_change": { /* or null */ },
  "ai_maturity": { /* required */ },
  "competitor_gap": { /* required */ },
  "hiring_signal_brief": { /* required */ }
}
```

## Signal-Specific Confidence

### 1. Funding Event

**Confidence Factors:**
- 1.0: Structured Crunchbase data with full date (YYYY-MM-DD)
- 0.7: Month-only precision (YYYY-MM)
- 0.5: Funding type present but date missing/invalid

**Metadata:**
- `source`: Always "crunchbase"
- `timestamp`: ISO 8601 timestamp when signal was collected
- `confidence`: 0.0-1.0 based on data quality

**Fields:**
```json
{
  "type": "series_a | series_b | series_c | seed",
  "date": "YYYY-MM-DD",
  "days_ago": "integer",
  "total_funding_usd": "integer",
  "in_window": "boolean (≤180 days)",
  "confidence": "0.0-1.0",
  "source": "crunchbase",
  "timestamp": "ISO 8601"
}
```

### 2. Layoff Signal

**Confidence Factors:**
- 0.9: Source URL present (verifiable)
- 0.7: From layoffs.fyi without URL (community-sourced)
- 0.5: Date parsing ambiguous or month-only precision

**Metadata:**
- `source`: URL if available, otherwise "layoffs.fyi"
- `timestamp`: ISO 8601 timestamp when signal was collected
- `confidence`: 0.0-1.0 based on source verifiability

**Fields:**
```json
{
  "date": "string",
  "days_ago": "integer",
  "headcount": "integer",
  "percentage": "number",
  "in_window": "boolean (≤120 days)",
  "source": "URL string or 'layoffs.fyi'",
  "confidence": "0.0-1.0",
  "timestamp": "ISO 8601"
}
```

### 3. Job Signals

**Confidence Factors:**
- 0.9: Playwright scrape (live data from careers page, respects robots.txt)
- 0.6: Crunchbase sample (static snapshot)

**Velocity Confidence:**
- 0.8: Historical 60-day snapshot available (true velocity)
- 0.3: Inferred from current count only (no historical data)

**Metadata:**
- `source`: "playwright_scrape" or "crunchbase_sample"
- `timestamp`: ISO 8601 timestamp when signal was collected
- `confidence`: 0.0-1.0 based on data freshness

**Scraping Policy:**
- Respects robots.txt directives
- Only accesses publicly available pages
- Uses identifiable user agent
- 8-second timeout per page

**Fields:**
```json
{
  "open_roles": "integer",
  "ai_roles": ["array of role titles"],
  "velocity": "high | medium | low | none",
  "source": "playwright_scrape | crunchbase_sample",
  "confidence": "0.0-1.0",
  "open_roles_60_days_ago": "integer | null",
  "velocity_confidence": "0.0-1.0",
  "timestamp": "ISO 8601"
}
```

### 4. Leadership Change

**Confidence Factors:**
- 0.9: Crunchbase People data (structured)
- 0.7: LinkedIn "started new position" inference
- 0.5: Press release only (no structured data)

**Metadata:**
- `source`: "crunchbase", "linkedin", or "press_release"
- `timestamp`: ISO 8601 timestamp when signal was collected
- `confidence`: 0.0-1.0 based on data source

**Fields:**
```json
{
  "role": "CTO | VP Engineering",
  "name": "string",
  "tenure_days": "integer",
  "in_window": "boolean (≤90 days)",
  "confidence": "0.0-1.0",
  "source": "crunchbase | linkedin | press_release",
  "timestamp": "ISO 8601"
}
```

### 5. AI Maturity

**Confidence Calculation:**
- 0.85: 2+ high-weight signals detected
- 0.70: 1 high-weight + 2 medium-weight signals
- 0.60: 1 high-weight OR 2+ medium-weight signals
- <0.60: Average of detected signal confidences

**Signal Weights:**
- **HIGH (0.9):** AI-adjacent roles (3+), Named AI leadership
- **MEDIUM (0.6):** Industry classification, Executive commentary
- **LOW (0.4):** ML stack keywords, Strategic AI communications

**Metadata:**
- `source`: "ai_maturity_config" (configuration-driven scoring)
- `timestamp`: ISO 8601 timestamp when signal was scored
- `confidence`: 0.0-1.0 aggregate confidence

**Fields:**
```json
{
  "score": "0-3 integer",
  "confidence": "0.0-1.0",
  "justification": ["array of strings with weight labels"],
  "signal_breakdown": [
    {
      "signal_name": "string",
      "weight": "high | medium | low",
      "detected": "boolean",
      "confidence": "0.0-1.0",
      "evidence": "string"
    }
  ],
  "source": "ai_maturity_config",
  "timestamp": "ISO 8601"
}
```

## Hiring Signal Brief (Summary)

The `hiring_signal_brief` provides a concise summary with **overall confidence** calculated as a weighted average:

| Signal | Weight |
|--------|--------|
| Funding | 20% |
| Layoff | 15% |
| Job Signals | 25% |
| Leadership | 15% |
| AI Maturity | 25% |

**Formula:**
```
overall_confidence = 
  funding_conf × 0.20 +
  layoff_conf × 0.15 +
  job_conf × 0.25 +
  leadership_conf × 0.15 +
  ai_conf × 0.25
```

**Structured Signals:**

Each signal in the brief now carries explicit metadata:

```json
{
  "type": "funding | layoff | leadership | job_signals",
  "summary": "Human-readable description",
  "source": "Data source identifier",
  "timestamp": "ISO 8601 timestamp",
  "confidence": "0.0-1.0"
}
```

**Fields:**
```json
{
  "signals": [
    {
      "type": "funding",
      "summary": "Recent Series B ($15M) — 45 days ago",
      "source": "crunchbase",
      "timestamp": "2026-04-25T10:30:00Z",
      "confidence": 1.0
    }
  ],
  "summary_signals": ["array of human-readable strings (backward compatibility)"],
  "ai_maturity_score": "0-3",
  "ai_maturity_confidence": "0.0-1.0",
  "ai_maturity_source": "ai_maturity_config",
  "ai_maturity_timestamp": "ISO 8601",
  "employee_count": "integer",
  "industry": "string",
  "country": "string",
  "overall_confidence": "0.0-1.0",
  "confidence_breakdown": {
    "funding": "0.0-1.0",
    "layoff": "0.0-1.0",
    "job_signals": "0.0-1.0",
    "leadership": "0.0-1.0",
    "ai_maturity": "0.0-1.0"
  }
}
```

## Usage Examples

### Example 1: High Confidence Outreach

```json
{
  "overall_confidence": 0.82,
  "confidence_breakdown": {
    "funding": 1.0,
    "job_signals": 0.9,
    "ai_maturity": 0.85
  }
}
```

**Outreach Language:** Assert facts directly
- "Following your $15M Series B..."
- "With 12 open engineering roles..."
- "Your AI team is clearly a strategic priority..."

### Example 2: Medium Confidence Outreach

```json
{
  "overall_confidence": 0.58,
  "confidence_breakdown": {
    "funding": 0.7,
    "job_signals": 0.6,
    "ai_maturity": 0.6
  }
}
```

**Outreach Language:** Use hedging
- "It appears you recently raised funding..."
- "Your careers page signals active hiring..."
- "Are you building out an AI function?"

### Example 3: Low Confidence - Abstain

```json
{
  "overall_confidence": 0.35,
  "confidence_breakdown": {
    "funding": 0.0,
    "job_signals": 0.6,
    "ai_maturity": 0.4
  }
}
```

**Outreach Language:** Generic exploratory email
- "We work with technology companies to scale engineering teams..."
- No specific signal references

## Downstream Consumer Guidelines

### Qualifier (`agent/core/qualifier.py`)

- Use `overall_confidence` to set `segment_confidence` field
- Confidence < 0.6 → trigger abstention path (generic email)
- Check individual signal confidences for mixed-signal edge cases

### Outreach Composer (`agent/main.py`)

- Read `confidence_breakdown` to adjust language per signal
- High confidence (≥0.8) → assert
- Medium confidence (0.5-0.7) → hedge or ask
- Low confidence (<0.5) → omit from outreach

### CRM Sync (`agent/integrations/hubspot_client.py`)

- Store `overall_confidence` in custom HubSpot field
- Flag contacts with confidence < 0.6 for manual review
- Use `confidence_breakdown` for lead scoring

## Validation

To validate enrichment output against this schema:

```python
from agent.core.enrichment import run_enrichment_pipeline

brief = await run_enrichment_pipeline("Company Name")

# Check required fields
assert "overall_confidence" in brief["hiring_signal_brief"]
assert "confidence_breakdown" in brief["hiring_signal_brief"]
assert "signal_breakdown" in brief["ai_maturity"]

# Check confidence ranges
assert 0.0 <= brief["hiring_signal_brief"]["overall_confidence"] <= 1.0
assert all(
    0.0 <= v <= 1.0 
    for v in brief["hiring_signal_brief"]["confidence_breakdown"].values()
)
```

## Future Enhancements

1. **Historical Job Velocity:** Implement 60-day snapshot storage to enable true velocity calculation (currently placeholder)

2. **Confidence Calibration:** Track actual conversion rates by confidence band to calibrate thresholds

3. **Signal Correlation:** Analyze which signal combinations predict highest conversion

4. **Confidence Decay:** Implement time-based confidence decay for stale signals (e.g., 6-month-old funding event)

## References

- Full schema: `schemas/hiring_signal_brief.schema.json`
- Implementation: `agent/core/enrichment.py`
- Probe library: `probes/probe_library.md` (see P-001, P-006, P-011, P-016, P-021, P-026 for signal over-claiming failures)
