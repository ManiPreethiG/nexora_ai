#!/usr/bin/env python3
"""Merge every skill's findings into the single audit report.

Responsibilities that belong here and nowhere else:
  * de-duplicate and suppress findings that another finding already explains
  * assign stable F-nnn identifiers in priority order
  * score the two halves of the problem separately
  * sequence the suggested actions so blockers are fixed before refinements
  * add site-type-appropriate proactive recommendations
  * state the audit's own limitations honestly

Usage:
    python3 compose_report.py --bundle ./bundle --findings a.json b.json ... \
        [--markdown report.md] [--out report.json]
"""

import argparse
import datetime as dt
import json
import os

SEVERITY_ORDER = ["critical", "high", "medium", "low", "info"]
SEVERITY_WEIGHT = {"critical": 25, "high": 12, "medium": 5, "low": 2, "info": 0}
CONFIDENCE_FACTOR = {"high": 1.0, "medium": 0.7, "low": 0.4}
EFFORT_RANK = {"low": 0, "medium": 1, "high": 2}

# When the left finding is present, the right ones are symptoms of it and are
# folded in rather than listed separately. Keeps the report honest about cause.
SUPERSEDES = {
    "CA-BLANKET-DISALLOW": ["CA-AI-RETRIEVAL-BLOCKED", "CA-SITEMAP-MISSING",
                            "CA-SITEMAP-NOT-DECLARED"],
    "CA-EDGE-BOT-BLOCK": ["CA-UA-CONTENT-VARIES", "CA-SLOW-RESPONSES"],
    "SD-NONE": ["SD-NO-ORGANIZATION", "SD-NO-SAMEAS", "SD-NO-WEBSITE-NODE",
                "SD-NO-BREADCRUMBS", "SD-FAQ-OPPORTUNITY", "SD-MISSING-EXPECTED-TYPES",
                "SD-NO-CONTEXT", "SD-MICRODATA-ONLY"],
    "RX-RENDER-GAP": ["RX-CLIENT-RENDERED-SHELL", "RX-NO-H1", "CA-LINK-DISCOVERY-GAP",
                      "RX-RENDER-GAP-SIGNALS"],
    "RX-CLIENT-RENDERED-SHELL": ["RX-NO-H1", "CA-LINK-DISCOVERY-GAP", "EN-THIN-KEY-PAGES"],
    "CF-CONTENT-STALE": ["CF-PUBLISHING-STALLED", "CF-STALE-COPYRIGHT"],
}

# Fix order. Nothing below a stage matters until that stage passes, which is why
# the plan is sequenced rather than merely sorted by severity.
STAGE = [
    ("Reachable", ["crawl-access-audit"],
     "An agent must be allowed in and get a response before anything else counts."),
    ("Navigable", ["site-architecture-audit"],
     "A crawler that got in must also be able to find the site's other pages; a dead "
     "end or an orphaned URL is invisible even though the entry point works."),
    ("Readable", ["render-extractability-audit"],
     "The facts must exist in the served HTML, as text."),
    ("Unambiguous", ["structured-data-audit"],
     "The page must state what it is and who the brand is, explicitly."),
    ("Answerable", ["answer-coverage-audit"],
     "Once a page states what it is, it must contain an answer worth quoting; a page "
     "that never poses or answers a real question has nothing for an assistant to lift."),
    ("Corroborated", ["corroboration-freshness-audit"],
     "The facts must be current and repeated by independent sources."),
    ("Trustworthy", ["trust-legitimacy-audit"],
     "Corroboration shows independent sources repeat the facts; trust signals show the "
     "facts come from an identifiable, accountable source in the first place."),
    ("Not diluted", ["duplicate-canonicalization-audit"],
     "Even a corroborated, trustworthy fact can be split across near-duplicate URLs so "
     "that none of them accumulates enough weight to be the one cited."),
    ("Locally consistent", ["local-presence-audit"],
     "For a local business, address, phone and hours must agree everywhere they "
     "appear, or a directory listing that disagrees with the site wins instead."),
    ("Worth staying for", ["engagement-audit"],
     "The visitor the citation delivers must find the answer and a reason to continue."),
]

