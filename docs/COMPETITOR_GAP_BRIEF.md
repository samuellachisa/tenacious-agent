# Competitor Gap Brief

The competitor gap brief converts vendor outreach from a generic pitch into a research finding by comparing the prospect's AI maturity against sector peers.

## Schema

The brief follows the JSON schema defined in `schemas/competitor_gap_brief.schema.json`. See `schemas/sample_competitor_gap_brief.json` for a complete example.

## Peer Sampling Strategy

### Source Data
Peers are sampled from the Crunchbase dataset (`data/crunchbase-companies.csv`) using the following logic:

### Sampling Algorithm

1. **Sector Matching** (Primary)
   - Extract category keywords from prospect's `category_list` field
   - Find companies sharing at least one category keyword
   - Example: "Business Intelligence | Analytics" matches "Analytics | SaaS"

2. **Fallback** (If no sector matches)
   - Use all other companies in the dataset
   - Ensures minimum peer sample size for comparison

3. **Sample Size**
   - Target: 5-10 peer companies
   - Implementation: `peers[:10]` in `build_competitor_gap_brief()`

### Peer Scoring

Each peer is scored on the same AI maturity rubric (0-3) using:
- Open AI/ML roles from `open_roles` field
- Leadership signals from `cto_name` and `cto_tenure_days`
- Industry classification keywords
- Recent news mentions of AI/ML

### Top Quartile Calculation

```python
top_quartile_score = _percentile(scores_only, 75)
```

Peers with `ai_maturity_score >= top_quartile_score` are marked as top quartile.

## Gap Finding Logic

The brief identifies 2-3 specific practices where top-quartile peers show public signal that the prospect does not:

1. **Dedicated AI Leadership** - Named VP/Head of AI role
2. **Active AI/ML Hiring** - 3+ open AI/ML roles
3. **Public AI Commentary** - Technical blog posts or executive statements

Each gap requires:
- At least 2 peer examples with source URLs
- Specific evidence (not generic claims)
- Confidence rating (high/medium/low)

## Quality Self-Check

Every brief includes a `gap_quality_self_check` section:

```json
{
  "all_peer_evidence_has_source_url": true,
  "at_least_one_gap_high_confidence": true,
  "prospect_silent_but_sophisticated_risk": false
}
```

This forces the agent to respect evidence quality when composing outreach.

## Production Considerations

### Current Implementation (File-Based)
- Static Crunchbase snapshot in `data/crunchbase-companies.csv`
- Peer sampling happens at enrichment time
- No caching of peer scores

### Production Recommendations

1. **Live Crunchbase API Integration**
   - Replace file-based lookup with Crunchbase API calls
   - Filter by `category_groups` and `employee_count` for better peer matching
   - Cache API responses to reduce latency

2. **Peer Score Caching**
   - Store pre-computed AI maturity scores for common companies
   - Refresh scores weekly or on-demand
   - Reduces enrichment pipeline latency from ~200ms to <50ms

3. **Enhanced Sector Matching**
   - Use Crunchbase `category_groups` (broader) + `categories` (specific)
   - Add headcount band filtering (±50% of prospect size)
   - Consider funding stage similarity (Series A vs Series C)

4. **Source URL Verification**
   - Validate that source URLs return 200 status
   - Fall back to archive.org for dead links
   - Flag low-confidence gaps when sources are unavailable

## Example Output

See `data/briefs/test_gap_brief.json` for a real enrichment pipeline output, or `schemas/sample_competitor_gap_brief.json` for a high-quality example with full peer evidence.
