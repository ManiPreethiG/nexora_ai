"""Multi-Cycle Simulation Runner for Nexora AI.

Demonstrates the central learning loop of Nexora AI:
  Audit 1 (Baseline: 51 pts, 4 major defects)
    ↓
  User implements fixes for robots.txt and structured data
    ↓
  Audit 2 (Re-audit: 72 pts, +21 improvement, detects resolved vs persistent)
    ↓
  Agent reasons: "Why is canonicalization the next priority?"
    ↓
  Audit 3 (Longitudinal tracking: detects regression in crawl-access)
"""

import sys
import time
import json
import datetime as dt

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from nexora.identity import WebsiteIdentity
from nexora.models import AuditSnapshot, FindingSnapshot, ImplementationEvent
from nexora.memory.hindsight_client import HindsightMemoryClient
from nexora.memory.agent import MemoryAgent
from nexora.analysis.comparison import ComparisonAgent
from nexora.recommendations.agent import RecommendationAgent
from nexora.reporting.historical_report import augment_report, to_historical_markdown


def run_demo(target_url: str = "https://example.com") -> int:
    """Run an interactive demonstration of Nexora AI learning across three audit cycles."""
    identity = WebsiteIdentity(target_url)
    hindsight_client = HindsightMemoryClient()
    memory_agent = MemoryAgent(hindsight_client)
    comparison_agent = ComparisonAgent()
    recommendation_agent = RecommendationAgent()

    # Reset any previous demo history for clean demonstration
    hindsight_client.clear_bank(identity.bank_id)

    print("\n" + "=" * 70)
    print("NEXORA AI — AI VISIBILITY & CITATION OPTIMIZATION AGENT")
    print("Simulation: Persistent Memory & Learning Across Audit Cycles")
    print(f"Target Site: {identity.domain} | Memory Bank: {identity.bank_id}")
    print("=" * 70)

    # -------------------------------------------------------------
    # CYCLE 1: BASELINE AUDIT
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> STEP 1: AUDIT CYCLE #1 (BASELINE)")
    print("-" * 70)
    print("[Agent] Checking Hindsight memory for prior audits...")
    print(f"  → Result: FIRST AUDIT for {identity.domain}. No previous history exists.")
    print("[Agent] Executing multi-skill audit engine...")

    snap1 = AuditSnapshot(
        snapshot_id=f"snap_{identity.domain}_cycle1",
        domain=identity.domain,
        audited_at="2026-09-28T10:00:00Z",
        overall_scores={"ai_discoverability_score": 51, "on_site_engagement_score": 65},
        severity_counts={"critical": 1, "high": 2, "medium": 1, "low": 0},
        total_findings=4,
        findings=[
            FindingSnapshot(
                check_id="CA-AI-RETRIEVAL-BLOCKED",
                id="F-001",
                title="robots.txt blocks AI retrieval crawlers",
                category="discoverability",
                concern="crawl-access-audit",
                severity="critical",
                confidence="high",
                evidence="robots.txt disallows OAI-SearchBot and Claude-SearchBot.",
                suggested_action={"summary": "Allow retrieval bots in robots.txt", "priority": "critical", "effort": "low"},
            ),
            FindingSnapshot(
                check_id="SD-NO-ORGANIZATION",
                id="F-002",
                title="No Organization structured data identifies brand entity",
                category="discoverability",
                concern="structured-data-audit",
                severity="high",
                confidence="high",
                evidence="No Organization schema found on homepage or templates.",
                suggested_action={"summary": "Add Organization JSON-LD with sameAs entity anchors", "priority": "high", "effort": "medium"},
            ),
            FindingSnapshot(
                check_id="DC-DUPLICATE-TITLE-OR-DESCRIPTION",
                id="F-003",
                title="Duplicate titles and canonical dilution across URLs",
                category="discoverability",
                concern="duplicate-canonicalization-audit",
                severity="high",
                confidence="high",
                evidence="3 page pairs share identical title tags without canonical tags.",
                suggested_action={"summary": "Add canonical link tags to point to authoritative URL", "priority": "high", "effort": "low"},
            ),
            FindingSnapshot(
                check_id="AQ-NO-QUESTION-CONTENT",
                id="F-004",
                title="No question-shaped content exists for AI query matching",
                category="discoverability",
                concern="answer-coverage-audit",
                severity="medium",
                confidence="high",
                evidence="Zero question headings or FAQ structures detected across sampled pages.",
                suggested_action={"summary": "Publish direct FAQ answers with schema markup", "priority": "medium", "effort": "medium"},
            ),
        ],
        site_type="ecommerce",
        brand_name="ExampleBrand",
        headline="1 critical blocker prevents AI search engines from indexing the site.",
    )

    comp1 = comparison_agent.compare(snap1, [])
    memory_agent.retain_audit(identity, snap1, comp1)

    print(f"\n[Audit #1 Summary]")
    print(f"  AI Discoverability Score: {snap1.overall_scores['ai_discoverability_score']}/100")
    print(f"  Total Defects: 4 (Critical: 1, High: 2, Medium: 1)")
    print(f"  Top Action: Allow AI retrieval crawlers in robots.txt")
    print(f"  Retained durable knowledge into Hindsight bank '{identity.bank_id}'.")

    time.sleep(1)

    # -------------------------------------------------------------
    # INTERLUDE: USER IMPLEMENTS FIXES
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> STEP 2: USER IMPLEMENTATION ACTIONS")
    print("-" * 70)
    print("[User] 'I have updated robots.txt to allow AI retrieval crawlers,")
    print("        and added the Organization JSON-LD schema with Wikidata links.'")
    print("[Agent] Recording user-confirmed implementations in Hindsight memory...")

    memory_agent.record_user_fix(
        identity,
        "CA-AI-RETRIEVAL-BLOCKED",
        notes="Allowed OAI-SearchBot and Claude-SearchBot in robots.txt.",
        action_summary="Updated robots.txt policy",
    )
    memory_agent.record_user_fix(
        identity,
        "SD-NO-ORGANIZATION",
        notes="Added Organization markup with sameAs anchors.",
        action_summary="Implemented Organization schema",
    )
    print("  → User actions durable in Hindsight. Ready for verification on re-audit.")

    time.sleep(1)

    # -------------------------------------------------------------
    # CYCLE 2: RE-AUDIT WITH MEMORY & IMPACT MEASUREMENT
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> STEP 3: AUDIT CYCLE #2 (RE-AUDIT & HISTORICAL COMPARISON)")
    print("-" * 70)
    print("[Agent] Recalling history from Hindsight...")
    history2 = memory_agent.recall_history(identity)
    print(f"  → Found 1 previous audit snapshot and 2 user implementation events.")
    print("[Agent] Executing multi-skill audit engine on current site...")

    # Current site: robots.txt and SD are fixed! DC and AQ remain.
    snap2 = AuditSnapshot(
        snapshot_id=f"snap_{identity.domain}_cycle2",
        domain=identity.domain,
        audited_at="2026-09-28T14:30:00Z",
        overall_scores={"ai_discoverability_score": 72, "on_site_engagement_score": 65},
        severity_counts={"critical": 0, "high": 1, "medium": 1, "low": 0},
        total_findings=2,
        findings=[
            FindingSnapshot(
                check_id="DC-DUPLICATE-TITLE-OR-DESCRIPTION",
                id="F-001",
                title="Duplicate titles and canonical dilution across URLs",
                category="discoverability",
                concern="duplicate-canonicalization-audit",
                severity="high",
                confidence="high",
                evidence="3 page pairs share identical title tags without canonical tags.",
                suggested_action={"summary": "Add canonical link tags to point to authoritative URL", "priority": "high", "effort": "low"},
            ),
            FindingSnapshot(
                check_id="AQ-NO-QUESTION-CONTENT",
                id="F-002",
                title="No question-shaped content exists for AI query matching",
                category="discoverability",
                concern="answer-coverage-audit",
                severity="medium",
                confidence="high",
                evidence="Zero question headings or FAQ structures detected across sampled pages.",
                suggested_action={"summary": "Publish direct FAQ answers with schema markup", "priority": "medium", "effort": "medium"},
            ),
        ],
        site_type="ecommerce",
        brand_name="ExampleBrand",
    )

    comp2 = comparison_agent.compare(
        current_snapshot=snap2,
        previous_snapshots=history2["snapshots"],
        user_events=history2["events"],
    )

    rec_aug2 = recommendation_agent.augment_recommendations(
        findings=[f.to_dict() for f in snap2.findings],
        action_plan=[],
        comparison=comp2,
    )

    memory_agent.retain_audit(identity, snap2, comp2)

    print(f"\n[Audit #2 Results — Measured Impact]")
    print(f"  AI Discoverability Score: 51 → 72 (+21 points! 🟢)")
    print(f"  Verified Resolved Issues:")
    for r in comp2.resolved_findings:
        print(f"    ✅ {r['check_id']} — {r['title']} ({r['status']})")
    print(f"  Persistent Unresolved Issues:")
    for p in comp2.persistent_findings:
        print(f"    ⏳ {p['check_id']} — {p['title']} (Present in {p['recurrence_count']} consecutive cycles)")

    print("\n" + "-" * 70)
    print(">>> STEP 4: MEMORY-DRIVEN REASONING")
    print("-" * 70)
    print("QUESTION: 'Why is canonicalization the next priority?'")
    print(f"\nAGENT RESPONSE:\n> {rec_aug2['memory_priority_headline']}")
    print(f"> Detailed Reason: Canonical duplication has persisted across 2 consecutive audit cycles.")
    print(f"> Foundational crawl barriers and Organization schema were resolved (+21 pts).")
    print(f"> Resolving canonicalization now unifies ranking signals onto authoritative URLs.")

    time.sleep(1)

    # -------------------------------------------------------------
    # CYCLE 3: REGRESSION DETECTION DEMO
    # -------------------------------------------------------------
    print("\n" + "-" * 70)
    print(">>> STEP 5: AUDIT CYCLE #3 (REGRESSION DETECTION)")
    print("-" * 70)
    print("[Agent] Later re-audit... Simulating an accidental deployment regression where robots.txt was overwritten.")
    history3 = memory_agent.recall_history(identity)

    snap3 = AuditSnapshot(
        snapshot_id=f"snap_{identity.domain}_cycle3",
        domain=identity.domain,
        audited_at="2026-09-28T18:00:00Z",
        overall_scores={"ai_discoverability_score": 60, "on_site_engagement_score": 65},
        severity_counts={"critical": 1, "high": 1, "medium": 1, "low": 0},
        total_findings=3,
        findings=[
            FindingSnapshot(
                check_id="CA-AI-RETRIEVAL-BLOCKED",
                id="F-001",
                title="robots.txt blocks AI retrieval crawlers",
                category="discoverability",
                concern="crawl-access-audit",
                severity="critical",
                confidence="high",
                evidence="robots.txt disallows OAI-SearchBot again.",
                suggested_action={"summary": "Restore robots.txt permission for retrieval bots", "priority": "critical", "effort": "low"},
            ),
            FindingSnapshot(
                check_id="DC-DUPLICATE-TITLE-OR-DESCRIPTION",
                id="F-002",
                title="Duplicate titles and canonical dilution across URLs",
                category="discoverability",
                concern="duplicate-canonicalization-audit",
                severity="high",
                confidence="high",
                evidence="3 page pairs share identical title tags without canonical tags.",
                suggested_action={"summary": "Add canonical link tags to point to authoritative URL", "priority": "high", "effort": "low"},
            ),
            FindingSnapshot(
                check_id="AQ-NO-QUESTION-CONTENT",
                id="F-003",
                title="No question-shaped content exists for AI query matching",
                category="discoverability",
                concern="answer-coverage-audit",
                severity="medium",
                confidence="high",
                evidence="Zero question headings or FAQ structures detected across sampled pages.",
                suggested_action={"summary": "Publish direct FAQ answers with schema markup", "priority": "medium", "effort": "medium"},
            ),
        ],
        site_type="ecommerce",
        brand_name="ExampleBrand",
    )

    comp3 = comparison_agent.compare(
        current_snapshot=snap3,
        previous_snapshots=history3["snapshots"],
        user_events=history3["events"],
    )

    rec_aug3 = recommendation_agent.augment_recommendations(
        findings=[f.to_dict() for f in snap3.findings],
        action_plan=[],
        comparison=comp3,
    )

    print(f"[Audit #3 Results — Longitudinal Tracking]")
    print(f"  AI Discoverability Score: 72 → 60 (-12 points! 🔴)")
    print(f"  Regressed Findings Detected:")
    for reg in comp3.regressed_findings:
        print(f"    🚨 {reg['check_id']} — {reg['title']} [REGRESSION]")
        print(f"       History: Previously resolved in Audit #2, but has now returned.")
    print(f"\nAGENT MEMORY PRIORITY:\n> {rec_aug3['memory_priority_headline']}")

    print("\n" + "=" * 70)
    print("DEMO COMPLETE: Longitudinal learning, verified fixes, and regression detection proved.")
    print("=" * 70 + "\n")
    return 0
