

# Failure Taxonomy with Economic Analysis

This document provides a comprehensive failure taxonomy for the Tenacious Agent with numeric aggregation and economic impact analysis grounded in Tenacious baseline numbers.

## Overview

The taxonomy categorizes 30 adversarial probes into 10 failure categories, each with:
- Trigger rate (probability of occurrence)
- Business cost per occurrence
- Expected loss per 100 leads
- Root cause analysis
- Fix status and location
- Economic impact modeling

## Methodology

### Data Sources

1. **Probe Library** (`probes/probe_library.md`): 30 adversarial probes with observed trigger rates and business costs
2. **Baseline Numbers** (`seed/baseline_numbers.md`): Tenacious conversion funnel, ACV ranges, operational metrics
3. **Bench Summary** (`seed/bench_summary.json`): Current bench capacity by stack
4. **Trace Logs** (`eval/trace_log.jsonl`): Observed agent behavior in production-like scenarios

### Calculation Framework

```
Expected Loss per 100 Leads = 
    100 × Average Trigger Rate × Average Business Cost per Occurrence

Business Cost per Occurrence =
    Expected Pipeline Value per Lead × Probability Lead Walks
    
Expected Pipeline Value per Lead =
    Average ACV × Discovery-to-Proposal Conversion × Proposal-to-Close Conversion
```

### Economic Assumptions (from baseline_numbers.md)

- **Average Engagement ACV (talent outsourcing):** $360,000 (midpoint of $240K–$480K)
- **Discovery-to-Proposal Conversion:** 40%
- **Proposal-to-Close Conversion:** 30%
- **Expected Pipeline Value per Qualified Lead:** $43,200
- **SDR Outbound Volume:** 60 touches/week, 7% reply rate = 4.2 qualified leads/week
- **Annual Qualified Leads (1 SDR):** 218 leads/year
- **Current Scale:** 3 SDRs (assumption for scaling calculations)

## Failure Categories (Ranked by Expected Loss)

### 1. Bench Over-Commitment ($821 per 100 leads)

**Description:** Agent promises engineering capacity without checking bench_summary.json availability.

**Probes:** P-003 (Python), P-008 (ML), P-013 (Infra), P-018 (Go)

**Metrics:**
- Probe Count: 4
- Average Trigger Rate: 0.45 (45%)
- Average Business Cost: $1,825
- Expected Loss per 100 Leads: $821

**Trigger Rates by Stack:**
- Python (7 available, 71% util): 0.40
- ML (5 available, 80% util): 0.45
- Infra (4 available, 75% util): 0.50
- Go (3 available, 67% util): 0.45

**Business Impact:**
- Deal Stage Failure: SOW (late-stage)
- Probability Lead Walks: 4%
- Cost per Occurrence: $1,728
- Deals Lost per Year (3 SDRs): 11.8
- Annual Revenue Impact: $509,760 in expected closed revenue

**Root Cause:**
- `agent/core/qualifier.py:build_pitch_language()` generates pitch without checking bench_summary.json
- No `check_bench_capacity()` validation before commitment
- No escalation path to delivery team

**Fix Status:** ✅ Implemented
- Location: `agent/core/qualifier.py:check_bench_capacity()`
- Mechanism: Hard constraint check before staffing language is generated
- Fallback: Escalation template when capacity insufficient

**Why This is #1:**
- Unrecoverable (deal dies at SOW after sales effort invested)
- Late-stage failure (discovery call + proposal already completed)
- Reputation damage ("they promised engineers they don't have")
- Creates sales/delivery team friction

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.45 trigger rate × $1,800 cost = $529,740
```

---

### 2. Cost Pathology ($500 per 100 leads)

**Description:** Playwright retry loops with no ceiling create runaway LLM + scraping costs.

**Probes:** P-030

**Metrics:**
- Probe Count: 1
- Average Trigger Rate: 0.10 (10%)
- Average Business Cost: $5,000 (at scale)
- Expected Loss per 100 Leads: $500

**Cost Breakdown:**
- Target Cost per Interaction: $0.05
- Observed Cost per Interaction: $0.72 (14.4× over budget)
- Weekly Lead Volume: 200 (3 SDRs)
- Weekly Cost Target: $10
- Weekly Cost Observed: $144
- Annual Cost Overrun: $6,968

**Root Cause:**
- `agent/core/enrichment.py:_scrape_careers_page()` has no max_retries limit
- No cost ceiling per interaction
- Complex multi-signal enrichment triggers repeated Playwright scrapes
- Dynamic JS content requires multiple retries

**Fix Status:** ❌ Not Implemented
- Recommended: max_retries=2, fallback to cached data
- Hard budget cap: $0.10 per interaction
- Circuit breaker: disable scraping if weekly cost exceeds $50

**Why This is #2:**
- Unrecoverable (cost already incurred)
- Scales linearly with lead volume
- Compounds over time (weekly cost overrun)
- Impacts unit economics at scale

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.10 trigger rate × $5,000 cost = $322,500
```

