#!/usr/bin/env python3
"""End-to-end driver: crawl once, run every skill's checks, compose one report.

This is the deterministic backbone the entrypoint skill invokes. The agent still
does the parts that need judgement (the off-site protocol, reading the sampled
pages as a visitor would) and merges those findings via --agent-findings.

Usage:
    python3 run_audit.py https://example.com --out ./audit [--max-pages 30]
"""

import argparse
import json
import os
import subprocess
import sys
import time

QUIET = False
HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = os.path.dirname(os.path.dirname(HERE))        # .../skills
CHECKS = [
    ("crawl-access-audit", "check_access.py"),
    ("render-extractability-audit", "check_render.py"),
    ("structured-data-audit", "check_schema.py"),
    ("corroboration-freshness-audit", "check_freshness.py"),
    ("engagement-audit", "check_engagement.py"),
    ("site-architecture-audit", "check_architecture.py"),
    ("answer-coverage-audit", "check_answers.py"),
    ("trust-legitimacy-audit", "check_trust.py"),
    ("duplicate-canonicalization-audit", "check_duplicates.py"),
    ("local-presence-audit", "check_local.py"),
]


if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def sh(cmd, stream_err=False):
    """Run a step. stream_err lets a child's progress reach the terminal live."""
    r = subprocess.run(cmd, stdout=subprocess.PIPE, text=True,
                       stderr=None if stream_err else subprocess.PIPE)
    return r.returncode, r.stdout, r.stderr


def say(msg):
    """Status on stderr; stdout stays the JSON summary a caller can parse."""
    if not QUIET:
        print(msg, file=sys.stderr, flush=True)


