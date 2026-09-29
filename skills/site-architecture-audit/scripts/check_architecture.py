#!/usr/bin/env python3
"""Stage 1b of the audit: once a crawler is let in, can it find the rest of the
site? Being allowed in (crawl-access-audit) is necessary but not sufficient —
a page that is reachable in principle but linked from nowhere, or that dead-ends
with no path onward, is functionally undiscoverable and never accumulates
enough signal to be a citation candidate.

Reads a crawl bundle and emits findings JSON. Performs no network requests of
its own.

Usage: python3 check_architecture.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
from urllib.parse import urlsplit

SKILL = "site-architecture-audit"


def _key(url):
    """Loose identity for comparing a sitemap/link URL against a crawled page:
    scheme, www and trailing slash are noise; query strings are not — a param
    variant is a different resource as far as internal-link discovery goes."""
    s = urlsplit(url)
    host = s.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = s.path.rstrip("/") or "/"
    return (host, path)


def load(bundle):
    def j(name, default=None):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            return default
        with open(path) as fh:
            return json.load(fh)
    meta, idx = j("meta.json"), j("index.json")
    sitemap = j("sitemap.json", {"documents": [], "urls": []})
    for p in idx["pages"]:
        path = os.path.join(bundle, "pages", p["id"] + ".extract.json")
        p["extract"] = None
        if os.path.exists(path):
            with open(path) as fh:
                p["extract"] = json.load(fh)
    return meta, idx["pages"], sitemap


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
    meta, pages, sitemap = load(bundle)
    out, na = [], []
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    if not ok:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [],
                "observations": {"note": "no HTML pages available to analyse"}}
    home = next((p for p in ok if p["type"] == "home"), ok[0])
    interior = [p for p in ok if p is not home and p["type"] != "legal"]

    # ---------------------------------------------------------------- 1. dead-end pages
    if interior:
        dead = []
        for p in interior:
            body_links = [l for l in p["extract"]["links_internal"]
                         if l.get("text") and len(l["text"]) > 2]
            if len(body_links) <= 1:
                dead.append(p["url"])
        if len(dead) >= max(2, len(interior) * 0.5):
            sev = "high" if len(dead) == len(interior) else "medium"
            out.append(finding(
                "SA-DEAD-END-PAGES", "Interior pages offer no path to the rest of the site",
                sev, category="both",
                evidence="%d of %d interior pages carry at most one in-body link to another "
                         "internal page, e.g. %s." % (len(dead), len(interior), dead[0]),
                action="Add contextual links from every page to related pages — other "
                       "products, the category it belongs to, adjacent articles, the section "
                       "index — not just a global nav.",
                mechanism="A crawler discovers new URLs by following <a href> links out of "
                          "pages it has already read. A page with nowhere to go is a leaf: the "
                          "crawler that reached it learns nothing else about the site, and any "
                          "page reachable only through that leaf stays undiscovered.",
                detail="Global navigation is not enough on its own — it repeats the same dozen "
                       "links on every page. The links that extend discovery are the "
                       "page-specific ones: 'related', 'next', 'see also', category and tag "
                       "links.",
                urls=dead[:10]))
        else:
            na.append({"check_id": "SA-DEAD-END-PAGES",
                       "reason": "%d of %d interior pages carry onward links"
                                 % (len(interior) - len(dead), len(interior))})
    else:
        na.append({"check_id": "SA-DEAD-END-PAGES", "reason": "no interior pages were crawled"})

    # ---------------------------------------------------------------- 2/3. sitemap vs link graph
    sm_urls = sitemap.get("urls", [])[:500]
    if len(sm_urls) >= 5:
        sm_keys = {_key(u["loc"]) for u in sm_urls if u.get("loc")}
        # A shallow crawl of a large site will *always* look like most of the
        # sitemap is "orphaned" simply because only a handful of pages were
        # sampled — that is a sampling artifact, not evidence about the site's
        # actual link graph. Only draw the conclusion when the sitemap is not
        # drastically larger than what this many crawled pages could plausibly
        # have linked to; otherwise this is exactly the "inference reported as
        # an observation" the evidence rules warn against.
        plausible_reach = max(50, len(ok) * 15)
        if len(sm_keys) <= plausible_reach:
            linked_keys = set()
            for p in ok:
                for l in p["extract"]["links_internal"]:
                    if l.get("href"):
                        linked_keys.add(_key(l["href"]))
            orphaned = sm_keys - linked_keys
            if len(orphaned) >= max(3, len(sm_keys) * 0.3):
                sample = sorted(k[1] for k in list(orphaned)[:5])
                out.append(finding(
                    "SA-ORPHAN-SITEMAP-URLS",
                    "Sitemap URLs are never linked from any crawled page", "medium",
                    evidence="%d of %d sitemap URLs (%.0f%%) do not appear as an <a href> on any "
                             "of %d crawled pages, e.g. %s." % (
                                 len(orphaned), len(sm_keys), 100 * len(orphaned) / len(sm_keys),
                                 len(ok), ", ".join(sample)),
                    action="Link every URL the sitemap declares from somewhere in the site's own "
                           "navigation, category pages or an on-site index — not only from the "
                           "sitemap file.",
                    mechanism="A sitemap is a hint, not a substitute for a link graph; several "
                              "major fetchers weight or skip URLs with no internal links pointing "
                              "at them. A page's own site is the strongest available signal that "
                              "the page matters.",
                    confidence="medium",
                    urls=[u["loc"] for u in sm_urls if _key(u["loc"]) in orphaned][:10]))
            else:
                na.append({"check_id": "SA-ORPHAN-SITEMAP-URLS",
                           "reason": "%d%% of sitemap URLs are reachable through in-page links"
                                     % round(100 * (1 - len(orphaned) / max(1, len(sm_keys))))})
        else:
            na.append({"check_id": "SA-ORPHAN-SITEMAP-URLS",
                       "reason": "sitemap declares %d URLs against only %d crawled pages — too "
                                 "large a gap for a shallow sample to reliably judge orphaning; "
                                 "a fuller crawl (--max-pages) is needed to check this"
                                 % (len(sm_keys), len(ok))})

        crawled_keys = {_key(p["url"]) for p in ok}
        missing = crawled_keys - sm_keys
        if len(missing) >= max(2, len(crawled_keys) * 0.3):
            missing_pages = [p["url"] for p in ok if _key(p["url"]) in missing]
            out.append(finding(
                "SA-PAGES-MISSING-FROM-SITEMAP",
                "Pages that exist and are linked are absent from the sitemap", "low",
                evidence="%d of %d crawled pages are not declared in the sitemap, e.g. %s."
                         % (len(missing), len(crawled_keys), missing_pages[0]),
                action="Regenerate the sitemap from the same source that drives navigation so "
                       "new pages are declared automatically.",
                mechanism="The sitemap is a crawler's fastest way to learn a URL exists and "
                          "when it last changed. A real page missing from it is discovered "
                          "later, if at all, and never gets a <lastmod> signal.",
                urls=missing_pages[:10]))
        else:
            na.append({"check_id": "SA-PAGES-MISSING-FROM-SITEMAP",
                       "reason": "crawled pages are declared in the sitemap"})
    else:
        na.append({"check_id": "SA-ORPHAN-SITEMAP-URLS",
                   "reason": "no usable sitemap (fewer than 5 URLs declared)"})
        na.append({"check_id": "SA-PAGES-MISSING-FROM-SITEMAP",
                   "reason": "no usable sitemap (fewer than 5 URLs declared)"})

    # ---------------------------------------------------------------- 4. links to redirecting URLs
    redirect_origins = {_key(p["url"]): p["url"] for p in pages if p.get("redirects")}
    if redirect_origins:
        stale_links = []
        for p in ok:
            for l in p["extract"]["links_internal"]:
                href = l.get("href", "")
                if href and _key(href) in redirect_origins and _key(href) != _key(p["url"]):
                    stale_links.append((p["url"], href))
        if stale_links:
            out.append(finding(
                "SA-INTERNAL-LINKS-TO-REDIRECTING-URLS",
                "Internal links point at URLs that redirect instead of the final URL", "low",
                evidence="%d internal link(s) target a URL that redirects during this crawl, "
                         "e.g. %s links to %s." % (
                             len(stale_links), stale_links[0][0], stale_links[0][1]),
                action="Update internal links to point directly at the final destination URL.",
                mechanism="Every redirect hop is a request some fetchers do not follow and "
                          "latency all of them pay. Internal links are entirely within the "
                          "site's control, so this is pure waste rather than an unavoidable "
                          "consequence of an external change.",
                urls=[u for _, u in stale_links][:10]))
        else:
            na.append({"check_id": "SA-INTERNAL-LINKS-TO-REDIRECTING-URLS",
                       "reason": "no internal link targets a URL that redirected during this "
                                 "crawl"})
    else:
        na.append({"check_id": "SA-INTERNAL-LINKS-TO-REDIRECTING-URLS",
                   "reason": "no crawled URL redirected"})

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "interior_pages": len(interior),
            "sitemap_urls": len(sm_urls),
            "pages_crawled": len(ok),
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
