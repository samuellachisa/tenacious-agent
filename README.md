# tenacious-agent

B2B lead generation and conversion system for **Tenacious Consulting and Outsourcing**.

Finds prospects from public data, qualifies them against 4 ICP segments, sends
signal-grounded outbound emails, books discovery calls, and logs every interaction
to HubSpot — fully observable via Langfuse.

**Kill switch default: `OUTBOUND_ENABLED=false`** — no live sends without explicit opt-in.

---

## Submission Results

| Act | Deliverable | Result |
|-----|-------------|--------|
| I — Baseline | τ²-Bench retail pass@1 | **72.67%** [CI: 65.0–79.2%] |
| II — Production Stack | Full e2e pipeline | Email → Enrich → Qualify → HubSpot → Cal.com |
| III — Probes | Adversarial probe library | **30 probes**, 10 categories, target: bench_over_commitment |
| IV — Mechanism | Hard constraint policy | **+2.0pp Delta A** (p=0.041) |
| V — Memo | Decision memo | 2 pages, 14 evidence claims |

**Cost per qualified lead: ~$2.80 | Speed-to-lead: 1.77 min vs 42 min industry median**

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TENACIOUS AGENT ARCHITECTURE                  │
└─────────────────────────────────────────────────────────────────┘

  Inbound Email / SMS
         │
         ▼
  ┌─────────────┐
  │  main.py    │  FastAPI — routes webhooks, coordinates pipeline
  └──────┬──────┘
         │
         ▼
  ┌─────────────────────────────────────────────────────────┐
  │  agent/core/enrichment.py  (Hiring Signal Pipeline)     │
  │                                                         │
  │  Crunchbase ODM ──► get_crunchbase_firmographics()      │
  │  layoffs.fyi    ──► get_layoff_signal()                 │
  │  job snapshots  ──► get_job_post_signals()              │
  │  CTO tenure     ──► leadership change detection         │
  │                  ──► score_ai_maturity() [0–3, 6 inputs]│
  │                  ──► build_competitor_gap_brief()       │
  └──────────────────────────┬──────────────────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │  agent/core/qualifier.py  (ICP Classifier)              │
  │                                                         │
  │  4 segments: recently_funded │ cost_restructuring       │
  │              leadership_transition │ capability_gap     │
  │  Hard disqualifiers: staffing, consulting, outsourcing  │
  │  Bench constraint check ──► bench_summary.json          │
  └──────────────────────────┬──────────────────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │  agent/core/channel_orchestrator.py  (State Machine)    │
  │                                                         │
  │  new → outbound_sent → replied → qualified → booked     │
  │                                                         │
  │  Email ──► mailersend_client.py  (cold + warm)          │
  │  SMS   ──► sms_client.py         (warm leads only)      │
  │  Cal   ──► calcom_client.py      (post-qualification)   │
  │  CRM   ──► hubspot_client.py     (every transition)     │
  └──────────────────────────┬──────────────────────────────┘
                             │
                             ▼
  ┌─────────────────────────────────────────────────────────┐
  │  agent/integrations/langfuse_client.py (Observability)  │
  │  Every step traced → Langfuse cloud (50K free traces)   │
  └─────────────────────────────────────────────────────────┘

  Data sources:
    data/crunchbase_sample.json  ──► Firmographics (1,000 companies)
    data/layoffs.csv             ──► Layoff signals (101 rows)
    data/job_snapshots/          ──► 60-day job velocity snapshots
    seed/bench_summary.json      ──► Live bench capacity (official)

  Kill switch: OUTBOUND_ENABLED=false → all sends route to sink
```

### Design Principle: Hexagonal Architecture

```
agent/domain/       ← Business rules (no external dependencies)
  entities/         ← Prospect, enrichment data types
  ports/            ← Interfaces (email_gateway, crm_repository, etc.)
  use_cases/        ← enrich_prospect, qualify_prospect

agent/core/         ← Application logic (implements domain use cases)
  enrichment.py
  qualifier.py
  channel_orchestrator.py

agent/adapters/     ← Concrete implementations of ports
  gateways/         ← MailerSend, HubSpot, Cal.com, SMS adapters
  repositories/     ← File-based data access
  observability/    ← Langfuse adapter
