#!/usr/bin/env python3
"""Comprehensive unit and scenario test suite for Nexora AI.

Covers:
  - Scenario A: First audit baseline (no prior history)
  - Scenario B: Resolved issue detection
  - Scenario C: Persistent issue tracking across cycles
  - Scenario D: Newly detected issue
  - Scenario E: Regression detection across longitudinal sequence
  - Scenario F: Score delta calculation and impact observation
  - Scenario G: User-confirmed implementation event tracking vs observed state
  - URL normalization and bank_id identity resolution
  - MemoryAgent recall, retention, and offline fallback
  - RecommendationAgent memory-aware priority synthesis
"""

import os
import sys
import shutil
import tempfile
import unittest
import datetime as dt

# Add project root to sys.path
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from nexora.identity import WebsiteIdentity, normalize_url, extract_domain, derive_bank_id
from nexora.models import (
    AuditSnapshot,
    FindingSnapshot,
    ImplementationEvent,
    AuditComparison,
    ImpactObservation,
)
from nexora.memory.hindsight_client import HindsightMemoryClient
from nexora.memory.agent import MemoryAgent
from nexora.analysis.comparison import ComparisonAgent
from nexora.recommendations.agent import RecommendationAgent
from nexora.reporting.historical_report import augment_report, to_historical_markdown


class TestNexoraIdentity(unittest.TestCase):
    """Test URL normalization and website memory identity resolution."""

    def test_domain_normalization(self):
        self.assertEqual(extract_domain("https://www.allbirds.com/"), "allbirds.com")
        self.assertEqual(extract_domain("http://allbirds.com"), "allbirds.com")
        self.assertEqual(extract_domain("https://www.example.org:443/products/"), "example.org")

    def test_bank_id_stability(self):
        id1 = derive_bank_id("https://www.example.com")
        id2 = derive_bank_id("http://example.com/subpath")
        self.assertEqual(id1, "site_example_com")
        self.assertEqual(id1, id2)

    def test_website_identity_object(self):
        w = WebsiteIdentity("https://www.my-brand.co.uk/")
        self.assertEqual(w.domain, "my-brand.co.uk")
        self.assertEqual(w.bank_id, "site_my_brand_co_uk")


