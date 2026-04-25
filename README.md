# tenacious-agent

B2B lead generation and conversion system for **Tenacious Consulting and Outsourcing**.

Finds prospects, qualifies them against 4 ICP segments, sends signal-grounded outbound
emails, and books discovery calls — fully observable via Langfuse.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        tenacious-agent                          │
│                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────┐  │
│  │  FastAPI     │    │  Enrichment  │    │   Qualifier      │  │
│  │  main.py     │───▶│  Pipeline    │───▶│   (ICP Segments) │  │
│  │              │    │  enrichment  │    │   qualifier.py   │  │
│  │  /prospect   │    │  .py         │    │                  │  │
│  │  /webhook/*  │    └──────┬───────┘    └────────┬─────────┘  │
│  └──────┬───────┘           │                     │            │
│         │            ┌──────▼───────┐    ┌────────▼─────────┐  │
│         │            │  Playwright  │    │  Channel         │  │
│         │            │  Job Scraper │    │  Orchestrator    │  │
│         │            └──────────────┘    │  (State Machine) │  │
│         │                                └────────┬─────────┘  │
│         │                                         │            │
│  ┌──────▼─────────────────────────────────────────▼─────────┐  │
│  │                   Integration Layer                       │  │
│  │                                                           │  │
│  │  ┌─────────────┐  ┌──────────────┐  ┌────────────────┐  │  │
│  │  │  HubSpot    │  │  Cal.com     │  │  Africa's      │  │  │
│  │  │  CRM        │  │  Booking     │  │  Talking SMS   │  │  │
│  │  │  hubspot_   │  │  calcom_     │  │  sms_client.py │  │  │
│  │  │  client.py  │  │  client.py   │  │  (warm leads)  │  │  │
│  │  └─────────────┘  └──────────────┘  └────────────────┘  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  Langfuse Observability (every pipeline event traced)    │  │
│  │  langfuse_client.py                                      │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘

Data Sources:
  data/crunchbase_sample.json  ──▶  Firmographics
  data/layoffs.csv             ──▶  Layoff signals
  Playwright scrape            ──▶  Job post signals (live)
  data/briefs/{company}.json   ──▶  Enrichment output cache
```

### Channel Orchestration

The **Channel Orchestrator** (`agent/core/channel_orchestrator.py`) is a central state machine that manages when to use email, SMS, CRM updates, and Cal.com bookings based on prospect lifecycle stage.

**Prospect Lifecycle**: `new → outbound_sent → email_opened → replied → qualified → scheduled → call_booked`

**Channel Rules**:
- Email: Available at all stages
- SMS: Only for warm leads (email_opened, replied, qualified, scheduled, call_booked)
- Cal.com: Only after qualification (qualified, scheduled, call_booked)
- CRM: Updated at every state transition

See `docs/CHANNEL_ORCHESTRATION.md` for full documentation.

---

## Kill Switch

`TENACIOUS_OUTBOUND_ENABLED` in `.env` controls all live outbound. `OUTBOUND_ENABLED` is also supported for compatibility.

| Value   | Behaviour                                                        |
|---------|------------------------------------------------------------------|
| `false` | All emails and SMS are routed to a local sink. Logged to Langfuse and printed to stdout with `[SINK]` prefix. No HTTP calls made. |
| `true`  | Live sends via MailerSend and Africa's Talking.                  |

**Default is `false`.** This is mandatory per challenge data policy and must remain
`false` during evaluation. Set to `true` only when ready for live outbound.

- Verify the outbound gate before starting the agent: `infra/smoke_test.sh`

---

## ICP Segments

| Segment | Trigger | ACV Estimate |
|---------|---------|-------------|
| `recently_funded` | Series A/B/seed in last 180 days | $85,000 |
| `cost_restructuring` | Post-layoff, 50–1000 employees, last 120 days | $60,000 |
| `leadership_transition` | New CTO/VP Eng in last 90 days | $75,000 |
| `capability_gap` | AI maturity score ≥ 2 (hard gate) | $95,000 |

**Hard disqualifiers**: consulting, staffing, recruiting, outsourcing firms.

**Mixed signal edge case**: company with both recent funding AND recent layoff →
defaults to `recently_funded` with reduced confidence (0.55) and `manual_review=true`.

---

## Directory Index

| Directory | Purpose |
|-----------|---------|
| `agent/` | Core application code — FastAPI server, enrichment, qualification, integrations |
| `agent/adapters/` | Hexagonal architecture adapters (gateways, repositories, observability) |
| `agent/core/` | Business logic — enrichment pipeline, qualifier, channel orchestrator |
| `agent/domain/` | Domain entities, ports (interfaces), and use cases |
| `agent/examples/` | Usage examples (email event handling, channel orchestration) |
| `agent/integrations/` | External service clients (HubSpot, MailerSend, Cal.com, SMS, Langfuse) |
| `agent/utils/` | Shared utilities (environment variable helpers) |
| `data/` | Sample data — Crunchbase firmographics, layoff signals, enrichment briefs |
| `docs/` | Configuration guide, enrichment schema, channel orchestration, competitor gap brief |
| `eval/` | τ²-Bench harness, end-to-end tests, baseline results, trace logs |
| `infra/` | Infrastructure scripts — smoke test, kill switch documentation |
| `policy/` | Data handling policy and acknowledgement |
| `probes/` | Failure analysis — taxonomy, ablation results, probe library, methods, monitoring tool |
| `schemas/` | JSON schemas for enrichment output, competitor gap briefs, hiring signals |
| `seed/` | Sales collateral — ICP definition, email sequences, discovery transcripts, pricing, style guide |

---

## Project Structure

| Path | Description |
|------|-------------|
| `agent/main.py` | FastAPI app — all routes and background tasks |
| `agent/core/enrichment.py` | Signal enrichment pipeline (firmographics, funding, layoffs, jobs, leadership, AI maturity, competitor gap brief) |
| `agent/core/qualifier.py` | ICP classifier — 4 segments, pitch language, confidence scoring |
| `agent/integrations/mailersend_client.py` | MailerSend email client with kill switch |
| `agent/integrations/sms_client.py` | Africa's Talking SMS client (sandbox, warm leads only) |
| `agent/integrations/hubspot_client.py` | HubSpot CRM — contacts, deals, lifecycle stages |
| `agent/integrations/calcom_client.py` | Cal.com availability + booking |
| `agent/integrations/langfuse_client.py` | Langfuse observability singleton |
| `agent/requirements.txt` | Pinned Python dependencies |
| `eval/tau2_harness.py` | τ²-Bench evaluation harness with CI |
| `eval/e2e_test.py` | End-to-end integration test |
| `eval/baseline.md` | Baseline results template |
| `data/crunchbase_sample.json` | Synthetic firmographic data (3 companies) |
| `data/layoffs.csv` | Synthetic layoff events |
| `docs/COMPETITOR_GAP_BRIEF.md` | Competitor gap brief peer sampling and quality standards |
| `schemas/competitor_gap_brief.schema.json` | JSON schema for competitor gap briefs |
| `schemas/sample_competitor_gap_brief.json` | High-quality example with full peer evidence |
| `probes/probe_monitor.py` | Probe monitoring tool — tracks trigger rates, visualizes trends, detects regressions |
| `probes/MONITORING.md` | Probe monitoring guide with workflow examples |

---

## Production Stack Status

| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI + uvicorn | ✅ Ready | `uvicorn agent.main:app --reload` |
| MailerSend | ✅ Ready | Kill switch active by default |
| Africa's Talking | ✅ Ready | Sandbox mode, warm leads only |
| HubSpot CRM | ✅ Ready | Bearer token auth |
| Cal.com | ✅ Ready | Falls back to +2d 10am UTC |
| Langfuse | ✅ Ready | Non-blocking, singleton |
| Playwright | ✅ Ready | Headless Chromium scrape |
| τ²-Bench harness | ✅ Ready | Synthetic scores if τ²-Bench not installed |

---

## Setup

### 1. Install dependencies

```bash
cd tenacious-agent
pip install -r agent/requirements.txt
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env — fill in API keys
# Leave OUTBOUND_ENABLED=false during development
```

### 3. Run the server

```bash
uvicorn agent.main:app --reload --port 8000
```

### 4. Test the health endpoint

```bash
curl http://localhost:8000/health
```

### 5. Run the prospect pipeline (kill switch active — no live sends)

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

### 6. Run the end-to-end test

```bash
# Server must be running on port 8000
python eval/e2e_test.py
```

---

## τ²-Bench Run Instructions

```bash
# Install tau2-bench (from sibling directory)
cd ../tau2-bench
pip install -e .
cd ../tenacious-agent

# Run the harness (30 tasks, 5 trials, retail domain)
python eval/tau2_harness.py

# Results written to:
#   eval/score_log.json      — run results with CI
#   eval/trace_log.jsonl     — per-trial traces
```

The harness uses synthetic scores if τ²-Bench is not installed, so it always runs
without errors. Replace with real τ²-Bench output for production evaluation.

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

## Langfuse Trace Events

Every pipeline step emits a named trace. Key events:

| Event | Trigger |
|-------|---------|
| `enrichment_pipeline_start` | Pipeline begins |
| `enrichment_firmographics` | Crunchbase data loaded |
| `enrichment_funding` | Funding signal evaluated |
| `enrichment_layoff` | Layoff signal evaluated |
| `enrichment_job_signals` | Job post signals collected |
| `enrichment_ai_maturity` | AI maturity scored |
| `enrichment_pipeline_complete` | Pipeline done, latency logged |
| `qualifier_result` | Segment assigned |
| `qualifier_disqualified` | Hard disqualifier matched |
| `qualifier_mixed_signal` | Funding + layoff edge case |
| `email_sink` | Email routed to sink (outbound disabled) |
| `email_sent` | Email sent live |
| `hubspot_contact_created` | New HubSpot contact |
| `hubspot_stage_updated` | Lifecycle stage advanced |
| `calcom_slot_found` | Available slot found |
| `calcom_booking_created` | Discovery call booked |
| `sms_sink` | SMS routed to sink |
| `sms_sent` | SMS sent live |

---

## Handoff & Known Limitations

### Recent Improvements

**AI Maturity Scorer Configuration** (April 2026): Externalized all AI maturity scoring logic to `agent/config/ai_maturity_config.json` for easy tuning without code changes:
- All six signal keyword lists now configurable (ai_adjacent_roles, named_ai_leadership, ai_industry_classification, executive_commentary, ml_stack_keywords, strategic_ai_communications)
- Score contribution and confidence thresholds externalized per signal
- Confidence rules (high: 0.85, medium_high: 0.70, medium: 0.60) now configurable
- Fallback to hardcoded defaults if config file missing or malformed
- See `docs/AI_MATURITY_TUNING.md` for tuning guide with examples
- Enables rapid iteration on keyword lists (e.g., add "generative ai", "chatgpt" to executive_commentary) without code deployment

**Bench Capacity Constraint** (April 2026): Fixed the highest-ROI failure mode (bench_over_commitment, $821 expected loss per 100 leads). The qualifier now:
- Loads `seed/bench_summary.json` before generating pitch language
- Infers required stacks from job signals and AI maturity (ml, python, data, go, infra, frontend)
- Checks available capacity vs required count for primary stack
- Adjusts pitch language: "We have 7 Python engineers available" (sufficient) vs "Our ML bench currently has 5 engineers — we can start with 5 and ramp within 2-3 weeks" (insufficient)
- Escalates to delivery lead when capacity is zero: "Let me connect you with our delivery lead"
- See `eval/test_bench_capacity.md` for full test specification
- Addresses Probes P-003, P-008, P-013, P-018 from the failure taxonomy

**60-Day Hiring Velocity Computation** (April 2026): The enrichment pipeline now includes a dedicated `compute_hiring_velocity_label()` helper function that computes categorical velocity labels ("tripled_or_more", "doubled", "increased_modestly", "flat", "declined", "insufficient_signal") from current vs 60-day-ago job counts. The function includes:
- Clear inline documentation with examples
- Confidence scoring (0.8 for clean data, 0.6 for edge cases, 0.3 for missing historical data)
- Edge case handling (division by zero, both counts zero, etc.)
- Full test specification in `eval/test_hiring_velocity.md`

The helper is integrated into `get_job_post_signals()` but currently returns "insufficient_signal" because no historical snapshot storage exists yet. See "Next Steps for Production" #8 below for implementation guidance.

### Sharp Edges

1. **Mixed signal edge case**: Companies with both recent funding AND recent layoff default to `recently_funded` with reduced confidence (0.55) and `manual_review=true`. This is a business logic decision, not a bug. Review `agent/core/qualifier.py` if you need to change the precedence.

2. **Playwright job scraping is brittle**: The job post scraper in `agent/core/enrichment.py` uses CSS selectors that break when job boards change their HTML. If job signals stop working, check the selectors first. Consider adding retry logic or fallback to a job board API.

3. **Cal.com fallback is naive**: When no slots are available, the system falls back to "+2 days at 10am UTC" without checking the prospect's timezone or business hours. This will book calls at awkward times for non-UTC prospects.

4. **HubSpot rate limits**: The HubSpot client has no rate limiting or retry logic. If you process >100 prospects/second, you'll hit 429 errors. Add exponential backoff in `agent/integrations/hubspot_client.py`.

5. **Langfuse is fire-and-forget**: Trace events are non-blocking and failures are silently logged. If Langfuse is down, you won't know unless you check logs. Consider adding a health check endpoint that verifies Langfuse connectivity.

6. **SMS is sandbox-only**: Africa's Talking SMS client is hardcoded to sandbox mode. To go live, you need to update `agent/integrations/sms_client.py` and verify compliance with `agent/integrations/SMS_POLICY.md`.

7. **No duplicate detection**: The system will re-enrich and re-email the same prospect if you POST to `/prospect` twice. Add a deduplication layer (check HubSpot for existing contact) before enrichment.

8. **Enrichment briefs are cached indefinitely**: `data/briefs/{company}.json` files are never invalidated. If a company's data changes (new funding round, new layoff), you need to manually delete the brief file to force re-enrichment.

### Next Steps for Production

1. **Add authentication**: All API routes are currently open. Add API key auth or OAuth before exposing to the internet.

2. **Implement proper job queue**: Background tasks in FastAPI are not durable. If the server crashes mid-enrichment, the prospect is lost. Replace with Celery + Redis or a managed queue (AWS SQS, GCP Pub/Sub).

3. **Add monitoring and alerting**: Set up Sentry or Datadog to catch exceptions. Add alerts for kill switch state changes, high disqualification rates, and email bounce rates.

4. **Improve AI maturity scoring**: The current AI maturity score is a placeholder (random 0-3). Replace with a real model or external API (e.g., LinkedIn company page analysis, tech stack detection).

5. **Add email reply parsing**: The `/webhook/email/reply` endpoint exists but doesn't parse intent (interested, not interested, out of office). Add NLP or use an LLM to classify replies and route to appropriate workflows.

6. **Implement A/B testing**: Email templates are hardcoded in `agent/core/qualifier.py`. Add a template versioning system and track conversion rates per template in Langfuse.

7. **Add GDPR compliance**: No opt-out mechanism exists. Add unsubscribe links to emails and a `/unsubscribe` endpoint that updates HubSpot and blocks future sends.

8. **Scale job scraping**: Playwright runs in-process and blocks the event loop. Move to a separate worker pool or use a headless browser service (Browserless, Apify). Also implement 60-day snapshot storage to enable true velocity calculation: store job counts in `data/job_snapshots/{company_domain}/{date}.json`, query the snapshot from 60 days ago in `get_job_post_signals()`, and pass to `compute_hiring_velocity_label()`. The helper function is already implemented and tested (see `eval/test_hiring_velocity.md`).

9. **Add integration tests for webhooks**: The webhook endpoints (`/webhook/email`, `/webhook/sms`, `/webhook/cal`) are not covered by tests. Add integration tests that simulate real webhook payloads from each service.

10. **Document the hexagonal architecture**: The `agent/domain/` and `agent/adapters/` structure follows hexagonal/ports-and-adapters architecture, but this isn't explained anywhere. Add an architecture decision record (ADR) or diagram explaining why this pattern was chosen and how to extend it.
