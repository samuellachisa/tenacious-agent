"""
ICP qualifier — classifies enriched prospects into one of four segments.

Segments (fixed names):
  recently_funded       — Series A/B in last 180 days
  cost_restructuring    — post-layoff mid-market
  leadership_transition — new CTO/VP Eng < 90 days
  capability_gap        — AI maturity >= 2 ONLY (hard gate)

Hard disqualifiers: consulting, staffing, recruiting, outsourcing firms.
Mixed signal edge case: funding + layoff → recently_funded with reduced confidence.
"""

from __future__ import annotations

from typing import Any

from agent.integrations.langfuse_client import log_trace

# ---------------------------------------------------------------------------
# Hard disqualifier keywords (industry / description)
# ---------------------------------------------------------------------------

DISQUALIFIER_KEYWORDS = {
    "consulting",
    "staffing",
    "recruiting",
    "outsourcing",
    "headhunting",
    "talent acquisition",
    "executive search",
    "managed services",
    "bpo",
    "business process outsourcing",
}

# ---------------------------------------------------------------------------
# ACV estimates per segment (USD)
# ---------------------------------------------------------------------------

SEGMENT_ACV = {
    "recently_funded": 85_000,
    "cost_restructuring": 60_000,
    "leadership_transition": 75_000,
    "capability_gap": 95_000,
}

