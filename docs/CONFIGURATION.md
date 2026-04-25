# Configuration Guide

## Overview

All URLs, API endpoints, and data paths in the tenacious-agent are configurable via environment variables. This enables:
- Testing with mock endpoints
- Self-hosted service instances
- Custom data locations
- Multi-environment deployments (dev/staging/prod)

## Environment Variables

### Kill Switch

| Variable | Default | Description |
|----------|---------|-------------|
| `TENACIOUS_OUTBOUND_ENABLED` | `false` | Master kill switch for all outbound communications |
| `OUTBOUND_ENABLED` | `false` | Alternative kill switch (both checked) |

**Important:** Must remain `false` during evaluation per challenge data policy.

### API Keys

| Variable | Required | Description |
|----------|----------|-------------|
| `MAILERSEND_API_KEY` | Yes | MailerSend transactional email API key |
| `AT_API_KEY` | Yes | Africa's Talking SMS API key |
| `HUBSPOT_ACCESS_TOKEN` | Yes | HubSpot private app access token |
| `HUBSPOT_USE_MCP` | No | `true` = MCP transport, `false` = REST API (default) |
| `CALCOM_API_KEY` | Yes | Cal.com API key |
| `LANGFUSE_PUBLIC_KEY` | Yes | Langfuse observability public key |
| `LANGFUSE_SECRET_KEY` | Yes | Langfuse observability secret key |
| `OPENROUTER_API_KEY` | No | OpenRouter LLM API key (optional) |

---

## HubSpot MCP Transport

The HubSpot integration supports two transports, switchable via `HUBSPOT_USE_MCP`:

### Option A — REST API (default, `HUBSPOT_USE_MCP=false`)

Uses `httpx` to call `https://api.hubapi.com` directly. No extra dependencies beyond the Python requirements. Best for environments without Node.js.

### Option B — MCP Transport (`HUBSPOT_USE_MCP=true`)

