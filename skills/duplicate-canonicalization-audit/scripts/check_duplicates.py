#!/usr/bin/env python3
"""Stage 4c of the audit: even a page that is reachable, readable, unambiguous
and corroborated can still lose the citation if its own content is split
across two or more near-identical URLs. When several URLs could equally be
"the" answer, none of them accumulates enough signal to be picked — this is a
distinct failure from anything structured-data-audit or crawl-access-audit
checks, both of which look at one URL at a time.

Reads a crawl bundle and emits findings JSON. Performs no network requests of
its own. O(n^2) page comparison is fine here: crawls are capped at a few dozen
pages.

Usage: python3 check_duplicates.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re

SKILL = "duplicate-canonicalization-audit"

STOPWORDS = {
    "with", "that", "this", "from", "your", "their", "have", "more", "than", "into",
    "over", "also", "them", "they", "which", "about", "help", "helps", "make", "makes",
}
GENERIC_TITLES = {"home", "homepage", "welcome", "untitled", "page", "index"}


def stem_set(text):
    return {w[:5] for w in re.findall(r"[a-z]{4,}", text.lower()) if w not in STOPWORDS}


def load(bundle):
    def j(name, default=None):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            return default
        with open(path) as fh:
            return json.load(fh)
    meta, idx = j("meta.json"), j("index.json")
    for p in idx["pages"]:
        path = os.path.join(bundle, "pages", p["id"] + ".extract.json")
        p["extract"] = None
        if os.path.exists(path):
            with open(path) as fh:
                p["extract"] = json.load(fh)
    return meta, idx["pages"]


def finding(check_id, title, severity, evidence, action, *, category="discoverability",
            confidence="high", urls=None, mechanism="", detail="", effort="low",
            verification=""):
    return {
        "check_id": check_id, "title": title, "category": category, "concern": SKILL,
        "severity": severity, "confidence": confidence, "evidence": evidence,
        "affected_urls": urls or [], "mechanism": mechanism,
        "suggested_action": {"summary": action, "detail": detail, "priority": severity,
                             "effort": effort, "verification": verification},
    }


def same_canonical_pair(a, b):
    ca = (a["extract"].get("canonical") or "").rstrip("/")
    cb = (b["extract"].get("canonical") or "").rstrip("/")
    return (ca and ca == b["url"].rstrip("/")) or (cb and cb == a["url"].rstrip("/")) or \
           (ca and ca == cb)


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages = load(bundle)
    out, na = [], []
    ok = [p for p in pages if p.get("extract") and p["status"] == 200 and p["type"] != "legal"]
    if len(ok) < 2:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [
            {"check_id": "DC-NEAR-DUPLICATE-PAGES", "reason": "fewer than two pages to compare"},
            {"check_id": "DC-DUPLICATE-TITLE-OR-DESCRIPTION",
             "reason": "fewer than two pages to compare"},
            {"check_id": "DC-PARAM-VARIANT-NOT-CANONICALIZED", "reason": "no pages crawled"},
        ], "observations": {}}

    # ---------------------------------------------------------------- 1. duplicate title/description
    dup_titles = {}
    for p in ok:
        t = (p["extract"].get("title") or "").strip()
        if t and len(t) >= 6 and t.lower() not in GENERIC_TITLES:
            dup_titles.setdefault(t, []).append(p)
    title_hits = [(t, ps) for t, ps in dup_titles.items()
                 if len(ps) >= 2 and not same_canonical_pair(ps[0], ps[1])]
    if title_hits:
        t, ps = title_hits[0]
        out.append(finding(
            "DC-DUPLICATE-TITLE-OR-DESCRIPTION",
            "Distinct URLs cannot be told apart by title", "medium",
            evidence="%d URLs share the exact title %r with no canonical relating them: %s. "
                     "(This can mean the pages are content duplicates, or that a shared "
                     "template never sets a page-specific title — either way the title carries "
                     "no distinguishing signal.)"
                     % (len(ps), t, ", ".join(p["url"] for p in ps[:4])),
            action="Give each URL a unique, specific title that names what that page covers; if "
                   "the pages genuinely are the same content, set rel=canonical on the "
                   "non-primary URL(s) instead.",
            mechanism="Title is one of the strongest signals a retrieval system uses to tell "
                      "pages apart and to choose which one to show for a query. When every page "
                      "shares one title, none of them is distinguishable from the others by that "
                      "signal, whether or not their content actually differs.",
            urls=[p["url"] for p in ps][:10]))
    else:
        na.append({"check_id": "DC-DUPLICATE-TITLE-OR-DESCRIPTION",
                   "reason": "no two distinct, non-canonicalised URLs share an identical title"})

    # ---------------------------------------------------------------- 2. near-duplicate body text
    near_dupes = []
    for i in range(len(ok)):
        for j in range(i + 1, len(ok)):
            a, b = ok[i], ok[j]
            if a["type"] != b["type"] or same_canonical_pair(a, b):
                continue
            wa, wb = a["extract"]["word_count"], b["extract"]["word_count"]
            if wa < 30 or wb < 30:
                continue
            sa, sb = stem_set(a["extract"]["main_text"] or a["extract"]["text"]), \
                     stem_set(b["extract"]["main_text"] or b["extract"]["text"])
            if not sa or not sb:
                continue
            overlap = len(sa & sb) / max(1, len(sa | sb))
            if overlap >= 0.85:
                near_dupes.append((a["url"], b["url"], overlap))
    if near_dupes:
        u1, u2, ov = max(near_dupes, key=lambda x: x[2])
        out.append(finding(
            "DC-NEAR-DUPLICATE-PAGES",
            "Two or more URLs carry near-identical body text", "medium",
            evidence="%d page pair(s) share 85%%+ word-stem overlap, e.g. %s and %s (%.0f%% "
                     "overlap), with no canonical relating them." % (
                         len(near_dupes), u1, u2, ov * 100),
            action="Pick one canonical URL per distinct piece of content and either "
                   "rel=canonical or 301-redirect the others to it; if both must stay live "
                   "(e.g. two locales), differentiate them or declare hreflang instead.",
            confidence="medium",
            mechanism="Two URLs with the same content compete against each other for the same "
                      "query, splitting the corroboration and link signal that would otherwise "
                      "accumulate on one page — the opposite of what makes a page citable.",
            urls=[u1, u2]))
    else:
        na.append({"check_id": "DC-NEAR-DUPLICATE-PAGES",
                   "reason": "no pair of same-type pages of substantive length shares 85%+ "
                             "word-stem overlap"})

    # ---------------------------------------------------------------- 3. param variants
    variant_pages = [p for p in ok if "?" in p["url"]]
    uncanonicalized = [p for p in variant_pages
                       if not p["extract"].get("canonical")
                       or "?" in p["extract"]["canonical"]]
    if uncanonicalized:
        p = uncanonicalized[0]
        out.append(finding(
            "DC-PARAM-VARIANT-NOT-CANONICALIZED",
            "A URL reached with query parameters carries no clean canonical", "medium",
            evidence="%s was crawled with a query string and its canonical is %s."
                     % (p["url"], "empty" if not p["extract"].get("canonical")
                        else repr(p["extract"]["canonical"])),
            action="Set rel=canonical on every parameterised URL to the clean, parameter-free "
                   "version of the page.",
            mechanism="Tracking and referral parameters create an unlimited number of URLs for "
                      "one piece of content. Without a canonical pointing back to the clean URL, "
                      "each variant is a separate, weaker competitor to the page that should be "
                      "cited.",
            urls=[p["url"] for p in uncanonicalized][:10]))
    else:
        na.append({"check_id": "DC-PARAM-VARIANT-NOT-CANONICALIZED",
                   "reason": "no crawled URL carried query parameters" if not variant_pages
                             else "parameterised URLs already declare a clean canonical"})

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {"pages_compared": len(ok), "param_variant_pages": len(variant_pages)},
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
