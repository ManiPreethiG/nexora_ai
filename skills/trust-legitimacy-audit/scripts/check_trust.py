#!/usr/bin/env python3
"""Stage 4b of the audit: corroboration-freshness-audit establishes that
independent sources repeat the same facts; this establishes that the facts
carry on-site signals of coming from an identifiable, accountable source in
the first place — legal disclosure, transport security, and (for published
content) real authorship.

This is deliberately narrower than a general trust/E-E-A-T audit: each check
here is a concrete, low-false-positive signal, not a subjective quality score.

Reads a crawl bundle and emits findings JSON. Performs no network requests of
its own.

Usage: python3 check_trust.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re

SKILL = "trust-legitimacy-audit"

LEGAL_LINK_RX = re.compile(
    r"(/privacy|/terms|/legal|/cookie-?policy|/imprint|/impressum|privacy policy|"
    r"terms of (service|use)|terms and conditions|cookie policy)", re.I)
AUTHOR_HINT_RX = re.compile(r"\bby\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2}\b|\bauthor\b", re.I)
REGISTRATION_RX = re.compile(
    r"\b(registered (?:company|charity|address)|company (?:no\.?|number|registration)|"
    r"\bein\b|\btax id\b|\bvat (?:no\.?|number)|\bcin\b|\bregistered office\b|"
    r"registered in [A-Z][a-z]+|501\(c\))", re.I)


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


def finding(check_id, title, severity, evidence, action, *, category="both",
            confidence="high", urls=None, mechanism="", detail="", effort="low",
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
    home = next((p for p in ok if p["type"] == "home"), ok[0])
    site_type = (profile or {}).get("site_type", "brochure")

    # ---------------------------------------------------------------- 1. HSTS
    hp = meta.get("probes", {}).get("http_to_https")
    if hp is not None:
        if hp.get("final_https") and not hp.get("hsts"):
            out.append(finding(
                "TL-NO-HSTS", "HTTPS is used but HSTS is not enforced", "low",
                category="discoverability",
                evidence="http:// requests reach an https:// final URL (status %s) but the "
                         "response carries no Strict-Transport-Security header."
                         % hp.get("status"),
                action="Add `Strict-Transport-Security: max-age=31536000; includeSubDomains` to "
                       "the HTTPS response.",
                mechanism="Without HSTS, every visit starts as an insecure request that is then "
                          "redirected, which is both a small security gap and a signal some "
                          "fetchers and browsers weigh when deciding how much to trust a domain.",
                urls=[meta.get("origin", "")]))
        else:
            na.append({"check_id": "TL-NO-HSTS",
                       "reason": "HSTS is present" if hp.get("hsts")
                                 else "site is not served over HTTPS"})
    else:
        na.append({"check_id": "TL-NO-HSTS", "reason": "seed URL was not https://, so the "
                                                        "http-to-https probe did not run"})

    # ---------------------------------------------------------------- 2. author byline
    blog_pages = [p for p in ok if p["type"] == "blog_post"]
    if len(blog_pages) >= 2:
        jsonld_has_author = False
        for p in blog_pages:
            for raw in p["extract"]["jsonld_raw"]:
                if re.search(r'"author"\s*:\s*[{"]', raw):
                    jsonld_has_author = True
                    break
        no_byline = [p for p in blog_pages
                    if not AUTHOR_HINT_RX.search(p["extract"]["text"][:1200])]
        if len(no_byline) >= len(blog_pages) * 0.6 and not jsonld_has_author:
            out.append(finding(
                "TL-NO-AUTHOR-BYLINE", "Published articles carry no identifiable author", "medium",
                category="discoverability",
                evidence="%d of %d article pages have neither a byline in the opening text nor "
                         "an author in structured data, e.g. %s."
                         % (len(no_byline), len(blog_pages), no_byline[0]["url"]),
                action="Attribute every article to a named author with a linked author page, "
                       "and add Person/author structured data.",
                mechanism="Attribution is part of how a source is weighted for factual claims. "
                          "Unattributed content is treated as anonymous, which lowers the "
                          "confidence a careful assistant places in repeating it.",
                urls=[p["url"] for p in no_byline][:8]))
        else:
            na.append({"check_id": "TL-NO-AUTHOR-BYLINE",
                       "reason": "articles carry byline text or author structured data"})
    else:
        na.append({"check_id": "TL-NO-AUTHOR-BYLINE",
                   "reason": "fewer than 2 article/blog pages were crawled"})

    # ---------------------------------------------------------------- 3. legal pages linked
    all_links = [l for p in ok for l in p["extract"]["links_internal"] + p["extract"]["links_external"]]
    legal_link = next((l for l in all_links
                       if LEGAL_LINK_RX.search(l.get("href", "") + " " + l.get("text", ""))), None)
    legal_typed_page = any(p["type"] == "legal" for p in ok)
    if not legal_link and not legal_typed_page:
        out.append(finding(
            "TL-NO-LEGAL-PAGES-LINKED",
            "No privacy policy or terms page is linked anywhere on the site", "medium",
            evidence="Checked the href and link text of %d links across %d crawled pages; none "
                     "matches a privacy, terms, cookie or legal policy pattern." % (
                         len(all_links), len(ok)),
            action="Publish a privacy policy and terms of service, and link both from the site "
                   "footer on every page.",
            mechanism="A privacy policy and terms page are baseline evidence that a site is "
                      "operated by an accountable, identifiable party rather than a throwaway "
                      "domain — both for a visitor deciding whether to trust it and for a "
                      "corroboration pass that has nothing else on-site to check.",
            urls=[home["url"]]))
    else:
        na.append({"check_id": "TL-NO-LEGAL-PAGES-LINKED",
                   "reason": "a privacy/terms/legal link or page was found"})

    # ---------------------------------------------------------------- 4. business identity disclosed
    if site_type in ("ecommerce", "nonprofit"):
        all_text = "\n".join(p["extract"]["text"] for p in ok)
        if not REGISTRATION_RX.search(all_text):
            out.append(finding(
                "TL-NO-BUSINESS-IDENTITY-DISCLOSED",
                "No registered business or charity identity is disclosed anywhere", "medium",
                evidence="No company registration number, VAT/tax ID, registered address or "
                         "charity registration was found in text across %d crawled pages."
                         % len(ok),
                action="Disclose the legal entity name, registration number and registered "
                       "address (or charity registration number) in the footer or an About/"
                       "Legal page.",
                confidence="medium",
                mechanism="For a site that takes payment or donations, this disclosure is what "
                          "lets a buyer or donor verify who they are actually dealing with. Its "
                          "absence is a concrete, checkable legitimacy gap distinct from general "
                          "off-site corroboration.",
                urls=[home["url"]]))
        else:
            na.append({"check_id": "TL-NO-BUSINESS-IDENTITY-DISCLOSED",
                       "reason": "a registration/identity disclosure was found in text"})
    else:
        na.append({"check_id": "TL-NO-BUSINESS-IDENTITY-DISCLOSED",
                   "reason": "site classified as %s; not scoped to this check" % site_type})

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "site_type": site_type,
            "blog_pages": len(blog_pages),
            "has_legal_link": bool(legal_link) or legal_typed_page,
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
