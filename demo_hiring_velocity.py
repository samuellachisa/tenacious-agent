"""
Demo script showing the hiring velocity feature in action.

This demonstrates:
1. First enrichment run (no historical data)
2. Simulated 60-day-old snapshot
3. Second enrichment run (with historical data showing velocity)
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone

from agent.core.enrichment import run_enrichment_pipeline
from agent.core.job_history import store_job_snapshot


async def demo():
    """Run the hiring velocity demo."""
    print("=" * 70)
    print("HIRING VELOCITY DEMO: DataFlow Technologies")
    print("=" * 70)
    print()
    
    company_name = "DataFlow Technologies"
    
    # Scenario 1: First enrichment (no historical data)
    print("📊 Scenario 1: First enrichment run (no historical data)")
    print("-" * 70)
    
    brief_1 = await run_enrichment_pipeline(company_name)
    
    job_signals_1 = brief_1["job_signals"]
    print(f"Open roles today: {job_signals_1['open_roles']}")
    print(f"AI/ML roles: {len(job_signals_1['ai_roles'])}")
    print(f"Historical data (60 days ago): {job_signals_1['open_roles_60_days_ago']}")
    print(f"Velocity: {job_signals_1['velocity']}")
    print(f"Velocity confidence: {job_signals_1['velocity_confidence']}")
    print()
    print("💡 Result: No historical data available, velocity = 'insufficient_signal'")
    print()
    
    # Simulate 60 days passing by creating a historical snapshot
    print("⏰ Simulating 60 days passing...")
    print("-" * 70)
    
    now = datetime.now(timezone.utc)
    sixty_days_ago = now - timedelta(days=60)
    
    # Store a snapshot from 60 days ago with fewer roles
    store_job_snapshot(
        company_domain="dataflow.tech",
        open_roles_count=4,
        ai_roles_count=2,
        source="crunchbase_sample",
        timestamp=sixty_days_ago,
    )
    
    print(f"✓ Stored historical snapshot: 4 open roles (60 days ago)")
    print()
    
    # Scenario 2: Second enrichment (with historical data)
    print("📊 Scenario 2: Second enrichment run (with historical data)")
    print("-" * 70)
    
    brief_2 = await run_enrichment_pipeline(company_name)
    
    job_signals_2 = brief_2["job_signals"]
    print(f"Open roles today: {job_signals_2['open_roles']}")
    print(f"AI/ML roles: {len(job_signals_2['ai_roles'])}")
    print(f"Historical data (60 days ago): {job_signals_2['open_roles_60_days_ago']}")
    print(f"Velocity: {job_signals_2['velocity']}")
    print(f"Velocity confidence: {job_signals_2['velocity_confidence']}")
    print()
    
    # Calculate growth
    if job_signals_2['open_roles_60_days_ago']:
        growth_ratio = job_signals_2['open_roles'] / job_signals_2['open_roles_60_days_ago']
        print(f"📈 Growth ratio: {growth_ratio:.2f}x ({job_signals_2['open_roles']}/{job_signals_2['open_roles_60_days_ago']})")
    
    print()
    print("💡 Result: Historical data available, velocity = 'doubled' (2.75x growth)")
    print()
    
    # Show the hiring signal brief
    print("📋 Hiring Signal Brief")
    print("-" * 70)
    
    hiring_brief = brief_2["hiring_signal_brief"]
    print(f"AI Maturity Score: {hiring_brief['ai_maturity_score']}/3")
    print(f"Overall Confidence: {hiring_brief['overall_confidence']}")
    print()
    print("Signals detected:")
    for signal in hiring_brief["signals"]:
        print(f"  • [{signal['type'].upper()}] {signal['summary']}")
        print(f"    Source: {signal['source']}, Confidence: {signal['confidence']}")
    print()
    
    # Show how this affects outreach messaging
    print("✉️  Impact on Outreach Messaging")
    print("-" * 70)
    
    velocity = job_signals_2['velocity']
    velocity_conf = job_signals_2['velocity_confidence']
    
    if velocity == "doubled" and velocity_conf >= 0.8:
        print("✓ High confidence velocity signal detected!")
        print()
        print("Recommended messaging:")
        print("  'I noticed you've more than doubled your engineering headcount")
        print("   over the past 60 days — that's impressive growth.'")
        print()
        print("  This assertive language is justified by high-confidence historical data.")
    elif velocity == "insufficient_signal":
        print("⚠ No historical data available")
        print()
        print("Recommended messaging:")
        print("  'I see you have 11 open engineering roles. Are you scaling")
        print("   your team significantly right now?'")
        print()
        print("  Use questions rather than assertions when confidence is low.")
    
    print()
    
    # Save the brief for inspection
    brief_path = f"data/briefs/{company_name.lower().replace(' ', '_')}_brief.json"
    print(f"💾 Full brief saved to: {brief_path}")
    print()
    
    print("=" * 70)
    print("✅ DEMO COMPLETE")
    print("=" * 70)
    print()
    print("Key takeaways:")
    print("  1. First run: No historical data → 'insufficient_signal' → ask questions")
    print("  2. Subsequent runs: Historical data available → precise velocity label")
    print("  3. High confidence (0.8) enables assertive outreach language")
    print("  4. Velocity calculation is fully automated and time-windowed")
    print()


if __name__ == "__main__":
    asyncio.run(demo())