---

### 3. Signal Over-Claiming ($383 per 100 leads)

**Description:** Agent asserts facts it cannot verify from public data with high confidence.

**Probes:** P-001, P-006, P-011, P-016, P-021, P-026

**Metrics:**
- Probe Count: 6
- Average Trigger Rate: 0.55 (55%)
- Average Business Cost: $697
- Expected Loss per 100 Leads: $383

**Trigger Rates by Type:**
- P-001 (aggressive hiring claim): 0.70
- P-006 (AI maturity over-claim): 0.35
- P-011 (velocity without baseline): 0.60
- P-016 (competitor gap with 1 peer): 0.55
- P-021 (stale news as current): 0.65
- P-026 (low-confidence competitive claim): 0.45

**Business Impact:**
- Credibility Loss Rate: 55%
- Average Cost per Credibility Loss: $697
- Recovery Rate: 15%
- Permanent Loss Rate: 85%

**Root Cause:**
- `agent/core/enrichment.py:score_ai_maturity()` keyword matching too broad
- `agent/core/qualifier.py:build_pitch_language()` does not check confidence before asserting
- No confidence gates on output language
- No staleness check on news/funding dates

**Fix Status:** 🟡 Partial
- Confidence scoring implemented in enrichment
- Pitch language does not consistently respect confidence levels
- Need: confidence-aware phrasing (assert when high, ask when medium/low)

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.55 trigger rate × $697 cost = $247,095
```

---

### 4. Gap Over-Claiming ($250 per 100 leads)

**Description:** Competitor gap framing sounds accusatory rather than advisory.

**Probes:** P-027, P-028

**Metrics:**
- Probe Count: 2
- Average Trigger Rate: 0.25 (25%)
- Average Business Cost: $1,000
- Expected Loss per 100 Leads: $250

**Business Impact:**
- Offense Rate: 25%
- Immediate Disengagement Rate: 80%
- Average Cost per Offense: $1,000

**Root Cause:**
- `agent/core/enrichment.py:build_competitor_gap_brief()` gap language written as statements not questions
- No strategy inquiry before gap assertion
- Framing: "Your competitors are pulling ahead" vs "There may be an opportunity to close a gap"

**Fix Status:** ❌ Not Implemented
- Recommended: Reframe all gaps as questions not assertions
- Add strategy inquiry: "Is this a deliberate choice or an opportunity?"
- Soften language: "potential opportunity" not "you're falling behind"

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.25 trigger rate × $1,000 cost = $161,250
```

---

### 5. Multi-Thread Leakage ($234 per 100 leads)

**Description:** Context from one contact at a company leaks to another contact at same company.

**Probes:** P-005, P-010, P-015

**Metrics:**
- Probe Count: 3
- Average Trigger Rate: 0.22 (22%)
- Average Business Cost: $1,067
- Expected Loss per 100 Leads: $234

**Business Impact:**
- Trust Breach Rate: 22%
- Deal Politics Created Rate: 60%
- Average Cost per Breach: $1,067

**Root Cause:**
- `agent/adapters/gateways/hubspot_crm_adapter.py` uses company domain for lookup, not individual email key
- Company-level properties shared across contacts
- No thread isolation mechanism

