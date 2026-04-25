# AI Maturity Scoring Configuration Guide

## Overview

The AI maturity scorer evaluates prospects on a 0-3 scale using six weighted signals. All configuration is externalized to `agent/config/ai_maturity_config.json` for easy tuning without code changes.

## Configuration File Location

```
agent/config/ai_maturity_config.json
```

## Scoring Bands

| Score | Label | Description |
|-------|-------|-------------|
| 0 | No signal | No AI maturity indicators detected |
| 1 | Weak | Low-weight signals only (marketing language, generic mentions) |
| 2 | Moderate | Medium-weight signals present (industry classification, executive commentary) |
| 3 | Strong | High-weight signals present (AI roles, named leadership) |

## Signal Weights

### High-Weight Signals (score contribution: 1-2 points)

**ai_adjacent_roles**: Open job posts for AI/ML roles
- Keywords: ai, ml, machine learning, llm, nlp, data scientist, deep learning, mlops, etc.
- Thresholds:
  - 3+ roles → +2 score, 0.9 confidence
  - 1+ roles → +1 score, 0.7 confidence
  - 0 roles → +0 score, 0.0 confidence

**named_ai_leadership**: Recent CTO/VP Eng appointment
- Tenure threshold: 90 days
- Score contribution: +1
- Confidence: 0.9

### Medium-Weight Signals (score contribution: 1 point)

**ai_industry_classification**: Industry field contains AI/ML keywords
- Keywords: artificial intelligence, machine learning, ai, ml
- Score contribution: +1
- Confidence: 0.6

**executive_commentary**: Recent news mentions AI/ML/automation
- Keywords: ai, machine learning, llm, automation
- Score contribution: +1
- Confidence: 0.6

### Low-Weight Signals (confidence contribution only)

**ml_stack_keywords**: Product description contains ML stack keywords
- Keywords: mlops, pipeline, data infrastructure, model, inference, vector, embedding, neural, deep learning
- Score contribution: +0 (confidence only)
- Confidence: 0.4

**strategic_ai_communications**: Description references AI-powered capabilities
- Keywords: ai-powered, ai powered, artificial intelligence
- Score contribution: +0 (confidence only)
- Confidence: 0.4

## Confidence Rules

Overall confidence is computed from signal votes:

| Criteria | Confidence Threshold |
|----------|---------------------|
| 2+ high-weight signals detected | 0.85 (high) |
| 1 high-weight + 2 medium-weight signals | 0.70 (medium-high) |
| 1 high-weight OR 2+ medium-weight signals | 0.60 (medium) |
| Low-weight signals only or no signals | 0.30 (fallback) |

## Tuning Examples

### Example 1: Increase Sensitivity to Aggressive Hiring

**Problem**: Companies with 5+ AI roles should score higher (more aggressive hiring signal).

**Solution**: Edit `agent/config/ai_maturity_config.json`:

```json
{
  "signals": {
    "ai_adjacent_roles": {
      "thresholds": {
        "very_high": {"min_roles": 5, "score_contribution": 3, "confidence": 0.95},
        "high": {"min_roles": 3, "score_contribution": 2, "confidence": 0.9},
        "medium": {"min_roles": 1, "score_contribution": 1, "confidence": 0.7}
      }
    }
  }
}
```

Then update `score_ai_maturity()` to check `very_high` threshold first.

### Example 2: Add New Keywords for Generative AI

**Problem**: Missing prospects who mention "generative ai", "genai", "chatgpt" in news.

**Solution**: Edit `agent/config/ai_maturity_config.json`:

```json
{
  "signals": {
    "executive_commentary": {
      "keywords": [
        "ai", "machine learning", "llm", "automation",
        "generative ai", "genai", "chatgpt", "gpt-4", "claude"
      ]
    }
  }
}
```

No code changes required — scorer will automatically use new keywords.

### Example 3: Downweight Marketing Language

**Problem**: Too many false positives from companies that say "AI-powered" in marketing copy but have no real AI capability.

**Solution**: Reduce confidence for `strategic_ai_communications`:

```json
{
  "signals": {
    "strategic_ai_communications": {
      "confidence": 0.2
    }
  }
}
```

Or remove the signal entirely by setting `score_contribution: 0` and `confidence: 0.0`.

### Example 4: Add VP Data / Head of AI to Leadership Detection

**Problem**: Only detecting CTO appointments, missing VP Data and Head of AI hires.

**Solution**: This requires code changes in `score_ai_maturity()` to check additional fields:

