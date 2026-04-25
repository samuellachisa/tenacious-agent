# Web Scraping Policy and Implementation

## Overview

The enrichment pipeline includes a Playwright-based web scraper for collecting job posting signals from company career pages. This document describes the ethical scraping practices and technical implementation.

## Ethical Scraping Principles

### 1. Robots.txt Compliance

The scraper respects `robots.txt` directives before accessing any page:

- Fetches and parses `/robots.txt` for each domain
- Checks if the target path is allowed for our user agent
- Skips scraping if disallowed by robots.txt
- Fails open (allows scraping) if robots.txt is unavailable or malformed

**Implementation:** `_check_robots_txt()` in `agent/core/enrichment.py`

```python
async def _check_robots_txt(website: str, path: str) -> bool:
    """
    Check if the given path is allowed by robots.txt.
    Returns True if allowed (or if robots.txt doesn't exist), False if disallowed.
    """
```

### 2. Public Page Access Only

The scraper only accesses publicly available pages:

- Checks HTTP response status codes
- Skips pages with 4xx/5xx errors (auth required, not found, etc.)
- Does not attempt to bypass authentication or paywalls
- Does not submit forms or interact with dynamic content

### 3. Respectful User Agent

The scraper identifies itself with a descriptive user agent:

```
Mozilla/5.0 (compatible; TenaciousBot/1.0; +https://tenacious-training.dev/bot)
```

This allows website administrators to:
- Identify our bot in their logs
- Contact us if there are concerns
- Block our bot specifically if needed

### 4. Rate Limiting and Timeouts

- 8-second timeout per page load
- Single request per company (tries `/careers` then `/jobs`)
- No concurrent requests to the same domain
- Headless browser mode to minimize resource usage

## Technical Implementation

### Scraping Flow

1. **Pre-flight Check:**
   ```python
   # Check robots.txt for each path
   allowed_urls = []
   for path in ["/careers", "/jobs"]:
       if await _check_robots_txt(website, path):
           allowed_urls.append(website + path)
   ```

2. **Page Access:**
   ```python
   # Set user agent
   await page.set_extra_http_headers({
       "User-Agent": "Mozilla/5.0 (compatible; TenaciousBot/1.0; ...)"
   })
   
   # Check response status
   response = await page.goto(url, timeout=8000)
   if response and response.status >= 400:
       continue  # Skip non-public pages
   ```

3. **Content Extraction:**
   - Extracts text from common job listing selectors
   - Limits to 20 elements per selector
   - Caps total results at 30 roles
   - Filters out overly long text (>100 chars)

### Fallback Behavior

If scraping fails or is disallowed:
- Falls back to Crunchbase sample data
- Sets `source: "crunchbase_sample"` with lower confidence (0.6)
- No error thrown - graceful degradation

## Signal Metadata

All scraped signals include:

- `source`: "playwright_scrape" (live data) or "crunchbase_sample" (fallback)
- `timestamp`: ISO 8601 timestamp when signal was collected
- `confidence`: 0.9 for live scrape, 0.6 for static fallback

Example:
```json
{
  "open_roles": 12,
  "ai_roles": ["ML Engineer", "AI Product Manager"],
  "velocity": "high",
  "source": "playwright_scrape",
  "confidence": 0.9,
  "timestamp": "2026-04-25T10:30:00Z"
}
```

## Monitoring and Compliance

### Logging

All scraping attempts are logged via Langfuse:
- Success/failure status
- Source used (playwright vs crunchbase)
- Robots.txt check results
- Response status codes

### Opt-Out Mechanism

Website administrators can opt out by:

1. **Robots.txt:** Add to `/robots.txt`:
   ```
   User-agent: TenaciousBot
   Disallow: /careers
   Disallow: /jobs
   ```

2. **Contact:** Email [contact@tenacious-training.dev] to request removal

3. **IP Blocking:** Block our scraper's IP range (provided on request)

## Future Enhancements

1. **Sitemap Support:** Parse XML sitemaps for job posting URLs
2. **Structured Data:** Extract JSON-LD job posting markup
3. **Caching:** Cache robots.txt responses for 24 hours
4. **Retry Logic:** Exponential backoff for transient failures
5. **Proxy Rotation:** Distribute load across multiple IPs

## References

- RFC 9309: Robots Exclusion Protocol
- Schema.org JobPosting vocabulary
- Web Scraping Best Practices (IETF)
- Implementation: `agent/core/enrichment.py:_check_robots_txt()`
- Implementation: `agent/core/enrichment.py:_scrape_careers_page()`