# Proactive moves that strengthen discoverability and engagement even when no
# defect was detected. Selected by site type, then filtered against what the
# site already does so nothing already true is recommended.
PROACTIVE = {
    "*": [
        ("Publish an answer-shaped FAQ on the questions sales actually gets",
         "Collect the questions prospects ask, publish each as a heading with a direct "
         "two-sentence answer immediately beneath it, and mark the block up as FAQPage. "
         "Question-shaped headings with short literal answers are the structure assistants "
         "quote most readily, because they match the shape of what was asked.",
         lambda pr, seen: "SD-FAQ-OPPORTUNITY" not in seen),
        ("Keep one canonical description and use it verbatim everywhere",
         "Write one sentence — '<brand> is a <category> that <does what> for <whom>' — and use "
         "it unchanged in the meta description, the Organization schema, the About page, and "
         "every third-party profile. Repetition across independent sources is what makes a "
         "description the one a model returns.",
         lambda pr, seen: True),
        ("Give each important question its own URL",
         "One page per question the brand should own, titled as the question, answering it in "
         "the first paragraph. A page that answers one thing precisely gets cited for it; a page "
         "that covers ten things gets cited for none.",
         lambda pr, seen: True),
    ],
    "ecommerce": [
        ("Mark up availability, shipping and returns, not just price",
         "Add availability, shippingDetails and hasMerchantReturnPolicy to Offer nodes. "
         "'Is it in stock, when does it arrive, can I send it back' are the questions that "
         "decide a purchase, and they are the ones assistants are asked to compare across "
         "retailers.", lambda pr, seen: True),
        ("Publish specifications as text tables on every product page",
         "A real HTML table of dimensions, materials, compatibility and model numbers makes the "
         "product matchable against a specific query. Specification sheets in images or PDFs "
         "cannot be compared against anything.", lambda pr, seen: True),
    ],
    "saas": [
        ("Publish an honest comparison page for each main alternative",
         "Assistants are asked 'X vs Y' constantly and will answer from whatever exists. A "
         "factual, dated comparison — including where the alternative is the better choice — is "
         "citable in a way a one-sided page is not.", lambda pr, seen: True),
        ("Put a real number on the pricing page",
         "A starting price, a range, or the unit of pricing. Cost is among the most common "
         "questions asked about any product, and 'contact us' cannot be quoted.",
         lambda pr, seen: "RX-PRICE-NOT-IN-TEXT" not in seen),
        ("Keep public documentation crawlable and dated",
         "Docs answer the specific implementation questions people ask assistants. Make sure "
         "they are server-rendered, not behind a JavaScript app shell, and that each page shows "
         "when it was last updated.", lambda pr, seen: True),
    ],
    "local_business": [
        ("Claim and complete the map and directory listings",
         "A Google Business Profile plus the two or three directories that matter locally, all "
         "carrying exactly the same name, address, phone and hours as the site. Local answers "
         "are assembled largely from these sources, and any disagreement between them and the "
         "site weakens all of them.", lambda pr, seen: True),
        ("Publish hours, service area and address as text on every page footer",
         "These are the three facts local searches turn on. In the footer they appear on every "
         "page an assistant might land on, not only the contact page.", lambda pr, seen: True),
    ],
    "media": [
        ("Give every author a real, linked author entity",
         "A byline that links to an author page with credentials, marked up as Person with "
         "sameAs. Attribution is a large part of how a source is weighted, and an unattributed "
         "article is treated as anonymous content.", lambda pr, seen: True),
        ("State corrections and update dates in the open",
         "A visible 'updated on' line and a corrections policy make the publication's claims "
         "safer to repeat, which is precisely the calculation a cautious assistant makes.",
         lambda pr, seen: True),
    ],
    "docs": [
        ("Put a one-paragraph plain-language summary at the top of every page",
         "Reference pages are written for people who already know the system. A short summary "
         "that names the thing and says what it is for gives an extractor something quotable and "
         "orients a visitor who arrived from a search.", lambda pr, seen: True),
        ("Version the docs in the URL and say which version a page describes",
         "Answers about the wrong version are worse than no answer. An explicit version in the "
         "URL and on the page keeps stale content from being cited as current.",
         lambda pr, seen: True),
    ],
    "nonprofit": [
        ("Publish programme outcomes as dated, sourced numbers",
         "Specific figures with a method and a date get cited by journalists and repeated by "
         "assistants; general mission language does not.", lambda pr, seen: True),
    ],
    "brochure": [
        ("Turn the services list into one substantial page per service",
         "A single page listing eight services cannot rank or be cited for any of them. One page "
         "per service, each answering what it is, who it is for, what it costs and what happens "
         "next, gives each an addressable URL.", lambda pr, seen: True),
    ],
}