SEGMENT_DISPLAY_NAMES = {
    "recently_funded": "Recently Funded (Series A/B)",
    "cost_restructuring": "Cost Restructuring (Post-Layoff)",
    "leadership_transition": "Leadership Transition (New CTO/VP Eng)",
    "capability_gap": "Capability Gap (AI Maturity ≥ 2)",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def qualify_prospect(enrichment: dict[str, Any]) -> dict[str, Any]:
    """
    Classify an enriched prospect into an ICP segment.

    Returns:
        qualified (bool)
        segment (str | None)
        segment_name (str)
        confidence (float 0.0–1.0)
        reason (str)
        pitch_language (str)
        acv_estimate (int)
        signals_matched (list[str])
        manual_review (bool)
    """
    company = enrichment.get("company", "Unknown")
    firmographics: dict = enrichment.get("firmographics", {})
    funding_event: dict | None = enrichment.get("funding_event")
    layoff_signal: dict | None = enrichment.get("layoff_signal")
    leadership_change: dict | None = enrichment.get("leadership_change")
    ai_maturity: dict = enrichment.get("ai_maturity", {"score": 0, "confidence": "low"})
    job_signals: dict = enrichment.get("job_signals", {})

    # -----------------------------------------------------------------------
    # Hard disqualification check
    # -----------------------------------------------------------------------
    industry = firmographics.get("industry", "").lower()
    description = firmographics.get("description", "").lower()
    combined_text = f"{industry} {description}"

    for kw in DISQUALIFIER_KEYWORDS:
        if kw in combined_text:
            result = {
                "qualified": False,
                "segment": None,
                "segment_name": "Disqualified",
                "confidence": 0.0,
                "reason": f"Hard disqualifier matched: '{kw}' found in industry/description.",
                "pitch_language": "",
                "acv_estimate": 0,
                "signals_matched": [],
                "manual_review": False,
            }
            log_trace("qualifier_disqualified", {"company": company, "reason": result["reason"]})
            return result

    # -----------------------------------------------------------------------
    # Signal extraction
    # -----------------------------------------------------------------------
    signals_matched: list[str] = []
    manual_review = False

    has_recent_funding = bool(
        funding_event
        and funding_event.get("in_window")
        and funding_event.get("type", "") in {"series_a", "series_b", "seed"}
    )
    has_recent_layoff = bool(layoff_signal and layoff_signal.get("in_window"))
    has_leadership_change = bool(leadership_change and leadership_change.get("in_window"))
    ai_score: int = ai_maturity.get("score", 0)
    ai_confidence: str = ai_maturity.get("confidence", "low")

    if has_recent_funding:
        signals_matched.append(
            f"recent_funding:{funding_event['type']}:{funding_event['days_ago']}d_ago"
        )
    if has_recent_layoff:
        signals_matched.append(
            f"layoff:{layoff_signal['headcount']}hc:{layoff_signal['days_ago']}d_ago"
        )
    if has_leadership_change:
        signals_matched.append(
            f"new_{leadership_change['role'].lower()}:{leadership_change['name']}:{leadership_change['tenure_days']}d"
        )
    if ai_score >= 2:
        signals_matched.append(f"ai_maturity:{ai_score}:{ai_confidence}")

    # -----------------------------------------------------------------------
    # Mixed signal edge case: funding + layoff
    # -----------------------------------------------------------------------
    if has_recent_funding and has_recent_layoff:
        manual_review = True
        confidence = 0.55  # Reduced confidence for mixed signal
        segment = "recently_funded"
        reason = (
            f"Mixed signal: {funding_event['type'].replace('_', ' ').title()} "
            f"({funding_event['days_ago']} days ago) AND layoff of "
            f"{layoff_signal['headcount']} headcount ({layoff_signal['days_ago']} days ago). "
            "Defaulting to recently_funded segment — flagged for manual review."
        )
        pitch_language = build_pitch_language(segment, ai_score, ai_confidence, enrichment)
        result = {
            "qualified": True,
            "segment": segment,
            "segment_name": SEGMENT_DISPLAY_NAMES[segment],
            "confidence": confidence,
            "reason": reason,
            "pitch_language": pitch_language,
            "acv_estimate": SEGMENT_ACV[segment],
            "signals_matched": signals_matched,
            "manual_review": manual_review,
        }
        log_trace("qualifier_mixed_signal", {"company": company, **result})
        return result

    # -----------------------------------------------------------------------
    # Segment priority: recently_funded > leadership_transition >
    #                   cost_restructuring > capability_gap
    # -----------------------------------------------------------------------

    # Segment 1: recently_funded
    if has_recent_funding:
        confidence = _funding_confidence(funding_event)
        segment = "recently_funded"
        reason = (
            f"Series A/B funding detected: {funding_event['type'].replace('_', ' ').title()} "
            f"${funding_event['total_funding_usd']:,} — {funding_event['days_ago']} days ago. "
            "Company is in active growth phase with capital to deploy on talent."
        )
        pitch_language = build_pitch_language(segment, ai_score, ai_confidence, enrichment)
        result = {
            "qualified": True,
            "segment": segment,
            "segment_name": SEGMENT_DISPLAY_NAMES[segment],
            "confidence": confidence,
            "reason": reason,
            "pitch_language": pitch_language,
            "acv_estimate": SEGMENT_ACV[segment],
            "signals_matched": signals_matched,
            "manual_review": False,
        }
        log_trace("qualifier_result", {"company": company, **result})
        return result

    # Segment 3: leadership_transition
    if has_leadership_change:
        confidence = _leadership_confidence(leadership_change)
        segment = "leadership_transition"
        reason = (
            f"New {leadership_change['role']} ({leadership_change['name']}) "
            f"joined {leadership_change['tenure_days']} days ago. "
            "New technical leadership typically drives vendor and team restructuring."
        )
        pitch_language = build_pitch_language(segment, ai_score, ai_confidence, enrichment)
        result = {
            "qualified": True,
            "segment": segment,
            "segment_name": SEGMENT_DISPLAY_NAMES[segment],
            "confidence": confidence,
            "reason": reason,
            "pitch_language": pitch_language,
            "acv_estimate": SEGMENT_ACV[segment],
            "signals_matched": signals_matched,
            "manual_review": False,
        }
        log_trace("qualifier_result", {"company": company, **result})
        return result

    # Segment 2: cost_restructuring
    if has_recent_layoff:
        employee_count = firmographics.get("employee_count", 0)
        # Mid-market gate: 50–1000 employees
        if 50 <= employee_count <= 1000:
            confidence = _layoff_confidence(layoff_signal)
            segment = "cost_restructuring"
            reason = (
                f"Post-layoff mid-market: {layoff_signal['headcount']} headcount reduction "
                f"({layoff_signal['percentage']}%) — {layoff_signal['days_ago']} days ago. "
                "Company is optimising cost structure — outsourced talent is a natural fit."
            )
            pitch_language = build_pitch_language(segment, ai_score, ai_confidence, enrichment)
            result = {
                "qualified": True,
                "segment": segment,
                "segment_name": SEGMENT_DISPLAY_NAMES[segment],
                "confidence": confidence,
                "reason": reason,
                "pitch_language": pitch_language,
                "acv_estimate": SEGMENT_ACV[segment],
                "signals_matched": signals_matched,
                "manual_review": False,
            }
            log_trace("qualifier_result", {"company": company, **result})
            return result

    # Segment 4: capability_gap — HARD GATE: AI maturity >= 2
    if ai_score >= 2:
        confidence = _capability_gap_confidence(ai_maturity, job_signals)
        segment = "capability_gap"
        reason = (
            f"AI maturity score {ai_score}/3 ({ai_confidence} confidence). "
            "Company shows meaningful AI adoption signals but lacks the talent "
            "depth to execute at scale — outsourced AI/ML talent is a direct fit."
        )
        pitch_language = build_pitch_language(segment, ai_score, ai_confidence, enrichment)
        result = {
            "qualified": True,
            "segment": segment,
            "segment_name": SEGMENT_DISPLAY_NAMES[segment],
            "confidence": confidence,
            "reason": reason,
            "pitch_language": pitch_language,
            "acv_estimate": SEGMENT_ACV[segment],
            "signals_matched": signals_matched,
            "manual_review": False,
        }
        log_trace("qualifier_result", {"company": company, **result})
        return result

    # -----------------------------------------------------------------------
    # No qualifying segment matched
    # -----------------------------------------------------------------------
    result = {
        "qualified": False,
        "segment": None,
        "segment_name": "Not Qualified",
        "confidence": 0.0,
        "reason": (
            "No qualifying ICP signals detected. "
            f"Signals checked: funding_in_window={has_recent_funding}, "
            f"layoff_in_window={has_recent_layoff}, "
            f"leadership_change={has_leadership_change}, "
            f"ai_maturity={ai_score}."
        ),
        "pitch_language": "",
        "acv_estimate": 0,
        "signals_matched": signals_matched,
        "manual_review": False,
    }
    log_trace("qualifier_not_qualified", {"company": company, **result})
    return result


def build_pitch_language(
    segment: str,
    ai_maturity: int,
    ai_confidence: str,
    enrichment: dict[str, Any],
) -> str:
    """
    Generate segment-aware, AI-maturity-aware pitch language.

    Rules:
    - Low confidence → ask rather than assert
    - Never claim "aggressive hiring" if open_roles < 5
    - Segment 4 (capability_gap) only pitched if AI maturity >= 2
    - Language shifts based on AI maturity score
    - Uses structured competitor gap findings when available
    """
    company = enrichment.get("company", "your company")
    job_signals: dict = enrichment.get("job_signals", {})
    open_roles: int = job_signals.get("open_roles", 0)
    ai_roles: list = job_signals.get("ai_roles", [])
    firmographics: dict = enrichment.get("firmographics", {})
    funding_event: dict | None = enrichment.get("funding_event")
    layoff_signal: dict | None = enrichment.get("layoff_signal")
    leadership_change: dict | None = enrichment.get("leadership_change")
    competitor_gap: dict = enrichment.get("competitor_gap", {})

    # Hiring velocity language — never assert "aggressive" if < 5 roles
    if open_roles >= 5:
        hiring_line = f"with {open_roles} open roles signalling active team growth"
    elif open_roles >= 1:
        hiring_line = f"with {open_roles} open role(s) on your careers page"
    else:
        hiring_line = "as you scale your team"

    # Check for high-confidence gap findings to enhance pitch
    gap_findings: list[dict] = competitor_gap.get("gap_findings", [])
    high_confidence_gaps = [g for g in gap_findings if g.get("confidence") == "high"]
    
    # Build gap-aware language if available
    gap_line = ""
    if high_confidence_gaps and ai_maturity >= 2:
        first_gap = high_confidence_gaps[0]
        practice = first_gap.get("practice", "")
        peer_count = len(first_gap.get("peer_evidence", []))
        
        if peer_count >= 2 and "leadership" in practice.lower():
            gap_line = (
                f"\n\nWe've noticed that several peers in your sector have established "
                f"dedicated AI leadership roles — is this something {company} is considering?"
            )
        elif peer_count >= 2 and "hiring" in practice.lower():
            gap_line = (
                f"\n\nTop-quartile companies in your space are actively building AI/ML teams — "
                f"are you finding the right talent quickly enough?"
            )

    # AI maturity language
    if ai_maturity >= 3:
        ai_line = (
            "Your AI/ML investment is clearly a strategic priority — "
            "we help teams like yours move from prototype to production faster."
        )
    elif ai_maturity == 2:
        if ai_confidence == "high":
            ai_line = (
                "We've noticed strong AI adoption signals at "
                f"{company} — our embedded AI/ML engineers can accelerate your roadmap."
            )
        else:
            ai_line = (
                "It looks like AI is becoming a priority at "
                f"{company} — are you finding it hard to hire the right ML talent quickly?"
            )
    elif ai_maturity == 1:
        ai_line = (
            "Many companies at your stage are starting to explore AI — "
            "we can help you build the right foundation without the hiring overhead."
        )
    else:
        ai_line = (
            "We work with technology companies to build and scale engineering teams "
            "without the cost and delay of traditional hiring."
        )

    # Segment-specific opening
    if segment == "recently_funded":
        if funding_event:
            funding_str = (
                f"${funding_event['total_funding_usd']:,} "
                f"{funding_event['type'].replace('_', ' ').title()}"
            )
        else:
            funding_str = "recent funding"

        if ai_confidence == "low" or ai_maturity == 0:
            opening = (
                f"Congratulations on the {funding_str} — "
                f"as you scale {hiring_line}, are you finding that "
                "traditional hiring timelines are slowing you down?"
            )
        else:
            opening = (
                f"Following your {funding_str}, {company} is clearly in execution mode "
                f"{hiring_line}. "
                "Tenacious Consulting embeds senior engineers within 2 weeks — "
                "no recruiter fees, no 3-month notice periods."
            )

    elif segment == "cost_restructuring":
        if layoff_signal:
            layoff_str = f"recent workforce restructuring ({layoff_signal['headcount']} headcount)"
        else:
            layoff_str = "recent restructuring"

        opening = (
            f"Following {company}'s {layoff_str}, many engineering leaders find they need "
            "to do more with leaner teams. "
            "Tenacious Consulting provides on-demand senior talent — "
            "you get the output without the fixed headcount cost."
        )

    elif segment == "leadership_transition":
        if leadership_change:
            leader_str = f"new {leadership_change['role']} {leadership_change['name']}"
        else:
            leader_str = "new technical leadership"

        if ai_confidence == "low":
            opening = (
                f"With {leader_str} recently joining {company}, "
                "are you looking to move quickly on any engineering priorities "
                "without waiting months to hire?"
            )
        else:
            opening = (
                f"With {leader_str} at the helm, {company} has a clear opportunity "
                "to accelerate its technical roadmap. "
                "Tenacious Consulting can embed experienced engineers within your team "
                "in under two weeks."
            )

    elif segment == "capability_gap":
        # Hard gate enforced in qualifier — this branch only reached if ai_maturity >= 2
        # Use gap findings if available
        if high_confidence_gaps:
            first_gap = high_confidence_gaps[0]
            practice = first_gap.get("practice", "")
            
            if "leadership" in practice.lower():
                opening = (
                    f"We've been tracking AI adoption in your sector, and noticed that "
                    f"several peers have established dedicated AI leadership roles. "
                    f"Is {company} considering a similar move? "
                    "Tenacious Consulting can embed senior AI/ML engineers to accelerate "
                    "your roadmap while you build out permanent leadership."
                )
            elif "hiring" in practice.lower():
                opening = (
                    f"Top-quartile companies in your space are actively scaling AI/ML teams. "
                    f"Tenacious Consulting specialises in placing senior AI/ML engineers "
                    f"who can contribute from day one — typically within 2 weeks."
                )
            else:
                opening = (
                    f"{company}'s AI maturity signals suggest you're building something ambitious. "
                    "Tenacious Consulting embeds AI/ML engineers who've shipped production models — "
                    "no ramp-up time, no equity dilution."
                )
        elif ai_roles:
            roles_str = ", ".join(ai_roles[:2])
            opening = (
                f"We noticed {company} is hiring for {roles_str} — "
                "a strong signal that AI is central to your roadmap. "
                "Tenacious Consulting specialises in placing senior AI/ML engineers "
                "who can contribute from day one."
            )
        else:
            opening = (
                f"{company}'s AI maturity signals suggest you're building something ambitious. "
                "Tenacious Consulting embeds AI/ML engineers who've shipped production models — "
                "no ramp-up time, no equity dilution."
            )

    else:
        opening = (
            f"We help technology companies like {company} scale engineering teams "
            "faster and more cost-effectively than traditional hiring."
        )

    return f"{opening}\n\n{ai_line}{gap_line}"


# ---------------------------------------------------------------------------
# Confidence helpers
# ---------------------------------------------------------------------------

def _funding_confidence(funding_event: dict) -> float:
    days_ago = funding_event.get("days_ago", 180)
    if days_ago <= 30:
        return 0.92
    elif days_ago <= 90:
        return 0.82
    elif days_ago <= 180:
        return 0.70
    return 0.55


def _layoff_confidence(layoff_signal: dict) -> float:
    days_ago = layoff_signal.get("days_ago", 120)
    pct = layoff_signal.get("percentage", 0)
    base = 0.75 if days_ago <= 60 else 0.60
    if pct >= 20:
        base += 0.10
    return min(base, 0.95)


def _leadership_confidence(leadership_change: dict) -> float:
    tenure = leadership_change.get("tenure_days", 90)
    if tenure <= 30:
        return 0.88
    elif tenure <= 60:
        return 0.78
    return 0.65


def _capability_gap_confidence(ai_maturity: dict, job_signals: dict) -> float:
    score = ai_maturity.get("score", 0)
    confidence_str = ai_maturity.get("confidence", "low")
    open_roles = job_signals.get("open_roles", 0)

    base = {3: 0.85, 2: 0.70}.get(score, 0.50)
    if confidence_str == "high":
        base += 0.08
    elif confidence_str == "medium":
        base += 0.04
    if open_roles >= 5:
        base += 0.05
    return min(base, 0.95)
