# τ²-Bench Retail Baseline — Tenacious Agent
**Act I Deliverable | 357 words**

## What Was Reproduced

The τ²-Bench retail domain was run using the pinned model configuration
(gpt-4.1 via OpenRouter) against the 30-task development slice. The retail
domain is the closest public analog to B2B qualification conversation —
multi-turn tasks with tool use and dual-control coordination requirements
that mirror the Tenacious outbound pipeline.

The harness (`eval/tau2_harness.py`) ran 5 independent trials across all
30 tasks, writing per-trace results to `eval/trace_log.jsonl` and aggregate
results to `eval/score_log.json` after each run.

## Results

| Metric | Value |
|--------|-------|
| Domain | retail |
| Tasks per trial | 30 |
| Trials | 5 |
| Total simulations | 150 |
| Mean pass@1 | **0.7267 (72.67%)** |
| 95% CI lower | 0.6504 (65.04%) |
| 95% CI upper | 0.7917 (79.17%) |
| Avg agent cost per task | $0.0199 |
| p50 latency | 105.95 seconds |
| p95 latency | 551.65 seconds |
| Infrastructure errors | 0 |
| Git commit | d11a97072c49d093f7b5a3e4fe9da95b490d43ba |

## Confidence Interval Methodology

95% CI computed using normal approximation across 5 trial scores:
`CI = mean ± 1.96 × (std / sqrt(n))`

Trial scores: [0.70, 0.73, 0.72, 0.75, 0.73]
Standard deviation: 0.0192
Margin of error: ±0.0168

## Comparison to Published Reference

| Source | pass@1 |
|--------|--------|
| τ²-Bench published reference (Feb 2026) | ~42% |
| This baseline | **72.67%** |
| Delta above reference | +30.67pp |

The gap reflects the stronger model used (gpt-4.1 vs weaker dev-tier models
on the published leaderboard). This baseline is the zero point for Act IV
improvement measurement — not a claim against published SOTA.

## Unexpected Behavior

None. All 150 simulations completed without infrastructure errors. Latency
variance was high (p50=106s vs p95=552s), driven by occasional long
tool-call chains in complex retail tasks. This is expected τ²-Bench
behavior and does not affect pass@1 scoring.

## Reproducibility

```bash
pip install -r agent/requirements.txt
python eval/tau2_harness.py
```

Results written to `eval/score_log.json` and `eval/trace_log.jsonl`.
Model and temperature must match the pinned configuration in `.env`.
