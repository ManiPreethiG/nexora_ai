#!/usr/bin/env python3
"""Local-business extension: for a site whose profile classifies it as a
local business, name/address/phone (NAP) consistency and hours/location
machine-readability are a well-documented, distinct failure mode from generic
corroboration — local answers are assembled largely from directory listings
that are compared against the site, and any on-site disagreement undermines
all of them at once.

Every check here is gated on `site_type == "local_business"` and reports
`not_applicable` with the reason otherwise, so it never fires a false positive
on a site the profile did not classify as local.

Reads a crawl bundle and emits findings JSON. Performs no network requests of
its own.

Usage: python3 check_local.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re

SKILL = "local-presence-audit"

ADDRESS_RX = re.compile(
    r"\b\d{1,5}\s+[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,4}\s+"
    r"(street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way|court|ct|"
    r"suite|floor|plaza|park|square|sector|marg|nagar)\b", re.I)
PHONE_RX = re.compile(r"(\+\d[\d\s().-]{7,}\d|\(\d{3}\)\s?\d{3}[-.\s]?\d{4}|"
                      r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")
HOURS_RX = re.compile(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*[-–—:]?\s*"
                      r"(mon|tue|wed|thu|fri|sat|sun|\d{1,2}\s?(am|pm|:))", re.I)
MAP_RX = re.compile(r"(google\.[a-z.]+/maps|goo\.gl/maps|maps\.app\.goo\.gl|"
                    r"apple\.com/maps|bing\.com/maps|openstreetmap\.org)", re.I)


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
            confidence="high", urls=None, mechanism="", detail="", effort="low",
            verification=""):
    return {
        "check_id": check_id, "title": title, "category": category, "concern": SKILL,
        "severity": severity, "confidence": confidence, "evidence": evidence,
        "affected_urls": urls or [], "mechanism": mechanism,
        "suggested_action": {"summary": action, "detail": detail, "priority": severity,
                             "effort": effort, "verification": verification},
    }


def _norm_phone(m):
    return re.sub(r"[^\d+]", "", m)


LOCAL_CHECK_IDS = ["LP-NAP-INCONSISTENT", "LP-HOURS-NOT-IN-SCHEMA", "LP-NO-MAP-EMBED-OR-LINK"]


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages, profile = load(bundle)
    out, na = [], []
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    site_type = (profile or {}).get("site_type")
    if site_type != "local_business":
        return {
            "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
            "findings": [],
            "not_applicable": [{"check_id": cid,
                                "reason": "site classified as %s, not local_business; NAP and "
                                          "map checks assume a physical, address-bound business"
                                          % (site_type or "unclassified")}
                               for cid in LOCAL_CHECK_IDS],
            "observations": {"site_type": site_type},
        }
    if not ok:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [],
                "observations": {"note": "no HTML pages available to analyse"}}
    home = next((p for p in ok if p["type"] == "home"), ok[0])
    all_text = "\n".join(p["extract"]["text"] for p in ok)

    # ---------------------------------------------------------------- 1. NAP consistency
    addresses = {re.sub(r"\s+", " ", m.group(0)).strip()
                for m in ADDRESS_RX.finditer(all_text)}
    phones = {_norm_phone(m) for m in PHONE_RX.findall(all_text)}
    phones = {p for p in phones if len(p) >= 9}
    if len(addresses) >= 2 or len(phones) >= 2:
        parts = []
        if len(addresses) >= 2:
            parts.append("%d distinct street addresses (%s)"
                         % (len(addresses), "; ".join(sorted(addresses)[:3])))
        if len(phones) >= 2:
            parts.append("%d distinct phone numbers (%s)"
                         % (len(phones), ", ".join(sorted(phones)[:3])))
        out.append(finding(
            "LP-NAP-INCONSISTENT",
            "The site publishes more than one address or phone number for the same business",
            "high",
            evidence="Across %d crawled pages: %s." % (len(ok), "; ".join(parts)),
            action="Publish exactly one name/address/phone combination sitewide (footer, "
                   "contact page, and LocalBusiness structured data), and route any secondary "
                   "line to a clearly labelled department rather than listing it as an "
                   "alternative.",
            mechanism="Local answers are assembled by matching name, address and phone across "
                      "the site and third-party directories. When the site itself disagrees "
                      "with itself, there is no single value for a directory listing to confirm "
                      "against, and mismatched NAP is the single most common cause of a local "
                      "business being cited with wrong or outdated details.",
            urls=[home["url"]]))
    else:
        na.append({"check_id": "LP-NAP-INCONSISTENT",
                   "reason": "at most one address and one phone number found across the site"})

    # ---------------------------------------------------------------- 2. hours in schema
    has_hours_text = bool(HOURS_RX.search(all_text))
    jsonld_has_hours = any(
        re.search(r'"openingHours(Specification)?"', raw)
        for p in ok for raw in p["extract"]["jsonld_raw"])
    if has_hours_text and not jsonld_has_hours:
        out.append(finding(
            "LP-HOURS-NOT-IN-SCHEMA",
            "Opening hours appear in text but not in structured data", "medium",
            evidence="Hours text (e.g. day-range/time patterns) was found on the site, but no "
                     "openingHours or openingHoursSpecification property was found in any "
                     "JSON-LD across %d crawled pages." % len(ok),
            action="Add openingHoursSpecification to the LocalBusiness node, matching the "
                   "hours shown in the page text exactly.",
            confidence="medium",
            mechanism="Hours are one of the highest-value facts for a 'is it open now' query. "
                      "Text alone requires a model to parse day-range prose correctly; "
                      "structured data makes the answer exact and machine-checkable.",
            urls=[home["url"]]))
    elif has_hours_text:
        na.append({"check_id": "LP-HOURS-NOT-IN-SCHEMA",
                   "reason": "openingHours structured data already present"})
    else:
        na.append({"check_id": "LP-HOURS-NOT-IN-SCHEMA",
                   "reason": "no hours text found on the site to compare against schema"})

    # ---------------------------------------------------------------- 3. map embed or link
    has_map = any(MAP_RX.search(l.get("href", "")) for p in ok
                 for l in p["extract"]["links_internal"] + p["extract"]["links_external"])
    has_map = has_map or any(MAP_RX.search(f.get("src", "")) for p in ok
                             for f in p["extract"]["iframes"])
    if not has_map:
        out.append(finding(
            "LP-NO-MAP-EMBED-OR-LINK",
            "No link or embed to a map provider was found", "medium",
            evidence="No Google/Apple/Bing/OpenStreetMap link or iframe embed was found across "
                     "%d crawled pages." % len(ok),
            action="Add a link to the Google Business Profile listing (and/or an embedded map) "
                   "on the contact page and in the footer.",
            confidence="medium",
            mechanism="A map link is both a direct navigation aid for the visitor and, for "
                      "Google specifically, one of the more direct on-site anchors to the "
                      "business's actual map listing — the source most local answers are built "
                      "from.",
            urls=[home["url"]]))
    else:
        na.append({"check_id": "LP-NO-MAP-EMBED-OR-LINK",
                   "reason": "a map provider link or embed was found"})

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "site_type": site_type,
            "distinct_addresses": len(addresses),
            "distinct_phones": len(phones),
            "has_map_anchor": has_map,
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
