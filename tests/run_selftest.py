#!/usr/bin/env python3
"""Cross-platform Python test runner for the 27-defect seeded fixture site.

Guards against checks ceasing to fire and verifies end-to-end audit execution.
Usage:
    python tests/run_selftest.py
"""

import os
import sys
import json
import time
import shutil
import tempfile
import subprocess

EXPECTED_DEFECTS = [
    "CA-AI-RETRIEVAL-BLOCKED",
    "CA-SITEMAP-MISSING",
    "CA-NOINDEX-ON-CONTENT",
    "CA-NOSNIPPET",
    "CA-CANONICAL-TO-HOMEPAGE",
    "RX-CLIENT-RENDERED-SHELL",
    "RX-FACTS-LOCKED-IN-IMAGES",
    "RX-TABBED-CONTENT-NOT-IN-HTML",
    "RX-CONTENT-IN-IFRAME",
    "RX-NO-QUOTABLE-DEFINITION",
    "RX-CONTACT-DETAILS-NOT-IN-TEXT",
    "RX-MULTIPLE-H1",
    "SD-NONE",
    "CF-STALE-COPYRIGHT",
    "CF-UNSOURCED-CLAIMS",
    "CF-NO-OFFSITE-ANCHORS",
    "EN-NO-VIEWPORT-META",
    "EN-INTERRUPTING-OVERLAY",
    "EN-ACCESSIBILITY-BASELINE",
    "EN-GATED-FACTS",
    "SA-DEAD-END-PAGES",
    "AQ-NO-QUESTION-CONTENT",
    "AQ-NO-COMPARISON-CONTENT",
    "AQ-NO-OBJECTION-HANDLING",
    "TL-NO-LEGAL-PAGES-LINKED",
    "DC-DUPLICATE-TITLE-OR-DESCRIPTION",
    "DC-PARAM-VARIANT-NOT-CANONICALIZED",
]


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fixture_dir = os.path.join(root, "tests", "fixture-site")
    port = int(os.getenv("PORT", "8731"))
    temp_out = tempfile.mkdtemp(prefix="nexora_test_")

    print(f"Starting fixture HTTP server on port {port}...")
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port), "--directory", fixture_dir],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    try:
        time.sleep(1.5)
        audit_script = os.path.join(root, "skills", "audit-orchestrator", "scripts", "run_audit.py")
        cmd = [
            sys.executable, audit_script, f"http://localhost:{port}",
            "--out", temp_out,
            "--max-pages", "8",
            "--delay", "0",
            "--budget", "60",
            "--render", "off",
            "--quiet",
        ]
        print(f"Running audit against http://localhost:{port}...")
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if res.returncode != 0:
            print(f"FAIL: Audit exited with code {res.returncode}")
            print(res.stderr)
            return 1

        report_path = os.path.join(temp_out, "report.json")
        if not os.path.exists(report_path):
            print("FAIL: report.json was not generated.")
            return 1

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        found_ids = {f["check_id"] for f in report.get("findings", [])}
        found_ids |= {n["check_id"] for n in report.get("checks_not_applicable", [])}

        missing = [cid for cid in EXPECTED_DEFECTS if cid not in found_ids]

        summary = report.get("summary", {})
        print(f"Findings detected: {summary.get('total_findings', 0)} "
              f"(critical: {summary.get('critical', 0)}, high: {summary.get('high', 0)}, "
              f"medium: {summary.get('medium', 0)}, low: {summary.get('low', 0)})")
        print(f"Scores: AI Discoverability {summary.get('ai_discoverability_score')}/100 | "
              f"On-site Engagement {summary.get('on_site_engagement_score')}/100")

        if missing:
            print(f"\nFAIL: Missing {len(missing)} seeded defect(s):")
            for m in missing:
                print(f"  - MISSING: {m}")
            return 1

        print("\nPASS: All 27 seeded defects were detected successfully.")
        return 0

    finally:
        server.terminate()
        server.wait()
        shutil.rmtree(temp_out, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