**Fix Status:** ❌ Not Implemented
- Recommended: Use contact-level properties, not company-level
- Add thread isolation: separate context per email address
- Validate: no cross-reference to other contacts in same company

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.22 trigger rate × $1,067 cost = $150,930
```

---

### 6. Dual Control Coordination ($200 per 100 leads)

**Description:** Agent takes action (booking call) without confirming prospect wants it.

**Probes:** P-029

**Metrics:**
- Probe Count: 1
- Average Trigger Rate: 0.40 (40%)
- Average Business Cost: $500
- Expected Loss per 100 Leads: $200

**Business Impact:**
- Premature Booking Rate: 40%
- Pushy Perception Rate: 75%
- Average Cost per Occurrence: $500

**Root Cause:**
- `agent/main.py:_run_prospect_pipeline()` books slot immediately after qualification
- No consent check before booking
- Assumes prospect wants call without asking

**Fix Status:** ❌ Not Implemented
- Recommended: Ask before booking: "Would a 30-minute call be useful?"
- Only attach Cal.com link after affirmative response
- Separate qualification from booking action

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.40 trigger rate × $500 cost = $129,000
```

---

### 7. ICP Misclassification ($175 per 100 leads)

**Description:** Prospect classified into wrong ICP segment or inconsistently across runs.

**Probes:** P-002, P-007, P-012, P-017

**Metrics:**
- Probe Count: 4
- Average Trigger Rate: 0.39 (39%)
- Average Business Cost: $450
- Expected Loss per 100 Leads: $175

**Business Impact:**
- Wrong Pitch Rate: 39%
- Prospect Dismissal Rate: 65%
- Average Cost per Misclassification: $450

**Root Cause:**
- `agent/core/qualifier.py:qualify_prospect()` segment priority logic
- Boundary conditions (e.g., 200 employees, 91-day tenure)
- Disqualifier keyword list incomplete
- Mixed signal handling (funding + layoff)

**Fix Status:** 🟡 Partial
- Mixed signal detection implemented
- Boundary conditions still have off-by-one errors
- Disqualifier keywords need expansion

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.39 trigger rate × $450 cost = $112,875
```

---

### 8. Tone Drift ($167 per 100 leads)

**Description:** Agent language becomes condescending, overly casual, or uses wrong voice.

**Probes:** P-004, P-009, P-014

**Metrics:**
- Probe Count: 3
- Average Trigger Rate: 0.25 (25%)
- Average Business Cost: $667
- Expected Loss per 100 Leads: $167

**Business Impact:**
- Tone Violation Rate: 25%
- Conversation End Rate: 50%
- Average Cost per Violation: $667

**Root Cause:**
- `agent/main.py:_build_email_text()` system prompt does not re-enforce style guide at each turn
- No formality floor
- Agent mirrors prospect informality

**Fix Status:** ❌ Not Implemented
- Recommended: Re-enforce style guide in every turn
- Add formality floor: never drop below professional tone
- Validate: no condescending language ("As I mentioned...")

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.25 trigger rate × $667 cost = $107,685
```

---

### 9. Signal Reliability ($114 per 100 leads)

**Description:** False positives/negatives in signal detection due to keyword matching or data quality.

**Probes:** P-023, P-024, P-025

**Metrics:**
- Probe Count: 3
- Average Trigger Rate: 0.18 (18%)
- Average Business Cost: $633
- Expected Loss per 100 Leads: $114

**Business Impact:**
- False Positive Rate: 40% (P-023)
- False Negative Rate: 8% (P-024)
- Average Cost per Error: $633

**Root Cause:**
- `agent/core/enrichment.py:score_ai_maturity()` keyword matching too broad
- Timezone-naive date comparison in `get_funding_event()`
- No stealth-mode detection (quiet but sophisticated companies)

