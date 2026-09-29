#!/usr/bin/env python3
"""Stage 3 of the audit: is the page's meaning stated explicitly, and is the
brand identified unambiguously?

Validates JSON-LD/microdata against what the site actually is (from
bundle/profile.json), checks required properties, and — the check that matters
most and is most often skipped — verifies that the structured data agrees with
the visible page.

If bundle/profile.json is absent this script runs only the type-agnostic checks
and records the rest as not-applicable rather than guessing.

Usage: python3 check_schema.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re

SKILL = "structured-data-audit"

# Properties without which a node cannot answer the question it exists to answer.
REQUIRED = {
    "organization": ["name", "url"],
    "localbusiness": ["name", "address", "telephone"],
    "product": ["name", "offers"],
    "offer": ["price", "priceCurrency", "availability"],
    "article": ["headline", "datePublished", "author"],
    "blogposting": ["headline", "datePublished", "author"],
    "newsarticle": ["headline", "datePublished", "author"],
    "techarticle": ["headline", "datePublished"],
    "event": ["name", "startDate", "location"],
    "faqpage": ["mainEntity"],
    "breadcrumblist": ["itemListElement"],
    "person": ["name"],
    "recipe": ["name", "recipeIngredient", "recipeInstructions"],
    "jobposting": ["title", "datePosted", "hiringOrganization"],
}
# Identity anchors: independent, machine-resolvable references to the same entity.
STRONG_SAMEAS = re.compile(
    r"(wikidata\.org|wikipedia\.org|crunchbase\.com|linkedin\.com/company|"
    r"github\.com|opencorporates\.com|bloomberg\.com|sec\.gov|companieshouse\.gov)", re.I)
QUESTION_HEADING = re.compile(
    r"^\s*(what|how|why|when|where|who|which|can|do|does|is|are|should|will)\b.*\?\s*$", re.I)
PRICE_RX = re.compile(r"[$£€₹¥]\s?([\d,]+(?:\.\d{1,2})?)|([\d,]+(?:\.\d{1,2})?)\s?(USD|EUR|GBP|INR)", re.I)


def load(bundle):
    def j(name, default=None):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            return default
        with open(path) as fh:
            return json.load(fh)
    meta, idx = j("meta.json"), j("index.json")
    profile = j("profile.json")
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


def walk(node):
    """Yield every dict that carries an @type, flattening @graph and nesting."""
    stack = [node]
    while stack:
        n = stack.pop()
        if isinstance(n, dict):
            if "@type" in n:
                yield n
            for v in n.values():
                if isinstance(v, (dict, list)):
                    stack.append(v)
        elif isinstance(n, list):
            stack.extend(n)


def type_names(node):
    t = node.get("@type")
    if isinstance(t, str):
        return [t.rsplit("/", 1)[-1].lower()]
    if isinstance(t, list):
        return [str(x).rsplit("/", 1)[-1].lower() for x in t]
    return []


def prop_present(node, prop):
    v = node.get(prop)
    if v is None:
        return False
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, dict)):
        return bool(v)
    return True


def parse_page_jsonld(extract):
    nodes, errors = [], []
    for raw in extract["jsonld_raw"]:
        try:
            data = json.loads(raw)
        except Exception as e:
            errors.append("%s: %s" % (type(e).__name__, str(e)[:90]))
            continue
        for n in walk(data):
            nodes.append(n)
    return nodes, errors


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages, profile = load(bundle)
    out, na = [], []
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    if not ok:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [],
                "observations": {"note": "no HTML pages available to analyse"}}
    home = next((p for p in ok if p["type"] == "home"), ok[0])
    site_type = (profile or {}).get("site_type")
    brand = (profile or {}).get("brand_name") or meta["site"]

    per_page, all_nodes, parse_errors = {}, [], []
    for p in ok:
        nodes, errors = parse_page_jsonld(p["extract"])
        per_page[p["id"]] = nodes
        all_nodes.extend(nodes)
        if errors:
            parse_errors.append((p["url"], errors))
    present_types = {t for n in all_nodes for t in type_names(n)}
    micro_types = {m.rsplit("/", 1)[-1].lower() for p in ok for m in p["extract"]["microdata_types"]}

    # ---------------------------------------------------------------- 1. none at all
    if not all_nodes and not micro_types:
        out.append(finding(
            "SD-NONE", "No structured data anywhere on the site", "high",
            "None of the %d crawled pages contains JSON-LD, microdata or RDFa." % len(ok),
            "Add JSON-LD: an Organization (or LocalBusiness) node sitewide, plus the type that "
            "matches each template (%s)."
            % ", ".join((profile or {}).get("expected_schema_types", ["Organization", "WebSite"])),
            mechanism="Structured data is the one place a page states its facts unambiguously "
                      "and in a form that needs no interpretation. Without it, every fact has to "
                      "be inferred from prose, which is lossy and often simply skipped.",
            detail="Start with one Organization node in the site template carrying name, url, "
                   "logo, description and sameAs; that single block does most of the work for "
                   "brand identity.",
            urls=[home["url"]],
            verification="Paste each template's URL into a schema validator; it should report the "
                         "expected type with no errors."))
    elif not all_nodes and micro_types:
        out.append(finding(
            "SD-MICRODATA-ONLY", "Structured data uses only microdata/RDFa, not JSON-LD", "low",
            "Found microdata types %s and no JSON-LD blocks." % ", ".join(sorted(micro_types)[:6]),
            "Move to JSON-LD in a <script type=\"application/ld+json\"> block.",
            mechanism="Microdata is still read, but it is interleaved with markup and breaks "
                      "whenever the template changes. JSON-LD is a single self-contained block "
                      "and is the format most consumers parse most reliably.",
            urls=[home["url"]], effort="medium"))

    # ---------------------------------------------------------------- 2. invalid JSON
    if parse_errors:
        out.append(finding(
            "SD-INVALID-JSON", "Structured data blocks contain invalid JSON", "high",
            "%d page(s) have unparseable JSON-LD. Example %s: %s"
            % (len(parse_errors), parse_errors[0][0], parse_errors[0][1][0]),
            "Fix the JSON syntax — most often an unescaped quote or a trailing comma from "
            "templated string interpolation.",
            mechanism="A block that does not parse is discarded entirely, so the page silently "
                      "has no structured data at all despite appearing to have it.",
            urls=[u for u, _ in parse_errors][:8], effort="low",
            verification="Run each block through a JSON parser in CI so it cannot regress."))

    # ---------------------------------------------------------------- 3. @context
    ctx_missing = []
    for p in ok:
        for raw in p["extract"]["jsonld_raw"]:
            try:
                d = json.loads(raw)
            except Exception:
                continue
            top = d[0] if isinstance(d, list) and d else d
            if isinstance(top, dict) and "@context" not in top:
                ctx_missing.append(p["url"])
                break
    if ctx_missing:
        out.append(finding(
            "SD-NO-CONTEXT", "JSON-LD blocks omit @context", "medium",
            "%d page(s) have a JSON-LD block with no @context, e.g. %s."
            % (len(ctx_missing), ctx_missing[0]),
            "Add \"@context\": \"https://schema.org\" to the top of each block.",
            mechanism="Without @context the types are undefined names rather than schema.org "
                      "terms, and the whole block is ignored.",
            urls=ctx_missing[:8], effort="low"))

    # ---------------------------------------------------------------- 4. organisation identity
    org_missing_reported = False
    org_nodes = [n for n in all_nodes if {"organization", "localbusiness", "corporation", "ngo",
                                          "onlinestore", "store", "restaurant", "medicalbusiness",
                                          "professionalservice", "educationalorganization"}
                 & set(type_names(n))]
    if all_nodes and not org_nodes:
        org_missing_reported = True
        out.append(finding(
            "SD-NO-ORGANIZATION", "No Organization node identifies the brand", "high",
            "%d JSON-LD node(s) across %d crawled pages declare types (%s), but none is an "
            "Organization or LocalBusiness."
            % (len(all_nodes), len(ok), ", ".join(sorted(present_types)[:6])),
            "Add an Organization node to the site-wide template with name, url, logo, description "
            "and sameAs.",
            mechanism="Page-level types describe individual pages. Only an Organization node says "
                      "who publishes them, which is what links every page to one brand entity.",
            urls=[home["url"]]))
    elif org_nodes:
        merged = {}
        for n in org_nodes:
            for k, v in n.items():
                merged.setdefault(k, v)
        weak = [f for f in ("name", "url", "logo", "description") if not prop_present(merged, f)]
        if weak:
            out.append(finding(
                "SD-ORGANIZATION-INCOMPLETE", "The Organization node is missing core properties",
                "medium",
                "Organization node present with %s; missing %s."
                % (", ".join(sorted(k for k in merged if not k.startswith("@")))[:120],
                   ", ".join(weak)),
                "Populate name, url, logo and a one-sentence description on the Organization node.",
                mechanism="These four properties are what a knowledge graph stores about the "
                          "brand. A description in particular is the text an assistant is most "
                          "likely to reuse when asked what the company is.",
                urls=[home["url"]], effort="low"))

        sameas = []
        for n in org_nodes:
            v = n.get("sameAs")
            if isinstance(v, str):
                sameas.append(v)
            elif isinstance(v, list):
                sameas.extend(x for x in v if isinstance(x, str))
        strong = [s for s in sameas if STRONG_SAMEAS.search(s)]
        if not sameas:
            out.append(finding(
                "SD-NO-SAMEAS", "The brand entity has no sameAs identity links", "high",
                "The Organization node declares no sameAs property on any crawled page.",
                "Add sameAs links to the brand's authoritative profiles — Wikidata and Wikipedia "
                "if they exist, plus LinkedIn company page, Crunchbase, GitHub org, and the main "
                "social accounts.",
                mechanism="sameAs is how a page says 'the thing I am describing is this known "
                          "entity'. Without it, a brand whose name resembles another company, a "
                          "common word or a product name gets conflated with them, and answers "
                          "about the brand carry facts belonging to something else.",
                detail="Order matters less than independence: two or three references that "
                       "resolve to registries a machine already trusts (Wikidata, Companies "
                       "House, LinkedIn) disambiguate far better than five social links.",
                urls=[home["url"]], effort="low",
                verification="Search the brand name plus its category and confirm the returned "
                             "entity carries this site's URL."))
        elif not strong:
            out.append(finding(
                "SD-WEAK-SAMEAS", "sameAs links point only at social profiles", "medium",
                "sameAs values: %s — none resolve to an identity registry (Wikidata, Wikipedia, "
                "LinkedIn company, Crunchbase, GitHub org)." % ", ".join(sameas[:5]),
                "Add at least one registry-grade identifier, and create a Wikidata item for the "
                "brand if none exists.",
                mechanism="Social handles are easy to duplicate and are weak evidence of identity. "
                          "Registry entries are what disambiguation actually resolves against.",
                urls=[home["url"]], effort="medium"))
        else:
            na.append({"check_id": "SD-NO-SAMEAS",
                       "reason": "registry-grade sameAs links present: %s" % ", ".join(strong[:3])})

        names = {str(n.get("name", "")).strip() for n in org_nodes if n.get("name")}
        if len(names) > 1:
            out.append(finding(
                "SD-CONFLICTING-ORG-NAMES", "Different pages declare different organisation names",
                "medium",
                "Organization nodes across the site use these names: %s."
                % ", ".join(sorted(names)[:5]),
                "Use one exact legal or trading name everywhere, and put the variants in "
                "alternateName.",
                mechanism="Conflicting names across a site split one entity into several, so "
                          "signals that should reinforce a single brand are divided between them.",
                urls=[home["url"]], effort="low"))

    # ---------------------------------------------------------------- 5. expected types per site type
    # Suppressed when SD-NONE already fired: "no markup at all" and "missing the
    # expected types" are the same defect, and reporting both inflates severity.
    if profile and not (all_nodes or micro_types):
        na.append({"check_id": "SD-MISSING-EXPECTED-TYPES",
                   "reason": "subsumed by SD-NONE (no structured data of any kind)"})
    elif profile:
        expected = [t for t in profile.get("expected_schema_types", [])]
        sig = profile.get("signals", {})
        applicable = []
        for t in expected:
            tl = t.lower()
            if tl in ("product", "offer") and sig.get("product_pages", 0) == 0:
                na.append({"check_id": "SD-MISSING-TYPE:%s" % t,
                           "reason": "no product pages were found on this site"})
                continue
            if tl == "article" and sig.get("article_pages", 0) == 0:
                na.append({"check_id": "SD-MISSING-TYPE:Article",
                           "reason": "no article pages were found on this site"})
                continue
            if tl in ("openinghoursspecification", "postaladdress") and not sig.get("has_address"):
                na.append({"check_id": "SD-MISSING-TYPE:%s" % t,
                           "reason": "no physical address found; opening hours do not apply"})
                continue
            if tl == "faqpage":
                continue  # handled as an opportunity below
            if tl == "organization" and org_missing_reported:
                continue  # already reported as SD-NO-ORGANIZATION
            if tl == "breadcrumblist":
                continue  # SD-NO-BREADCRUMBS reports this with better evidence
            applicable.append(t)
        missing = [t for t in applicable if t.lower() not in present_types
                   and t.lower() not in micro_types]
        if missing:
            sev = "high" if any(m.lower() in ("product", "localbusiness", "organization")
                                for m in missing) else "medium"
            out.append(finding(
                "SD-MISSING-EXPECTED-TYPES",
                "Structured data is missing the types this kind of site needs", sev,
                "Site classified as %s (%s). Missing: %s. Present: %s."
                % (site_type, profile.get("classification_reason"), ", ".join(missing),
                   ", ".join(sorted(present_types | micro_types)) or "none"),
                "Add %s markup to the matching templates." % ", ".join(missing),
                mechanism="Each type answers a different question. Product/Offer answers 'what is "
                          "it and what does it cost', LocalBusiness answers 'where and when', "
                          "Article answers 'who wrote this and when'. A missing type means that "
                          "question has no machine-readable answer on the page that should own it.",
                urls=[home["url"]]))

    # ---------------------------------------------------------------- 6. required properties
    incomplete = {}
    for p in ok:
        for n in per_page.get(p["id"], []):
            for t in type_names(n):
                if t not in REQUIRED:
                    continue
                # Listing pages legitimately carry stub Product nodes that defer
                # detail to the product page; only the detail page must be complete.
                if t in ("product", "offer") and p["type"] != "product":
                    continue
                missing = [f for f in REQUIRED[t] if not prop_present(n, f)]
                if missing:
                    incomplete.setdefault(t, []).append((p["url"], missing))
    for t, hits in incomplete.items():
        fields = sorted({f for _, ms in hits for f in ms})
        sev = "high" if t in ("product", "offer", "localbusiness") else "medium"
        out.append(finding(
            "SD-INCOMPLETE-%s" % t.upper(),
            "%s markup is missing required properties" % t.title(), sev,
            "%d %s node(s) lack %s. Example: %s (missing %s)."
            % (len(hits), t.title(), ", ".join(fields), hits[0][0], ", ".join(hits[0][1])),
            "Populate %s on every %s node." % (", ".join(fields), t.title()),
            mechanism="An incomplete node is often treated as invalid and dropped, which is worse "
                      "than having no markup: the page appears marked up while providing nothing "
                      "extractable.",
            urls=[u for u, _ in hits][:8], effort="low",
            verification="Validate a page of each template and confirm zero required-property "
                         "errors."))

    # ---------------------------------------------------------------- 7. schema vs visible page
    contradictions = []
    for p in ok:
        text = p["extract"]["text"]
        page_prices = {m.group(1) or m.group(2) for m in PRICE_RX.finditer(text)}
        page_prices = {x.replace(",", "") for x in page_prices if x}
        for n in per_page.get(p["id"], []):
            if "offer" not in " ".join(type_names(n)) and "offers" not in n:
                continue
            offers = n.get("offers", n) if isinstance(n.get("offers", n), dict) else n
            price = offers.get("price") if isinstance(offers, dict) else None
            if price is None:
                continue
            sp = str(price).replace(",", "").rstrip("0").rstrip(".") or str(price)
            if page_prices and not any(sp in q or q in sp for q in page_prices):
                contradictions.append((p["url"], "offer price %s vs price(s) shown on the page: %s"
                                       % (price, ", ".join(sorted(page_prices)[:3]))))
        for n in per_page.get(p["id"], []):
            if not ({"product", "article", "blogposting", "newsarticle"} & set(type_names(n))):
                continue
            name = str(n.get("name") or n.get("headline") or "").strip()
            if not name or len(name) < 6:
                continue
            haystack = (p["extract"]["title"] + " " + " ".join(p["extract"]["h1s"])).lower()
            if name.lower() not in haystack and haystack and \
                    len(set(name.lower().split()) & set(haystack.split())) < 2:
                contradictions.append((p["url"], "structured name %r does not match the page "
                                                 "heading/title %r" % (name[:60], haystack[:60])))
    if contradictions:
        out.append(finding(
            "SD-CONTRADICTS-PAGE", "Structured data disagrees with the visible page", "high",
            "%d mismatch(es). Example — %s: %s" % (len(contradictions), contradictions[0][0],
                                                   contradictions[0][1]),
            "Generate structured data from the same data source that renders the page, so the two "
            "cannot drift apart.",
            confidence="medium",
            mechanism="A contradiction between markup and visible content is a trust signal in "
                      "reverse: consumers that detect it discount the markup, and some discount "
                      "the whole domain. Hand-maintained or hard-coded JSON-LD is the usual cause.",
            urls=[u for u, _ in contradictions][:8],
            verification="Change a price in the CMS and confirm both the visible page and the "
                         "JSON-LD update together."))
    else:
        na.append({"check_id": "SD-CONTRADICTS-PAGE",
                   "reason": "no price or name mismatches detected between markup and page text"})

    # ---------------------------------------------------------------- 8. breadcrumbs
    deep = [p for p in ok if len([s for s in p["url"].split("/") if s]) >= 4]
    if deep and "breadcrumblist" not in present_types and "breadcrumblist" not in micro_types:
        out.append(finding(
            "SD-NO-BREADCRUMBS", "Deep pages carry no BreadcrumbList markup", "medium",
            "%d crawled pages are three or more levels deep (e.g. %s) and no BreadcrumbList node "
            "was found." % (len(deep), deep[0]["url"]),
            "Add BreadcrumbList markup, and render matching visible breadcrumbs, on every page "
            "below the top level.",
            category="both",
            mechanism="Breadcrumbs tell a machine where a page sits in the site and tell a "
                      "visitor arriving from an AI answer what the surrounding context is. "
                      "Assistants send people to deep pages, not homepages, so this is the "
                      "cheapest fix that helps both extraction and orientation.",
            urls=[p["url"] for p in deep][:8], effort="low"))

    # ---------------------------------------------------------------- 9. FAQ opportunity
    q_pages = []
    for p in ok:
        qs = [h for h in p["extract"]["headings"] if QUESTION_HEADING.match(h["text"] or "")]
        if len(qs) >= 3:
            q_pages.append((p, len(qs), qs[0]["text"][:70]))
    if q_pages and "faqpage" not in present_types and "qapage" not in present_types:
        p, nq, sample = q_pages[0]
        out.append(finding(
            "SD-FAQ-OPPORTUNITY", "Question-and-answer content is not marked up as FAQPage",
            "medium",
            "%s has %d question-shaped headings (e.g. %r) with no FAQPage markup."
            % (p["url"], nq, sample),
            "Wrap the existing Q&A in FAQPage markup, with each answer as acceptedAnswer text.",
            mechanism="Question-shaped headings paired with short direct answers are the single "
                      "most quotable structure on a site — it matches the shape of what a user "
                      "asked. Marking it up makes the pairing explicit instead of inferred.",
            detail="Only mark up Q&A that is genuinely visible on the page; markup for hidden "
                   "content is a policy violation with most consumers.",
            urls=[q[0]["url"] for q in q_pages][:6], effort="low"))
    elif not q_pages:
        na.append({"check_id": "SD-FAQ-OPPORTUNITY",
                   "reason": "no page carries three or more question-shaped headings"})

    # ---------------------------------------------------------------- 10. WebSite node
    if all_nodes and "website" not in present_types:
        out.append(finding(
            "SD-NO-WEBSITE-NODE", "No WebSite node declares the site's name", "low",
            "Structured data present but no WebSite node found across %d pages." % len(ok),
            "Add a WebSite node with name, url and (if the site has search) a "
            "potentialAction/SearchAction.",
            mechanism="The WebSite node is what supplies the site's display name and links the "
                      "domain to the brand entity, rather than leaving it inferred from the URL.",
            urls=[home["url"]], effort="low"))

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "site_type": site_type, "brand": brand,
            "schema_types_found": sorted(present_types | micro_types),
            "jsonld_nodes": len(all_nodes), "pages_analysed": len(ok),
            "profile_available": bool(profile),
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
