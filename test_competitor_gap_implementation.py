"""
Test: Competitor Gap Brief Implementation

Validates that the competitor gap brief module is properly integrated
and produces schema-compliant output.
"""

import asyncio
import json
from pathlib import Path

from agent.core.enrichment import (
    get_crunchbase_firmographics,
    score_ai_maturity,
    build_competitor_gap_brief,
    run_enrichment_pipeline,
)


def test_competitor_gap_schema_compliance():
    """Test that competitor gap brief output matches schema."""
    print("Testing competitor gap brief schema compliance...")
    
    # Load schema
    schema_path = Path("schemas/competitor_gap_brief.schema.json")
    with open(schema_path, "r", encoding="utf-8") as fh:
        schema = json.load(fh)
    
    required_fields = schema.get("required", [])
    print(f"  Required fields: {', '.join(required_fields)}")
    
    # Generate a brief
    company_name = "Test Company"
    firmographics = get_crunchbase_firmographics(company_name)
    
    job_signals = {
        "open_roles": len(firmographics.get("open_roles_raw", [])),
        "ai_roles": [],
    }
    
    ai_maturity = score_ai_maturity(job_signals, firmographics)
    competitor_gap = build_competitor_gap_brief(company_name, firmographics, ai_maturity)
    
    # Validate required fields
    missing_fields = [f for f in required_fields if f not in competitor_gap]
    if missing_fields:
        print(f"  ❌ FAIL: Missing required fields: {missing_fields}")
        return False
    
    print(f"  ✓ All required fields present")
    
    # Validate competitors_analyzed structure
    competitors = competitor_gap.get("competitors_analyzed", [])
    if not competitors:
        print(f"  ⚠ WARNING: No competitors analyzed (empty dataset?)")
    else:
        print(f"  ✓ Analyzed {len(competitors)} competitors")
        
        # Check first competitor has required fields
        first_comp = competitors[0]
        comp_required = ["name", "domain", "ai_maturity_score", "ai_maturity_justification", "headcount_band"]
        comp_missing = [f for f in comp_required if f not in first_comp]
        if comp_missing:
            print(f"  ❌ FAIL: Competitor missing fields: {comp_missing}")
            return False
        print(f"  ✓ Competitor structure valid")
    
    # Validate gap_findings structure
    gap_findings = competitor_gap.get("gap_findings", [])
    if not gap_findings:
        print(f"  ❌ FAIL: No gap findings (schema requires minItems: 1)")
        return False
    
    print(f"  ✓ Found {len(gap_findings)} gap finding(s)")
    
    # Check first gap has required fields and peer evidence
    first_gap = gap_findings[0]
    gap_required = ["practice", "peer_evidence", "prospect_state", "confidence"]
    gap_missing = [f for f in gap_required if f not in first_gap]
    if gap_missing:
        print(f"  ❌ FAIL: Gap finding missing fields: {gap_missing}")
        return False
    
    peer_evidence = first_gap.get("peer_evidence", [])
    if len(peer_evidence) < 2:
        print(f"  ❌ FAIL: Gap finding has {len(peer_evidence)} peer evidence (schema requires minItems: 2)")
        return False
    
    print(f"  ✓ Gap finding structure valid ({len(peer_evidence)} peer examples)")
    
    # Validate all peer evidence has source URLs
    for i, evidence in enumerate(peer_evidence):
        if not evidence.get("source_url"):
            print(f"  ❌ FAIL: Peer evidence {i} missing source_url")
            return False
    
    print(f"  ✓ All peer evidence has source URLs")
    
    # Validate quality self-check
    quality_check = competitor_gap.get("gap_quality_self_check", {})
    if not quality_check:
        print(f"  ⚠ WARNING: No quality self-check present")
    else:
        print(f"  ✓ Quality self-check present")
        print(f"    - All peer evidence has source URL: {quality_check.get('all_peer_evidence_has_source_url', False)}")
        print(f"    - At least one high-confidence gap: {quality_check.get('at_least_one_gap_high_confidence', False)}")
        print(f"    - Silent-but-sophisticated risk: {quality_check.get('prospect_silent_but_sophisticated_risk', False)}")
    
    print(f"\n✅ PASS: Competitor gap brief is schema-compliant")
    return True


