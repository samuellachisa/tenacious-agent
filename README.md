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
│         │            │  Playwright  │    │  MailerSend      │  │
│         │            │  Job Scraper │    │  Email Client    │  │
│         │            └──────────────┘    └──────────────────┘  │
│         │                                                       │
│  ┌──────▼───────────────────────────────────────────────────┐  │
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

## Project Structure

| Path | Description |
|------|-------------|
| `agent/main.py` | FastAPI app — all routes and background tasks |
| `agent/enrichment.py` | Signal enrichment pipeline (firmographics, funding, layoffs, jobs, leadership, AI maturity) |
| `agent/qualifier.py` | ICP classifier — 4 segments, pitch language, confidence scoring |
| `agent/mailersend_client.py` | MailerSend email client with kill switch |
| `agent/sms_client.py` | Africa's Talking SMS client (sandbox, warm leads only) |
| `agent/hubspot_client.py` | HubSpot CRM — contacts, deals, lifecycle stages |
| `agent/calcom_client.py` | Cal.com availability + booking |
| `agent/langfuse_client.py` | Langfuse observability singleton |
| `agent/requirements.txt` | Pinned Python dependencies |
| `eval/tau2_harness.py` | τ²-Bench evaluation harness with CI |
| `eval/e2e_test.py` | End-to-end integration test |
| `eval/baseline.md` | Baseline results template |
| `data/crunchbase_sample.json` | Synthetic firmographic data (3 companies) |
| `data/layoffs.csv` | Synthetic layoff events |

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