def main():
    ap = argparse.ArgumentParser(description="AI Visibility & Citation Audit with Longitudinal Memory")
    ap.add_argument("url")
    ap.add_argument("--out", default="./audit")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--budget", type=int, default=210)
    ap.add_argument("--render", choices=["auto", "off"], default="auto")
    ap.add_argument("--agent-findings", help="JSON of findings the agent produced")
    ap.add_argument("--quiet", action="store_true", help="suppress progress on stderr")
    ap.add_argument("--no-history", action="store_true", help="disable longitudinal memory tracking")
    ap.add_argument("--history-only", action="store_true", help="display historical audit memory for site and exit")
    ap.add_argument("--record-fix", help="record user confirmation of a fixed check_id and exit")
    ap.add_argument("--notes", default="", help="notes for user-confirmed fix")
    a = ap.parse_args()

    global QUIET
    QUIET = a.quiet

    ROOT = os.path.dirname(SKILLS)
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    if a.history_only:
        from nexora.identity import WebsiteIdentity
        from nexora.memory.agent import MemoryAgent
        ident = WebsiteIdentity(a.url)
        ma = MemoryAgent()
        hist = ma.recall_history(ident)
        print(json.dumps({
            "domain": ident.domain,
            "bank_id": ident.bank_id,
            "audit_count": hist["audit_count"],
            "snapshots": [s.to_dict() for s in hist["snapshots"]],
            "events": [e.to_dict() for e in hist["events"]],
        }, indent=2))
        return 0

    if a.record_fix:
        from nexora.identity import WebsiteIdentity
        from nexora.memory.agent import MemoryAgent
        ident = WebsiteIdentity(a.url)
        ma = MemoryAgent()
        ev = ma.record_user_fix(ident, a.record_fix, notes=a.notes or "")
        print(json.dumps(ev.to_dict(), indent=2))
        return 0

    t0 = time.time()
    bundle = os.path.join(a.out, "bundle")
    os.makedirs(a.out, exist_ok=True)

    say("\nAuditing %s" % a.url)
    say("\nStage 1/3  Crawl  (one request at a time, %.1fs apart)" % a.delay)
    crawl_cmd = [sys.executable, os.path.join(HERE, "crawl.py"), a.url,
                 "--out", bundle, "--max-pages", str(a.max_pages),
                 "--delay", str(a.delay), "--budget", str(a.budget), "--render", a.render]
    if a.quiet:
        crawl_cmd.append("--quiet")
    rc, so, se = sh(crawl_cmd, stream_err=not a.quiet)
    if rc != 0:
        print("crawl failed:\n" + (se or ""), file=sys.stderr)
        return 1

    say("\nStage 2/3  Analyse  (reads the bundle, no further requests)")
    sh([sys.executable, os.path.join(HERE, "profile.py"), "--bundle", bundle])
    say("  site profiled")

    produced, failed = [], []
    for i, (skill, script) in enumerate(CHECKS, 1):
        path = os.path.join(SKILLS, skill, "scripts", script)
        dest = os.path.join(a.out, "findings-%s.json" % skill)
        rc, so, se = sh([sys.executable, path, "--bundle", bundle, "--json-out", dest])
        if rc == 0 and os.path.exists(dest):
            produced.append(dest)
            try:
                with open(dest, encoding="utf-8") as dfh:
                    n = len(json.load(dfh).get("findings", []))
            except Exception:
                n = "?"
            say("  [%d/%d] %-30s %s finding(s)" % (i, len(CHECKS), skill, n))
        else:
            failed.append((skill, se.strip().splitlines()[-1] if se.strip() else "unknown error"))
            say("  [%d/%d] %-30s FAILED" % (i, len(CHECKS), skill))

    say("\nStage 3/3  Compose report")

    cmd = [sys.executable, os.path.join(HERE, "compose_report.py"), "--bundle", bundle,
           "--findings"] + produced + [
           "--out", os.path.join(a.out, "report.json"),
           "--markdown", os.path.join(a.out, "report.md")]
    if a.agent_findings:
        cmd += ["--agent-findings", a.agent_findings]
    rc, so, se = sh(cmd)
    if rc != 0:
        print("compose failed:\n" + se, file=sys.stderr)
        return 1

    with open(os.path.join(a.out, "report.json"), encoding="utf-8") as fh:
        report = json.load(fh)

    # Longitudinal memory & comparison integration
    hist_summary = {}
    if not a.no_history:
        try:
            from nexora.identity import WebsiteIdentity
            from nexora.models import AuditSnapshot
            from nexora.memory.agent import MemoryAgent
            from nexora.analysis.comparison import ComparisonAgent
            from nexora.recommendations.agent import RecommendationAgent
            from nexora.reporting.historical_report import augment_report, to_historical_markdown

            ident = WebsiteIdentity(a.url)
            ma = MemoryAgent()
            hist = ma.recall_history(ident)
            snap = AuditSnapshot.from_report(report)
            ca = ComparisonAgent()
            comp = ca.compare(snap, hist.get("snapshots", []), hist.get("events", []))
            ra = RecommendationAgent()
            rec_aug = ra.augment_recommendations(report.get("findings", []), report.get("action_plan", []), comp)
            final_rep = augment_report(report, comp, rec_aug)

            with open(os.path.join(a.out, "report.json"), "w", encoding="utf-8") as fh:
                json.dump(final_rep, fh, indent=2)
            with open(os.path.join(a.out, "report.md"), "w", encoding="utf-8") as fh:
                fh.write(to_historical_markdown(final_rep))

            ma.retain_audit(ident, snap, comp)
            report = final_rep
            hist_summary = {
                "audit_number": comp.audit_number,
                "is_first_audit": comp.is_first_audit,
                "score_changes": comp.score_changes,
                "memory_priority": rec_aug.get("memory_priority_headline", ""),
            }
        except Exception as e:
            say(f"  [Notice] Longitudinal memory step: {e}")

    say("  wrote %s and report.md\n" % os.path.join(a.out, "report.json"))
    out_obj = {
        "site": report["site"],
        "summary": report["summary"],
        "skills_run": [s for s, _ in CHECKS if not any(s == f[0] for f in failed)],
        "skills_failed": failed,
        "report_json": os.path.join(a.out, "report.json"),
        "report_markdown": os.path.join(a.out, "report.md"),
        "total_seconds": round(time.time() - t0, 1),
    }
    if hist_summary:
        out_obj["historical_memory"] = hist_summary
    print(json.dumps(out_obj, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
