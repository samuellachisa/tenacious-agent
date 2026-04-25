"""
Test script to verify signal metadata (source, timestamp, confidence) implementation.
"""
import asyncio
import json
from datetime import datetime
from agent.core.enrichment import (
    get_crunchbase_firmographics,
    get_funding_event,
    get_layoff_signal,
    get_job_post_signals,
    get_leadership_change,
    score_ai_maturity,
    _build_hiring_signal_brief,
)


async def test_signal_metadata():
    """Test that all signals carry source, timestamp, and confidence metadata."""
    
    # Test with a sample company
    company_name = "DataFlow Technologies"
    
    # Get firmographics
    firmographics = get_crunchbase_firmographics(company_name)
    print(f"\n=== Testing {company_name} ===\n")
    
    # Test funding event
    funding_event = get_funding_event(company_name, firmographics)
    if funding_event:
        print("✓ Funding Event:")
        print(f"  - Source: {funding_event.get('source', 'MISSING')}")
        print(f"  - Timestamp: {funding_event.get('timestamp', 'MISSING')}")
        print(f"  - Confidence: {funding_event.get('confidence', 'MISSING')}")
        assert 'source' in funding_event, "Funding event missing 'source'"
        assert 'timestamp' in funding_event, "Funding event missing 'timestamp'"
        assert 'confidence' in funding_event, "Funding event missing 'confidence'"
    else:
        print("✗ No funding event found")
    
    # Test layoff signal
    layoff_signal = get_layoff_signal(company_name)
    if layoff_signal:
        print("\n✓ Layoff Signal:")
        print(f"  - Source: {layoff_signal.get('source', 'MISSING')}")
        print(f"  - Timestamp: {layoff_signal.get('timestamp', 'MISSING')}")
        print(f"  - Confidence: {layoff_signal.get('confidence', 'MISSING')}")
        assert 'source' in layoff_signal, "Layoff signal missing 'source'"
        assert 'timestamp' in layoff_signal, "Layoff signal missing 'timestamp'"
        assert 'confidence' in layoff_signal, "Layoff signal missing 'confidence'"
    else:
        print("\n✗ No layoff signal found")
    
    # Test job signals
    job_signals = await get_job_post_signals(company_name, firmographics)
    print("\n✓ Job Signals:")
    print(f"  - Source: {job_signals.get('source', 'MISSING')}")
    print(f"  - Timestamp: {job_signals.get('timestamp', 'MISSING')}")
    print(f"  - Confidence: {job_signals.get('confidence', 'MISSING')}")
    assert 'source' in job_signals, "Job signals missing 'source'"
    assert 'timestamp' in job_signals, "Job signals missing 'timestamp'"
    assert 'confidence' in job_signals, "Job signals missing 'confidence'"
    
    # Test leadership change
    leadership_change = get_leadership_change(company_name, firmographics)
    if leadership_change:
        print("\n✓ Leadership Change:")
        print(f"  - Source: {leadership_change.get('source', 'MISSING')}")
        print(f"  - Timestamp: {leadership_change.get('timestamp', 'MISSING')}")
        print(f"  - Confidence: {leadership_change.get('confidence', 'MISSING')}")
        assert 'source' in leadership_change, "Leadership change missing 'source'"
        assert 'timestamp' in leadership_change, "Leadership change missing 'timestamp'"
        assert 'confidence' in leadership_change, "Leadership change missing 'confidence'"
    else:
        print("\n✗ No leadership change found")
    
    # Test AI maturity
    ai_maturity = score_ai_maturity(job_signals, firmographics)
    print("\n✓ AI Maturity:")
    print(f"  - Source: {ai_maturity.get('source', 'MISSING')}")
    print(f"  - Timestamp: {ai_maturity.get('timestamp', 'MISSING')}")
    print(f"  - Confidence: {ai_maturity.get('confidence', 'MISSING')}")
    assert 'source' in ai_maturity, "AI maturity missing 'source'"
    assert 'timestamp' in ai_maturity, "AI maturity missing 'timestamp'"
    assert 'confidence' in ai_maturity, "AI maturity missing 'confidence'"
    
    # Test hiring signal brief
    brief = _build_hiring_signal_brief(
        firmographics,
        funding_event,
        layoff_signal,
        job_signals,
        leadership_change,
        ai_maturity,
    )
    
    print("\n✓ Hiring Signal Brief:")
    print(f"  - Signals with metadata: {len(brief.get('signals', []))}")
    print(f"  - AI Maturity Source: {brief.get('ai_maturity_source', 'MISSING')}")
    print(f"  - AI Maturity Timestamp: {brief.get('ai_maturity_timestamp', 'MISSING')}")
    
    # Verify structured signals
    assert 'signals' in brief, "Brief missing 'signals' array"
    assert 'ai_maturity_source' in brief, "Brief missing 'ai_maturity_source'"
    assert 'ai_maturity_timestamp' in brief, "Brief missing 'ai_maturity_timestamp'"
    
    for signal in brief.get('signals', []):
        print(f"\n  Signal: {signal.get('type', 'unknown')}")
        print(f"    - Source: {signal.get('source', 'MISSING')}")
        print(f"    - Timestamp: {signal.get('timestamp', 'MISSING')}")
        print(f"    - Confidence: {signal.get('confidence', 'MISSING')}")
        assert 'source' in signal, f"Signal {signal.get('type')} missing 'source'"
        assert 'timestamp' in signal, f"Signal {signal.get('type')} missing 'timestamp'"
        assert 'confidence' in signal, f"Signal {signal.get('type')} missing 'confidence'"
    
    print("\n" + "="*60)
    print("✓ All signals carry source, timestamp, and confidence metadata!")
    print("="*60)
    
    return brief


if __name__ == "__main__":
    asyncio.run(test_signal_metadata())
