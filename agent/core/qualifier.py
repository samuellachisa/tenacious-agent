"""
ICP qualifier — classifies enriched prospects into one of four segments.

Segments (fixed names):
  recently_funded       — Series A/B in last 180 days
  cost_restructuring    — post-layoff mid-market
  leadership_transition — new CTO/VP Eng < 90 days
  capability_gap        — AI maturity >= 2 ONLY (hard gate)

Hard disqualifiers: consulting, staffing, recruiting, outsourcing firms.
Mixed signal edge case: funding + layoff → recently_funded with reduced confidence.

Bench capacity constraint: Never commit to capacity that exceeds bench_summary.json counts.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from agent.integrations.langfuse_client import log_trace

# LLM integration flag - set to False to use hardcoded templates
USE_LLM_FOR_PITCH = os.getenv("USE_LLM_FOR_PITCH", "true").lower() == "true"

# ---------------------------------------------------------------------------
# Bench capacity helpers
# ---------------------------------------------------------------------------

def _load_bench_summary() -> dict[str, Any]:
    """Load bench_summary.json from seed/ directory."""
    bench_path = Path(__file__).parent.parent.parent / "seed" / "bench_summary.json"
    try:
        with open(bench_path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError):
        # Fallback to empty bench if file missing
        return {"stacks": {}}


def check_bench_capacity(required_stack: str, required_count: int = 1) -> dict[str, Any]:
    """
    Check if bench has capacity for the required stack.
    
    Args:
        required_stack: Stack name (python, ml, go, infra, data, frontend, fullstack_nestjs)
        required_count: Number of engineers needed (default 1)
    
    Returns:
        {
            "available": bool,
            "available_count": int,
            "required_count": int,
            "stack": str,
            "gap": int (negative if insufficient),
            "recommendation": str (what to say to prospect)
        }
    
    Example:
        >>> check_bench_capacity("python", 5)
        {
            "available": True,
            "available_count": 7,
            "required_count": 5,
            "stack": "python",
            "gap": 2,
            "recommendation": "We have 7 Python engineers available — we can place your team within 7 days."
        }
        
        >>> check_bench_capacity("ml", 6)
        {
            "available": False,
            "available_count": 5,
            "required_count": 6,
            "stack": "ml",
            "gap": -1,
            "recommendation": "Our ML bench currently has 5 engineers available. We can start with 5 and ramp the 6th within 2-3 weeks — would that timeline work?"
        }
    """
    bench = _load_bench_summary()
    stacks = bench.get("stacks", {})
    
    stack_data = stacks.get(required_stack.lower(), {})
    available_count = stack_data.get("available_engineers", 0)
    gap = available_count - required_count
    
    if gap >= 0:
        # Sufficient capacity
        deploy_days = stack_data.get("time_to_deploy_days", 14)
        return {
            "available": True,
            "available_count": available_count,
            "required_count": required_count,
            "stack": required_stack,
            "gap": gap,
            "recommendation": (
                f"We have {available_count} {required_stack.title()} engineers available — "
                f"we can place your team within {deploy_days} days."
            ),
        }
    else:
        # Insufficient capacity — offer phased ramp
        return {
            "available": False,
            "available_count": available_count,
            "required_count": required_count,
            "stack": required_stack,
            "gap": gap,
            "recommendation": (
                f"Our {required_stack.title()} bench currently has {available_count} engineers available. "
                f"We can start with {available_count} and ramp the remaining {abs(gap)} within 2-3 weeks — "
                "would that timeline work for your needs?"
            ) if available_count > 0 else (
                f"Our {required_stack.title()} bench is currently at capacity. "
                "Let me connect you with our delivery lead to discuss timeline and alternatives."
            ),
        }


def infer_required_stacks(enrichment: dict[str, Any]) -> list[str]:
    """
    Infer which stacks the prospect likely needs based on enrichment signals.
    
    Returns list of stack names in priority order: ["ml", "python", "data"]
    
    Logic:
    - AI maturity >= 2 → ml stack
    - AI roles in job posts → ml stack
    - Data-related job posts → data stack
    - Backend/API roles → python or go
    - Frontend roles → frontend
    - DevOps/infra roles → infra
    """
    stacks: list[str] = []
    
    ai_maturity = enrichment.get("ai_maturity", {}).get("score", 0)
    job_signals = enrichment.get("job_signals", {})
    ai_roles = job_signals.get("ai_roles", [])
    open_roles_raw = enrichment.get("firmographics", {}).get("open_roles_raw", [])
    
    # AI/ML stack
    if ai_maturity >= 2 or ai_roles:
        stacks.append("ml")
    
    # Data stack
    data_keywords = {"data engineer", "data analyst", "analytics", "dbt", "snowflake", "databricks"}
    if any(any(kw in role.lower() for kw in data_keywords) for role in open_roles_raw):
        stacks.append("data")
    
    # Python backend
    python_keywords = {"python", "django", "fastapi", "flask", "backend"}
    if any(any(kw in role.lower() for kw in python_keywords) for role in open_roles_raw):
        if "python" not in stacks:  # Don't duplicate if already added via ML
            stacks.append("python")
    
    # Go backend
    go_keywords = {"go", "golang", "microservices"}
    if any(any(kw in role.lower() for kw in go_keywords) for role in open_roles_raw):
        stacks.append("go")
    
    # Infra/DevOps
    infra_keywords = {"devops", "infrastructure", "kubernetes", "k8s", "terraform", "aws", "gcp", "sre"}
    if any(any(kw in role.lower() for kw in infra_keywords) for role in open_roles_raw):
        stacks.append("infra")
    
    # Frontend
    frontend_keywords = {"frontend", "react", "next.js", "typescript", "ui", "ux"}
    if any(any(kw in role.lower() for kw in frontend_keywords) for role in open_roles_raw):
        stacks.append("frontend")
    
    # Default to python if no specific signals
    if not stacks:
        stacks.append("python")
    
    return stacks


# ---------------------------------------------------------------------------
# Hard disqualifier keywords (industry / description)
# ---------------------------------------------------------------------------

def _confidence_tier(value: Any) -> str:
    """Convert float confidence (0.0–1.0) or legacy string tier to 'high'/'medium'/'low'."""
    if isinstance(value, (int, float)):
        if value >= 0.75:
            return "high"
        if value >= 0.50:
            return "medium"
        return "low"
    return str(value)


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

async def qualify_prospect(enrichment: dict[str, Any]) -> dict[str, Any]:
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
    ai_confidence: str = _confidence_tier(ai_maturity.get("confidence", 0.0))

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
        pitch_language = await build_pitch_language(segment, ai_score, ai_confidence, enrichment)
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
        pitch_language = await build_pitch_language(segment, ai_score, ai_confidence, enrichment)
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
        pitch_language = await build_pitch_language(segment, ai_score, ai_confidence, enrichment)
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
            pitch_language = await build_pitch_language(segment, ai_score, ai_confidence, enrichment)
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
        pitch_language = await build_pitch_language(segment, ai_score, ai_confidence, enrichment)
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


async def build_pitch_language(
    segment: str,
    ai_maturity: int,
    ai_confidence: str,
    enrichment: dict[str, Any],
) -> str:
    """
    Generate segment-aware, AI-maturity-aware, bench-capacity-aware pitch language.

    Uses LLM (via OpenRouter) when USE_LLM_FOR_PITCH=true, with automatic
    fallback to hardcoded templates if the LLM call fails.

    Rules:
    - Low confidence → ask rather than assert
    - Never claim "aggressive hiring" if open_roles < 5
    - Segment 4 (capability_gap) only pitched if AI maturity >= 2
    - Language shifts based on AI maturity score
    - Uses structured competitor gap findings when available
    - CRITICAL: Never commit to capacity that exceeds bench_summary.json counts
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

    # Infer required stacks and check bench capacity
    required_stacks = infer_required_stacks(enrichment)
    primary_stack = required_stacks[0] if required_stacks else "python"
    capacity_check = check_bench_capacity(primary_stack, required_count=1)

    # Try LLM-generated pitch first
    if USE_LLM_FOR_PITCH:
        llm_pitch = await _generate_pitch_with_llm(
            segment=segment,
            ai_maturity=ai_maturity,
            ai_confidence=ai_confidence,
            company=company,
            enrichment=enrichment,
            capacity_check=capacity_check,
            primary_stack=primary_stack,
        )
        if llm_pitch:
            return llm_pitch

    # Fallback: hardcoded templates
    return _build_pitch_language_fallback(
        segment=segment,
        ai_maturity=ai_maturity,
        ai_confidence=ai_confidence,
        company=company,
        open_roles=open_roles,
        ai_roles=ai_roles,
        funding_event=funding_event,
        layoff_signal=layoff_signal,
        leadership_change=leadership_change,
        competitor_gap=competitor_gap,
        capacity_check=capacity_check,
        primary_stack=primary_stack,
    )


