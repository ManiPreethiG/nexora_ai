"""Nexora AI Master Orchestrator.

Coordinates:
  1. Pre-audit Recall via MemoryAgent
  2. Deterministic Audit Execution via existing orchestrator
  3. Longitudinal Comparison & Regression Detection via ComparisonAgent
  4. Memory-Aware Recommendation Prioritization via RecommendationAgent
  5. Report Augmentation & Markdown Generation
  6. Durable Memory Retention to Hindsight
"""

import os
import sys
import json
import time
import logging
import subprocess
from typing import Dict, Any, Optional, List

from nexora.identity import WebsiteIdentity, extract_domain
from nexora.models import AuditSnapshot, AuditComparison
from nexora.memory.hindsight_client import HindsightMemoryClient
from nexora.memory.agent import MemoryAgent
from nexora.analysis.comparison import ComparisonAgent
from nexora.recommendations.agent import RecommendationAgent
from nexora.reporting.historical_report import augment_report, to_historical_markdown

logger = logging.getLogger("nexora.orchestrator")


class NexoraOrchestrator:
    """Master agent workflow coordinator for Nexora AI."""

    def __init__(
        self,
        hindsight_client: Optional[HindsightMemoryClient] = None,
        base_dir: Optional[str] = None,
    ):
        self.base_dir = base_dir or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.memory_agent = MemoryAgent(hindsight_client)
        self.comparison_agent = ComparisonAgent()
        self.recommendation_agent = RecommendationAgent()

    def run(
        self,
        url: str,
        out_dir: str = "./audit",
        max_pages: int = 30,
        delay: float = 1.0,
        budget: int = 210,
        render: str = "auto",
        agent_findings: Optional[str] = None,
        quiet: bool = False,
        enable_history: bool = True,
    ) -> Dict[str, Any]:
        """Execute the end-to-end memory-aware audit workflow."""
        t0 = time.time()
        os.makedirs(out_dir, exist_ok=True)

        identity = WebsiteIdentity(url)
        if not quiet:
            print(f"\n=======================================================", file=sys.stderr)
            print(f"Nexora AI — AI Visibility & Citation Optimization Agent", file=sys.stderr)
            print(f"Auditing: {url} (Domain: {identity.domain})", file=sys.stderr)
            print(f"Memory Bank: {identity.bank_id} | Hindsight: {'LIVE' if self.memory_agent.client.is_live else 'OFFLINE (Local Snapshot Cache)'}", file=sys.stderr)
            print(f"=======================================================\n", file=sys.stderr)

        # ---------------------------------------------------------
        # Phase 1: Pre-Audit Memory Recall
        # ---------------------------------------------------------
        if not quiet:
            print("[Stage 1/5] Recalling historical memory from Hindsight...", file=sys.stderr)

        history_context = {"is_first_audit": True, "snapshots": [], "events": []}
        if enable_history:
            history_context = self.memory_agent.recall_history(identity)
            prev_count = history_context.get("audit_count", 0)
            if history_context.get("is_first_audit"):
                if not quiet:
                    print(f"  → First recorded audit for {identity.domain}. Establishing baseline.", file=sys.stderr)
            else:
                if not quiet:
                    print(f"  → Retrieved {prev_count} prior audit(s) and {len(history_context.get('events', []))} user action(s).", file=sys.stderr)

        # ---------------------------------------------------------
        # Phase 2: Execute Core Deterministic Audit Engine
        # ---------------------------------------------------------
        if not quiet:
            print("\n[Stage 2/5] Running core multi-skill audit engine...", file=sys.stderr)

        orch_script = os.path.join(self.base_dir, "skills", "audit-orchestrator", "scripts", "run_audit.py")
        cmd = [
            sys.executable, orch_script, url,
            "--out", out_dir,
            "--max-pages", str(max_pages),
            "--delay", str(delay),
            "--budget", str(budget),
            "--render", render,
        ]
        if agent_findings:
            cmd += ["--agent-findings", agent_findings]
        if quiet:
            cmd.append("--quiet")

        # Execute existing orchestrator to preserve 100% of existing behavior and safety boundaries
        sub_res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=None if not quiet else subprocess.PIPE, text=True)
        if sub_res.returncode != 0:
            err_msg = sub_res.stderr or "audit failed"
            raise RuntimeError(f"Audit engine execution failed: {err_msg}")

        # Load generated report.json
        report_json_path = os.path.join(out_dir, "report.json")
        with open(report_json_path, "r", encoding="utf-8") as f:
            base_report = json.load(f)

        # ---------------------------------------------------------
        # Phase 3: Longitudinal Comparison & Regression Analysis
        # ---------------------------------------------------------
        if not quiet:
            print("\n[Stage 3/5] Performing longitudinal comparison...", file=sys.stderr)

        curr_snapshot = AuditSnapshot.from_report(base_report)
        comparison = self.comparison_agent.compare(
            current_snapshot=curr_snapshot,
            previous_snapshots=history_context.get("snapshots", []),
            user_events=history_context.get("events", []),
        )

        if not quiet:
            if comparison.is_first_audit:
                print("  → Baseline scores recorded: Discoverability %d, Engagement %d" % (
                    curr_snapshot.overall_scores.get("ai_discoverability_score", 0),
                    curr_snapshot.overall_scores.get("on_site_engagement_score", 0),
                ), file=sys.stderr)
            else:
                disc_d = comparison.score_changes.get("ai_discoverability_delta", 0)
                print(f"  → Score Changes: AI Discoverability {disc_d:+d} pts | Total Findings {comparison.score_changes.get('total_findings_delta', 0):+d}", file=sys.stderr)
                print(f"  → Resolved: {len(comparison.resolved_findings)} | Persistent: {len(comparison.persistent_findings)} | Regressed: {len(comparison.regressed_findings)} | New: {len(comparison.new_findings)}", file=sys.stderr)

        # ---------------------------------------------------------
        # Phase 4: Memory-Aware Recommendation Prioritization
        # ---------------------------------------------------------
        if not quiet:
            print("\n[Stage 4/5] Synthesizing memory-aware recommendations...", file=sys.stderr)

        rec_aug = self.recommendation_agent.augment_recommendations(
            findings=base_report.get("findings", []),
            action_plan=base_report.get("action_plan", []),
            comparison=comparison,
        )

        # Augment report JSON and write markdown
        final_report = augment_report(base_report, comparison, rec_aug)
        report_md_path = os.path.join(out_dir, "report.md")

        with open(report_json_path, "w", encoding="utf-8") as f:
            json.dump(final_report, f, indent=2)

        with open(report_md_path, "w", encoding="utf-8") as f:
            f.write(to_historical_markdown(final_report))

        if not quiet:
            print(f"  → Updated {report_json_path} and {report_md_path}", file=sys.stderr)

        # ---------------------------------------------------------
        # Phase 5: Retain Learning & Durable Knowledge in Hindsight
        # ---------------------------------------------------------
        if enable_history:
            if not quiet:
                print("\n[Stage 5/5] Retaining audit outcomes in Hindsight memory...", file=sys.stderr)
            self.memory_agent.retain_audit(identity, curr_snapshot, comparison)
            if not quiet:
                print(f"  → Durable audit knowledge stored for {identity.domain}.", file=sys.stderr)

        elapsed = round(time.time() - t0, 1)
        if not quiet:
            print(f"\nAudit completed in {elapsed}s.\n", file=sys.stderr)

        result_summary = {
            "site": final_report["site"],
            "audit_number": comparison.audit_number,
            "is_first_audit": comparison.is_first_audit,
            "scores": curr_snapshot.overall_scores,
            "score_changes": comparison.score_changes,
            "resolved_count": len(comparison.resolved_findings),
            "persistent_count": len(comparison.persistent_findings),
            "regressed_count": len(comparison.regressed_findings),
            "new_count": len(comparison.new_findings),
            "memory_priority": rec_aug.get("memory_priority_headline", ""),
            "report_json": report_json_path,
            "report_markdown": report_md_path,
            "total_seconds": elapsed,
        }

        return result_summary


CiteTrailOrchestrator = NexoraOrchestrator
