#!/usr/bin/env python3
"""Nexora AI — AI Visibility & Citation Optimization Agent with Hindsight Memory.

Command Line Interface:
  audit         Run an AI visibility audit with longitudinal memory and regression analysis
  history       Retrieve historical memory, audit trends, and Hindsight reflections for a site
  record-fix    Log user confirmation that a recommended fix was implemented
  compare       Compare two audit report folders or snapshots
  demo/simulate Run the end-to-end multi-cycle simulation demonstrating continuous learning
"""

import os
import sys
import json
import argparse
import datetime as dt

# Ensure package root is in python path
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from nexora.identity import WebsiteIdentity, extract_domain
from nexora.models import AuditSnapshot
from nexora.memory.hindsight_client import HindsightMemoryClient
from nexora.memory.agent import MemoryAgent
from nexora.analysis.comparison import ComparisonAgent
from nexora.orchestrator import NexoraOrchestrator


def cmd_audit(args):
    """Run an audit with longitudinal memory."""
    orch = NexoraOrchestrator(base_dir=HERE)
    result = orch.run(
        url=args.url,
        out_dir=args.out,
        max_pages=args.max_pages,
        delay=args.delay,
        budget=args.budget,
        render=args.render,
        agent_findings=args.agent_findings,
        quiet=args.quiet,
        enable_history=not args.no_history,
    )
    print(json.dumps(result, indent=2))
    return 0


def cmd_history(args):
    """Retrieve historical memory and audit sequence for a site."""
    identity = WebsiteIdentity(args.url)
    memory_agent = MemoryAgent()
    history = memory_agent.recall_history(identity)

    snapshots = history.get("snapshots", [])
    events = history.get("events", [])

    print(f"\n=======================================================")
    print(f"Nexora AI Historical Memory — {identity.domain}")
    print(f"Bank ID: {identity.bank_id} | Backend: {'Hindsight (Live)' if history.get('hindsight_live') else 'Local Cache'}")
    print(f"Recorded Audits: {len(snapshots)} | Recorded User Fixes: {len(events)}")
    print(f"=======================================================\n")

    if not snapshots:
        print(f"No prior audits recorded for {identity.domain}.")
        print("Run 'python nexora.py audit <URL>' to establish baseline memory.")
        return 0

    print("Audit History Timeline:")
    print("-----------------------")
    for i, s in enumerate(snapshots, 1):
        disc = s.overall_scores.get("ai_discoverability_score", 0)
        eng = s.overall_scores.get("on_site_engagement_score", 0)
        print(f"  Cycle #{i} | {s.audited_at} | Discoverability: {disc}/100 | Engagement: {eng}/100 | Findings: {s.total_findings}")

    if events:
        print("\nUser-Confirmed Implementations:")
        print("-------------------------------")
        for e in events:
            print(f"  [{e.recorded_at}] Fix recorded for '{e.check_id}': {e.notes or 'No notes'}")

    # Ask Hindsight for reflective summary if live
    if history.get("hindsight_live"):
        print("\nHindsight Reflective Synthesis:")
        print("------------------------------")
        reflection = memory_agent.reflect_on_history(identity)
        if reflection:
            print(reflection)
        else:
            print("No reflection available.")

    print("")
    return 0


def cmd_record_fix(args):
    """Log a user-confirmed implementation action."""
    identity = WebsiteIdentity(args.url)
    memory_agent = MemoryAgent()
    event = memory_agent.record_user_fix(
        identity=identity,
        check_id=args.fix,
        notes=args.notes or "",
        action_summary=args.summary or "",
    )
    print(f"\n[Recorded] User implementation logged for {identity.domain}:")
    print(f"  Check ID: {event.check_id}")
    print(f"  Timestamp: {event.recorded_at}")
    print(f"  Notes: {event.notes}")
    print("Future audits will automatically verify if this finding remains detected or is resolved.\n")
    return 0


def cmd_compare(args):
    """Compare two audit report directories."""
    path1 = os.path.join(args.audit1, "report.json") if os.path.isdir(args.audit1) else args.audit1
    path2 = os.path.join(args.audit2, "report.json") if os.path.isdir(args.audit2) else args.audit2

    if not os.path.exists(path1):
        print(f"Error: {path1} not found", file=sys.stderr)
        return 1
    if not os.path.exists(path2):
        print(f"Error: {path2} not found", file=sys.stderr)
        return 1

    with open(path1, "r", encoding="utf-8") as f:
        rep1 = json.load(f)
    with open(path2, "r", encoding="utf-8") as f:
        rep2 = json.load(f)

    snap1 = AuditSnapshot.from_report(rep1)
    snap2 = AuditSnapshot.from_report(rep2)

    comp_agent = ComparisonAgent()
    comparison = comp_agent.compare(current_snapshot=snap2, previous_snapshots=[snap1])

    print(json.dumps(comparison.to_dict(), indent=2))
    return 0


def cmd_demo(args):
    """Run an interactive demonstration of Nexora AI learning over time."""
    from nexora.demo import run_demo
    return run_demo(target_url=args.url)


def main():
    parser = argparse.ArgumentParser(
        description="Nexora AI — AI Visibility & Citation Optimization Agent with Hindsight Memory"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Command: audit
    p_audit = subparsers.add_parser("audit", help="Run an AI visibility audit with longitudinal memory")
    p_audit.add_argument("url", help="Target website URL")
    p_audit.add_argument("--out", default="./audit", help="Output directory for reports")
    p_audit.add_argument("--max-pages", type=int, default=30, help="Maximum pages to crawl")
    p_audit.add_argument("--delay", type=float, default=1.0, help="Politeness delay between requests")
    p_audit.add_argument("--budget", type=int, default=210, help="Crawl timeout in seconds")
    p_audit.add_argument("--render", choices=["auto", "off"], default="auto")
    p_audit.add_argument("--agent-findings", help="Path to supplemental agent findings JSON")
    p_audit.add_argument("--no-history", action="store_true", help="Disable longitudinal memory tracking")
    p_audit.add_argument("--quiet", action="store_true", help="Suppress progress output")

    # Command: history
    p_hist = subparsers.add_parser("history", help="View historical audit timeline and Hindsight memory")
    p_hist.add_argument("url", help="Target website URL or domain")

    # Command: record-fix
    p_fix = subparsers.add_parser("record-fix", help="Log a user-confirmed implementation action")
    p_fix.add_argument("url", help="Target website URL")
    p_fix.add_argument("--fix", required=True, help="Check ID that was fixed (e.g. CA-AI-RETRIEVAL-BLOCKED)")
    p_fix.add_argument("--notes", default="", help="User implementation notes or details")
    p_fix.add_argument("--summary", default="", help="Short action summary")

    # Command: compare
    p_comp = subparsers.add_parser("compare", help="Compare two audit reports")
    p_comp.add_argument("--audit1", required=True, help="Path to previous audit folder or report.json")
    p_comp.add_argument("--audit2", required=True, help="Path to current audit folder or report.json")

    # Command: demo / simulate
    p_demo = subparsers.add_parser("demo", help="Run a multi-cycle simulation demonstrating continuous learning and regression tracking", aliases=["simulate"])
    p_demo.add_argument("--url", default="https://example.com", help="Simulated target URL")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 0

    dispatch = {
        "audit": cmd_audit,
        "history": cmd_history,
        "record-fix": cmd_record_fix,
        "compare": cmd_compare,
        "demo": cmd_demo,
        "simulate": cmd_demo,
    }

    return dispatch[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