def rank_key(f):
    sev = SEVERITY_ORDER.index(f["severity"])
    impact = SEVERITY_WEIGHT[f["severity"]] * CONFIDENCE_FACTOR.get(f.get("confidence", "high"), 1.0)
    effort = EFFORT_RANK.get(f.get("suggested_action", {}).get("effort", "medium"), 1)
    return (sev, -impact, effort, f.get("check_id", ""))


def compose(bundle, findings_files, agent_findings=None):
    with open(os.path.join(bundle, "meta.json")) as fh:
        meta = json.load(fh)
    profile = {}
    ppath = os.path.join(bundle, "profile.json")
    if os.path.exists(ppath):
        with open(ppath) as fh:
            profile = json.load(fh)

    raw, na, observations = [], [], {}
    for path in findings_files:
        with open(path) as fh:
            data = json.load(fh)
        raw.extend(data.get("findings", []))
        na.extend([dict(n, skill=data.get("skill", "?")) for n in data.get("not_applicable", [])])
        observations[data.get("skill", os.path.basename(path))] = data.get("observations", {})
    if agent_findings:
        with open(agent_findings) as fh:
            data = json.load(fh)
        raw.extend(data.get("findings", []))
        na.extend([dict(n, skill=data.get("skill", "agent")) for n in data.get("not_applicable", [])])
        observations[data.get("skill", "agent-supplied")] = data.get("observations", {})

    # de-duplicate by check_id, keeping the most severe instance
    by_id = {}
    for f in raw:
        cid = f.get("check_id") or f.get("title")
        if cid not in by_id or SEVERITY_ORDER.index(f["severity"]) < \
                SEVERITY_ORDER.index(by_id[cid]["severity"]):
            by_id[cid] = f

    # suppress symptoms of a cause that is itself reported
    suppressed = {}
    for cause, symptoms in SUPERSEDES.items():
        if cause in by_id:
            for s in symptoms:
                if s in by_id:
                    suppressed[s] = cause
                    by_id.pop(s)
    for s, cause in suppressed.items():
        na.append({"check_id": s, "skill": "compose", "reason":
                   "folded into %s, which is the underlying cause" % cause})

    for f in by_id.values():
        # Several nodes on one page produce the same URL repeatedly; a reader
        # needs the distinct pages affected, not the hit count.
        f["affected_urls"] = list(dict.fromkeys(f.get("affected_urls") or []))[:10]

    findings = sorted(by_id.values(), key=rank_key)
    proactive = [f for f in findings if f["severity"] == "info"]
    defects = [f for f in findings if f["severity"] != "info"]
    for i, f in enumerate(defects, 1):
        f["id"] = "F-%03d" % i
        f.setdefault("confidence", "high")
        f["suggested_action"].setdefault("priority", f["severity"])

    counts = {s: len([f for f in defects if f["severity"] == s]) for s in SEVERITY_ORDER[:-1]}

    def score(cats):
        penalty = sum(SEVERITY_WEIGHT[f["severity"]] *
                      CONFIDENCE_FACTOR.get(f.get("confidence", "high"), 1.0)
                      for f in defects if f.get("category") in cats)
        return max(0, round(100 - penalty))

    # sequenced remediation plan
    plan, used = [], set()
    for stage_name, concerns, why in STAGE:
        items = [f for f in defects if f.get("concern") in concerns and f["id"] not in used]
        if not items:
            continue
        used.update(f["id"] for f in items)
        plan.append({
            "stage": stage_name, "why_this_order": why,
            "actions": [{"finding_id": f["id"], "severity": f["severity"],
                         "effort": f["suggested_action"].get("effort", "medium"),
                         "action": f["suggested_action"]["summary"]} for f in items],
        })
    leftover = [f for f in defects if f["id"] not in used]
    if leftover:
        plan.append({"stage": "Other", "why_this_order": "findings outside the staged pipeline",
                     "actions": [{"finding_id": f["id"], "severity": f["severity"],
                                  "effort": f["suggested_action"].get("effort", "medium"),
                                  "action": f["suggested_action"]["summary"]} for f in leftover]})

    # proactive recommendations
    seen_ids = set(by_id) | set(suppressed)
    recs = []
    for key in ("*", profile.get("site_type", "brochure")):
        for title, detail, applies in PROACTIVE.get(key, []):
            if applies(profile, seen_ids):
                recs.append({"title": title, "detail": detail,
                             "basis": "always applicable" if key == "*"
                                      else "site classified as %s" % key})
    for f in proactive:
        recs.append({"title": f["suggested_action"]["summary"],
                     "detail": f.get("mechanism", ""), "basis": "opportunity check %s"
                     % f["check_id"], "evidence": f["evidence"]})

    caps = meta.get("capabilities", {})
    limitations = []
    if not caps.get("rendering"):
        limitations.append(
            "No headless browser was available (%s), so JavaScript-render gaps were inferred "
            "from the served HTML. Findings that depend on rendering are marked confidence "
            "'medium'." % caps.get("render_note", "reason not recorded"))
    if not any(o.get("offsite_checked") for o in observations.values()):
        limitations.append(
            "Off-site corroboration (independent sources, entity collisions, what assistants "
            "currently say about the brand) was not verified with live search; only the on-site "
            "half of those signals was assessed.")
    if meta.get("skipped_by_robots"):
        limitations.append("%d URL(s) were not fetched because robots.txt disallows this agent."
                           % len(meta["skipped_by_robots"]))
    if meta.get("notes"):
        limitations.extend(meta["notes"])
    limitations.append(
        "%d page(s) were crawled (%s). Findings describe the sampled pages; a finding reported on "
        "a sample of one template usually applies to every page built from it."
        % (meta.get("pages_crawled", 0),
           ", ".join("%s×%s" % (v, k) for k, v in meta.get("pages_by_type", {}).items())))

    return {
        "site": meta["site"],
        "audited_at": meta["audited_at"],
        "report_version": "1.0",
        "marketplace": "brand-ai-readiness-audit",
        "site_profile": {
            "brand_name": profile.get("brand_name"),
            "site_type": profile.get("site_type"),
            "classification_reason": profile.get("classification_reason"),
            "primary_language": profile.get("primary_language"),
        },
        "scope": {
            "seed_url": meta.get("seed_url"),
            "pages_crawled": meta.get("pages_crawled"),
            "pages_by_type": meta.get("pages_by_type"),
            "crawler_user_agent": meta.get("crawler_user_agent"),
            "rendering_available": caps.get("rendering", False),
            "elapsed_s": meta.get("elapsed_s"),
            "read_only": True,
        },
        "summary": {
            "total_findings": len(defects),
            "critical": counts["critical"], "high": counts["high"],
            "medium": counts["medium"], "low": counts["low"],
            "ai_discoverability_score": score({"discoverability", "both"}),
            "on_site_engagement_score": score({"engagement", "both"}),
            "headline": headline(defects, meta, profile),
        },
        "findings": defects,
        "action_plan": plan,
        "proactive_recommendations": recs,
        "checks_not_applicable": na,
        "limitations": limitations,
        "observations": observations,
    }