```python
# In firmographics, add:
vp_data_name: str = firmographics.get("vp_data_name", "")
vp_data_tenure: int | None = firmographics.get("vp_data_tenure_days")
head_of_ai_name: str = firmographics.get("head_of_ai_name", "")
head_of_ai_tenure: int | None = firmographics.get("head_of_ai_tenure_days")

# Then check:
if (cto_name and cto_tenure <= tenure_threshold) or \
   (vp_data_name and vp_data_tenure <= tenure_threshold) or \
   (head_of_ai_name and head_of_ai_tenure <= tenure_threshold):
    # Leadership signal detected
```

### Example 5: Adjust Confidence Thresholds

**Problem**: Probe results show too many false positives at 0.60 confidence threshold.

**Solution**: Increase medium confidence threshold:

```json
{
  "confidence_rules": {
    "high": {"threshold": 0.85},
    "medium_high": {"threshold": 0.75},
    "medium": {"threshold": 0.70},
    "fallback": 0.30
  }
}
```

This will make the scorer more conservative — fewer prospects will qualify for capability_gap segment.

## Testing Configuration Changes

After editing `ai_maturity_config.json`, test with synthetic prospects:

```python
from agent.core.enrichment import score_ai_maturity

# Test case 1: High AI maturity (3+ roles, new CTO)
job_signals = {
    "ai_roles": ["ML Engineer", "Data Scientist", "AI Platform Lead"],
    "open_roles": 10
}
firmographics = {
    "description": "AI-powered platform for enterprise workflows",
    "industry": "artificial intelligence",
    "recent_news": "CEO announces new AI strategy",
    "cto_name": "Jane Doe",
    "cto_tenure_days": 30
}

result = score_ai_maturity(job_signals, firmographics)
print(f"Score: {result['score']}, Confidence: {result['confidence']}")
# Expected: Score: 3, Confidence: 0.85+

# Test case 2: Low AI maturity (marketing language only)
job_signals = {"ai_roles": [], "open_roles": 5}
firmographics = {
    "description": "We use AI-powered insights to help customers",
    "industry": "software",
    "recent_news": "",
    "cto_name": "",
    "cto_tenure_days": None
}

result = score_ai_maturity(job_signals, firmographics)
print(f"Score: {result['score']}, Confidence: {result['confidence']}")
# Expected: Score: 0 or 1, Confidence: 0.30-0.40
```

## Monitoring Configuration Impact

Track these metrics in Langfuse after config changes:

1. **AI maturity score distribution**: How many prospects score 0, 1, 2, 3?
2. **Capability_gap segment rate**: % of prospects classified as capability_gap (requires score >= 2)
3. **False positive rate**: Prospects scored 2-3 who don't actually have AI capability (from probe results)
4. **False negative rate**: Prospects scored 0-1 who actually have strong AI teams (silent companies)

## Configuration Validation

The scorer includes fallback logic if config file is missing or malformed:

```python
def _load_ai_maturity_config() -> dict[str, Any]:
    """Load AI maturity scoring configuration from config file."""
    config_path = Path(__file__).parent.parent / "config" / "ai_maturity_config.json"
    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        # Fallback to hardcoded defaults if config missing
        log_trace("ai_maturity_config_load_failed", {"error": str(e)})
        return _get_default_ai_maturity_config()
```

If config load fails, a Langfuse trace event `ai_maturity_config_load_failed` is logged and hardcoded defaults are used.

## Best Practices

1. **Version control**: Commit `ai_maturity_config.json` changes with descriptive messages explaining the tuning rationale.

2. **A/B testing**: Keep a backup of the current config before making changes. Run both configs on the same prospect set to compare results.

3. **Incremental tuning**: Change one parameter at a time (e.g., add one keyword, adjust one threshold) to isolate impact.

4. **Document tuning decisions**: Use the `tuning_notes` section in the config file to explain why changes were made.

5. **Monitor for drift**: AI/ML terminology evolves quickly. Review keywords quarterly and add new terms (e.g., "transformer", "diffusion model", "RAG").

6. **Probe-driven tuning**: Use probe results (P-023, P-024 in `probes/probe_library.md`) to identify false positives/negatives and adjust accordingly.

## Related Files

- **Config**: `agent/config/ai_maturity_config.json`
- **Implementation**: `agent/core/enrichment.py::score_ai_maturity()`
- **Schema**: `schemas/enrichment_output.schema.json` (ai_maturity field)
- **Probes**: `probes/probe_library.md` (P-023: false positive, P-024: false negative)
- **ICP Definition**: `seed/icp_definition.md` (capability_gap segment requires score >= 2)

## Changelog

| Date | Change | Rationale |
|------|--------|-----------|
| 2026-04-25 | Externalized all keywords and thresholds to config file | Enable tuning without code changes |
| 2026-04-25 | Added fallback config if file missing | Prevent scorer from breaking if config deleted |
| 2026-04-25 | Added `tuning_notes` section to config | Document common tuning scenarios |
