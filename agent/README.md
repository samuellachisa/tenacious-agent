# Agent Directory Structure

Organized by functional responsibility for better maintainability and discoverability.

## Structure

```
agent/
├── main.py                    # FastAPI application entry point
├── requirements.txt           # Python dependencies
│
├── core/                      # Core business logic
│   ├── enrichment.py         # Company enrichment pipeline
│   └── qualifier.py          # Prospect qualification logic
│
├── integrations/             # External service clients
│   ├── calcom_client.py     # Cal.com scheduling API
│   ├── hubspot_client.py    # HubSpot CRM operations
│   ├── langfuse_client.py   # Langfuse observability
│   ├── mailersend_client.py # Email sending with kill-switch
│   └── sms_client.py        # Africa's Talking SMS
│
├── utils/                    # Shared utilities
│   └── env_utils.py         # Environment variable helpers
│
└── examples/                 # Usage demonstrations
    └── email_event_example.py  # Email event handler examples
```

## Import Patterns

```python
# Core logic
from agent.core.enrichment import run_enrichment_pipeline
from agent.core.qualifier import qualify_prospect

# Integrations
from agent.integrations.hubspot_client import create_or_update_contact
from agent.integrations.mailersend_client import send_email
from agent.integrations.langfuse_client import log_trace

# Utils
from agent.utils.env_utils import outbound_enabled
```

## Categories

- **core/**: Business logic that defines what the agent does
- **integrations/**: External API clients (can be swapped/mocked)
- **utils/**: Shared helpers with no external dependencies
- **examples/**: Documentation and usage patterns