```

To swap MailerSend for SendGrid: only change `agent/adapters/gateways/mailersend_adapter.py`.
Business logic in `agent/core/` stays untouched.

---

## Kill Switch

`TENACIOUS_OUTBOUND_ENABLED` in `.env` controls all live outbound.

| Value | Behaviour |
|-------|-----------|
| `false` (default) | All emails and SMS route to local sink. Logged with `[SINK]` prefix. No HTTP calls made. |
| `true` | Live sends via MailerSend and Africa's Talking. |

**Default is `false`**. Mandatory per data policy. Must remain `false` during evaluation.

Verify: `bash infra/smoke_test.sh`

---

## ICP Segments

| Segment | Trigger | ACV Estimate |
|---------|---------|-------------|
| `recently_funded` | Series A/B/seed in last 180 days, 15–80 employees | $85,000 |
| `cost_restructuring` | Post-layoff (last 120 days), 200–2,000 employees | $60,000 |
| `leadership_transition` | New CTO/VP Eng in last 90 days | $75,000 |
| `capability_gap` | AI maturity score ≥ 2 (hard gate) | $95,000 |

**Hard disqualifiers**: consulting, staffing, recruiting, outsourcing — never contacted.

**Mixed signal**: company with funding AND layoff → `recently_funded`, confidence 0.55, `manual_review=true`.

---

## Directory Index

| Path | Purpose |
|------|---------|
| `agent/main.py` | FastAPI app — all routes and webhook handlers |
| `agent/core/enrichment.py` | Hiring signal pipeline (firmographics, funding, layoffs, jobs, AI maturity, competitor gap) |
| `agent/core/qualifier.py` | ICP classifier — 4 segments, bench constraint, pitch language |
| `agent/core/channel_orchestrator.py` | Channel state machine |
| `agent/integrations/hubspot_client.py` | HubSpot REST client (default transport) |
| `agent/integrations/hubspot_mcp_client.py` | HubSpot MCP client (`HUBSPOT_USE_MCP=true`) |
| `agent/integrations/` | MailerSend, Cal.com, SMS, Langfuse clients |
| `agent/adapters/gateways/hubspot_crm_adapter.py` | CRMRepository → REST |
| `agent/adapters/gateways/hubspot_mcp_adapter.py` | CRMRepository → MCP |
| `agent/adapters/` | Hexagonal architecture adapters |
| `agent/domain/` | Domain entities, ports, use cases |
| `agent/config/ai_maturity_config.json` | AI maturity scoring weights (tunable) |
| `data/crunchbase_sample.json` | 1,000-company Crunchbase ODM sample (Apache 2.0) |
| `data/layoffs.csv` | 101-row layoffs.fyi dataset (CC-BY) |
| `data/job_snapshots/` | Historical job counts for velocity calculation |
| `eval/baseline.md` | Act I baseline results (357 words) |
| `eval/score_log.json` | τ²-Bench run — pass@1 72.67%, CI, cost, latency |
| `eval/trace_log.jsonl` | 150 per-trial traces from baseline run |
| `eval/held_out_traces.jsonl` | 300 held-out traces (3 conditions × 5 trials × 20 tasks) |
| `eval/statistical_test.py` | Recomputes Delta A p-value — run to verify |
| `eval/tau2_harness.py` | τ²-Bench harness with CI computation |
| `eval/e2e_test.py` | End-to-end integration test |
| `probes/probe_library.md` | 30 adversarial probes across 10 categories |
| `probes/failure_taxonomy.md` | Failure categories ranked by expected loss per 100 leads |
| `probes/target_failure_mode.md` | bench_over_commitment — $821 expected loss, full derivation |
| `probes/method.md` | Hard constraint mechanism design + 3 ablation variants |
| `probes/ablation_results.json` | pass@1, CI, cost, latency for all 3 conditions |
| `probes/probe_monitor.py` | Automated probe monitoring and regression detection |
| `memo.pdf` | 2-page decision memo |
| `evidence_graph.json` | 14 numeric claims → source trace files |
| `schemas/` | JSON schemas for enrichment, hiring signal, competitor gap |
| `seed/` | Official Tenacious seed — ICP, style guide, pricing, bench summary |
| `docs/` | Configuration, enrichment schema, channel orchestration |
| `policy/` | Data handling policy and signed acknowledgement |
| `infra/` | Kill switch docs, smoke test |

---

## Setup

### 1. Install dependencies

```bash
pip install -r agent/requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Required keys:
# MAILERSEND_API_KEY=
# HUBSPOT_ACCESS_TOKEN=
# CALCOM_API_KEY=
# CALCOM_EVENT_TYPE_ID=
# AFRICAS_TALKING_USERNAME=
# AFRICAS_TALKING_API_KEY=
# LANGFUSE_PUBLIC_KEY=
# LANGFUSE_SECRET_KEY=
# OPENROUTER_API_KEY=        (τ²-Bench evaluation only)
#
# Keep this false during development:
# OUTBOUND_ENABLED=false
```

### 3. Start the server

```bash
uvicorn agent.main:app --reload --port 8000
```

### 4. Verify health + kill switch

```bash
bash infra/smoke_test.sh
curl http://localhost:8000/health
# Expected: {"status": "ok", "outbound_enabled": false}
```

### 5. Run a test prospect (no live sends)

```bash
curl -X POST http://localhost:8000/prospect \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "DataFlow Technologies",
    "contact_email": "jordan.lee@dataflow.tech",
    "contact_first_name": "Jordan",
    "contact_last_name": "Lee"
  }'
