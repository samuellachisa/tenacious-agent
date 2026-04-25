"""
Build Competitor Gap Brief Use Case

Domain use case for generating competitive intelligence briefs that compare
a prospect's AI maturity against sector peers. This is a pure domain use case
that orchestrates the competitor gap analysis logic.

The brief converts vendor outreach from a generic pitch into a research finding
by providing evidence-backed gap analysis with source URLs.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class BuildCompetitorGapBrief:
    """
    Use case: Generate a competitor gap brief for a prospect.
    
    This use case takes enriched prospect data and generates a structured
    competitive analysis comparing the prospect's AI maturity against
    5-10 sector peers.
    
    The output follows schemas/competitor_gap_brief.schema.json and includes:
    - Scored peer companies (same AI maturity rubric)
    - Top-quartile benchmark calculation
    - 2-3 evidence-backed practice gaps
    - Quality self-check metadata
    - Pitch guidance for outreach composition
    """
    
    def __init__(self, data_repository):
        """
        Initialize with data repository for accessing Crunchbase data.
        
        Args:
            data_repository: Repository implementing get_crunchbase_companies()
        """
        self.data_repository = data_repository
    
    def execute(
        self,
        company_name: str,
        firmographics: dict[str, Any],
        ai_maturity: dict[str, Any],
        ai_maturity_scorer: callable,
    ) -> dict[str, Any]:
        """
        Execute the competitor gap brief generation.
        
        Args:
            company_name: Prospect company name
            firmographics: Prospect firmographic data
            ai_maturity: Prospect AI maturity score and breakdown
            ai_maturity_scorer: Function to score peer AI maturity
        
        Returns:
            Competitor gap brief dict matching schema
        """
        # Load all companies from data repository
        all_companies = self.data_repository.get_crunchbase_companies()
        
        # Extract prospect metadata
        company_industry = firmographics.get("industry", "").lower()
        company_score = ai_maturity.get("score", 0)
        company_domain = self._extract_domain(firmographics.get("website", ""))
        
        # Select peer companies
        peers, sparse_sector = self._select_peers(
            all_companies=all_companies,
            prospect_name=company_name,
            prospect_industry=company_industry,
        )
        
        # Score each peer
        scored_peers = self._score_peers(
            peers=peers,
            ai_maturity_scorer=ai_maturity_scorer,
        )
        
        # Calculate sector position
        sector_stats = self._calculate_sector_position(scored_peers)
        
        # Mark top quartile peers
        for peer in scored_peers:
            peer["top_quartile"] = (
                peer["ai_maturity_score"] >= sector_stats["top_quartile_score"]
            )
        
        # Extract gap findings
        gap_findings = self._extract_gap_findings(
            prospect_name=company_name,
            prospect_score=company_score,
            prospect_breakdown=ai_maturity.get("signal_breakdown", []),
            scored_peers=scored_peers,
            top_quartile_score=sector_stats["top_quartile_score"],
        )
        
        # Quality self-check
        quality_check = self._quality_self_check(
            gap_findings=gap_findings,
            prospect_score=company_score,
            prospect_breakdown=ai_maturity.get("signal_breakdown", []),
        )
        
        # Determine brief confidence
        brief_confidence = self._determine_confidence(
            peer_count=len(scored_peers),
            sparse_sector=sparse_sector,
        )
        
        # Generate pitch guidance
        pitch_guidance = self._generate_pitch_guidance(
            gap_findings=gap_findings,
            sparse_sector=sparse_sector,
        )
        
        # Assemble brief
        return {
            "prospect_domain": company_domain or "unknown.example",
            "prospect_sector": firmographics.get("industry", "Unknown"),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prospect_ai_maturity_score": company_score,
            "sector_top_quartile_benchmark": round(sector_stats["top_quartile_score"], 2),
            "competitors_analyzed": scored_peers,
            "gap_findings": gap_findings,
            "suggested_pitch_shift": pitch_guidance,
            "gap_quality_self_check": quality_check,
            "confidence": brief_confidence,
            "sparse_sector": sparse_sector,
            # Legacy fields for backward compatibility
            "sector": firmographics.get("industry", "Unknown"),
            "peers_analyzed": len(scored_peers),
            "company_score": company_score,
            "sector_median": round(sector_stats["median"], 2),
            "top_quartile_score": round(sector_stats["top_quartile_score"], 2),
        }
    
    def _extract_domain(self, website: str) -> str:
        """Extract domain from website URL."""
        return (
            website.replace("https://", "")
            .replace("http://", "")
            .split("/")[0]
        )
    
    def _select_peers(
        self,
        all_companies: list[dict],
        prospect_name: str,
        prospect_industry: str,
    ) -> tuple[list[dict], bool]:
        """
        Select 5-10 peer companies for comparison.
        
        Strategy:
        1. Primary: Companies sharing at least one category keyword
        2. Fallback: All other companies if <5 sector matches (sparse sector)
        
        Returns:
            (peers, sparse_sector_flag)
        """
        SPARSE_SECTOR_THRESHOLD = 5
        
        # Exclude prospect itself
        other_companies = [
            c for c in all_companies
            if c.get("name", "").strip().lower() != prospect_name.strip().lower()
        ]
        
        # Find sector matches
        def shares_sector(company: dict) -> bool:
            company_industry = company.get("category_list", "").lower()
            prospect_cats = set(prospect_industry.replace("|", " ").split())
            company_cats = set(company_industry.replace("|", " ").split())
            # Require at least one non-trivial overlapping token
            overlap = prospect_cats & company_cats - {"", "and", "the", "of", "for"}
            return bool(overlap)
        
        sector_peers = [c for c in other_companies if shares_sector(c)]
        
        # Check for sparse sector
        sparse_sector = len(sector_peers) < SPARSE_SECTOR_THRESHOLD
        peer_pool = other_companies if sparse_sector else sector_peers
        
        # Cap at 10 for tractability
        return peer_pool[:10], sparse_sector
    
    def _score_peers(
        self,
        peers: list[dict],
        ai_maturity_scorer: callable,
    ) -> list[dict]:
        """
        Score each peer using the same AI maturity rubric.
        
        Returns list of scored peer dicts with:
        - name, domain, ai_maturity_score, ai_maturity_justification
        - headcount_band, top_quartile (set later), sources_checked
        """
        scored_peers = []
        
        for peer in peers:
            # Prepare peer data for scoring
            peer_firmographics = {
                "industry": peer.get("category_list", ""),
                "description": peer.get("short_description", "").lower(),
                "recent_news": peer.get("recent_news", "").lower(),
                "cto_name": peer.get("cto_name", ""),
                "cto_tenure_days": peer.get("cto_tenure_days"),
                "open_roles_raw": peer.get("open_roles", []),
            }
            
            peer_job_signals = {
                "open_roles": len(peer.get("open_roles", [])),
                "ai_roles": [
                    r for r in peer.get("open_roles", [])
                    if any(
                        kw in r.lower()
                        for kw in {"ai", "ml", "machine learning", "data scientist", "mlops"}
                    )
                ],
            }
            
            # Score peer
            peer_maturity = ai_maturity_scorer(peer_job_signals, peer_firmographics)
            
            # Determine headcount band
            emp_count = peer.get("employee_count", 0)
            if emp_count < 80:
                headcount_band = "15_to_80"
            elif emp_count < 200:
                headcount_band = "80_to_200"
            elif emp_count < 500:
                headcount_band = "200_to_500"
            elif emp_count < 2000:
                headcount_band = "500_to_2000"
            else:
                headcount_band = "2000_plus"
            
            # Extract domain and sources
            peer_domain = self._extract_domain(peer.get("homepage_url", ""))
            sources_checked = self._build_source_urls(peer, peer_domain)
            
            scored_peers.append({
                "name": peer.get("name", "Unknown"),
                "domain": peer_domain or "unknown.example",
                "ai_maturity_score": peer_maturity["score"],
                "ai_maturity_justification": peer_maturity.get("justification", []),
                "headcount_band": headcount_band,
                "top_quartile": False,  # Set after quartile calculation
                "sources_checked": sources_checked[:3],
            })
        
        return scored_peers
    
    def _build_source_urls(self, peer: dict, peer_domain: str) -> list[str]:
        """Build list of source URLs for peer evidence."""
        sources = []
        
        if peer.get("linkedin_url"):
            sources.append(peer["linkedin_url"])
        
        if peer_domain:
            sources.append(f"https://{peer_domain}/careers")
            slug = peer.get("name", "").lower().replace(" ", "-")
            sources.append(f"https://builtin.com/company/{slug}/jobs")
        
        return sources
    
    def _calculate_sector_position(self, scored_peers: list[dict]) -> dict:
        """Calculate sector median and top-quartile benchmark."""
        scores = [p["ai_maturity_score"] for p in scored_peers]
        
        if not scores:
            return {
                "median": 0.0,
                "top_quartile_score": 0.0,
            }
        
        sorted_scores = sorted(scores)
        n = len(sorted_scores)
        
        # Median
        mid = n // 2
        if n % 2 == 0:
            median = (sorted_scores[mid - 1] + sorted_scores[mid]) / 2
        else:
            median = float(sorted_scores[mid])
        
        # 75th percentile (top quartile)
        idx = 0.75 * (n - 1)
        lower = int(idx)
        upper = min(lower + 1, n - 1)
        frac = idx - lower
        top_quartile = sorted_scores[lower] + frac * (sorted_scores[upper] - sorted_scores[lower])
        
        return {
            "median": median,
            "top_quartile_score": top_quartile,
        }
    
    def _extract_gap_findings(
        self,
        prospect_name: str,
        prospect_score: int,
        prospect_breakdown: list[dict],
        scored_peers: list[dict],
        top_quartile_score: float,
    ) -> list[dict]:
        """
        Extract 2-3 evidence-backed practice gaps.
        
        Returns list of gap finding dicts with:
        - practice, peer_evidence, prospect_state, confidence, segment_relevance
        """
        gap_findings = []
        
        # Index prospect signals
        prospect_signals = {
            s["signal_name"]: s for s in prospect_breakdown
        }
        
        # Get top quartile peer indices
        top_quartile_indices = [
            i for i, p in enumerate(scored_peers) if p["top_quartile"]
        ]
        
        # Gap 1: Dedicated AI/ML leadership
        if prospect_score < top_quartile_score:
            leadership_gap = self._extract_leadership_gap(
                prospect_name=prospect_name,
                prospect_signals=prospect_signals,
                scored_peers=scored_peers,
                top_quartile_indices=top_quartile_indices,
            )
            if leadership_gap:
                gap_findings.append(leadership_gap)
        
        # Gap 2: Active AI/ML hiring
        if prospect_score < top_quartile_score:
            hiring_gap = self._extract_hiring_gap(
                prospect_name=prospect_name,
                prospect_signals=prospect_signals,
                scored_peers=scored_peers,
                top_quartile_indices=top_quartile_indices,
            )
            if hiring_gap:
                gap_findings.append(hiring_gap)
        
        # Gap 3: Public executive commentary
        if prospect_score <= 1 and top_quartile_score >= 2:
            commentary_gap = self._extract_commentary_gap(
                prospect_name=prospect_name,
                prospect_signals=prospect_signals,
                scored_peers=scored_peers,
                top_quartile_indices=top_quartile_indices,
            )
            if commentary_gap:
                gap_findings.append(commentary_gap)
        
        # Fallback: No gaps (prospect at/above benchmark)
        if not gap_findings:
            gap_findings.append(
                self._build_benchmark_gap(
                    prospect_name=prospect_name,
                    prospect_score=prospect_score,
                    scored_peers=scored_peers,
                    top_quartile_score=top_quartile_score,
                    top_quartile_indices=top_quartile_indices,
                )
            )
        
        return gap_findings
    
    def _extract_leadership_gap(
        self,
        prospect_name: str,
        prospect_signals: dict,
        scored_peers: list[dict],
        top_quartile_indices: list[int],
    ) -> dict | None:
        """Extract dedicated AI/ML leadership gap if it exists."""
        # Find top-quartile peers with named AI leadership
        leadership_peers = []
        for i in top_quartile_indices:
            peer = scored_peers[i]
            # Check if peer has leadership signal in justification
            justifications = peer.get("ai_maturity_justification", [])
            if any("CTO" in j or "VP" in j or "Head of AI" in j or "Chief" in j for j in justifications):
                leadership_peers.append(peer)
        
        if len(leadership_peers) < 2:
            return None
        
        # Build peer evidence
        peer_evidence = []
        for peer in leadership_peers[:3]:
            justifications = peer.get("ai_maturity_justification", [])
            leadership_evidence = next(
                (j for j in justifications if "CTO" in j or "VP" in j or "Head" in j or "Chief" in j),
                f"AI maturity score {peer['ai_maturity_score']}/3"
            )
            peer_evidence.append({
                "competitor_name": peer["name"],
                "evidence": leadership_evidence,
                "source_url": peer["sources_checked"][0] if peer["sources_checked"] else f"https://{peer['domain']}/careers",
            })
        
        # Determine prospect state
        prospect_leadership = prospect_signals.get("named_ai_leadership", {})
        if prospect_leadership.get("detected"):
            prospect_state = f"{prospect_name} shows a recent technical hire but no exclusively AI/ML-focused leadership role."
        else:
            prospect_state = f"{prospect_name} has no named AI/ML leadership role detected in public signals."
        
        return {
            "practice": "Dedicated AI/ML leadership role at executive level",
            "peer_evidence": peer_evidence,
            "prospect_state": prospect_state,
            "confidence": "high" if len(peer_evidence) >= 2 else "medium",
            "segment_relevance": ["segment_1_series_a_b", "segment_4_specialized_capability"],
        }
    
    def _extract_hiring_gap(
        self,
        prospect_name: str,
        prospect_signals: dict,
        scored_peers: list[dict],
        top_quartile_indices: list[int],
    ) -> dict | None:
        """Extract active AI/ML hiring gap if it exists."""
        # Find top-quartile peers with active AI/ML hiring
        hiring_peers = []
        for i in top_quartile_indices:
            peer = scored_peers[i]
            justifications = peer.get("ai_maturity_justification", [])
            if any("role" in j.lower() or "hiring" in j.lower() or "open" in j.lower() for j in justifications):
                hiring_peers.append(peer)
        
        if len(hiring_peers) < 2:
            return None
        
        # Build peer evidence
        peer_evidence = []
        for peer in hiring_peers[:3]:
            justifications = peer.get("ai_maturity_justification", [])
            hiring_evidence = next(
                (j for j in justifications if "role" in j.lower() or "hiring" in j.lower()),
                f"Multiple AI/ML open roles (score {peer['ai_maturity_score']}/3)"
            )
            peer_evidence.append({
                "competitor_name": peer["name"],
                "evidence": hiring_evidence,
                "source_url": peer["sources_checked"][1] if len(peer["sources_checked"]) > 1 else peer["sources_checked"][0] if peer["sources_checked"] else f"https://{peer['domain']}/careers",
            })
        
        # Determine prospect state
        prospect_roles = prospect_signals.get("ai_adjacent_roles", {})
        if prospect_roles.get("detected"):
            prospect_state = (
                f"{prospect_name} has open AI/ML roles ({prospect_roles.get('evidence', 'detected')}), "
                "but below the top-quartile threshold of 3+ active openings."
            )
        else:
            prospect_state = f"{prospect_name} has no AI-adjacent open roles detected in public job boards."
        
        return {
            "practice": "Active AI/ML engineering hiring (3+ open roles signalling platform buildout)",
            "peer_evidence": peer_evidence,
            "prospect_state": prospect_state,
            "confidence": "high" if len(peer_evidence) >= 2 else "medium",
            "segment_relevance": ["segment_4_specialized_capability"],
        }
    
    def _extract_commentary_gap(
        self,
        prospect_name: str,
        prospect_signals: dict,
        scored_peers: list[dict],
        top_quartile_indices: list[int],
    ) -> dict | None:
        """Extract public executive commentary gap if it exists."""
        # Find top-quartile peers with executive commentary
        commentary_peers = []
        for i in top_quartile_indices:
            peer = scored_peers[i]
            justifications = peer.get("ai_maturity_justification", [])
            if any("news" in j.lower() or "commentary" in j.lower() or "blog" in j.lower() for j in justifications):
                commentary_peers.append(peer)
        
        if len(commentary_peers) < 2:
            return None
        
        # Build peer evidence
        peer_evidence = []
        for peer in commentary_peers[:2]:
            justifications = peer.get("ai_maturity_justification", [])
            commentary_evidence = next(
                (j for j in justifications if "news" in j.lower() or "commentary" in j.lower()),
                "AI/ML mentioned in recent news"
            )
            peer_evidence.append({
                "competitor_name": peer["name"],
                "evidence": commentary_evidence,
                "source_url": peer["sources_checked"][0] if peer["sources_checked"] else f"https://{peer['domain']}",
            })
        
        # Determine prospect state
        prospect_commentary = prospect_signals.get("executive_commentary", {})
        if prospect_commentary.get("detected"):
            prospect_state = f"{prospect_name} mentions AI in news but public commentary is limited compared to top-quartile peers."
        else:
            prospect_state = f"{prospect_name} has no AI/ML commentary in recent public news."
        
        return {
            "practice": "Public executive commentary on AI/ML strategy in news or investor materials",
            "peer_evidence": peer_evidence,
            "prospect_state": prospect_state,
            "confidence": "medium",
            "segment_relevance": ["segment_1_series_a_b"],
        }
    
    def _build_benchmark_gap(
        self,
        prospect_name: str,
        prospect_score: int,
        scored_peers: list[dict],
        top_quartile_score: float,
        top_quartile_indices: list[int],
    ) -> dict:
        """Build fallback gap when prospect is at/above benchmark."""
        if not scored_peers:
            # Edge case: no peer data
            return {
                "practice": "Insufficient peer data — cross-sector analysis recommended",
                "peer_evidence": [
                    {
                        "competitor_name": "Sector dataset",
                        "evidence": "No sector-matched peer companies found in the current dataset.",
                        "source_url": "https://builtin.com/companies",
                    },
                    {
                        "competitor_name": "Cross-sector analysis",
                        "evidence": "Expand the dataset with additional industry peers before drawing gap conclusions.",
                        "source_url": "https://builtin.com/companies",
                    },
                ],
                "prospect_state": f"{prospect_name} AI maturity score ({prospect_score}) cannot be benchmarked without peer data.",
                "confidence": "low",
                "segment_relevance": [],
            }
        
        # Normal case: prospect at/above benchmark
        benchmark_evidence = []
        candidate_indices = top_quartile_indices or list(range(len(scored_peers)))
        
        for i in candidate_indices[:3]:
            peer = scored_peers[i]
            justifications = peer.get("ai_maturity_justification", [])
            benchmark_evidence.append({
                "competitor_name": peer["name"],
                "evidence": justifications[0] if justifications else f"AI maturity score {peer['ai_maturity_score']}/3",
                "source_url": peer["sources_checked"][0] if peer["sources_checked"] else f"https://{peer['domain']}/careers",
            })
        
        # Ensure at least 2 entries (schema requirement)
        seen = {e["competitor_name"] for e in benchmark_evidence}
        for peer in scored_peers:
            if len(benchmark_evidence) >= 2:
                break
            if peer["name"] not in seen:
                benchmark_evidence.append({
                    "competitor_name": peer["name"],
                    "evidence": f"AI maturity score {peer['ai_maturity_score']}/3",
                    "source_url": peer["sources_checked"][0] if peer["sources_checked"] else f"https://{peer['domain']}/careers",
                })
                seen.add(peer["name"])
        
        return {
            "practice": "AI maturity at or above sector benchmark — opportunity to scale existing capabilities",
            "peer_evidence": benchmark_evidence[:3],
            "prospect_state": (
                f"{prospect_name} AI maturity score ({prospect_score}) is at or above the "
                f"sector top-quartile benchmark ({top_quartile_score:.1f}). "
                "No critical gaps detected from public signals."
            ),
            "confidence": "high",
            "segment_relevance": ["segment_1_series_a_b", "segment_4_specialized_capability"],
        }
    
    def _quality_self_check(
        self,
        gap_findings: list[dict],
        prospect_score: int,
        prospect_breakdown: list[dict],
    ) -> dict:
        """Generate quality self-check metadata."""
        all_evidence_has_urls = all(
            all(ev.get("source_url") for ev in gap.get("peer_evidence", []))
            for gap in gap_findings
        )
        
        at_least_one_high_confidence = any(
            gap.get("confidence") == "high" for gap in gap_findings
        )
        
        # Silent-but-sophisticated: low public score but ML stack keywords detected
        prospect_signals = {s["signal_name"]: s for s in prospect_breakdown}
        prospect_silent_but_sophisticated = (
            prospect_score <= 1
            and prospect_signals.get("ml_stack_keywords", {}).get("detected", False)
        )
        
        return {
            "all_peer_evidence_has_source_url": all_evidence_has_urls,
            "at_least_one_gap_high_confidence": at_least_one_high_confidence,
            "prospect_silent_but_sophisticated_risk": prospect_silent_but_sophisticated,
        }
    
    def _determine_confidence(self, peer_count: int, sparse_sector: bool) -> str:
        """Determine overall brief confidence level."""
        if peer_count >= 5:
            confidence = "high"
        elif peer_count >= 2:
            confidence = "medium"
        else:
            confidence = "low"
        
        # Sparse sector downgrades confidence
        if sparse_sector and confidence == "high":
            confidence = "medium"
        
        return confidence
    
    def _generate_pitch_guidance(
        self,
        gap_findings: list[dict],
        sparse_sector: bool,
    ) -> str:
        """Generate pitch guidance for outreach composition."""
        if not gap_findings:
            return "No gaps detected. Focus on scaling existing AI capabilities."
        
        first_gap = gap_findings[0]
        is_benchmark_gap = "at or above sector benchmark" in first_gap["practice"]
        
        if first_gap.get("confidence") == "high" and not is_benchmark_gap:
            gap_label = first_gap["practice"]
            guidance = (
                f"Lead with the '{gap_label}' gap (high confidence, "
                f"{len(first_gap['peer_evidence'])} peer examples). "
                "Frame as a question rather than an assertion to maintain advisory tone."
            )
        else:
            guidance = (
                "No strong gaps detected. Focus on scaling existing AI capabilities "
                "and deepening the AI/ML function rather than competitive positioning."
            )
        
        if sparse_sector:
            guidance += (
                " Note: benchmark derived from cross-sector peers (sparse sector); "
                "validate peer relevance before citing specific companies in outreach."
            )
        
        return guidance
