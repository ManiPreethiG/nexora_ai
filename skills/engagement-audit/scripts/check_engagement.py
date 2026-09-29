#!/usr/bin/env python3
"""Stage 5 of the audit: the visitor arrives — do they stay?

The model this skill is built on: an assistant that cites a site sends people to
a deep page, not the homepage, with a specific question already in mind and no
memory of the journey a designed funnel assumes. So engagement is assessed as
"does an arbitrary interior page stand on its own?" — can a stranger landing
cold tell where they are, get the fact they came for, and see what to do next,
before anything blocks or slows them.

Usage: python3 check_engagement.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re
import statistics

SKILL = "engagement-audit"

CTA_RX = re.compile(
    r"\b(get started|start (?:free|now|building)|sign up|book (?:a )?(?:demo|call|table)|"
    r"request (?:a )?(?:quote|demo|callback)|contact (?:us|sales)|talk to|buy|shop|order|"
    r"add to (?:cart|bag)|subscribe|download|try (?:it )?free|see pricing|view plans|"
    r"apply now|enquire|book now|learn more|read more|see how)\b", re.I)
BREADCRUMB_RX = re.compile(r"(breadcrumb|aria-label=[\"']breadcrumb|itemtype=[\"'][^\"']*BreadcrumbList)", re.I)
VAGUE_RX = re.compile(
    r"\b(innovative|cutting[- ]edge|world[- ]class|seamless|synerg|holistic|"
    r"empower(?:ing|ment)?|unlock(?:ing)?|transform(?:ing|ation)?|revolutionar|"
    r"next[- ]generation|best[- ]in[- ]class|state[- ]of[- ]the[- ]art|leverage|"
    r"solutions? provider|end[- ]to[- ]end|bespoke|tailored|passionate|"
    r"redefin(?:e|ing)|reimagin(?:e|ing)|elevate|disrupt)\b", re.I)
CONCRETE_CATEGORY_RX = re.compile(
    r"\b(software|platform|app|agency|studio|consultanc|firm|shop|store|restaurant|cafe|"
    r"hotel|clinic|school|college|charity|manufactur|supplier|distributor|marketplace|"
    r"service|tool|library|framework|api|database|insurance|bank|lender|broker|"
    r"builder|installer|repair|salon|gym|bakery|brewery|law|dental|medical|"
    r"accounting|recruitment|logistics|freight|hosting|analytics|crm|erp)\b", re.I)
GATED_RX = re.compile(
    r"\b(contact (?:us )?for (?:a )?(?:price|pricing|quote)|request (?:a )?quote|"
    r"pricing on request|talk to sales for pricing|custom pricing|"
    r"(?:download|unlock|access) (?:the )?(?:full |complete )?"
    r"(?:report|guide|whitepaper|spec|datasheet|case study)\b[^.]{0,40}\bform\b)", re.I)
FILTER_HINT_RX = re.compile(r"(data-filter|data-sort|class=[\"'][^\"']*(facet|filter|sort)[^\"']*[\"']|"
                            r"name=[\"'](sort|orderby|filter|category|price_range)[\"'])", re.I)
SEARCH_INPUT_RX = re.compile(r"(type=[\"']search[\"']|name=[\"'](q|s|query|search|keyword)[\"']|"
                             r"role=[\"']searchbox[\"'])", re.I)


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
        raw = os.path.join(bundle, "pages", p["id"] + ".html")
        p["html"] = open(raw, encoding="utf-8", errors="ignore").read() if os.path.exists(raw) else ""
    return meta, idx["pages"], profile


def finding(check_id, title, severity, evidence, action, *, category="engagement",
            confidence="high", urls=None, mechanism="", detail="", effort="medium",
            verification=""):
    return {
        "check_id": check_id, "title": title, "category": category, "concern": SKILL,
        "severity": severity, "confidence": confidence, "evidence": evidence,
        "affected_urls": urls or [], "mechanism": mechanism,
        "suggested_action": {"summary": action, "detail": detail, "priority": severity,
                             "effort": effort, "verification": verification},
    }


def depth(url):
    return len([s for s in url.split("//", 1)[-1].split("/")[1:] if s])


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages, profile = load(bundle)
    out, na = [], []
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    if not ok:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [],
                "observations": {"note": "no HTML pages available to analyse"}}
    home = next((p for p in ok if p["type"] == "home"), ok[0])
    brand = (profile or {}).get("brand_name") or meta["site"].split(".")[0]
    brand_token = re.split(r"\W+", brand)[0].lower()
    interior = [p for p in ok if depth(p["url"]) >= 1 and p is not home
                and p["type"] != "legal"]
    substantive = [p for p in interior if p["extract"]["word_count"] >= 120]

    # ---------------------------------------------------------------- 1. orientation on arrival
    if substantive:
        unoriented = []
        for p in substantive:
            ex = p["extract"]
            has_crumbs = bool(BREADCRUMB_RX.search(p["html"]))
            head = (" ".join(ex["h1s"]) + " " + ex["text_head"][:400]).lower()
            names_brand = brand_token in head or brand_token in (ex["title"] or "").lower()
            if not has_crumbs and not names_brand:
                unoriented.append(p["url"])
        if len(unoriented) >= max(2, len(substantive) * 0.5):
            out.append(finding(
                "EN-NO-ARRIVAL-ORIENTATION",
                "Interior pages do not tell a cold visitor where they have landed", "high",
                "%d of %d substantive interior pages have neither breadcrumbs nor the brand name "
                "in the heading, title or opening text. Example: %s."
                % (len(unoriented), len(substantive), unoriented[0]),
                "Add visible breadcrumbs and make the first screen of every interior page state "
                "the site it belongs to and what the page covers.",
                mechanism="An AI answer links straight to the page that held the fact. The "
                          "visitor arrives mid-site with no homepage context, no navigation "
                          "history and one specific question. A page that assumes they walked "
                          "there from the homepage reads as a fragment, and they leave to "
                          "re-ask the assistant rather than exploring the site.",
                detail="The test to apply: open the page in a private window and ask whether a "
                       "stranger can name the company, the subject, and one next step within "
                       "five seconds without scrolling.",
                urls=unoriented[:10], effort="low"))
        else:
            na.append({"check_id": "EN-NO-ARRIVAL-ORIENTATION",
                       "reason": "interior pages carry breadcrumbs or name the brand up front"})

    # ---------------------------------------------------------------- 2. no next step
    dead_ends = []
    for p in substantive:
        ex = p["extract"]
        body_links = [l for l in ex["links_internal"] if l["text"] and len(l["text"]) > 2]
        has_cta = bool(CTA_RX.search(" ".join(ex["buttons"]) + " " +
                                     " ".join(l["text"] for l in body_links)))
        if len(body_links) < 5 or not has_cta:
            dead_ends.append((p["url"], len(body_links), has_cta))
    if dead_ends and len(dead_ends) >= max(2, len(substantive) * 0.4):
        out.append(finding(
            "EN-NO-NEXT-STEP", "Interior pages offer no obvious next step", "high",
            "%d of %d substantive interior pages have fewer than five in-body links or no "
            "recognisable call to action. Example %s: %d body links, call to action %s."
            % (len(dead_ends), len(substantive), dead_ends[0][0], dead_ends[0][1],
               "present" if dead_ends[0][2] else "absent"),
            "End every interior page with one primary action and two or three relevant onward "
            "links, chosen for the question that page answers.",
            mechanism="A visitor arriving from an assistant has their answer within seconds; "
                      "whether they do anything else is decided entirely by what the page offers "
                      "next. With no onward path the visit ends at one page, and the citation "
                      "produces no value even though it worked.",
            detail="Match the step to intent: an informational page should offer the next "
                   "question, not a demo request; a product page should offer the buying action.",
            urls=[u for u, _, _ in dead_ends][:10]))

    # ---------------------------------------------------------------- 3. blocking interstitials
    consent = sorted({v for p in ok for v in p["extract"]["consent_vendors"]})
    overlay_pages = [p for p in ok if len(p["extract"]["overlay_hints"]) >= 2
                     or p["extract"]["fixed_fullscreen_inline"] >= 1]
    newsletter = [p for p in ok if any(h in ("newsletter", "subscribe-", "exit-intent", "paywall")
                                       for h in p["extract"]["overlay_hints"])]
    if newsletter:
        out.append(finding(
            "EN-INTERRUPTING-OVERLAY", "Pages carry newsletter or exit-intent overlays", "medium",
            "%d page(s) contain overlay markup (%s), e.g. %s."
            % (len(newsletter), ", ".join(sorted({h for p in newsletter
                                                  for h in p["extract"]["overlay_hints"]}))[:80],
               newsletter[0]["url"]),
            "Remove interruptive overlays on first visit, or delay them until the visitor has "
            "scrolled through the content they came for; use an inline sign-up block instead.",
            confidence="medium",
            mechanism="A visitor arriving from an AI answer came for one fact and has no "
                      "relationship with the brand yet. An overlay before that fact is delivered "
                      "is the highest-friction moment possible, and it is the single most common "
                      "cause of an immediate bounce from cited traffic.",
            urls=[p["url"] for p in newsletter][:8], effort="low"))
    if consent and len(overlay_pages) >= len(ok) * 0.8:
        out.append(finding(
            "EN-CONSENT-WALL", "A consent layer covers the content on every page", "medium",
            "Consent platform detected sitewide (%s) with full-screen overlay markup on %d of %d "
            "pages." % (", ".join(consent), len(overlay_pages), len(ok)),
            "Keep the consent notice non-blocking where the law allows it: a bottom banner that "
            "leaves the content readable and does not shift the layout.",
            confidence="medium", category="both",
            mechanism="Consent is often a legal requirement, so the fix is its implementation, "
                      "not its removal. A full-screen blocking layer delays the first useful "
                      "moment for every visitor, and some fetchers capture the overlay instead "
                      "of the page.",
            urls=[home["url"]], effort="medium"))

    # ---------------------------------------------------------------- 4. weight and speed
    html_kb = [p["bytes"] / 1024 for p in ok if p["bytes"]]
    med_kb = statistics.median(html_kb) if html_kb else 0
    med_scripts = statistics.median([len(p["extract"]["scripts_external"]) for p in ok])
    blocking = statistics.median([p["extract"]["scripts_blocking"] for p in ok])
    if med_kb > 500 or med_scripts >= 25:
        out.append(finding(
            "EN-PAGE-WEIGHT", "Pages are heavy before any media is counted",
            "high" if med_kb > 900 or med_scripts >= 40 else "medium",
            "Median HTML document is %.0f KB with %d external scripts and %d render-blocking "
            "scripts per page, across %d pages. (HTML and resource counts only; images and "
            "fonts are additional.)" % (med_kb, med_scripts, blocking, len(ok)),
            "Cut third-party scripts to the ones with a named owner and a measured purpose, defer "
            "everything non-critical, and split oversized HTML documents.",
            mechanism="Cited traffic skews mobile and impatient — the visitor did not choose this "
                      "site, an assistant suggested it. Every second before the answer appears is "
                      "spent on a page they have no prior commitment to.",
            detail="Audit tag-manager containers first; they are usually where script count grows "
                   "without anyone deciding it should.",
            urls=[p["url"] for p in sorted(ok, key=lambda x: -x["bytes"])[:3]],
            verification="Re-measure document size and script count after the cull."))
    elif med_kb:
        na.append({"check_id": "EN-PAGE-WEIGHT",
                   "reason": "median HTML %.0f KB with %d external scripts is within budget"
                             % (med_kb, med_scripts)})
    if blocking >= 4:
        out.append(finding(
            "EN-RENDER-BLOCKING", "Several render-blocking scripts sit in the document head",
            "medium",
            "Median of %d scripts per page load synchronously without async or defer." % blocking,
            "Add defer (or async where order does not matter) to every script that is not needed "
            "for first paint.",
            mechanism="Each synchronous script pauses parsing, so the visitor stares at a blank "
                      "screen while code they did not ask for downloads and executes.",
            urls=[p["url"] for p in ok][:5], effort="low"))

    # ---------------------------------------------------------------- 5. mobile readiness
    no_viewport = [p for p in ok if not p["extract"]["meta"].get("viewport")]
    if no_viewport:
        out.append(finding(
            "EN-NO-VIEWPORT-META", "Pages declare no mobile viewport", "high",
            "%d of %d pages have no <meta name=\"viewport\">, e.g. %s."
            % (len(no_viewport), len(ok), no_viewport[0]["url"]),
            "Add <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"> and "
            "verify the layout at 375px wide.",
            mechanism="Without a viewport declaration a phone renders the desktop layout zoomed "
                      "out, so the visitor's first action is pinching to read. Most traffic "
                      "arriving from assistants is mobile.",
            urls=[p["url"] for p in no_viewport][:8], effort="low"))
    else:
        na.append({"check_id": "EN-NO-VIEWPORT-META", "reason": "all pages declare a viewport"})

    unsized = sum(len([i for i in p["extract"]["images"]
                       if not i["width"] or not i["height"]]) for p in ok)
    total_img = sum(len(p["extract"]["images"]) for p in ok)
    if total_img >= 10 and unsized >= total_img * 0.7:
        out.append(finding(
            "EN-UNSIZED-IMAGES", "Images have no width/height attributes", "low",
            "%d of %d images across %d pages declare neither width nor height."
            % (unsized, total_img, len(ok)),
            "Set width and height (or an aspect-ratio) on every image so the browser reserves "
            "space before the file loads.",
            mechanism="Unsized images let the layout jump as they arrive, which makes the page "
                      "feel broken and causes mis-taps on mobile at exactly the moment the "
                      "visitor is deciding whether to stay.",
            urls=[p["url"] for p in ok][:5], effort="low"))
    no_lazy = sum(len([i for i in p["extract"]["images"] if i["loading"] != "lazy"]) for p in ok)
    if total_img >= 20 and no_lazy >= total_img * 0.9:
        out.append(finding(
            "EN-NO-LAZY-LOADING", "Below-the-fold images are not lazy-loaded", "low",
            "%d of %d images have no loading=\"lazy\" attribute." % (no_lazy, total_img),
            "Add loading=\"lazy\" to images below the fold (never to the main above-fold image).",
            mechanism="Loading every image up front competes for bandwidth with the content the "
                      "visitor actually came to read.", effort="low",
            urls=[p["url"] for p in ok][:5]))

    # ---------------------------------------------------------------- 6. thin key pages
    key_types = {"pricing", "product", "about", "contact", "case_study", "faq"}
    thin = [p for p in ok if p["type"] in key_types and p["extract"]["word_count"] < 120]
    if thin:
        out.append(finding(
            "EN-THIN-KEY-PAGES", "Pages that should answer questions carry almost no content",
            "medium",
            "%d key page(s) under 120 words. Example %s (%s): %d words."
            % (len(thin), thin[0]["url"], thin[0]["type"], thin[0]["extract"]["word_count"]),
            "Expand each page to answer the questions a visitor actually arrives with, in the "
            "words they would use to ask them.",
            category="both",
            mechanism="A thin page fails twice: it gives an assistant nothing worth quoting, and "
                      "it gives the visitor who arrives anyway no reason to continue.",
            urls=[p["url"] for p in thin][:8]))

    # ---------------------------------------------------------------- 7. readability
    # Legal text is long and dense by necessity; judging it on scannability is a
    # false positive, so it is excluded from the readability check.
    # Only pages whose job is to be read. Legal text is dense by necessity, and a
    # product grid or homepage is not prose, so neither is judged on scannability.
    PROSE_TYPES = {"blog_post", "docs", "about", "case_study", "faq", "careers", "other"}
    long_pages = [p for p in ok if p["extract"]["word_count"] > 400
                  and p["type"] in PROSE_TYPES]
    hard = []
    for p in long_pages:
        ex = p["extract"]
        headings_in_body = len([h for h in ex["headings"] if not h["in_chrome"] and h["level"] > 1])
        if ex["avg_sentence_words"] > 26 or ex["long_paragraphs"] >= 3 or \
                (headings_in_body <= 1 and ex["word_count"] > 800):
            hard.append((p["url"], ex["avg_sentence_words"], ex["long_paragraphs"], headings_in_body))
    if hard and len(hard) >= max(2, len(long_pages) * 0.4):
        u, avg, lp, h = hard[0]
        out.append(finding(
            "EN-HARD-TO-SCAN", "Long pages are written as unbroken prose", "medium",
            "%d of %d long pages are hard to scan. Example %s: average sentence %.0f words, %d "
            "paragraphs over 120 words, %d subheadings in the body."
            % (len(hard), len(long_pages), u, avg, lp, h),
            "Break long pages with a descriptive subheading every 150–250 words, shorten "
            "sentences to around 20 words, and use lists for anything enumerable.",
            category="both",
            mechanism="Visitors scan for the specific thing they came for. Subheadings are also "
                      "what lets an extractor pull the one relevant passage instead of the whole "
                      "page, so the same fix improves quoting and reading at once.",
            urls=[q[0] for q in hard][:8]))

    # ---------------------------------------------------------------- 8. vague above-fold copy
    ex = home["extract"]
    above = " ".join(ex["h1s"][:1]) + " " + ex["text_head"][:350]
    vague = VAGUE_RX.findall(above)
    concrete = CONCRETE_CATEGORY_RX.search(above)
    if len(vague) >= 2 and not concrete:
        out.append(finding(
            "EN-VAGUE-ABOVE-FOLD", "The homepage opens with abstract language and no category",
            "medium",
            "First screen of %s uses %d abstract marketing terms (%s) and names no concrete "
            "category. H1: %r." % (home["url"], len(vague), ", ".join(sorted(set(
                v.lower() for v in vague))[:4]), (ex["h1s"][0] if ex["h1s"] else "(none)")[:80]),
            "Replace the abstract opener with a concrete one: what it is, who it is for, and what "
            "it does — the category noun in the first line.",
            confidence="medium", category="both",
            mechanism="A visitor who cannot tell what a company does within one screen leaves, "
                      "and a machine that cannot find a category noun has nothing to file the "
                      "brand under. Abstract positioning language fails both readers at once.",
            urls=[home["url"]], effort="low"))

    # ---------------------------------------------------------------- 9. gated facts
    gated = []
    for p in ok:
        m = GATED_RX.search(p["extract"]["text"])
        if m:
            gated.append((p["url"], m.group(0)[:70]))
    if gated:
        out.append(finding(
            "EN-GATED-FACTS", "Key information is held behind a form", "medium",
            "%d page(s) withhold information pending contact or a form. Example — %s: %r"
            % (len(gated), gated[0][0], gated[0][1]),
            "Publish enough in the open to answer the question — a price range, the pricing model, "
            "the summary of the report — and keep the form for the detailed version.",
            confidence="medium", category="both",
            mechanism="Gating is a deliberate trade, but the cost has changed: a visitor sent by "
                      "an assistant expects the answer on arrival and returns to the assistant "
                      "when they hit a form, and the gated fact cannot be cited at all, so "
                      "competitors who publish theirs are the ones named in the answer.",
            detail="Frame this as a decision for the business rather than a defect: the fix is to "
                   "publish an anchor value openly, not to remove lead capture.",
            urls=[u for u, _ in gated][:8]))

    # ---------------------------------------------------------------- 10. state not addressable
    filterish = [p for p in ok if FILTER_HINT_RX.search(p["html"])
                 and p["type"] in ("category", "product", "blog_index", "docs", "other")]
    if filterish:
        param_links = [l for p in ok for l in p["extract"]["links_internal"] if "?" in l["href"]]
        if not param_links:
            out.append(finding(
                "EN-STATE-NOT-IN-URL", "Filtered and sorted views have no shareable URL", "medium",
                "%d page(s) expose filter/sort controls (e.g. %s) but no internal link on the "
                "site carries a query string, so the chosen state is held only in the browser."
                % (len(filterish), filterish[0]["url"]),
                "Reflect filter, sort and pagination state in the URL, and make those URLs "
                "linkable and indexable where they represent something people search for.",
                confidence="medium", category="both",
                mechanism="State that lives only in memory cannot be linked, cited, bookmarked or "
                          "returned to — a refresh or a back-button press throws away everything "
                          "the visitor set up, and no assistant can ever send someone to the "
                          "filtered view that actually answers their question.",
                urls=[p["url"] for p in filterish][:6]))

    # ---------------------------------------------------------------- 11. site search
    has_search = any(SEARCH_INPUT_RX.search(p["html"]) for p in ok)
    total_urls = max(len(ok), (profile or {}).get("signals", {}).get("pages", 0))
    if not has_search and total_urls >= 12:
        out.append(finding(
            "EN-NO-SITE-SEARCH", "The site has no search box", "low",
            "No search input found on any of %d crawled pages." % len(ok),
            "Add site search to the header, and make sure it is reachable on mobile.",
            mechanism="A visitor who lands on a page that is close but not quite what they asked "
                      "for has exactly two options: search the site or go back to the assistant. "
                      "Without search, they go back.",
            urls=[home["url"]]))

    # ---------------------------------------------------------------- 12. accessibility baseline
    a11y = []
    no_lang = [p for p in ok if not p["extract"]["lang"]]
    if no_lang:
        a11y.append("%d page(s) have no lang attribute on <html>" % len(no_lang))
    unlabelled = 0
    for p in ok:
        for i in p["extract"]["inputs"]:
            if i["type"] in ("hidden", "submit", "button", "image"):
                continue
            if not (i["aria_label"] or i["labelledby"] or i["id"] or i["placeholder"]):
                unlabelled += 1
    if unlabelled:
        a11y.append("%d form field(s) have no label, aria-label or id to bind a label to" % unlabelled)
    all_links = [l for p in ok for l in p["extract"]["links_internal"] + p["extract"]["links_external"]]
    empty_links = len([l for l in all_links
                       if not l["text"].strip() and not l.get("aria_label")])
    # A handful of unnamed links is noise; a fifth of them is a pattern.
    if empty_links >= 10 and all_links and empty_links >= len(all_links) * 0.2:
        a11y.append("%d of %d link(s) contain no text, title or aria-label"
                    % (empty_links, len(all_links)))
    if a11y:
        out.append(finding(
            "EN-ACCESSIBILITY-BASELINE", "Basic accessibility attributes are missing",
            "medium" if len(a11y) > 1 else "low",
            "; ".join(a11y) + " (across %d crawled pages)." % len(ok),
            "Fix the mechanical basics: a lang attribute on <html>, a bound label for every form "
            "field, and text or an aria-label on every link.",
            category="both",
            mechanism="These attributes are what both assistive technology and text extractors "
                      "rely on to know what an element is. Missing them excludes real users and "
                      "leaves machine readers guessing at the same time.",
            detail="This is a floor, not an accessibility audit: passing these checks does not "
                   "make the site conformant, but failing them guarantees it is not.",
            urls=[p["url"] for p in (no_lang or ok)][:8], effort="low"))

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "interior_pages_assessed": len(substantive),
            "median_html_kb": round(med_kb, 1),
            "median_external_scripts": med_scripts,
            "consent_platforms": consent,
            "has_site_search": has_search,
            "median_words": statistics.median([p["extract"]["word_count"] for p in ok]),
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
