#!/usr/bin/env python3
"""Stage 3b of the audit: the page states what it is (structured-data-audit) —
but does the site actually contain an answer worth quoting for the questions
people ask before choosing a brand? Extractability (render-extractability-audit)
asks whether an existing fact can be read; this asks whether the fact exists to
begin with. A perfectly crawlable, perfectly marked-up page that never poses or
answers a real question has nothing for an assistant to lift into an answer.

Reads a crawl bundle and emits findings JSON. Performs no network requests of
its own.

Usage: python3 check_answers.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re

SKILL = "answer-coverage-audit"

# Matches skills/structured-data-audit/scripts/check_schema.py's QUESTION_HEADING,
# kept identical so the two skills agree on what counts as a question.
QUESTION_HEADING = re.compile(
    r"^\s*(what|how|why|when|where|who|which|can|do|does|is|are|should|will)\b.*\?\s*$", re.I)
COMPARISON_RX = re.compile(r"\b(vs\.?|versus|alternatives?|compare|comparison)\b", re.I)
OBJECTION_RX = re.compile(
    r"\b(refund|money[- ]back|guarantee|cancel anytime|cancel any time|free returns?|"
    r"return policy|security|encrypt|soc\s?2|gdpr|compliance|certified|privacy policy)\b", re.I)
QA_SITE_TYPES = {"saas", "ecommerce"}


def load(bundle):
    def j(name, default=None):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            return default
        with open(path) as fh:
            return json.load(fh)
    meta, idx, profile = j("meta.json"), j("index.json"), j("profile.json")
    for p in idx["pages"]:
        path = os.path.join(bundle, "pages", p["id"] + ".extract.json")
        p["extract"] = None
        if os.path.exists(path):
            with open(path) as fh:
                p["extract"] = json.load(fh)
    return meta, idx["pages"], profile


def finding(check_id, title, severity, evidence, action, *, category="discoverability",
            confidence="high", urls=None, mechanism="", detail="", effort="medium",
            verification=""):
    return {
        "check_id": check_id, "title": title, "category": category, "concern": SKILL,
        "severity": severity, "confidence": confidence, "evidence": evidence,
        "affected_urls": urls or [], "mechanism": mechanism,
        "suggested_action": {"summary": action, "detail": detail, "priority": severity,
                             "effort": effort, "verification": verification},
    }


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages, profile = load(bundle)
    out, na = [], []
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    if not ok:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [],
                "observations": {"note": "no HTML pages available to analyse"}}
    site_type = (profile or {}).get("site_type", "brochure")
    home = next((p for p in ok if p["type"] == "home"), ok[0])

    q_by_page = {}
    for p in ok:
        qs = [h["text"] for h in p["extract"]["headings"] if QUESTION_HEADING.match(h["text"] or "")]
        if qs:
            q_by_page[p["id"]] = qs
    jsonld_types = {t.lower() for p in ok for t in p["extract"].get("jsonld_types", [])}
    has_qa_schema = bool({"faqpage", "qapage", "howto"} & jsonld_types)

    # ---------------------------------------------------------------- 1. no question content at all
    # Reference and documentation content is already organised around answering
    # implicit questions (an encyclopedia entry, a how-to page) without needing
    # literal question-shaped headings; demanding FAQ framing there is exactly
    # the kind of context-free expectation this marketplace treats as a false
    # positive. Every other site type is expected to have at least some
    # question-answering content somewhere across a multi-page crawl.
    if site_type in ("media", "docs"):
        na.append({"check_id": "AQ-NO-QUESTION-CONTENT",
                   "reason": "site classified as %s; reference/documentation content answers "
                             "implicit questions without needing question-shaped headings"
                             % site_type})
    elif not q_by_page and not has_qa_schema:
        out.append(finding(
            "AQ-NO-QUESTION-CONTENT",
            "The site poses and answers no question anywhere", "medium",
            evidence="0 question-shaped headings (matching a question word and ending in '?') "
                     "found across %d crawled pages, and no FAQPage, QAPage or HowTo structured "
                     "data." % len(ok),
            action="Write down the ten questions people most often ask about the organisation "
                   "or what it offers, and give each its own heading with a direct answer "
                   "immediately beneath it.",
            mechanism="An assistant builds its answer from what a page happens to say. A site "
                      "that never poses the question a user asked has no sentence positioned to "
                      "be the answer, however well-optimised the surrounding pages are — this is "
                      "a content gap, not an extraction problem.",
            detail="This is distinct from a markup gap: adding FAQPage schema to content that "
                   "does not exist yet fixes nothing. The content has to exist first.",
            urls=[home["url"]], effort="medium"))
    else:
        na.append({"check_id": "AQ-NO-QUESTION-CONTENT",
                   "reason": "%d page(s) carry question-shaped headings or FAQ/HowTo structured "
                             "data exists" % len(q_by_page)})

    # ---------------------------------------------------------------- 2. question posed, not answered
    thin = []
    for p in ok:
        qs = q_by_page.get(p["id"])
        if not qs:
            continue
        words_per_q = p["extract"]["word_count"] / len(qs)
        if words_per_q < 20:
            thin.append((p, qs, words_per_q))
    if thin:
        p, qs, wpq = thin[0]
        out.append(finding(
            "AQ-THIN-ANSWER-PAGE",
            "A question is posed as a heading with almost no answer beneath it", "medium",
            category="both",
            evidence="%s asks %d question(s) (e.g. %r) across %d words total — %.0f words per "
                     "question." % (p["url"], len(qs), qs[0][:70], p["extract"]["word_count"], wpq),
            action="Give each question a direct two-to-four sentence answer immediately below "
                   "it, before any further elaboration.",
            mechanism="A question-shaped heading signals to both a reader and an extractor that "
                      "an answer follows. When almost no text follows, the heading is a "
                      "placeholder — worse for citation than not posing the question at all, "
                      "because it primes an extractor to look for an answer that is not there.",
            urls=[q[0]["url"] for q in thin][:8]))
    elif q_by_page:
        na.append({"check_id": "AQ-THIN-ANSWER-PAGE",
                   "reason": "pages with question-shaped headings carry a substantive amount of "
                             "text per question"})
    else:
        na.append({"check_id": "AQ-THIN-ANSWER-PAGE",
                   "reason": "no question-shaped headings found to evaluate for answer depth"})

    # ---------------------------------------------------------------- 3. comparison content
    if site_type in QA_SITE_TYPES:
        all_text = "\n".join(p["extract"]["text"] for p in ok)
        if not COMPARISON_RX.search(all_text):
            out.append(finding(
                "AQ-NO-COMPARISON-CONTENT",
                "No page compares the brand against alternatives", "info",
                evidence="No page in %d crawled pages contains 'vs', 'versus', 'alternative' or "
                         "'compare'." % len(ok),
                action="Publish one factual, dated comparison page against each main "
                       "alternative, including where the alternative is the better fit.",
                confidence="medium",
                mechanism="'X vs Y' and 'alternatives to X' are asked constantly, and an "
                          "assistant answers from whatever exists — usually a third party's "
                          "one-sided comparison when the brand has published none of its own.",
                urls=[home["url"]]))
        else:
            na.append({"check_id": "AQ-NO-COMPARISON-CONTENT",
                       "reason": "comparison-shaped content already exists"})
    else:
        na.append({"check_id": "AQ-NO-COMPARISON-CONTENT",
                   "reason": "site classified as %s; comparison content is most relevant to "
                             "saas/ecommerce" % site_type})

    # ---------------------------------------------------------------- 4. objection handling
    if site_type in QA_SITE_TYPES:
        all_text = "\n".join(p["extract"]["text"] for p in ok)
        if not OBJECTION_RX.search(all_text):
            out.append(finding(
                "AQ-NO-OBJECTION-HANDLING",
                "The site never addresses the standard purchase objections", "medium",
                evidence="No mention of a refund/return/cancellation policy, a guarantee, or "
                         "security/compliance practices was found across %d crawled pages."
                         % len(ok),
                action="Publish a plain-text answer to the objections that stall a purchase or "
                       "signup decision: what happens if it doesn't work out, and how data or "
                       "money is protected.",
                confidence="medium",
                mechanism="Assistants are frequently asked the skeptical follow-up — 'is it "
                          "legit', 'can I get my money back', 'is it secure' — right after the "
                          "descriptive one. A site with no text answering it is either skipped "
                          "for that question or answered from an unrelated third-party source.",
                urls=[home["url"]]))
        else:
            na.append({"check_id": "AQ-NO-OBJECTION-HANDLING",
                       "reason": "objection-handling content (refunds, guarantees, security) "
                                 "already exists"})
    else:
        na.append({"check_id": "AQ-NO-OBJECTION-HANDLING",
                   "reason": "site classified as %s; not scoped to this check" % site_type})

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "site_type": site_type,
            "pages_with_question_headings": len(q_by_page),
            "has_qa_schema": has_qa_schema,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--json-out")
    a = ap.parse_args()
    res = run(a.bundle)
    text = json.dumps(res, indent=1)
    if a.json_out:
        with open(a.json_out, "w") as fh:
            fh.write(text)
    print(text)


if __name__ == "__main__":
    main()
