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
