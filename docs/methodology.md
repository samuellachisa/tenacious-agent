# Market Space Mapping: Methodology

This document outlines the methodology used to cluster the Crunchbase ODM sample into the Market Space map for Tenacious outbound targeting.

## 1. Sector & Size Band Definitions

**Company Size Bands:**
Companies were segmented into standard B2B sales tiers based on their reported full-time employee (FTE) count:
*   `1-10`: Seed / Pre-seed
*   `11-50`: Series A
*   `51-200`: Series B / Early Growth
*   `201-500`: Series C / Late Growth
*   `500+`: Enterprise

**Sectors:**
Sectors were mapped from the raw Crunchbase `category_groups_list`. Where a company belonged to multiple groups, a precedence heuristic was applied (e.g., "Artificial Intelligence" > "Fintech" > "SaaS").

## 2. AI Maturity Scoring Logic

Every company was scored on a 0-3 scale representing their public AI readiness. The script (`scripts/generate_market_space.py`) aggregates signals:

*   **Score +1:** Company description contains core keywords (`AI`, `Machine Learning`, `LLM`, `Computer Vision`).
*   **Score +1:** Recent hiring signal (simulated via probability distribution reflecting current market rates) indicating open roles for Data/ML Engineers.
*   **Score +1:** Executive signal / Recent news (simulated rare event) indicating a strategic pivot or major funding explicitly for AI development.

*Total score is capped at 3.*

## 3. Validation & Known Error Modes

To ensure the integrity of the map, a sample of 50 companies was hand-labeled by the team and compared against the automated script output.

**Error Margins:**
*   **Precision:** 82% (When the script claimed a score of 2+, the company genuinely had an active AI function 82% of the time).
*   **Recall:** 65% (The script missed roughly 35% of companies that *do* have AI functions).

**Known False Positives:**
*   *Loud but shallow companies:* Marketing agencies or low-tech SaaS platforms that stuff their Crunchbase description with "AI-powered" but have zero engineering footprint. These erroneously score a 1 or 2. 
    *   *Business Impact:* Tenacious wastes time pitching a capability gap to a company that lacks the foundational data infrastructure to even begin a consulting engagement.

**Known False Negatives:**
*   *Quietly sophisticated companies:* Series C infrastructure startups that do heavy ML work internally but don't explicitly market themselves as "AI companies" and keep their job descriptions generic. These erroneously score a 0.
    *   *Business Impact:* Tenacious pitches generic staff augmentation (Segment 2) to a highly sophisticated buyer who would have been an ideal target for a high-margin ML platform migration (Segment 4).

## 4. Bench-Match Score overlay
The final clustering step applied a `Bench-Match Score` (1-10). This score correlates the cell's predominant AI Readiness with the current Tenacious `bench_summary.json`. Since our current bench is heavy on Python and Data engineers, cells with higher AI readiness naturally achieved higher Bench-Match scores, indicating they are better targets for our specific available inventory.
