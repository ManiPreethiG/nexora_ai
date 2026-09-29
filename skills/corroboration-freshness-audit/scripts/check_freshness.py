#!/usr/bin/env python3
"""Stage 4 of the audit, on-site half: is what the site says current, internally
consistent, and anchored to something outside itself?

This script covers only what can be established deterministically from the crawl
bundle. The off-site half — whether independent sources repeat the same facts,
whether the brand name collides with other entities, and what assistants
currently say about the brand — needs live search and is run by the agent
following references/offsite-protocol.md; its findings are merged by the
entrypoint.

Usage: python3 check_freshness.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import datetime as dt
import json
import os
import re

SKILL = "corroboration-freshness-audit"
NOW = dt.datetime.now(dt.timezone.utc)

ISO_RX = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")
LONG_DATE_RX = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2}),?\s+(20\d{2})\b|"
    r"\b(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?,?\s+(20\d{2})\b", re.I)
COPYRIGHT_RX = re.compile(r"(?:©|\(c\)|copyright)\s*(?:20\d{2}\s*[-–—]\s*)?(20\d{2})", re.I)
PHONE_RX = re.compile(r"(\+\d[\d\s().-]{7,}\d|\(\d{3}\)\s?\d{3}[-.\s]?\d{4}|"
                      r"\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")
EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
CLAIM_RX = re.compile(
    r"\b(#\s?1|no\.?\s?1|number one|world'?s (?:leading|largest|best|first)|"
    r"(?:the|a) leading|market leader|industry[- ]leading|best[- ]in[- ]class|"
    r"most (?:popular|trusted|advanced)|award[- ]winning|fastest[- ]growing|"
    r"\d{1,3}(?:\.\d+)?%\s+(?:more|faster|better|higher|lower|increase|reduction|growth)|"
    r"trusted by [\d,]+|\b[\d,]{4,}\+? (?:customers|clients|users|companies))\b", re.I)
FUTURE_PROMISE_RX = re.compile(
    r"\b(coming soon|launching (?:in|on)|available (?:in|from)|will launch|"
    r"join us (?:on|at)|register (?:now|today) for|save the date)\b[^.]{0,60}?(20\d{2})", re.I)
AUTHORITY_RX = re.compile(
    r"(wikipedia\.org|wikidata\.org|crunchbase\.com|linkedin\.com/company|github\.com/|"
    r"g2\.com|capterra\.com|trustpilot\.com|glassdoor|bbb\.org|opencorporates|"
    r"companieshouse|sec\.gov|producthunt\.com|yelp\.com|tripadvisor|"
    r"google\.com/maps|goo\.gl/maps|maps\.app\.goo\.gl)", re.I)
# Names that are ordinary words carry a high risk of entity collision.
STOPWORDS = {
    "with", "that", "this", "from", "your", "their", "have", "more", "than", "into",
    "over", "also", "them", "they", "which", "about", "help", "helps", "make", "makes",
    "using", "used", "when", "what", "were", "been", "will", "such", "other", "many",
    "types", "kinds", "sizes", "based", "across", "through", "including", "provides",
}
COMMON_WORDS = {
    "apex", "arc", "atlas", "aurora", "beacon", "bloom", "bolt", "boost", "bridge",
    "canvas", "cargo", "chain", "circle", "clarity", "climb", "cloud", "compass",
    "core", "craft", "crest", "cube", "current", "delta", "drift", "echo", "edge",
    "element", "ember", "engine", "epic", "everest", "flow", "focus", "forge",
    "forest", "found", "frame", "fresh", "fusion", "gather", "glow", "grain",
    "grid", "grove", "harbor", "harbour", "haven", "helix", "horizon", "hub",
    "impact", "index", "insight", "ivy", "journey", "keystone", "lantern", "layer",
    "leaf", "ledger", "lift", "linear", "link", "loop", "lumen", "matrix", "meridian",
    "mesh", "method", "momentum", "motion", "nexus", "north", "notion", "oak",
    "onward", "orbit", "origin", "otter", "pace", "path", "peak", "pillar", "pine",
    "pivot", "pixel", "plane", "prism", "pulse", "quest", "radius", "ramp", "range",
    "reach", "relay", "ripple", "river", "rocket", "root", "scale", "sequoia",
    "shift", "signal", "slate", "spark", "sphere", "spring", "sprout", "stack",
    "stone", "storm", "stream", "summit", "surge", "swift", "tempo", "thread",
    "tide", "torch", "trace", "track", "trail", "vector", "venture", "vertex",
    "vessel", "vine", "vista", "voyage", "wave", "willow", "window", "zenith",
}


def load(bundle):
    def j(name, default=None):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            return default
        with open(path) as fh:
            return json.load(fh)
    meta, idx = j("meta.json"), j("index.json")
    profile, sitemap = j("profile.json"), j("sitemap.json", {"documents": [], "urls": []})
    for p in idx["pages"]:
        path = os.path.join(bundle, "pages", p["id"] + ".extract.json")
        p["extract"] = None
        if os.path.exists(path):
            with open(path) as fh:
                p["extract"] = json.load(fh)
    return meta, idx["pages"], profile, sitemap


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


def page_dates(p):
    """Every credible publication/update date for a page, newest first."""
    found = []
    ex = p["extract"]
    for key in ("article:published_time", "article:modified_time", "og:updated_time",
                "date", "last-modified", "dc.date"):
        v = ex["meta"].get(key) or ex["og"].get(key, "")
        m = ISO_RX.search(v or "")
        if m:
            found.append(m.group(0))
    for t in ex["time_tags"]:
        m = ISO_RX.search(t.get("datetime", ""))
        if m:
            found.append(m.group(0))
    for raw in ex["jsonld_raw"]:
        for m in re.finditer(r'"(?:datePublished|dateModified|uploadDate)"\s*:\s*"(20\d{2}-\d{2}-\d{2})',
                             raw):
            found.append(m.group(1))
    body = ex["text"][:4000]
    for m in ISO_RX.finditer(body):
        found.append(m.group(0))
    for m in LONG_DATE_RX.finditer(body):
        g = m.groups()
        try:
            if g[0]:
                found.append(dt.datetime.strptime("%s %s %s" % (g[0][:3], g[1], g[2]),
                                                  "%b %d %Y").strftime("%Y-%m-%d"))
            else:
                found.append(dt.datetime.strptime("%s %s %s" % (g[4][:3], g[3], g[5]),
                                                  "%b %d %Y").strftime("%Y-%m-%d"))
        except ValueError:
            pass
    out = []
    for d in found:
        try:
            parsed = dt.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=dt.timezone.utc)
        except ValueError:
            continue
        if dt.datetime(2000, 1, 1, tzinfo=dt.timezone.utc) < parsed < NOW + dt.timedelta(days=400):
            out.append(parsed)
    return sorted(out, reverse=True)


def months_ago(d):
    return (NOW - d).days / 30.44


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages, profile, sitemap = load(bundle)
    out, na = [], []
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    if not ok:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [],
                "observations": {"note": "no HTML pages available to analyse"}}
    home = next((p for p in ok if p["type"] == "home"), ok[0])
    brand = (profile or {}).get("brand_name") or meta["site"].split(".")[0]
    all_text = "\n".join(p["extract"]["text"] for p in ok)
    dated = {p["id"]: page_dates(p) for p in ok}

    # ---------------------------------------------------------------- 1. stale copyright
    years = [int(m.group(1)) for m in COPYRIGHT_RX.finditer(all_text)]
    if years:
        newest = max(years)
        if newest < NOW.year - 1:
            out.append(finding(
                "CF-STALE-COPYRIGHT", "Footer copyright year is out of date", "low",
                "The newest copyright year found anywhere on the site is %d; the current year is "
                "%d." % (newest, NOW.year),
                "Render the copyright year dynamically from the server date.",
                mechanism="A stale copyright is a small signal read widely: it is the quickest "
                          "cue that a site is unmaintained, for a human deciding whether to trust "
                          "it and for a model weighing how current the page is.",
                urls=[home["url"]], effort="low"))
        else:
            na.append({"check_id": "CF-STALE-COPYRIGHT",
                       "reason": "copyright year %d is current" % newest})

    # ---------------------------------------------------------------- 2. dateless content
    # Only content that carries an implicit "as of when" claim. Marketing, legal
    # and product pages are not expected to be dated, so demanding it there is a
    # false positive.
    DATED_TYPES = {"blog_post", "blog_index", "docs", "case_study"}
    UNDATED_TYPES = {"home", "pricing", "legal", "contact", "about", "careers", "product",
                     "category"}
    content_pages = [p for p in ok if p["type"] in DATED_TYPES
                     or (p["extract"]["word_count"] > 900 and p["type"] not in UNDATED_TYPES)]
    dateless = [p for p in content_pages if not dated[p["id"]]]
    if content_pages and len(dateless) >= max(2, len(content_pages) * 0.6):
        out.append(finding(
            "CF-NO-VISIBLE-DATES", "Substantive pages carry no publication or update date",
            "medium",
            "%d of %d substantive pages expose no date in text, <time>, meta tags or structured "
            "data. Example: %s." % (len(dateless), len(content_pages), dateless[0]["url"]),
            "Show 'Published <date>' and 'Last updated <date>' on every substantive page, and "
            "mirror them as datePublished/dateModified in structured data.",
            mechanism="Recency is one of the few quality signals available for an unfamiliar "
                      "page. Given two pages that answer a question equally well, the one with a "
                      "visible recent date gets cited; an undated page is treated as unknown age, "
                      "which is scored like old.",
            detail="Only update dateModified when the content actually changes — a date that "
                   "moves on every deploy is quickly discounted.",
            urls=[p["url"] for p in dateless][:10], effort="low"))

    # ---------------------------------------------------------------- 3. stale content
    newest_dates = [d[0] for d in dated.values() if d]
    if newest_dates:
        newest = max(newest_dates)
        age = months_ago(newest)
        blog_pages = [p for p in ok if p["type"] in ("blog_post", "blog_index")]
        if age > 18:
            out.append(finding(
                "CF-CONTENT-STALE", "Nothing on the site has been updated in over a year", "high",
                "The most recent date found anywhere across %d crawled pages is %s (%.0f months "
                "ago)." % (len(ok), newest.date().isoformat(), age),
                "Refresh the pages that carry answerable facts first — pricing, product details, "
                "contact information, and the top three most-visited articles — and publish the "
                "update date.",
                mechanism="Sites that never change are re-crawled less often, so even corrections "
                          "take a long time to propagate into what assistants say. Sustained "
                          "staleness also lowers the confidence weight the whole domain carries.",
                urls=[home["url"]]))
        elif blog_pages and age > 9:
            out.append(finding(
                "CF-PUBLISHING-STALLED", "Publishing has stalled", "medium",
                "The site has a blog/news section but the most recent dated item is %s (%.0f "
                "months ago)." % (newest.date().isoformat(), age),
                "Either resume a regular publishing cadence on the topics the brand should own, "
                "or retire the section so it stops signalling abandonment.",
                confidence="medium",
                mechanism="A visibly dormant blog is worse than no blog: it dates the whole "
                          "domain and gives crawlers a large set of pages with nothing new to "
                          "read.",
                urls=[p["url"] for p in blog_pages][:5]))
        else:
            na.append({"check_id": "CF-CONTENT-STALE",
                       "reason": "most recent content date is %s" % newest.date().isoformat()})

    # ---------------------------------------------------------------- 4. expired forward promises
    stale_promises = []
    for p in ok:
        for m in FUTURE_PROMISE_RX.finditer(p["extract"]["text"]):
            if int(m.group(2)) < NOW.year:
                stale_promises.append((p["url"], m.group(0)[:100]))
    if stale_promises:
        out.append(finding(
            "CF-EXPIRED-FORWARD-PROMISES",
            "Pages still advertise events or launches that are in the past", "medium",
            "%d instance(s). Example — %s: %r"
            % (len(stale_promises), stale_promises[0][0], stale_promises[0][1]),
            "Remove or update expired announcements; for recurring events, keep one evergreen URL "
            "and update its dates rather than leaving old pages live.",
            mechanism="Text that says something is upcoming when it has already passed produces "
                      "confidently wrong answers, because the assistant repeats the page's own "
                      "framing. It is also the clearest possible signal that nobody maintains "
                      "the page.",
            urls=[u for u, _ in stale_promises][:8], effort="low"))

    # ---------------------------------------------------------------- 5. internal inconsistency
    phones = {re.sub(r"[^\d+]", "", m) for m in PHONE_RX.findall(all_text)
              if isinstance(m, str)} if PHONE_RX.findall(all_text) else set()
    phones = {p for p in phones if len(p) >= 9}
    emails = {m.lower() for m in EMAIL_RX.findall(all_text)
              if not re.search(r"(example|sentry|wixpress|\.png|\.jpg)", m, re.I)}
    contact_emails = {e for e in emails
                      if re.match(r"(info|hello|contact|sales|support|enquir|inquir|admin)@", e)}
    if len(phones) > 2:
        out.append(finding(
            "CF-INCONSISTENT-PHONE", "The site lists several different phone numbers", "medium",
            "%d distinct phone numbers appear across the crawled pages: %s."
            % (len(phones), ", ".join(sorted(phones)[:5])),
            "Publish one primary contact number consistently in the footer, on the contact page "
            "and in structured data; keep department or branch numbers on a clearly-labelled "
            "page only.",
            confidence="medium", category="both",
            mechanism="Machines corroborate a business by matching name, address and phone across "
                      "sources. Several competing numbers on the brand's own site means no single "
                      "value is reinforced, so directory listings — often outdated — win instead.",
            urls=[home["url"]], effort="low"))
    if len(contact_emails) > 3:
        out.append(finding(
            "CF-INCONSISTENT-CONTACT-EMAIL", "Several general contact addresses are published",
            "low",
            "%d general-purpose contact addresses found: %s."
            % (len(contact_emails), ", ".join(sorted(contact_emails)[:5])),
            "Consolidate to one published general contact address and route internally.",
            confidence="medium", category="both",
            mechanism="Multiple general inboxes dilute the same corroboration signal as multiple "
                      "phone numbers, and leave visitors guessing which one is monitored.",
            urls=[home["url"]], effort="low"))

    # ---------------------------------------------------------------- 6. boilerplate consistency
    descs = []
    for p in ok:
        d = (p["extract"]["meta"].get("description")
             or p["extract"]["og"].get("og:description") or "").strip()
        if d:
            descs.append((p["url"], d))
    # Must come from an Organization-ish node: comparing the homepage description
    # against, say, an ImageObject caption compares two unrelated strings.
    org_desc = ""
    for p in ok:
        for raw in p["extract"]["jsonld_raw"]:
            try:
                data = json.loads(raw)
            except Exception:
                continue
            stack = [data]
            while stack and not org_desc:
                n = stack.pop()
                if isinstance(n, dict):
                    t = n.get("@type")
                    tl = [str(x).lower() for x in (t if isinstance(t, list) else [t]) if x]
                    if any(x in ("organization", "localbusiness", "corporation", "ngo",
                                 "website", "onlinestore") for x in tl):
                        d = n.get("description")
                        if isinstance(d, str) and len(d) >= 20:
                            org_desc = d
                    stack.extend(v for v in n.values() if isinstance(v, (dict, list)))
                elif isinstance(n, list):
                    stack.extend(n)
    if org_desc and descs:
        home_desc = next((d for u, d in descs if u == home["url"]), descs[0][1])
        # Compare on 5-character stems so "payment"/"payments" and
        # "platform"/"platforms" count as agreement rather than divergence.
        stem = lambda t: {w[:5] for w in re.findall(r"[a-z]{4,}", t.lower())
                          if w not in STOPWORDS}
        a, b = stem(home_desc), stem(org_desc)
        overlap = len(a & b) / max(1, len(a | b))
        if len(home_desc) >= 40 and len(org_desc) >= 40 and a and b and overlap < 0.12:
            out.append(finding(
                "CF-INCONSISTENT-BOILERPLATE",
                "The brand describes itself differently in different places", "medium",
                "Homepage meta description: %r. Organization description in structured data: %r. "
                "They share almost no vocabulary (%.0f%% stem overlap)." % (home_desc[:110], org_desc[:110]),
                "Agree one canonical one-sentence description and use it verbatim in the meta "
                "description, the Organization schema, the About page, and every third-party "
                "profile.",
                confidence="medium",
                mechanism="Corroboration works on repetition. One sentence repeated identically "
                          "across many places becomes the description a model returns; several "
                          "competing phrasings mean none of them accumulates enough weight, and "
                          "the model falls back on a third-party summary.",
                urls=[home["url"]], effort="low"))
        else:
            na.append({"check_id": "CF-INCONSISTENT-BOILERPLATE",
                       "reason": "on-page and structured-data descriptions are consistent"})

    # ---------------------------------------------------------------- 7. no off-site anchors
    external = [l["href"] for p in ok for l in p["extract"]["links_external"]]
    authority = [u for u in external if AUTHORITY_RX.search(u)]
    sameas = (profile or {}).get("declared_same_as", [])
    home_ok = home["status"] == 200 and home["type"] == "home"
    if not authority and not sameas and home_ok:
        out.append(finding(
            "CF-NO-OFFSITE-ANCHORS",
            "The site links to no independent profile that could corroborate it", "high",
            "%d external links found across %d pages, none pointing to an identity or review "
            "source (Wikipedia/Wikidata, LinkedIn company page, Crunchbase, GitHub, G2, "
            "Trustpilot, Google Maps, a registry)." % (len(external), len(ok)),
            "Create and link the brand's authoritative profiles — at minimum a LinkedIn company "
            "page, a Google Business Profile if there is a physical location, an industry "
            "directory or review listing, and a Wikidata item — then reference them from sameAs.",
            mechanism="A claim that appears in exactly one place on the internet is fragile. "
                      "Machines weight a fact by how many independent sources repeat it, so a "
                      "brand described only by its own website has nothing reinforcing what it "
                      "says about itself.",
            detail="This is the on-site half of the signal only. The off-site protocol in "
                   "references/offsite-protocol.md checks whether those profiles exist, are "
                   "current, and agree with the site.",
            urls=[home["url"]]))
    elif not home_ok:
        na.append({"check_id": "CF-NO-OFFSITE-ANCHORS",
                   "reason": "homepage was not retrieved, and footer identity links cannot be "
                             "assessed from interior pages alone"})
    else:
        na.append({"check_id": "CF-NO-OFFSITE-ANCHORS",
                   "reason": "authority references present: %s"
                             % ", ".join((authority + sameas)[:3])})

    # ---------------------------------------------------------------- 8. unsourced claims
    claims = []
    for p in ok:
        for m in CLAIM_RX.finditer(p["extract"]["text"]):
            claims.append((p["url"], m.group(0)[:80]))
    cited = [u for u in external
             if re.search(r"(\.gov|\.edu|\.org|gartner|forrester|statista|nielsen|mckinsey|"
                          r"idc\.com|g2\.com|pubmed|doi\.org|iso\.org)", u, re.I)]
    if len(claims) >= 5 and len(cited) < 2:
        out.append(finding(
            "CF-UNSOURCED-CLAIMS", "Superlative and statistical claims carry no citation",
            "medium",
            "%d unsourced claim(s) found, e.g. %r on %s. The site links to %d citable external "
            "sources." % (len(claims), claims[0][1], claims[0][0], len(cited)),
            "Attach a source, a date and a method to every number — 'reduced processing time by "
            "34%% across 12 customer deployments, measured Q1 2026' — and link the underlying "
            "study or report where one exists.",
            confidence="medium",
            mechanism="Uncited superlatives are exactly the claims a careful assistant declines "
                      "to repeat, while a specific, sourced, dated number is quotable. "
                      "Publishing verifiable figures is also what earns citations from other "
                      "sites, which is the corroboration this brand lacks.",
            urls=list({u for u, _ in claims})[:8]))

    # ---------------------------------------------------------------- 9. name ambiguity risk
    tokens = [t for t in re.findall(r"[a-z]+", brand.lower()) if len(t) > 2]
    generic = [t for t in tokens if t in COMMON_WORDS]
    short = len(brand.replace(" ", "")) <= 4
    strong_sameas = [s for s in sameas if re.search(
        r"(wikidata|wikipedia|crunchbase|linkedin\.com/company|opencorporates)", s, re.I)]
    if (generic or short) and not strong_sameas:
        out.append(finding(
            "CF-NAME-AMBIGUITY-RISK", "The brand name is likely to collide with other entities",
            "high",
            "Brand name %r %s, and the site declares no registry-grade identity link "
            "(Wikidata/Wikipedia/Crunchbase/LinkedIn company) to distinguish it."
            % (brand, "is an ordinary English word (%s)" % ", ".join(generic) if generic
               else "is only %d characters long" % len(brand.replace(" ", ""))),
            "Always pair the name with a category descriptor in titles, headings and structured "
            "data — '%s, the <category> for <audience>' — and publish registry entries "
            "(Wikidata item, LinkedIn company page) that carry this domain as the official "
            "website." % brand,
            confidence="medium",
            mechanism="When several things share a name, a system needs something to tell them "
                      "apart. With no disambiguating anchor, answers about the brand get mixed "
                      "with answers about the word — or about a better-known company with the "
                      "same name — and the brand is misrepresented rather than merely missing.",
            detail="Verify the actual collision off-site before acting: search the bare name and "
                   "see what else claims it. The off-site protocol covers this.",
            urls=[home["url"]]))
    else:
        na.append({"check_id": "CF-NAME-AMBIGUITY-RISK",
                   "reason": "distinctive name or registry-grade identity links already present"})

    # ---------------------------------------------------------------- 10. sitemap freshness drift
    sm_dates = []
    for u in sitemap.get("urls", [])[:500]:
        m = ISO_RX.search(u.get("lastmod", ""))
        if m:
            try:
                sm_dates.append(dt.datetime.strptime(m.group(0), "%Y-%m-%d")
                                .replace(tzinfo=dt.timezone.utc))
            except ValueError:
                pass
    if len(sm_dates) >= 10 and len({d.date() for d in sm_dates}) == 1:
        out.append(finding(
            "CF-LASTMOD-UNIFORM", "Every sitemap entry shares the same <lastmod> date", "low",
            "All %d dated sitemap entries carry %s, which indicates a build timestamp rather than "
            "real content change dates." % (len(sm_dates), sm_dates[0].date().isoformat()),
            "Emit each URL's genuine last content-change date in <lastmod>.",
            mechanism="A <lastmod> that moves for every page on every deploy carries no "
                      "information, and crawlers learn to ignore the field for this site — so "
                      "genuinely updated pages lose their re-crawl signal.",
            confidence="medium", effort="medium"))

    # ---------------------------------------------------------------- 11. proactive
    has_data_asset = bool(re.search(
        r"(research|report|survey|benchmark|index|state of|study|whitepaper|dataset)",
        " ".join(l["text"] for p in ok for l in p["extract"]["links_internal"]), re.I))
    if not has_data_asset:
        out.append(finding(
            "CF-NO-CITABLE-ASSET", "The site publishes nothing others would cite", "info",
            "No original research, benchmark, dataset, survey or reference resource was found in "
            "the crawled navigation and link text.",
            "Publish one original, dated, methodologically-stated data asset a year in the brand's "
            "domain — a benchmark, a survey of its customers, a pricing or market breakdown — with "
            "a stable URL and reusable figures.",
            confidence="medium",
            mechanism="Corroboration cannot be bought, but it can be earned: original numbers get "
                      "quoted and linked by other sites, and those independent repetitions are "
                      "exactly the signal that makes a brand's facts trusted and repeated back.",
            detail="Make it easy to cite: one headline number in the first paragraph, a clear "
                   "method note, a fixed URL, and a stated licence for reuse."))

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "brand": brand,
            "newest_content_date": max(newest_dates).date().isoformat() if newest_dates else None,
            "pages_with_dates": len([d for d in dated.values() if d]),
            "authority_links": sorted(set(authority))[:10],
            "declared_same_as": sameas,
            "distinct_phone_numbers": len(phones),
            "unsourced_claims": len(claims),
            "offsite_corroboration": "not checked by this script — run the off-site protocol",
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