class TestNexoraScenarios(unittest.TestCase):
    """Test core longitudinal audit scenarios A through G."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="nexora_unit_")
        self.hindsight_client = HindsightMemoryClient(storage_dir=self.temp_dir)
        self.memory_agent = MemoryAgent(self.hindsight_client)
        self.comparison_agent = ComparisonAgent()
        self.recommendation_agent = RecommendationAgent()
        self.identity = WebsiteIdentity("https://test-site.com")

    def tearDown(self):
        self.hindsight_client.close()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_scenario_a_first_audit(self):
        """Scenario A: First audit baseline with no prior history."""
        snap = AuditSnapshot(
            snapshot_id="snap_1",
            domain=self.identity.domain,
            audited_at="2026-09-28T10:00:00Z",
            overall_scores={"ai_discoverability_score": 50, "on_site_engagement_score": 60},
            severity_counts={"critical": 1, "high": 1, "medium": 0, "low": 0},
            total_findings=2,
            findings=[
                FindingSnapshot(
                    check_id="CA-AI-RETRIEVAL-BLOCKED",
                    id="F-001",
                    title="robots.txt blocks AI",
                    category="discoverability",
                    concern="crawl-access-audit",
                    severity="critical",
                    confidence="high",
                    evidence="robots.txt disallow",
                )
            ],
        )

        comparison = self.comparison_agent.compare(current_snapshot=snap, previous_snapshots=[])
        self.assertTrue(comparison.is_first_audit)
        self.assertEqual(comparison.audit_number, 1)
        self.assertEqual(comparison.score_changes["ai_discoverability_delta"], 0)
        self.assertEqual(len(comparison.resolved_findings), 0)
        self.assertEqual(len(comparison.persistent_findings), 0)
        self.assertEqual(len(comparison.regressed_findings), 0)

        # Retain baseline in memory
        retained = self.memory_agent.retain_audit(self.identity, snap, comparison)
        self.assertTrue(os.path.exists(os.path.join(self.temp_dir, "snapshots", self.identity.bank_id, "snap_1.json")))

    def test_scenario_b_resolved_issue(self):
        """Scenario B: Resolved issue detection (present previously, absent now)."""
        snap1 = AuditSnapshot(
            snapshot_id="snap_1",
            domain=self.identity.domain,
            audited_at="2026-09-28T10:00:00Z",
            overall_scores={"ai_discoverability_score": 50, "on_site_engagement_score": 60},
            severity_counts={"critical": 1, "high": 0, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="CA-AI-RETRIEVAL-BLOCKED",
                    id="F-001",
                    title="robots.txt blocks AI",
                    category="discoverability",
                    concern="crawl-access-audit",
                    severity="critical",
                    confidence="high",
                    evidence="Disallow /",
                )
            ],
        )
        snap2 = AuditSnapshot(
            snapshot_id="snap_2",
            domain=self.identity.domain,
            audited_at="2026-09-28T12:00:00Z",
            overall_scores={"ai_discoverability_score": 75, "on_site_engagement_score": 60},
            severity_counts={"critical": 0, "high": 0, "medium": 0, "low": 0},
            total_findings=0,
            findings=[],
        )

        comp = self.comparison_agent.compare(current_snapshot=snap2, previous_snapshots=[snap1])
        self.assertFalse(comp.is_first_audit)
        self.assertEqual(len(comp.resolved_findings), 1)
        self.assertEqual(comp.resolved_findings[0]["check_id"], "CA-AI-RETRIEVAL-BLOCKED")
        self.assertEqual(comp.resolved_findings[0]["status"], "observed_resolved")

    def test_scenario_c_persistent_issue(self):
        """Scenario C: Persistent issue tracking across multiple cycles."""
        snap1 = AuditSnapshot(
            snapshot_id="snap_1",
            domain=self.identity.domain,
            audited_at="2026-09-28T10:00:00Z",
            overall_scores={"ai_discoverability_score": 60, "on_site_engagement_score": 60},
            severity_counts={"critical": 0, "high": 1, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="DC-DUPLICATE-TITLE-OR-DESCRIPTION",
                    id="F-001",
                    title="Duplicate titles",
                    category="discoverability",
                    concern="duplicate-canonicalization-audit",
                    severity="high",
                    confidence="high",
                    evidence="2 pairs share title",
                )
            ],
        )
        snap2 = AuditSnapshot(
            snapshot_id="snap_2",
            domain=self.identity.domain,
            audited_at="2026-09-28T12:00:00Z",
            overall_scores={"ai_discoverability_score": 60, "on_site_engagement_score": 60},
            severity_counts={"critical": 0, "high": 1, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="DC-DUPLICATE-TITLE-OR-DESCRIPTION",
                    id="F-001",
                    title="Duplicate titles",
                    category="discoverability",
                    concern="duplicate-canonicalization-audit",
                    severity="high",
                    confidence="high",
                    evidence="2 pairs share title",
                )
            ],
        )

        comp = self.comparison_agent.compare(current_snapshot=snap2, previous_snapshots=[snap1])
        self.assertEqual(len(comp.persistent_findings), 1)
        self.assertEqual(comp.persistent_findings[0]["check_id"], "DC-DUPLICATE-TITLE-OR-DESCRIPTION")
        self.assertEqual(comp.persistent_findings[0]["recurrence_count"], 2)

    def test_scenario_d_new_issue(self):
        """Scenario D: Newly detected defect not present previously."""
        snap1 = AuditSnapshot(
            snapshot_id="snap_1",
            domain=self.identity.domain,
            audited_at="2026-09-28T10:00:00Z",
            overall_scores={"ai_discoverability_score": 80, "on_site_engagement_score": 80},
            severity_counts={"critical": 0, "high": 0, "medium": 0, "low": 0},
            total_findings=0,
            findings=[],
        )
        snap2 = AuditSnapshot(
            snapshot_id="snap_2",
            domain=self.identity.domain,
            audited_at="2026-09-28T12:00:00Z",
            overall_scores={"ai_discoverability_score": 68, "on_site_engagement_score": 80},
            severity_counts={"critical": 0, "high": 1, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="SD-NO-ORGANIZATION",
                    id="F-001",
                    title="No Organization structured data",
                    category="discoverability",
                    concern="structured-data-audit",
                    severity="high",
                    confidence="high",
                    evidence="Missing JSON-LD",
                )
            ],
        )

        comp = self.comparison_agent.compare(current_snapshot=snap2, previous_snapshots=[snap1])
        self.assertEqual(len(comp.new_findings), 1)
        self.assertEqual(comp.new_findings[0]["check_id"], "SD-NO-ORGANIZATION")
        self.assertEqual(comp.new_findings[0]["status"], "new")

    def test_scenario_e_regression(self):
        """Scenario E: Regression detection (present in #1, resolved in #2, reappears in #3)."""
        snap1 = AuditSnapshot(
            snapshot_id="snap_1",
            domain=self.identity.domain,
            audited_at="2026-09-28T10:00:00Z",
            overall_scores={"ai_discoverability_score": 50, "on_site_engagement_score": 60},
            severity_counts={"critical": 1, "high": 0, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="CA-AI-RETRIEVAL-BLOCKED",
                    id="F-001",
                    title="robots.txt blocks AI",
                    category="discoverability",
                    concern="crawl-access-audit",
                    severity="critical",
                    confidence="high",
                    evidence="Disallow /",
                )
            ],
        )
        snap2 = AuditSnapshot(
            snapshot_id="snap_2",
            domain=self.identity.domain,
            audited_at="2026-09-28T12:00:00Z",
            overall_scores={"ai_discoverability_score": 75, "on_site_engagement_score": 60},
            severity_counts={"critical": 0, "high": 0, "medium": 0, "low": 0},
            total_findings=0,
            findings=[],
        )
        snap3 = AuditSnapshot(
            snapshot_id="snap_3",
            domain=self.identity.domain,
            audited_at="2026-09-28T14:00:00Z",
            overall_scores={"ai_discoverability_score": 50, "on_site_engagement_score": 60},
            severity_counts={"critical": 1, "high": 0, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="CA-AI-RETRIEVAL-BLOCKED",
                    id="F-001",
                    title="robots.txt blocks AI",
                    category="discoverability",
                    concern="crawl-access-audit",
                    severity="critical",
                    confidence="high",
                    evidence="Disallow /",
                )
            ],
        )

        comp = self.comparison_agent.compare(
            current_snapshot=snap3,
            previous_snapshots=[snap1, snap2],
        )
        self.assertEqual(len(comp.regressed_findings), 1)
        self.assertEqual(comp.regressed_findings[0]["check_id"], "CA-AI-RETRIEVAL-BLOCKED")
        self.assertEqual(comp.regressed_findings[0]["status"], "regression")

    def test_scenario_f_score_change_and_impact(self):
        """Scenario F: Score delta calculation (e.g. 62 -> 76 = +14) with non-causal language."""
        snap1 = AuditSnapshot(
            snapshot_id="snap_1",
            domain=self.identity.domain,
            audited_at="2026-09-28T10:00:00Z",
            overall_scores={"ai_discoverability_score": 62, "on_site_engagement_score": 70},
            severity_counts={"critical": 0, "high": 1, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="CA-AI-RETRIEVAL-BLOCKED",
                    id="F-001",
                    title="robots.txt blocks AI",
                    category="discoverability",
                    concern="crawl-access-audit",
                    severity="high",
                    confidence="high",
                    evidence="Disallow /",
                )
            ],
        )
        snap2 = AuditSnapshot(
            snapshot_id="snap_2",
            domain=self.identity.domain,
            audited_at="2026-09-28T12:00:00Z",
            overall_scores={"ai_discoverability_score": 76, "on_site_engagement_score": 70},
            severity_counts={"critical": 0, "high": 0, "medium": 0, "low": 0},
            total_findings=0,
            findings=[],
        )

        comp = self.comparison_agent.compare(current_snapshot=snap2, previous_snapshots=[snap1])
        self.assertEqual(comp.score_changes["ai_discoverability_delta"], 14)
        self.assertEqual(len(comp.impact_observations), 1)
        obs_text = comp.impact_observations[0].observation_text
        self.assertIn("14 points", obs_text)
        # Ensure careful non-causal language is used
        self.assertTrue("coincided with" in obs_text or "followed" in obs_text or "associated with" in obs_text)
        self.assertNotIn("caused", obs_text.lower())

    def test_scenario_g_user_confirmed_action(self):
        """Scenario G: User-confirmed implementation event stored distinctly from observed state."""
        # 1. User confirms fixing robots.txt
        event = self.memory_agent.record_user_fix(
            identity=self.identity,
            check_id="CA-AI-RETRIEVAL-BLOCKED",
            notes="Updated robots.txt on staging server and pushed to production.",
            action_summary="Allowed bots",
        )
        self.assertEqual(event.status, "user_confirmed")
        self.assertEqual(event.check_id, "CA-AI-RETRIEVAL-BLOCKED")

        # 2. Re-audit where the issue is indeed resolved
        snap1 = AuditSnapshot(
            snapshot_id="snap_1",
            domain=self.identity.domain,
            audited_at="2026-09-28T10:00:00Z",
            overall_scores={"ai_discoverability_score": 50, "on_site_engagement_score": 60},
            severity_counts={"critical": 1, "high": 0, "medium": 0, "low": 0},
            total_findings=1,
            findings=[
                FindingSnapshot(
                    check_id="CA-AI-RETRIEVAL-BLOCKED",
                    id="F-001",
                    title="robots.txt blocks AI",
                    category="discoverability",
                    concern="crawl-access-audit",
                    severity="critical",
                    confidence="high",
                    evidence="Disallow /",
                )
            ],
        )
        snap2 = AuditSnapshot(
            snapshot_id="snap_2",
            domain=self.identity.domain,
            audited_at="2026-09-28T12:00:00Z",
            overall_scores={"ai_discoverability_score": 75, "on_site_engagement_score": 60},
            severity_counts={"critical": 0, "high": 0, "medium": 0, "low": 0},
            total_findings=0,
            findings=[],
        )

        comp = self.comparison_agent.compare(
            current_snapshot=snap2,
            previous_snapshots=[snap1],
            user_events=[event],
        )
        self.assertEqual(len(comp.resolved_findings), 1)
        self.assertEqual(comp.resolved_findings[0]["status"], "user_confirmed_and_resolved")
        self.assertIn("staging server", comp.resolved_findings[0]["user_notes"])

    def test_memory_aware_recommendations(self):
        """Test that RecommendationAgent elevates persistent and regression issues."""
        comp = AuditComparison(
            is_first_audit=False,
            audit_number=2,
            previous_snapshot_id="snap_1",
            current_snapshot_id="snap_2",
            audited_at_prev="2026-09-28T10:00:00Z",
            audited_at_curr="2026-09-28T12:00:00Z",
            score_changes={"ai_discoverability_delta": 21, "on_site_engagement_delta": 0, "total_findings_delta": -2},
            resolved_findings=[{"check_id": "CA-AI-RETRIEVAL-BLOCKED", "title": "robots.txt"}],
            persistent_findings=[
                {"check_id": "DC-DUPLICATE-TITLE-OR-DESCRIPTION", "title": "Canonical Duplication", "recurrence_count": 2, "status": "persistent"}
            ],
            new_findings=[],
            regressed_findings=[],
            user_actions=[],
            impact_observations=[],
            learned_insights=[],
        )

        findings = [{
            "id": "F-001",
            "check_id": "DC-DUPLICATE-TITLE-OR-DESCRIPTION",
            "title": "Canonical Duplication",
            "severity": "medium",
            "suggested_action": {"summary": "Fix canonicals", "priority": "medium", "effort": "low"},
        }]

        plan = [{
            "stage": "Not diluted",
            "why_this_order": "reason",
            "actions": [{"finding_id": "F-001", "severity": "medium", "effort": "low", "action": "Fix canonicals"}],
        }]

        augmented = self.recommendation_agent.augment_recommendations(findings, plan, comp)
        self.assertIn("DC-DUPLICATE-TITLE-OR-DESCRIPTION", augmented["memory_priority_headline"])
        self.assertIn("2 audit cycles", augmented["memory_priority_headline"])
        self.assertEqual(augmented["findings"][0]["historical_status"], "persistent")


if __name__ == "__main__":
    unittest.main()