async def _generate_pitch_with_llm(
    segment: str,
    ai_maturity: int,
    ai_confidence: str,
    company: str,
    enrichment: dict[str, Any],
    capacity_check: dict[str, Any],
    primary_stack: str,
) -> str:
    """
    Generate personalized pitch language using LLM.
    Returns empty string on failure (triggers fallback).
    """
    from agent.integrations.llm_client import generate_text

    job_signals: dict = enrichment.get("job_signals", {})
    open_roles: int = job_signals.get("open_roles", 0)
    ai_roles: list = job_signals.get("ai_roles", [])
    firmographics: dict = enrichment.get("firmographics", {})
    funding_event: dict | None = enrichment.get("funding_event")
    layoff_signal: dict | None = enrichment.get("layoff_signal")
    leadership_change: dict | None = enrichment.get("leadership_change")
    competitor_gap: dict = enrichment.get("competitor_gap", {})
    hiring_signal_brief: dict = enrichment.get("hiring_signal_brief", {})

    # Build signal context for the prompt
    signal_lines: list[str] = []

    if funding_event and funding_event.get("in_window"):
        signal_lines.append(
            f"- Funding: {funding_event['type'].replace('_', ' ').title()} "
            f"${funding_event.get('total_funding_usd', 0):,} "
            f"({funding_event.get('days_ago', '?')} days ago)"
        )

    if layoff_signal and layoff_signal.get("in_window"):
        signal_lines.append(
            f"- Layoff: {layoff_signal.get('headcount', '?')} headcount "
            f"({layoff_signal.get('percentage', '?')}%) "
            f"{layoff_signal.get('days_ago', '?')} days ago"
        )

    if leadership_change and leadership_change.get("in_window"):
        signal_lines.append(
            f"- New {leadership_change.get('role', 'CTO')}: "
            f"{leadership_change.get('name', 'Unknown')} "
            f"({leadership_change.get('tenure_days', '?')} days tenure)"
        )

    if open_roles > 0:
        signal_lines.append(f"- Open roles: {open_roles} total")
    if ai_roles:
        signal_lines.append(f"- AI/ML roles: {', '.join(ai_roles[:3])}")

    # Competitor gap context
    gap_findings: list[dict] = competitor_gap.get("gap_findings", [])
    high_confidence_gaps = [g for g in gap_findings if g.get("confidence") == "high"]
    gap_context = ""
    if high_confidence_gaps:
        first_gap = high_confidence_gaps[0]
        peer_names = [p.get("competitor_name", "") for p in first_gap.get("peer_evidence", [])[:2]]
        gap_context = (
            f"\nCompetitor gap: {first_gap.get('practice', '')} "
            f"(peers doing this: {', '.join(filter(None, peer_names))})"
        )

    # Capacity context
    if capacity_check["available"]:
        capacity_context = (
            f"{capacity_check['available_count']} {primary_stack.title()} engineers "
            f"available on bench, deployable in {_get_deploy_days(primary_stack)} days"
        )
    else:
        capacity_context = capacity_check["recommendation"]

    # Confidence gate: low confidence → ask, don't assert
    confidence_instruction = (
        "Use assertive language — the signals are strong."
        if ai_confidence in ("high", "medium")
        else "Use questions rather than assertions — signal confidence is low."
    )

    # Hiring velocity instruction
    if open_roles >= 5:
        velocity_instruction = f"You may reference {open_roles} open roles as a signal of active growth."
    elif open_roles >= 1:
        velocity_instruction = f"Reference {open_roles} open role(s) but do not claim 'aggressive hiring'."
    else:
        velocity_instruction = "Do not make claims about hiring velocity — no open roles detected."

    segment_context = {
        "recently_funded": (
            "The prospect recently closed a funding round. "
            "They have fresh capital and need to scale engineering output faster than in-house hiring allows."
        ),
        "cost_restructuring": (
            "The prospect recently went through a layoff/restructuring. "
            "They need to maintain engineering output with a leaner team — outsourced talent is cost-efficient."
        ),
        "leadership_transition": (
            "The prospect has a new CTO or VP Engineering. "
            "New technical leaders reassess vendors and offshore mix in their first 6 months."
        ),
        "capability_gap": (
            "The prospect shows AI maturity signals but lacks the talent depth to execute at scale. "
            "They need senior AI/ML engineers who can contribute from day one."
        ),
    }.get(segment, "The prospect is a B2B technology company that could benefit from outsourced engineering talent.")

    industry = firmographics.get("industry", "technology")
    employee_count = firmographics.get("employee_count", "unknown")

    prompt = f"""You are writing a cold outbound email body for Tenacious Consulting, a B2B talent outsourcing firm.

PROSPECT: {company}
INDUSTRY: {industry}
EMPLOYEES: {employee_count}
SEGMENT: {segment}
AI MATURITY: {ai_maturity}/3 ({ai_confidence} confidence)

SITUATION:
{segment_context}

SIGNALS DETECTED:
{chr(10).join(signal_lines) if signal_lines else "- No strong signals detected"}
{gap_context}

BENCH CAPACITY:
{capacity_context}

INSTRUCTIONS:
- Write 3 short paragraphs (total 150-220 words)
- Paragraph 1: Open with the specific signal that triggered this outreach (funding, layoff, new leader, or AI gap). Be concrete — name the signal, the date/amount if available.
- Paragraph 2: Connect the signal to a pain point Tenacious solves. Reference the competitor gap if available.
- Paragraph 3: State bench capacity honestly, then close with a single low-friction CTA: "Would you have 20 minutes this week for a quick call?"
- {confidence_instruction}
- {velocity_instruction}
- Never fabricate signals not listed above.
- Never promise capacity beyond what is stated in bench capacity.
- Tone: direct, warm, peer-to-peer — not salesy. Write as if from a senior consultant, not a sales rep.
- Do NOT include a subject line, greeting, or sign-off — body paragraphs only.

Write the email body now:"""

    result = await generate_text(prompt=prompt, max_tokens=400, temperature=0.7)

    if result["success"] and result["text"]:
        log_trace("llm_pitch_generated", {
            "company": company,
            "segment": segment,
            "model": result["model"],
            "cost_usd": result["cost_usd"],
            "tokens": result["tokens"],
        })
        return result["text"]

    # LLM failed — log and return empty to trigger fallback
    log_trace("llm_pitch_failed", {
        "company": company,
        "segment": segment,
        "error": result.get("error", "unknown"),
    })
    return ""