def headline(defects, meta, profile):
    if not defects:
        return ("No blocking discoverability or engagement defects were detected on the pages "
                "sampled; see proactive recommendations.")
    top = defects[0]
    crit = len([f for f in defects if f["severity"] == "critical"])
    if crit:
        return ("%d critical issue(s) prevent AI assistants from reaching or reading this site. "
                "Start with %s: %s" % (crit, top["id"], top["title"]))
    return ("No hard blockers; the largest problem is %s: %s" % (top["id"], top["title"]))


def to_markdown(r):
    L = []
    a = L.append
    a("# AI-readiness audit — %s" % r["site"])
    a("")
    a("*%s · %s site · %d pages sampled*"
      % (r["audited_at"], r["site_profile"].get("site_type", "unclassified"),
         r["scope"]["pages_crawled"]))
    a("")
    a("**%s**" % r["summary"]["headline"])
    a("")
    a("| | |")
    a("|---|---|")
    a("| AI discoverability score | **%d/100** |" % r["summary"]["ai_discoverability_score"])
    a("| On-site engagement score | **%d/100** |" % r["summary"]["on_site_engagement_score"])
    a("| Findings | %d (%d critical, %d high, %d medium, %d low) |"
      % (r["summary"]["total_findings"], r["summary"]["critical"], r["summary"]["high"],
         r["summary"]["medium"], r["summary"]["low"]))
    a("")
    a("## Findings")
    for f in r["findings"]:
        a("")
        a("### %s · %s — %s" % (f["id"], f["severity"].upper(), f["title"]))
        a("")
        a("- **Category:** %s · **Confidence:** %s · **Source check:** `%s`"
          % (f.get("category", "-"), f.get("confidence", "-"), f.get("check_id", "-")))
        a("- **Evidence:** %s" % f["evidence"])
        if f.get("mechanism"):
            a("- **Why it matters:** %s" % f["mechanism"])
        a("- **Fix (%s effort, %s priority):** %s"
          % (f["suggested_action"].get("effort", "-"), f["suggested_action"]["priority"],
             f["suggested_action"]["summary"]))
        if f["suggested_action"].get("detail"):
            a("- **How:** %s" % f["suggested_action"]["detail"])
        if f["suggested_action"].get("verification"):
            a("- **Verify:** %s" % f["suggested_action"]["verification"])
        if f.get("affected_urls"):
            a("- **Affected:** %s" % ", ".join(f["affected_urls"][:5]))
    a("")
    a("## Fix in this order")
    for stage in r["action_plan"]:
        a("")
        a("**%s** — %s" % (stage["stage"], stage["why_this_order"]))
        a("")
        for act in stage["actions"]:
            a("- `%s` (%s, %s effort) %s"
              % (act["finding_id"], act["severity"], act["effort"], act["action"]))
    a("")
    a("## Worth doing even with no defect found")
    for rec in r["proactive_recommendations"]:
        a("")
        a("**%s**  " % rec["title"])
        a("%s" % rec["detail"])
    a("")
    a("## What this audit could not check")
    for lim in r["limitations"]:
        a("- %s" % lim)
    a("")
    a("## Checks deliberately not fired")
    a("")
    a("These were evaluated and found not to apply — recorded so the report can be trusted "
      "to have looked.")
    a("")
    for n in r["checks_not_applicable"][:40]:
        a("- `%s` — %s" % (n.get("check_id", "?"), n.get("reason", "")))
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--findings", nargs="+", required=True)
    ap.add_argument("--agent-findings", help="JSON file of findings produced by the agent "
                                             "(off-site protocol, judgement checks)")
    ap.add_argument("--out", default="report.json")
    ap.add_argument("--markdown")
    a = ap.parse_args()
    report = compose(a.bundle, a.findings, a.agent_findings)
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    if a.markdown:
        with open(a.markdown, "w", encoding="utf-8") as fh:
            fh.write(to_markdown(report))
    print(json.dumps({"site": report["site"], "written": a.out,
                      "summary": report["summary"]}, indent=1))


if __name__ == "__main__":
    main()
