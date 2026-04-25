"""
Demo: Competitor Gap Brief Generation

Demonstrates the competitor gap brief module with real examples from the
Crunchbase sample dataset.
"""

import asyncio
import json
from pathlib import Path

from agent.core.enrichment import (
    get_crunchbase_firmographics,
    score_ai_maturity,
    build_competitor_gap_brief,
)


async def demo_competitor_gap_brief():
    """Run competitor gap brief demo with sample companies."""
    
    print("=" * 80)
    print("COMPETITOR GAP BRIEF DEMO")
    print("=" * 80)
    print()
    
    # Load sample companies from Crunchbase
    crunchbase_path = Path("data/crunchbase_sample.json")
    with open(crunchbase_path, "r", encoding="utf-8") as fh:
        companies = json.load(fh)
    
    # Demo with first 3 companies
    demo_companies = companies[:3]
    
    for i, company_data in enumerate(demo_companies, 1):
        company_name = company_data.get("name", "Unknown")
        
        print(f"\n{'─' * 80}")
        print(f"EXAMPLE {i}: {company_name}")
        print(f"{'─' * 80}\n")
        
        # Get firmographics
        firmographics = get_crunchbase_firmographics(company_name)
        
        print(f"Industry: {firmographics.get('industry', 'Unknown')}")
        print(f"Employee Count: {firmographics.get('employee_count', 0)}")
        print(f"Website: {firmographics.get('website', 'N/A')}")
        print()
        
        # Score AI maturity
        job_signals = {
            "open_roles": len(firmographics.get("open_roles_raw", [])),
            "ai_roles": [
                r for r in firmographics.get("open_roles_raw", [])
                if any(kw in r.lower() for kw in {"ai", "ml", "machine learning", "data scientist"})
            ],
        }
        
        ai_maturity = score_ai_maturity(job_signals, firmographics)
        
        print(f"AI Maturity Score: {ai_maturity['score']}/3")
        print(f"Confidence: {ai_maturity['confidence']:.2f}")
        print(f"Justification:")
        for j in ai_maturity.get("justification", [])[:3]:
            print(f"  • {j}")
        print()
        
        # Build competitor gap brief
        competitor_gap = build_competitor_gap_brief(
            company_name=company_name,
            firmographics=firmographics,
            ai_maturity=ai_maturity,
        )
        
        print(f"Sector: {competitor_gap['prospect_sector']}")
        print(f"Peers Analyzed: {competitor_gap['peers_analyzed']}")
        print(f"Sector Top Quartile Benchmark: {competitor_gap['sector_top_quartile_benchmark']:.2f}")
        print(f"Brief Confidence: {competitor_gap['confidence']}")
        print(f"Sparse Sector: {competitor_gap.get('sparse_sector', False)}")
        print()
        
        # Show gap findings
        print("Gap Findings:")
        for gap_idx, gap in enumerate(competitor_gap.get("gap_findings", []), 1):
            print(f"\n  Gap {gap_idx}: {gap['practice']}")
            print(f"  Confidence: {gap['confidence']}")
            print(f"  Prospect State: {gap['prospect_state'][:100]}...")
            print(f"  Peer Evidence ({len(gap['peer_evidence'])} examples):")
            for ev in gap['peer_evidence'][:2]:
                print(f"    • {ev['competitor_name']}: {ev['evidence'][:80]}...")
                print(f"      Source: {ev['source_url']}")
        
        print()
        print("Suggested Pitch Shift:")
        print(f"  {competitor_gap['suggested_pitch_shift'][:200]}...")
        print()
        
        # Quality self-check
        quality = competitor_gap.get("gap_quality_self_check", {})
        print("Quality Self-Check:")
        print(f"  ✓ All peer evidence has source URL: {quality.get('all_peer_evidence_has_source_url', False)}")
        print(f"  ✓ At least one high-confidence gap: {quality.get('at_least_one_gap_high_confidence', False)}")
        print(f"  ⚠ Silent-but-sophisticated risk: {quality.get('prospect_silent_but_sophisticated_risk', False)}")
        print()
        
        # Save brief to file
        output_dir = Path("data/briefs")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        safe_name = company_name.lower().replace(" ", "_").replace("/", "_")
        output_path = output_dir / f"{safe_name}_competitor_gap_brief.json"
        
        with open(output_path, "w", encoding="utf-8") as fh:
            json.dump(competitor_gap, fh, indent=2, default=str)
        
        print(f"Brief saved to: {output_path}")
    
    print()
    print("=" * 80)
    print("DEMO COMPLETE")
    print("=" * 80)
    print()
    print("Key Observations:")
    print("  • Competitor gap briefs provide evidence-backed competitive intelligence")
    print("  • Each gap finding includes 2+ peer examples with source URLs")
    print("  • Quality self-check ensures brief reliability before outreach")
    print("  • Sparse sector detection prevents over-claiming with limited data")
    print("  • Pitch guidance adapts to gap confidence and sector context")
    print()


if __name__ == "__main__":
    asyncio.run(demo_competitor_gap_brief())