async def test_enrichment_pipeline_integration():
    """Test that competitor gap brief is included in enrichment pipeline."""
    print("\nTesting enrichment pipeline integration...")
    
    # Run enrichment pipeline
    company_name = "Test Company"
    brief = await run_enrichment_pipeline(company_name)
    
    # Check competitor_gap is present
    if "competitor_gap" not in brief:
        print(f"  ❌ FAIL: competitor_gap not in enrichment brief")
        return False
    
    print(f"  ✓ competitor_gap present in enrichment brief")
    
    # Check it has expected structure
    competitor_gap = brief["competitor_gap"]
    if not competitor_gap.get("competitors_analyzed"):
        print(f"  ⚠ WARNING: No competitors analyzed")
    else:
        print(f"  ✓ Competitors analyzed: {len(competitor_gap['competitors_analyzed'])}")
    
    if not competitor_gap.get("gap_findings"):
        print(f"  ❌ FAIL: No gap findings")
        return False
    
    print(f"  ✓ Gap findings: {len(competitor_gap['gap_findings'])}")
    
    # Check brief is saved to file
    safe_name = company_name.lower().replace(" ", "_").replace("/", "_")
    brief_path = Path("data/briefs") / f"{safe_name}_brief.json"
    
    if not brief_path.exists():
        print(f"  ❌ FAIL: Brief not saved to {brief_path}")
        return False
    
    print(f"  ✓ Brief saved to {brief_path}")
    
    # Validate saved brief has competitor_gap
    with open(brief_path, "r", encoding="utf-8") as fh:
        saved_brief = json.load(fh)
    
    if "competitor_gap" not in saved_brief:
        print(f"  ❌ FAIL: Saved brief missing competitor_gap")
        return False
    
    print(f"  ✓ Saved brief includes competitor_gap")
    
    print(f"\n✅ PASS: Enrichment pipeline integration working")
    return True


def test_failure_taxonomy_aggregation():
    """Test that failure taxonomy aggregation is complete."""
    print("\nTesting failure taxonomy aggregation...")
    
    # Load aggregated taxonomy
    taxonomy_path = Path("probes/failure_taxonomy_aggregated.json")
    if not taxonomy_path.exists():
        print(f"  ❌ FAIL: {taxonomy_path} not found")
        return False
    
    with open(taxonomy_path, "r", encoding="utf-8") as fh:
        taxonomy = json.load(fh)
    
    print(f"  ✓ Taxonomy file loaded")
    
    # Validate structure
    if "categories" not in taxonomy:
        print(f"  ❌ FAIL: No categories in taxonomy")
        return False
    
    categories = taxonomy["categories"]
    print(f"  ✓ Found {len(categories)} categories")
    
    # Check each category has required fields
    required_fields = [
        "category", "description", "probes", "probe_count",
        "avg_trigger_rate", "avg_business_cost_usd",
        "expected_loss_per_100_leads", "ranking", "severity",
        "root_cause", "fix_implemented", "fix_location",
        "business_impact"
    ]
    
    for cat in categories:
        missing = [f for f in required_fields if f not in cat]
        if missing:
            print(f"  ❌ FAIL: Category {cat.get('category', 'unknown')} missing: {missing}")
            return False
    
    print(f"  ✓ All categories have required fields")
    
    # Validate summary statistics
    summary = taxonomy.get("summary_statistics", {})
    if not summary:
        print(f"  ❌ FAIL: No summary statistics")
        return False
    
    print(f"  ✓ Summary statistics present")
    print(f"    - Total probes: {summary.get('total_probes', 0)}")
    print(f"    - Total categories: {summary.get('total_categories', 0)}")
    print(f"    - Total expected loss per 100 leads: ${summary.get('total_expected_loss_per_100_leads', 0)}")
    print(f"    - Top 3 categories: {', '.join(summary.get('top_3_categories_by_loss', []))}")
    
    # Validate economic context
    economic = taxonomy.get("economic_context", {})
    if not economic:
        print(f"  ❌ FAIL: No economic context")
        return False
    
    print(f"  ✓ Economic context present")
    print(f"    - Avg engagement ACV: ${economic.get('avg_engagement_acv_talent', 0):,}")
    print(f"    - Expected pipeline value per lead: ${economic.get('expected_pipeline_value_per_qualified_lead', 0):,}")
    
    print(f"\n✅ PASS: Failure taxonomy aggregation complete")
    return True


async def main():
    """Run all tests."""
    print("=" * 80)
    print("COMPETITOR GAP BRIEF & FAILURE TAXONOMY VALIDATION")
    print("=" * 80)
    print()
    
    results = []
    
    # Test 1: Schema compliance
    results.append(("Schema Compliance", test_competitor_gap_schema_compliance()))
    
    # Test 2: Pipeline integration
    results.append(("Pipeline Integration", await test_enrichment_pipeline_integration()))
    
    # Test 3: Taxonomy aggregation
    results.append(("Taxonomy Aggregation", test_failure_taxonomy_aggregation()))
    
    # Summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print()
    
    for test_name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    all_passed = all(passed for _, passed in results)
    
    print()
    if all_passed:
        print("🎉 ALL TESTS PASSED")
        print()
        print("Next steps:")
        print("  1. Run: python demo_competitor_gap_brief.py")
        print("  2. Review: data/briefs/*_competitor_gap_brief.json")
        print("  3. Read: docs/IMPLEMENTATION_SUMMARY.md")
    else:
        print("⚠️ SOME TESTS FAILED")
        print()
        print("Review the output above for details.")
    
    print()
    return all_passed


if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)