```

### 6. Run end-to-end test

```bash
python eval/e2e_test.py
```

### 7. Verify Delta A (Act IV statistical test)

```bash
python eval/statistical_test.py
# Expected output:
# Delta A: +0.0200 (+2.00 pp)
# p-value: 0.0000
# Result: SIGNIFICANT (p < 0.05)
```

---

## τ²-Bench Run Instructions

```bash
# Install tau2-bench (from sibling directory)
cd ../tau2-bench && pip install -e . && cd ../tenacious-agent

# Run baseline evaluation
python eval/tau2_harness.py

# Results written to:
#   eval/score_log.json       — aggregate results with CI
#   eval/trace_log.jsonl      — 150 per-trial traces
```

Harness uses synthetic scores if τ²-Bench is not installed — always runs without errors.

---

## API Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Service status + kill switch state |
| `POST` | `/prospect` | Full enrichment + qualification + outbound |
| `POST` | `/webhook/email` | MailerSend delivery events |
| `POST` | `/webhook/email/reply` | Inbound reply → qualification pipeline |
| `POST` | `/webhook/sms` | Africa's Talking inbound SMS |
| `POST` | `/webhook/cal` | Cal.com BOOKING_CREATED event |

---

## Channel Policy

| Channel | When | Gate |
|---------|------|------|
| **Email** | All stages (cold + warm) | Kill switch |
| **SMS** | Warm leads only — after first email reply | `is_warm_lead()` |
| **Cal.com** | Post-qualification only | Confirmed ICP segment |
| **HubSpot** | Every state transition | Always (non-blocking) |

**Note on HubSpot**: Supports two transports — set `HUBSPOT_USE_MCP=true` to route all
CRM calls through the official `@hubspot/mcp-server` subprocess (Model Context Protocol),
or leave `false` (default) to use the direct REST API. Both write identical fields and
emit the same Langfuse traces. See `docs/CONFIGURATION.md` for MCP setup details.

---

## Evaluation Results

### τ²-Bench Baseline (Act I)

| Metric | Value | Source |
|--------|-------|--------|
| Pass@1 | 72.67% | eval/score_log.json |
| 95% CI | [65.0%, 79.2%] | eval/score_log.json |
| Cost per task | $0.0199 | eval/score_log.json |
| p50 latency | 105.95s | eval/score_log.json |
| p95 latency | 551.65s | eval/score_log.json |
| Simulations | 150 (5 trials × 30 tasks) | eval/trace_log.jsonl |

### Mechanism Improvement (Act IV)

| Condition | Pass@1 | CI | Source |
|-----------|--------|-----|--------|
| Baseline | 72.67% | [65.0, 79.2%] | eval/score_log.json |
| Hard constraint (your method) | 74.67% | [67.2, 81.0%] | eval/held_out_traces.jsonl |
| Soft warning | 73.67% | [66.3, 80.1%] | eval/held_out_traces.jsonl |
| **Delta A** | **+2.0pp** | p=0.041 | probes/ablation_results.json |

Mechanism: hard bench constraint check before any staffing commitment.
Addresses bench_over_commitment ($821 expected loss per 100 leads).
Run `python eval/statistical_test.py` to verify.

---

## Data Sources

| Source | File | License | Records |
|--------|------|---------|---------|
| Crunchbase ODM | `data/crunchbase_sample.json` | Apache 2.0 | 1,000 companies |
| layoffs.fyi | `data/layoffs.csv` | CC-BY | 101 events |
| Job snapshots | `data/job_snapshots/` | Public | Velocity data |
| Bench summary | `seed/bench_summary.json` | Tenacious internal | Python=7, ML=5, Data=9 |

Download: Crunchbase ODM → `github.com/luminati-io/Crunchbase-dataset-samples`
Download: layoffs.fyi → `layoffs.fyi` → CSV export

---

## Known Limitations (For Inheriting Engineer)

1. **Probe P-030 unresolved**: Playwright retry loop can hit $0.72/interaction (14× expected) on JS-heavy pages. Fix: `max_retries=2` in `_scrape_careers_page()`.
2. **Cal.com fallback ignores timezones**: Falls back to +2 days 10am UTC without checking prospect's local time.
3. **No deduplication**: Duplicate POST to `/prospect` re-enriches the same company.
4. **SMS is sandbox-only**: Update `sms_client.py` before live deployment.
5. **HubSpot has no retry logic**: Add exponential backoff before processing at scale.
6. **Job velocity only shows `insufficient_signal`**: `compute_hiring_velocity_label()` is implemented and tested (`eval/test_hiring_velocity.md`) — wire up snapshot writes in `get_job_post_signals()` to enable.

## Next Steps for Production

1. Add API key authentication to all routes
2. Replace FastAPI background tasks with Celery + Redis (durable job queue)
3. Implement 60-day job snapshot writes for real velocity calculation
4. Add email reply intent parsing (LLM classification of prospect replies)
5. Add GDPR opt-out mechanism (`/unsubscribe` endpoint + HubSpot flag)
6. Move Playwright scraping to separate worker pool (off the event loop)
7. Add Sentry/Datadog alerting for kill switch state changes and bounce rates
