# Hiring Velocity Implementation

## Overview

The hiring velocity feature provides time-windowed job post delta computation with 60-day historical snapshots. This enables the agent to make confident assertions about hiring trends rather than asking questions.

## Architecture

### Components

1. **Job History Storage** (`agent/core/job_history.py`)
   - Stores daily snapshots of job post counts per company
   - Retrieves historical snapshots with ±7 day tolerance
   - Automatic cleanup of snapshots older than 90 days

2. **Velocity Computation** (`agent/core/enrichment.py::compute_hiring_velocity_label`)
   - Computes categorical velocity labels from current vs historical counts
   - Returns confidence scores based on data availability

3. **Integration** (`agent/core/enrichment.py::get_job_post_signals`)
   - Stores current snapshot after each enrichment run
   - Retrieves 60-day-old snapshot for comparison
   - Computes velocity label and confidence

### Data Flow

```
Enrichment Pipeline
    ↓
get_job_post_signals()
    ↓
1. Scrape/fetch current job posts
2. Store current snapshot → data/job_snapshots/{domain}/{date}.json
3. Query 60-day-old snapshot
4. Compute velocity: current_count / historical_count
5. Map ratio to label (tripled_or_more, doubled, etc.)
6. Return with confidence score
```

## Velocity Labels

| Label | Ratio | Example | Confidence |
|-------|-------|---------|------------|
| `tripled_or_more` | ≥3.0x | 12 → 36 roles | 0.8 |
| `doubled` | 2.0-3.0x | 4 → 11 roles | 0.8 |
| `increased_modestly` | 1.2-2.0x | 5 → 7 roles | 0.8 |
| `flat` | 0.8-1.2x | 10 → 10 roles | 0.8 |
| `declined` | <0.8x | 10 → 5 roles | 0.8 |
| `insufficient_signal` | N/A | No historical data | 0.3 |

### Confidence Scoring

- **0.8**: Historical data available, both counts > 0
- **0.6**: Edge case (one count is 0, can't compute ratio)
- **0.3**: No historical data available

## Usage

### Storing Snapshots

```python
from agent.core.job_history import store_job_snapshot

store_job_snapshot(
    company_domain="dataflow.tech",
    open_roles_count=11,
    ai_roles_count=5,
    source="playwright_scrape",
)
```

### Retrieving Historical Data

```python
from agent.core.job_history import get_historical_snapshot

snapshot = get_historical_snapshot(
    company_domain="dataflow.tech",
    days_ago=60,
)

if snapshot:
    historical_count = snapshot["open_roles_count"]
```

### Computing Velocity

```python
from agent.core.enrichment import compute_hiring_velocity_label

velocity, confidence = compute_hiring_velocity_label(
    current_count=11,
    historical_count=4,
)

# velocity = "doubled" (11/4 = 2.75x)
# confidence = 0.8
```

### Integration with Enrichment

```python
from agent.core.enrichment import run_enrichment_pipeline

brief = await run_enrichment_pipeline("DataFlow Technologies")

job_signals = brief["job_signals"]
print(f"Velocity: {job_signals['velocity']}")
print(f"Confidence: {job_signals['velocity_confidence']}")
print(f"Current: {job_signals['open_roles']}")
print(f"60 days ago: {job_signals['open_roles_60_days_ago']}")
```

## Messaging Strategy

### High Confidence (0.8) - Assertive

When historical data is available and confidence is 0.8:

```
"I noticed you've more than doubled your engineering headcount 
over the past 60 days — that's impressive growth."
```

### Low Confidence (0.3) - Question-Based

When no historical data is available:

```
"I see you have 11 open engineering roles. Are you scaling 
your team significantly right now?"
```

## Storage Format

### Snapshot File Structure

```
data/job_snapshots/
  ├── dataflow_tech/
  │   ├── 2026-02-24.json  # 60 days ago
  │   ├── 2026-03-15.json
  │   └── 2026-04-25.json  # Today
  └── rapidgrowth_io/
      └── 2026-04-25.json
```

### Snapshot Schema

```json
{
  "company_domain": "dataflow.tech",
  "date": "2026-04-25",
  "timestamp": "2026-04-25T07:50:07.496383+00:00",
  "open_roles_count": 11,
  "ai_roles_count": 5,
  "source": "playwright_scrape"
}
```

## Edge Cases

### No Historical Data

First enrichment run for a company:

```python
velocity, confidence = compute_hiring_velocity_label(11, None)
# ("insufficient_signal", 0.3)
```

### Division by Zero

Historical count is 0:

```python
velocity, confidence = compute_hiring_velocity_label(10, 0)
# ("tripled_or_more", 0.6)  # Can't compute ratio, infer from magnitude
```

### Both Zero

No hiring activity:

```python
velocity, confidence = compute_hiring_velocity_label(0, 0)
# ("flat", 0.6)
```

### Current Zero

Hiring stopped:

```python
velocity, confidence = compute_hiring_velocity_label(0, 10)
# ("declined", 0.6)
```

## Maintenance

### Automatic Cleanup

Old snapshots are automatically cleaned up after each enrichment run:

```python
cleanup_old_snapshots(company_domain, keep_days=90)
```

This prevents unbounded storage growth while maintaining sufficient history for velocity calculation.

### Manual Cleanup

```python
from agent.core.job_history import cleanup_old_snapshots

deleted = cleanup_old_snapshots("dataflow.tech", keep_days=60)
print(f"Deleted {deleted} old snapshots")
```

## Testing

### Unit Tests

```bash
python test_hiring_velocity_implementation.py
```

Tests cover:
- Velocity label computation (all scenarios)
- Snapshot storage and retrieval
- Historical lookback with ±7 day tolerance
- Integration with enrichment pipeline
- Schema compliance

### Demo

```bash
python demo_hiring_velocity_standalone.py
```

Shows:
- First run (no historical data)
- Second run (with historical data)
- Impact on outreach messaging
- Complete data flow

## Schema Compliance

Output matches `schemas/enrichment_output.schema.json`:

```json
{
  "job_signals": {
    "open_roles": 11,
    "ai_roles": ["Senior ML Engineer", "..."],
    "velocity": "doubled",
    "source": "playwright_scrape",
    "confidence": 0.9,
    "open_roles_60_days_ago": 4,
    "velocity_confidence": 0.8,
    "timestamp": "2026-04-25T07:50:07.496383+00:00"
  }
}
```

## Performance

- Snapshot storage: O(1) write
- Historical retrieval: O(1) read with ±7 day tolerance
- Cleanup: O(n) where n = number of snapshots (runs async)

Storage overhead: ~200 bytes per snapshot per company per day

## Future Enhancements

1. **Trend Analysis**: Compute 30-day, 60-day, 90-day trends
2. **Role-Specific Velocity**: Track AI/ML roles separately
3. **Seasonality Detection**: Identify hiring patterns
4. **Predictive Modeling**: Forecast future hiring based on trends
5. **Multi-Source Aggregation**: Combine Playwright, LinkedIn, Greenhouse data

## References

- Test specification: `eval/test_hiring_velocity.md`
- Schema: `schemas/enrichment_output.schema.json`
- Implementation: `agent/core/enrichment.py`, `agent/core/job_history.py`
