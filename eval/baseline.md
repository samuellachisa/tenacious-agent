# τ²-Bench Baseline Evaluation — Tenacious Agent

## What Was Reproduced

This baseline evaluates the Tenacious Agent's underlying LLM (via OpenRouter) against
the τ²-Bench retail domain benchmark. The agent is tested on its ability to handle
multi-turn customer service tasks that mirror the qualification and outbound pipeline.

Evaluation was run using `eval/tau2_harness.py` with the following configuration:
- Domain: `retail`
- Tasks per trial: 30
- Trials: 5
- Model: `gpt-4.1`
- Confidence interval: 95% (z = 1.96, normal approximation)

---

## Results

| Metric            | Value              |
|-------------------|--------------------|
| Domain            | retail             |
| Model             | gpt-4.1            |
| Tasks / trial     | 30                 |
| Trials            | 5                  |
| Mean pass@1       | [TO BE FILLED]     |
| 95% CI lower      | [TO BE FILLED]     |
| 95% CI upper      | [TO BE FILLED]     |
| Std deviation     | [TO BE FILLED]     |
| Margin of error   | [TO BE FILLED]     |
| Trial scores      | [TO BE FILLED]     |
| Run timestamp     | [TO BE FILLED]     |

---

## Methodology

1. **Environment setup**: Install τ²-Bench from the `tau2-bench/` directory.
   Configure `.env` with `OPENROUTER_API_KEY` and `LLM_MODEL=openai/gpt-4.1`.

2. **Sealed partition**: Tasks are drawn from the sealed τ²-Bench retail task set.
   No task content was inspected prior to evaluation. The harness uses the
   `--num-tasks` flag to sample randomly from the full task pool.

3. **Scoring**: Each task is scored pass@1 — the agent either completes the task
   correctly on the first attempt (1.0) or does not (0.0). Partial credit is not
   applied. The mean across all tasks in a trial gives the trial pass@1 score.

4. **Confidence interval**: The 95% CI is computed using normal approximation
   across the 5 trial scores: `CI = mean ± 1.96 * (std / sqrt(n))`.

5. **Logging**: All trial results are appended to `eval/score_log.json`.
   Per-trial traces are appended to `eval/trace_log.jsonl` for Langfuse review.

---

## Unexpected Behavior

| Observation | Impact | Notes |
|-------------|--------|-------|
| [TO BE FILLED] | [TO BE FILLED] | [TO BE FILLED] |

---

## Notes on Sealed Partition

- The τ²-Bench retail task set was not inspected prior to running this evaluation.
- Task sampling is handled entirely by the τ²-Bench framework via `--num-tasks`.
- No prompt engineering was performed against the eval task content.
- Results reflect zero-shot performance of the configured LLM model.
- To reproduce: run `python eval/tau2_harness.py` with a valid `.env` configuration.

---

## How to Run

```bash
# From the tenacious-agent/ directory:
pip install -r agent/requirements.txt
playwright install chromium

# Install tau2-bench (from the tau2-bench/ sibling directory):
cd ../tau2-bench && pip install -e . && cd ../tenacious-agent

# Run the harness:
python eval/tau2_harness.py
```

Results will be written to `eval/score_log.json` and `eval/trace_log.jsonl`.
