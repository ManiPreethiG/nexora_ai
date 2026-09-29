#!/usr/bin/env python3
"""Classify the site before any check runs, and write bundle/profile.json.

Every downstream check consults this profile so that expectations match what the
site actually is. Flagging "no Product schema" on a consultancy or "no opening
hours" on a SaaS product is the main source of false positives in an audit like
this one, and the profile is how that is prevented.

Usage: python3 profile.py --bundle ./bundle
"""

import argparse
import json
import os
import re

PRICE_RX = re.compile(r"[$£€₹¥]\s?\d|(?:\d[\d,.]*)\s?(?:USD|EUR|GBP|INR|AUD|CAD)", re.I)
CART_RX = re.compile(r"(add[-_ ]to[-_ ]cart|/cart|/checkout|/basket|add to bag|buy now|"
                     r"shopify|woocommerce|bigcommerce|magento|snipcart)", re.I)
TRIAL_RX = re.compile(r"(free trial|start free|sign up free|get started free|book a demo|"
                      r"request a demo|start building|create an account)", re.I)
HOURS_RX = re.compile(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*[-–—:]?\s*"
                      r"(mon|tue|wed|thu|fri|sat|sun|\d{1,2}\s?(am|pm|:))", re.I)
PHONE_RX = re.compile(r"(\+\d[\d\s().-]{7,}\d|\(\d{3}\)\s?\d{3}[-.\s]?\d{4}|"
                      r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")
ADDRESS_RX = re.compile(r"\b\d{1,5}\s+[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,4}\s+"
                        r"(street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way|"
                        r"court|ct|suite|floor|plaza|park|square|sector|marg|nagar)\b", re.I)
DONATE_RX = re.compile(r"(donate|donation|charity|nonprofit|non-profit|registered charity|501\(c\))", re.I)

# Only types whose absence is a genuine defect for that kind of site. Anything
# merely desirable (SoftwareApplication, OpeningHoursSpecification, FAQPage) is
# raised as a proactive recommendation instead, so the findings list stays
# defensible.
SITE_TYPE_EXPECTATIONS = {
    "ecommerce":      ["Organization", "Product", "Offer", "BreadcrumbList"],
    "local_business": ["LocalBusiness", "PostalAddress"],
    "saas":           ["Organization", "WebSite"],
    "media":          ["Organization", "Article"],
    "docs":           ["Organization", "WebSite"],
    "nonprofit":      ["Organization"],
    "brochure":       ["Organization", "WebSite"],
}


def load(bundle):
    def j(name):
        with open(os.path.join(bundle, name)) as fh:
            return json.load(fh)
    meta, idx = j("meta.json"), j("index.json")
    pages = idx["pages"]
    for p in pages:
        path = os.path.join(bundle, "pages", p["id"] + ".extract.json")
        p["extract"] = None
        if os.path.exists(path):
            with open(path) as fh:
                p["extract"] = json.load(fh)
    return meta, pages


def derive_brand(extract, registrable):
    """The brand name, not the tagline.

    Title tags are usually "Brand | Tagline" but sometimes "Tagline | Brand", so
    the segment is chosen by matching against the domain rather than by position
    — picking the wrong half turns every brand-name check downstream into noise.
    """
    def norm(x):
        return re.sub(r"[^a-z0-9]", "", (x or "").lower())

    og = (extract.get("og", {}) or {}).get("og:site_name", "").strip()
    if og and len(og) <= 40:
        return og
    label = registrable.split(".")[0]
    segments = [x.strip() for x in
                re.split(r"\s*[|\u2013\u2014\-\u00b7\u2022:]\s+", extract.get("title", "") or "")
                if x.strip()]
    for seg in segments:
        n = norm(seg)
        if n and (n in norm(label) or norm(label) in n):
            return seg
    generic = {"home", "homepage", "welcome", "index", "untitled", "main", "start",
               "official site", "official website", "home page"}
    candidates = [x for x in segments if x.lower() not in generic]
    if candidates:
        shortest = min(candidates, key=len)
        if len(shortest) <= 30 and len(shortest.split()) <= 4:
            return shortest
    return label.replace("-", " ").title()


def build(bundle):
    meta, pages = load(bundle)
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    types = {}
    for p in ok:
        types[p["type"]] = types.get(p["type"], 0) + 1
    all_text = "\n".join(p["extract"]["text"] for p in ok)
    all_html_links = " ".join(l["href"] for p in ok for l in
                              p["extract"]["links_internal"] + p["extract"]["links_external"])
    jsonld_types = {t.lower() for p in ok for t in p["extract"].get("jsonld_types", [])}
    micro = {m.rsplit("/", 1)[-1].lower() for p in ok for m in p["extract"]["microdata_types"]}
    schema_types = jsonld_types | micro

    signals = {
        "pages": len(ok),
        "page_types": types,
        "has_cart": bool(CART_RX.search(all_text + " " + all_html_links)),
        "price_mentions": len(PRICE_RX.findall(all_text)),
        "has_trial_cta": bool(TRIAL_RX.search(all_text)),
        "has_phone": bool(PHONE_RX.search(all_text)),
        "has_address": bool(ADDRESS_RX.search(all_text)),
        "has_hours": bool(HOURS_RX.search(all_text)),
        "has_donate": bool(DONATE_RX.search(all_text)),
        "article_pages": types.get("blog_post", 0),
        "docs_pages": types.get("docs", 0),
        "product_pages": types.get("product", 0) + types.get("category", 0),
        "has_pricing_page": types.get("pricing", 0) > 0,
        "schema_types": sorted(schema_types),
        "languages": sorted({p["extract"]["lang"].split("-")[0] for p in ok
                             if p["extract"].get("lang")}),
        "hreflangs": sorted({h for p in ok for h in p["extract"]["hreflangs"]}),
    }

    # Ordered from most to least specific; first match wins.
    if "localbusiness" in schema_types or (
            signals["has_address"] and signals["has_phone"] and signals["has_hours"]
            and signals["product_pages"] <= 1):
        site_type, why = "local_business", "address, phone and opening hours present on the site"
    elif signals["has_donate"] and not signals["has_cart"]:
        site_type, why = "nonprofit", "donation/charity language without commerce checkout"
    elif "product" in schema_types or (signals["has_cart"] and signals["product_pages"] >= 1):
        site_type, why = "ecommerce", "cart/checkout signals with product pages"
    elif signals["article_pages"] >= 3 and signals["article_pages"] >= signals["docs_pages"]:
        site_type, why = "media", "%d article pages found" % signals["article_pages"]
    elif signals["docs_pages"] >= 3:
        site_type, why = "docs", "%d documentation pages found" % signals["docs_pages"]
    elif signals["has_pricing_page"] or signals["has_trial_cta"]:
        site_type, why = "saas", "pricing page and/or trial/demo call to action"
    else:
        site_type, why = "brochure", "no commerce, publishing or documentation signals found"

    home = next((p for p in ok if p["type"] == "home"), ok[0] if ok else None)
    brand = derive_brand(home["extract"] if home else {},
                         meta.get("registrable_domain", meta["site"]))

    sameas = []
    for p in ok:
        for raw in p["extract"]["jsonld_raw"]:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            stack = [data]
            while stack:
                n = stack.pop()
                if isinstance(n, dict):
                    v = n.get("sameAs")
                    if isinstance(v, str):
                        sameas.append(v)
                    elif isinstance(v, list):
                        sameas.extend(x for x in v if isinstance(x, str))
                    stack.extend(x for x in n.values() if isinstance(x, (dict, list)))
                elif isinstance(n, list):
                    stack.extend(n)

    profile = {
        "site": meta["site"], "brand_name": brand, "site_type": site_type,
        "classification_reason": why, "signals": signals,
        "expected_schema_types": SITE_TYPE_EXPECTATIONS[site_type],
        "declared_same_as": sorted(set(sameas)),
        "primary_language": (signals["languages"] or ["unknown"])[0],
        "multilingual": len(signals["hreflangs"]) > 1,
    }
    with open(os.path.join(bundle, "profile.json"), "w") as fh:
        json.dump(profile, fh, indent=1)
    return profile


def load_profile(bundle):
    """Used by every check script; builds the profile on demand if absent."""
    path = os.path.join(bundle, "profile.json")
    if os.path.exists(path):
        with open(path) as fh:
            return json.load(fh)
    return build(bundle)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    a = ap.parse_args()
    print(json.dumps(build(a.bundle), indent=1))


if __name__ == "__main__":
    main()
