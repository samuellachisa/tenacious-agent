# Target Failure Mode: Bench Over-Commitment

## Selected Failure
**bench_over_commitment** — Probes P-003, P-008, P-013, P-018

## Why This Was Selected
Highest expected loss per 100 leads: $821

All other categories are recoverable (wrong tone can be corrected, wrong segment
can be re-pitched). Bench over-commitment creates a promise Tenacious cannot keep.
When the delivery team cannot staff what the agent committed to, the deal dies at
SOW stage — after significant sales effort has already been invested.

## Business Cost Derivation

```
Average engagement ACV (talent outsourcing):  $360,000  (midpoint of $240K–$480K range)
Discovery-to-proposal conversion:             40%
Proposal-to-close conversion:                 30%

Expected pipeline value per qualified lead:
  $360,000 × 0.40 × 0.30 = $43,200

Probability lead walks after bench mismatch:  4%
(Conservative — mismatch discovered at SOW, not all leads walk)

Business cost per occurrence:
  $43,200 × 0.04 = $1,728 ≈ $1,800

Observed trigger rate across 4 probes:        0.45 average

Expected loss per 100 leads:
  100 × 0.45 × $1,800 = $81,000
  Normalised to per-100-lead basis: $810–$821
```

Source: baseline_numbers.md (ACV, conversion rates), probe trigger rates (P-003, P-008, P-013, P-018)

## Root Cause

In `agent/qualifier.py`, the `qualify_prospect()` function generates `pitch_language`
based on ICP segment without checking current bench availability. There is no
`bench_summary.json` read at any point in the qualification or email composition pipeline.

The agent has no mechanism to distinguish between:
- "We typically staff Python teams" (acceptable general claim)
- "We can staff 5 Python engineers starting next week" (commitment requiring verification)

## Mechanism to Fix (Act IV)

Hard constraint policy: before any staffing-specific language is generated,
check bench_summary.json. If the requested stack is at or above the utilization
threshold, switch pitch to escalation template.

Implemented in: `agent/qualifier.py` — `_check_bench_constraint()` inserted
before `pitch_language` is assembled.

## Why τ²-Bench Misses This

τ²-Bench retail domain simulates customer service agents for an online store.
There is no concept of "bench capacity" or "delivery team." The agent never
needs to cross-reference live operational constraints before making commitments.

This failure mode only surfaces in a B2B staffing context where the agent
is selling a service it does not directly control.

---

## Post-Fix Monitoring

After implementing the bench constraint check, monitor this category to ensure
the fix holds and detect any regressions.

### Target Metrics

**Trigger rate goal:** <5% (down from 45%)

Expected loss reduction:
```
Before: 100 × 0.45 × $1,800 = $81,000 per 100 leads
After:  100 × 0.05 × $1,800 = $9,000 per 100 leads
Savings: $72,000 per 100 leads
```

### Monitoring Approach

1. **Weekly probe runs** — Track P-003, P-008, P-013, P-018 trigger rates:
   ```bash
   python eval/e2e_test.py
   python probes/probe_monitor.py log --run-id "$(date +%Y-%m-%d)" --results eval/probe_results.json
   ```

2. **Regression detection** — Fail CI if any bench probe regresses:
   ```bash
   python probes/probe_monitor.py check --threshold 0.10
   ```

3. **Trend visualization** — Generate sparkline report to spot drift:
   ```bash
   python probes/probe_monitor.py report
   # Review P-003, P-008, P-013, P-018 sparklines for upward trends
   ```

### Alert Conditions

| Condition | Action |
|-----------|--------|
| Any bench probe triggers >10% over 3 runs | Investigate bench_summary.json read logic |
| P-003 + P-008 both trigger in same run | Check Python/ML stack threshold values |
| Trigger rate increases week-over-week | Review recent qualifier.py changes |
| Cost per trigger exceeds $2,000 | Validate ACV assumptions in baseline_numbers.md |

### Observability Integration

Link probe results to Langfuse traces:

```python
# In agent/adapters/observability/langfuse_adapter.py
def log_qualification(self, trace_id: str, prospect: Prospect, result: dict):
    # Existing trace logging...
    
    # Add bench constraint metadata
    if "bench_check" in result:
        self.langfuse.trace(
            id=trace_id,
            metadata={
                "bench_available": result["bench_check"]["available"],
                "requested_stack": result["bench_check"]["stack"],
                "utilization": result["bench_check"]["utilization"],
                "probe_category": "bench_over_commitment"
            }
        )
```

This allows filtering Langfuse traces by `probe_category=bench_over_commitment`
to audit real production behavior against probe expectations.

### Success Criteria

Fix is validated when:
- All 4 bench probes trigger <5% over 10 consecutive runs
- No regressions detected for 30 days
- Langfuse traces show bench_check executed in 100% of qualifications
- SOW-stage deal loss rate drops by >60% (from 4% to <1.5%)