Uses the [Model Context Protocol](https://modelcontextprotocol.io) to communicate with HubSpot via the official `@hubspot/mcp-server` Node.js subprocess.

**Prerequisites:**

```bash
# 1. Node.js (v18+) with npx
node --version   # must be v18+

# 2. Python MCP client
pip install 'mcp>=1.0.0'
```

**How it works:**

```
FastAPI request
      │
      ▼
HubSpotMCPAdapter  (agent/adapters/gateways/hubspot_mcp_adapter.py)
      │
      ▼
hubspot_mcp_client._call_mcp_tool()
      │  spawns subprocess
      ▼
npx @hubspot/mcp-server --access-token <token>
      │  JSON-RPC over stdio (MCP protocol)
      ▼
HubSpot CRM API  (api.hubapi.com)
```

**MCP tools used:**

| MCP Tool | Maps to |
|----------|---------|
| `search_contacts` | Contact lookup by email |
| `create_contact` | New contact creation |
| `update_contact` | Contact enrichment updates |
| `create_deal` | Deal creation |
| `associate_records` | Deal ↔ contact association |

**Enable MCP:**

```bash
# .env
HUBSPOT_USE_MCP=true
HUBSPOT_ACCESS_TOKEN=your_private_app_token
```

Both transports write identical fields (`icp_segment`, `ai_maturity_score`, `hs_lead_status`, `enrichment_timestamp`) and emit the same Langfuse trace events — swapping transport requires only the env var change.

### API URLs

All API URLs can be overridden for testing or self-hosted instances:

| Variable | Default | Description |
|----------|---------|-------------|
| `MAILERSEND_API_URL` | `https://api.mailersend.com/v1/email` | MailerSend email endpoint |
| `HUBSPOT_API_URL` | `https://api.hubapi.com` | HubSpot CRM base URL |
| `CALCOM_API_URL` | `https://api.cal.com/v2` | Cal.com API v2 base URL |
| `AT_API_URL` | `https://api.sandbox.africastalking.com/version1/messaging` | Africa's Talking SMS endpoint (auto-switches based on `AT_USERNAME`) |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Langfuse observability host |

### Data Paths

All data paths are relative to the project root:

| Variable | Default | Description |
|----------|---------|-------------|
| `CRUNCHBASE_DATA_PATH` | `data/crunchbase_sample.json` | Firmographic data source |
| `LAYOFFS_DATA_PATH` | `data/layoffs.csv` | Layoff events data source |
| `BRIEFS_OUTPUT_PATH` | `data/briefs` | Enrichment output directory |

### Email Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MAILERSEND_FROM_EMAIL` | `outbound@tenacious.consulting` | Sender email address |
| `MAILERSEND_FROM_NAME` | `Tenacious Consulting` | Sender display name |

### SMS Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AT_USERNAME` | `sandbox` | Africa's Talking username (use "sandbox" for testing) |
| `AT_SHORTCODE` | `15629` | SMS sender shortcode (production only) |

### Cal.com Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `CALCOM_EVENT_TYPE_ID` | None | Event type ID for discovery calls |

### LLM Configuration (Optional)

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_MODEL` | `openai/gpt-4o-mini` | Model identifier for OpenRouter |

### Webhook Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_BASE_URL` | None | Public URL for receiving inbound webhooks |

## Testing with Mock Endpoints

### Local Mock Server

```bash
# Start a local mock server on port 8001
python tests/mock_server.py

# Override API URLs to point to mock
export MAILERSEND_API_URL=http://localhost:8001/email
export HUBSPOT_API_URL=http://localhost:8001/hubspot
export CALCOM_API_URL=http://localhost:8001/calcom
export AT_API_URL=http://localhost:8001/sms
```

### Docker Compose Example

```yaml
version: '3.8'
services:
  agent:
    build: .
    environment:
      - MAILERSEND_API_URL=http://mock-mailersend:8080/v1/email
      - HUBSPOT_API_URL=http://mock-hubspot:8080
      - CALCOM_API_URL=http://mock-calcom:8080/v2
      - AT_API_URL=http://mock-at:8080/messaging
      - CRUNCHBASE_DATA_PATH=/data/crunchbase.json
      - LAYOFFS_DATA_PATH=/data/layoffs.csv
      - BRIEFS_OUTPUT_PATH=/output/briefs
    volumes:
      - ./data:/data
      - ./output:/output
```

## Self-Hosted Services

### Self-Hosted Langfuse

```bash
export LANGFUSE_HOST=https://langfuse.yourcompany.com
export LANGFUSE_PUBLIC_KEY=pk-lf-your-key
export LANGFUSE_SECRET_KEY=sk-lf-your-secret
```

### Self-Hosted Cal.com

```bash
export CALCOM_API_URL=https://cal.yourcompany.com/api/v2
export CALCOM_API_KEY=your-self-hosted-key
```

## Multi-Environment Setup

### Development (.env.dev)

```bash
TENACIOUS_OUTBOUND_ENABLED=false
MAILERSEND_API_URL=http://localhost:8001/email
HUBSPOT_API_URL=http://localhost:8001/hubspot
CRUNCHBASE_DATA_PATH=data/test/crunchbase_dev.json
BRIEFS_OUTPUT_PATH=data/test/briefs
```

### Staging (.env.staging)

```bash
TENACIOUS_OUTBOUND_ENABLED=false
MAILERSEND_API_URL=https://api.mailersend.com/v1/email
HUBSPOT_API_URL=https://api.hubapi.com
CRUNCHBASE_DATA_PATH=data/staging/crunchbase.json
BRIEFS_OUTPUT_PATH=data/staging/briefs
```

### Production (.env.prod)

```bash
TENACIOUS_OUTBOUND_ENABLED=true
MAILERSEND_API_URL=https://api.mailersend.com/v1/email
HUBSPOT_API_URL=https://api.hubapi.com
CRUNCHBASE_DATA_PATH=/var/data/crunchbase.json
BRIEFS_OUTPUT_PATH=/var/output/briefs
```

Load environment-specific config:

```bash
# Development
cp .env.dev .env
uvicorn agent.main:app --reload

# Staging
cp .env.staging .env
uvicorn agent.main:app --host 0.0.0.0 --port 8000

# Production
cp .env.prod .env
uvicorn agent.main:app --host 0.0.0.0 --port 8000 --workers 4
```

## Custom Data Locations

### Network Storage

```bash
export CRUNCHBASE_DATA_PATH=/mnt/nfs/data/crunchbase.json
export LAYOFFS_DATA_PATH=/mnt/nfs/data/layoffs.csv
export BRIEFS_OUTPUT_PATH=/mnt/nfs/output/briefs
```

### S3-Mounted Paths

```bash
# Mount S3 bucket using s3fs
s3fs my-bucket /mnt/s3-data

export CRUNCHBASE_DATA_PATH=/mnt/s3-data/crunchbase.json
export LAYOFFS_DATA_PATH=/mnt/s3-data/layoffs.csv
export BRIEFS_OUTPUT_PATH=/mnt/s3-data/briefs
```

## Validation

Verify configuration before starting:

```bash
python -c "
import os
from dotenv import load_dotenv

load_dotenv()

print('Kill Switch:', os.getenv('OUTBOUND_ENABLED', 'false'))
print('MailerSend URL:', os.getenv('MAILERSEND_API_URL', 'default'))
print('HubSpot URL:', os.getenv('HUBSPOT_API_URL', 'default'))
print('Cal.com URL:', os.getenv('CALCOM_API_URL', 'default'))
print('Crunchbase Path:', os.getenv('CRUNCHBASE_DATA_PATH', 'default'))
print('Briefs Output:', os.getenv('BRIEFS_OUTPUT_PATH', 'default'))
"
```

## Security Best Practices

1. **Never commit .env files** - Use .env.example as template
2. **Rotate API keys regularly** - Especially after team changes
3. **Use separate keys per environment** - Dev/staging/prod isolation
4. **Restrict API key permissions** - Minimum required scopes only
5. **Monitor API usage** - Set up alerts for unusual patterns
6. **Use secrets management** - Consider AWS Secrets Manager, HashiCorp Vault, etc.

## Troubleshooting

### Connection Refused

```bash
# Check if URL is reachable
curl -I $MAILERSEND_API_URL

# Verify environment variable is loaded
echo $MAILERSEND_API_URL
```

### File Not Found

```bash
# Check if data path exists
ls -la $CRUNCHBASE_DATA_PATH

# Verify path is relative to project root
pwd
echo $CRUNCHBASE_DATA_PATH
```

### API Authentication Errors

```bash
# Verify API key is set
echo ${MAILERSEND_API_KEY:0:10}...  # Show first 10 chars only

# Test API key directly
curl -H "Authorization: Bearer $MAILERSEND_API_KEY" \
  $MAILERSEND_API_URL
```

## References

- `.env.example` - Complete environment variable template
- `agent/utils/env_utils.py` - Environment variable helpers
- `infra/smoke_test.sh` - Configuration validation script