**Fix Status:** 🟡 Partial
- AI maturity scoring improved with signal breakdown
- Timezone handling still naive
- No stealth-mode detection mechanism

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.18 trigger rate × $633 cost = $73,530
```

---

### 10. Scheduling Edge Cases ($77 per 100 leads)

**Description:** Timezone handling errors, DST boundary issues, or business hours violations.

**Probes:** P-019, P-020, P-022

**Metrics:**
- Probe Count: 3
- Average Trigger Rate: 0.22 (22%)
- Average Business Cost: $350
- Expected Loss per 100 Leads: $77

**Business Impact:**
- Scheduling Error Rate: 22%
- Reschedule Friction Rate: 80%
- Average Cost per Error: $350

**Root Cause:**
- `agent/integrations/calcom_client.py` timezone handling converts but does not validate business hours
- No DST explicit test
- No validation that suggested time is in the future

**Fix Status:** ❌ Not Implemented
- Recommended: Validate business hours (9 AM - 6 PM local time)
- Add DST handling test
- Ensure all suggested times are in the future

**Annual Cost at Scale (3 SDRs):**
```
218 leads/year/SDR × 3 SDRs × 0.22 trigger rate × $350 cost = $49,665
```

---

## Summary Statistics

### Total Risk Exposure

| Metric | Value |
|--------|-------|
| Total Probes | 30 |
| Total Categories | 10 |
| Total Expected Loss per 100 Leads | $2,921 |
| Weighted Average Trigger Rate | 33% |
| Weighted Average Business Cost | $885 |
| Annual Risk Exposure (3 SDRs) | $1,884,270 |

### Severity Distribution

| Severity | Count | Categories |
|----------|-------|------------|
| Critical | 2 | bench_over_commitment, cost_pathology |
| High | 4 | signal_over_claiming, gap_over_claiming, multi_thread_leakage |
| Medium | 4 | dual_control_coordination, icp_misclassification, tone_drift, signal_reliability |
| Low | 0 | scheduling_edge_cases (reclassified to medium) |

### Fix Status

| Status | Count | Categories |
|--------|-------|------------|
| ✅ Implemented | 1 | bench_over_commitment |
| 🟡 Partial | 3 | signal_over_claiming, icp_misclassification, signal_reliability |
| ❌ Not Implemented | 6 | cost_pathology, gap_over_claiming, multi_thread_leakage, dual_control_coordination, tone_drift, scheduling_edge_cases |

---

## Economic Impact Analysis

### Cost per Qualified Lead

```
Total Expected Loss per 100 Leads: $2,921
Cost per Qualified Lead: $29.21

Target Cost per Qualified Lead: $15.00
Cost Penalty Threshold: $25.00

Current Status: ⚠️ ABOVE PENALTY THRESHOLD
Overage: $4.21 per lead (28% over threshold)
```

### ROI of Fixing Top 3 Categories

If bench_over_commitment, cost_pathology, and signal_over_claiming are fixed:

```
Expected Loss Reduction per 100 Leads:
  $821 + $500 + $383 = $1,704

New Cost per Qualified Lead:
  ($2,921 - $1,704) / 100 = $12.17

Status: ✅ BELOW TARGET ($15.00)
Savings: $2.83 per lead below target
```

### Annual Savings (3 SDRs)

```
Annual Qualified Leads: 218 × 3 = 654 leads

Annual Savings from Fixing Top 3:
  654 × $17.04 = $11,144

Annual Risk Reduction:
  $529,740 + $322,500 + $247,095 = $1,099,335
```

### Break-Even Analysis

Assuming 40 hours of engineering time to fix each category:

```
Engineering Cost per Category:
  40 hours × $150/hour = $6,000

Total Engineering Cost (Top 3):
  3 × $6,000 = $18,000

Break-Even Period:
  $18,000 / $11,144 annual savings = 1.6 months

ROI (Year 1):
  ($11,144 - $18,000) / $18,000 = -38% (negative)
  
ROI (Year 2+):
  $11,144 / $0 = ∞ (pure savings)
```

---

## Monitoring and Regression Detection

### Weekly Probe Runs

```bash
# Run all probes
python eval/e2e_test.py

# Log results
python probes/probe_monitor.py log --run-id "$(date +%Y-%m-%d)" --results eval/probe_results.json

# Check for regressions
python probes/probe_monitor.py check --threshold 0.10

# Generate trend report
python probes/probe_monitor.py report
```

### Alert Conditions

| Condition | Action |
|-----------|--------|
| Any bench probe triggers >10% over 3 runs | Investigate bench_summary.json read logic |
| Cost pathology probe triggers >15% | Review Playwright retry logic |
| Signal over-claiming probes average >60% | Audit confidence gates |
| Any category regresses week-over-week | Review recent code changes |
| Cost per trigger exceeds $2,000 | Validate ACV assumptions |

### Success Criteria

Fix is validated when:
- All probes in category trigger <5% over 10 consecutive runs
- No regressions detected for 30 days
- Langfuse traces show fix executed in 100% of cases
- Business cost per occurrence drops by >60%

---

## References

- **Probe Library:** `probes/probe_library.md`
- **Baseline Numbers:** `seed/baseline_numbers.md`
- **Bench Summary:** `seed/bench_summary.json`
- **Target Failure Mode:** `probes/target_failure_mode.md`
- **Aggregated Taxonomy:** `probes/failure_taxonomy_aggregated.json`
- **Monitoring Guide:** `probes/MONITORING.md`