def _build_pitch_language_fallback(
    segment: str,
    ai_maturity: int,
    ai_confidence: str,
    company: str,
    open_roles: int,
    ai_roles: list,
    funding_event: dict | None,
    layoff_signal: dict | None,
    leadership_change: dict | None,
    competitor_gap: dict,
    capacity_check: dict,
    primary_stack: str,
) -> str:
    """
    Hardcoded template fallback for pitch language.
    Used when LLM is disabled or unavailable.
    """
    # Build capacity-aware language
    if capacity_check["available"]:
        capacity_line = (
            f"\n\nWe have {capacity_check['available_count']} "
            f"{primary_stack.title()} engineers on our bench right now — "
            f"we can place your first engineer within {_get_deploy_days(primary_stack)} days."
        )
    else:
        capacity_line = f"\n\n{capacity_check['recommendation']}"

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

    return f"{opening}\n\n{ai_line}{gap_line}{capacity_line}"


def _get_deploy_days(stack: str) -> int:
    """Get deployment timeline for a stack from bench_summary.json."""
    bench = _load_bench_summary()
    stacks = bench.get("stacks", {})
    stack_data = stacks.get(stack.lower(), {})
    return stack_data.get("time_to_deploy_days", 14)


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
    confidence_str = _confidence_tier(ai_maturity.get("confidence", 0.0))
    open_roles = job_signals.get("open_roles", 0)

    base = {3: 0.85, 2: 0.70}.get(score, 0.50)
    if confidence_str == "high":
        base += 0.08
    elif confidence_str == "medium":
        base += 0.04
    if open_roles >= 5:
        base += 0.05
    return min(base, 0.95)
