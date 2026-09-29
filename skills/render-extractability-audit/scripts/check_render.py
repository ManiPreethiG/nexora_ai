#!/usr/bin/env python3
"""Stage 2 of the audit: can a machine read the page, and pick a fact out of it?

Compares what the server sends with what a browser ends up showing, and looks
for facts that exist on screen but not in machine-readable text.

Degrades explicitly: when no headless browser is available the render gap is
inferred from single-page-app markers in the served HTML and every such finding
is emitted at `confidence: medium` with the limitation stated in the evidence.

Usage: python3 check_render.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re
import sys

SKILL = "render-extractability-audit"

PRICE_RX = re.compile(r"(?:[$£€₹¥]\s?\d|(?:\d[\d,.]*)\s?(?:USD|EUR|GBP|INR|AUD|CAD|per month|/mo|/month|/yr|a month))", re.I)
PHONE_RX = re.compile(r"(\+\d[\d\s().-]{7,}\d|\(\d{3}\)\s?\d{3}[-.\s]?\d{4}|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")
EMAIL_RX = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]{2,}")
ADDRESS_RX = re.compile(
    r"\b\d{1,5}\s+[A-Z][\w'.-]*(?:\s+[A-Z][\w'.-]*){0,4}\s+"
    r"(street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd|way|court|ct|"
    r"suite|floor|plaza|park|square|sector|marg|nagar)\b", re.I)
POSTCODE_RX = re.compile(r"\b([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}|\d{5}(-\d{4})?|\d{6})\b")
HOURS_RX = re.compile(r"(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?\s*[-–—:]?\s*"
                      r"(mon|tue|wed|thu|fri|sat|sun|\d{1,2}\s?(am|pm|:))", re.I)
DEFINITION_RX = re.compile(
    r"\b(is|are|was|provides?|offers?|helps?|builds?|makes?|sells?|delivers?|creates?|"
    r"designs?|manufactures?|specialises?|specializes?|develops?|makers? of|home of|"
    r"provider of|maker of|producers? of)\b", re.I)
# "Brand: the world's most comfortable shoes" defines just as well as "Brand is …".
APPOSITIVE_RX = re.compile(r"[:\u2013\u2014-]\s+\S+(\s+\S+){2,}")
# Deliberately concrete: "solutions", "services" and "brand" describe nothing and
# would let an empty slogan pass this check.
CATEGORY_RX = re.compile(
    r"\b(software|platform|app|agency|studio|consultanc|firm|shop|store|retailer|"
    r"restaurant|cafe|hotel|museum|gallery|clinic|hospital|school|university|"
    r"college|charity|foundation|manufacturer|supplier|marketplace|"
    r"magazine|newspaper|publisher|library|bank|insurer|broker|label|"
    r"shoes|clothing|furniture|jewell?ery|skincare|coffee|brewery|bakery)\b", re.I)
TEXTY_IMAGE_RX = re.compile(
    r"(price|pricing|menu|spec|specs|table|chart|infographic|comparison|features?|"
    r"tarif|rate-?card|hours|schedule)", re.I)
FACT_PAGE_TYPES = {"pricing", "product", "contact", "faq", "docs", "about"}


def load(bundle):
    def j(name, default=None):
        path = os.path.join(bundle, name)
        if not os.path.exists(path):
            return default
        with open(path) as fh:
            return json.load(fh)
    meta, idx, profile = j("meta.json"), j("index.json"), j("profile.json")
    for p in idx["pages"]:
        for key, suffix in (("extract", ".extract.json"), ("rendered", ".rendered.extract.json")):
            path = os.path.join(bundle, "pages", p["id"] + suffix)
            p[key] = None
            if os.path.exists(path):
                with open(path) as fh:
                    p[key] = json.load(fh)
        raw = os.path.join(bundle, "pages", p["id"] + ".html")
        p["html"] = open(raw, encoding="utf-8", errors="ignore").read() if os.path.exists(raw) else ""
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


def brand_name(meta, pages, profile):
    """Prefer the shared profile; fall back only when running standalone."""
    if profile and profile.get("brand_name"):
        return profile["brand_name"]
    for p in pages:
        ex = p.get("extract")
        if ex and ex.get("og", {}).get("og:site_name"):
            return ex["og"]["og:site_name"].strip()
    return meta.get("registrable_domain", meta["site"]).split(".")[0].replace("-", " ").title()


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages, profile = load(bundle)
    out, na = [], []
    rendered_available = meta.get("capabilities", {}).get("rendering", False)
    ok = [p for p in pages if p.get("extract") and p["status"] == 200]
    if not ok:
        return {"skill": SKILL, "site": meta["site"], "findings": [], "not_applicable": [],
                "observations": {"note": "no HTML pages available to analyse"}}
    home = next((p for p in ok if p["type"] == "home"), ok[0])
    brand = brand_name(meta, ok, profile)

    # ---------------------------------------------------------------- 1. render gap
    if rendered_available:
        gaps = []
        for p in ok:
            r = p.get("rendered")
            if not r:
                continue
            raw_w, ren_w = p["extract"]["word_count"], r["word_count"]
            if ren_w - raw_w > 150 and raw_w < ren_w * 0.4:
                gaps.append((p, raw_w, ren_w))
        if gaps:
            worst = max(gaps, key=lambda g: g[2] - g[1])
            sev = "critical" if worst[1] < 120 else "high"
            out.append(finding(
                "RX-RENDER-GAP", "Page content is assembled by JavaScript and missing from the "
                                 "served HTML", sev,
                "%d of %d rendered pages gained substantial text after JavaScript ran. Worst: %s "
                "— %d words in the server HTML vs %d words after rendering."
                % (len(gaps), len([p for p in ok if p.get("rendered")]),
                   worst[0]["url"], worst[1], worst[2]),
                "Server-render (SSR) or pre-render the primary content of these pages so the "
                "facts are present in the initial HTML response.",
                mechanism="Many AI fetchers read the raw HTTP response and never execute "
                          "JavaScript. Content that only exists after hydration is invisible to "
                          "them even though it is plainly visible to a person.",
                detail="Prioritise the templates that carry answerable facts (product, pricing, "
                       "docs, location) over marketing pages. Static generation or SSR for those "
                       "routes is usually enough; the rest can stay client-rendered.",
                urls=[g[0]["url"] for g in gaps][:10],
                verification="curl -s <url> | grep -c '<the key fact>' returns a non-zero count."))
            for p, raw_w, ren_w in gaps[:1]:
                r = p["rendered"]
                lost = []
                if not p["extract"]["h1s"] and r["h1s"]:
                    lost.append("H1 %r" % r["h1s"][0][:60])
                if not p["extract"]["jsonld_raw"] and r["jsonld_raw"]:
                    lost.append("%d JSON-LD block(s)" % len(r["jsonld_raw"]))
                if len(p["extract"]["links_internal"]) + 3 < len(r["links_internal"]):
                    lost.append("%d internal links (%d in HTML vs %d rendered)"
                                % (len(r["links_internal"]) - len(p["extract"]["links_internal"]),
                                   len(p["extract"]["links_internal"]), len(r["links_internal"])))
                if lost:
                    out.append(finding(
                        "RX-RENDER-GAP-SIGNALS",
                        "Key machine-readable signals are absent until JavaScript runs", "high",
                        "On %s the served HTML is missing: %s." % (p["url"], "; ".join(lost)),
                        "Emit the H1, structured data and navigation links in the server HTML.",
                        mechanism="Headings, JSON-LD and links are the signals used to identify "
                                  "what a page is about and what else exists on the site. If they "
                                  "appear only after hydration, a non-rendering fetcher sees an "
                                  "untitled, unlinked, untyped document.",
                        urls=[p["url"]]))
        else:
            na.append({"check_id": "RX-RENDER-GAP",
                       "reason": "rendered DOM matched served HTML within tolerance on all "
                                 "sampled pages"})
    else:
        suspects = []
        for p in ok:
            ex = p["extract"]
            markers = bool(ex["spa_roots"]) + bool(ex["framework_hints"]) + bool(ex["preloaded_state"])
            if ex["word_count"] < 120 and markers >= 1 and len(ex["scripts_external"]) >= 3:
                suspects.append((p, ex))
        # One thin page proves nothing; the pattern has to hold across the site or
        # hit the homepage, which every visitor and fetcher sees.
        home_is_shell = any(q[0]["type"] == "home" for q in suspects)
        if suspects and (len(suspects) >= 2 or home_is_shell):
            p, ex = next((q for q in suspects if q[0]["type"] == "home"), suspects[0])
            sev = "high" if len(suspects) >= max(2, len(ok) * 0.5) else "medium"
            out.append(finding(
                "RX-CLIENT-RENDERED-SHELL",
                "Served HTML looks like an empty single-page-app shell", sev,
                "%d of %d pages returned under 120 words of text with app-shell markers present. "
                "Example %s: %d words, root element(s) %s, bundles %s. "
                "(No headless browser was available, so this is inferred from the served HTML.)"
                % (len(suspects), len(ok), p["url"], ex["word_count"],
                   ex["spa_roots"] or "n/a", ", ".join(ex["framework_hints"][:3]) or "n/a"),
                "Server-render or pre-render these routes so the content is in the HTML response.",
                confidence="medium",
                mechanism="A fetcher that does not execute JavaScript receives only the shell. "
                          "The page is then indistinguishable from a blank document.",
                detail="Confirm by running `curl -s <url> | wc -c` against what the page shows in "
                       "a browser, or re-run this audit on a machine with a headless browser.",
                urls=[s[0]["url"] for s in suspects][:10]))
        elif suspects:
            na.append({"check_id": "RX-CLIENT-RENDERED-SHELL",
                       "reason": "only one interior page looked thin (%s); not enough to conclude "
                                 "the site is client-rendered" % suspects[0][0]["url"]})
        else:
            na.append({"check_id": "RX-CLIENT-RENDERED-SHELL",
                       "reason": "served HTML already contains substantial text on every page"})

    # ---------------------------------------------------------------- 2. noscript-only
    for p in ok[:12]:
        ns = re.findall(r"(?is)<noscript>(.*?)</noscript>", p["html"])
        ns_text = " ".join(re.sub(r"(?s)<[^>]+>", " ", n) for n in ns)
        if len(ns_text.split()) > 60 and p["extract"]["word_count"] < 150:
            out.append(finding(
                "RX-NOSCRIPT-FALLBACK-ONLY",
                "The only readable text on the page is inside <noscript>", "high",
                "%s carries %d words inside <noscript> but only %d words of ordinary text."
                % (p["url"], len(ns_text.split()), p["extract"]["word_count"]),
                "Move the real content into the document body rather than relying on a "
                "<noscript> fallback.",
                mechanism="<noscript> is widely ignored by extraction pipelines, which treat the "
                          "page as empty rather than reading the fallback.",
                urls=[p["url"]]))
            break

    # ---------------------------------------------------------------- 3. content in iframes
    iframed = []
    for p in ok:
        for f in p["extract"]["iframes"]:
            src = (f.get("src") or "").lower()
            if not src or re.search(r"(analytics|gtm|doubleclick|facebook|hotjar|recaptcha|"
                                    r"consent|tagmanager|pixel|youtube|vimeo|player)", src):
                continue
            if p["extract"]["word_count"] < 250:
                iframed.append((p, f))
    if iframed:
        p, f = iframed[0]
        out.append(finding(
            "RX-CONTENT-IN-IFRAME", "Primary content is delivered inside a third-party iframe",
            "high",
            "%s contains only %d words of its own text and embeds %s%s."
            % (p["url"], p["extract"]["word_count"], f["src"][:120],
               " (no title attribute)" if not f.get("title") else ""),
            "Render the embedded information (menu, booking options, listings, specifications) "
            "as text in the host page, or mirror it server-side alongside the widget.",
            mechanism="An iframe is a separate document. Crawlers attribute its content to the "
                      "third-party origin, not to this page, so the facts inside it never count "
                      "as this brand's content and cannot be cited against this URL.",
            detail="Common with booking engines, restaurant menus, job boards, store locators and "
                   "review widgets. Keeping the widget is fine — the fix is to also publish the "
                   "underlying facts as HTML.",
            urls=[q[0]["url"] for q in iframed][:8],
            verification="curl -s <url> | grep -i '<key item from the widget>' matches."))

    # ---------------------------------------------------------------- 4. facts locked in images
    image_locked = []
    for p in ok:
        ex = p["extract"]
        body_images = [i for i in ex["images"] if not i["in_chrome"]]
        texty = [i for i in body_images if TEXTY_IMAGE_RX.search((i["src"] or "") + " " + i["alt"])]
        thin = ex["word_count"] < 220
        if p["type"] in FACT_PAGE_TYPES and len(body_images) >= 3 and thin:
            image_locked.append((p, len(body_images), len(texty)))
        elif texty and thin:
            image_locked.append((p, len(body_images), len(texty)))
    if image_locked:
        p, nimg, ntexty = image_locked[0]
        out.append(finding(
            "RX-FACTS-LOCKED-IN-IMAGES",
            "Pages carry few words and many images — key facts are likely rendered as pictures",
            "high",
            "%d page(s) match. Example %s (%s page): %d words of body text across %d body images"
            "%s." % (len(image_locked), p["url"], p["type"], p["extract"]["word_count"], nimg,
                     ", %d of which have image-of-text filenames or alt text" % ntexty if ntexty else ""),
            "Publish the same information as HTML text — a real table for specifications or "
            "pricing, real headings and paragraphs for value propositions — and keep the image "
            "as illustration.",
            confidence="medium" if not ntexty else "high",
            mechanism="Text baked into an image is not extractable. The fact is visible to a "
                      "visitor and absent for every machine, so an assistant answering 'how much "
                      "does X cost' has nothing on this page to quote.",
            detail="Price tables, spec sheets, opening hours, menus and comparison charts are the "
                   "usual offenders. HTML tables also read better on mobile.",
            urls=[q[0]["url"] for q in image_locked][:8]))

    # ---------------------------------------------------------------- 5. facts only in PDFs
    docs = meta.get("linked_documents", [])
    if len(docs) >= 3:
        thin_hosts = [d for d in docs if any(
            p["url"] == d["from"] and p["extract"]["word_count"] < 250 for p in ok)]
        if thin_hosts:
            out.append(finding(
                "RX-FACTS-ONLY-IN-DOCUMENTS",
                "Substantive information is published only as downloadable documents", "medium",
                "%d document links found (e.g. %s from %s), while the linking pages average under "
                "250 words of their own text."
                % (len(docs), docs[0]["url"], docs[0]["from"]),
                "Publish an HTML version of each document's key content; keep the PDF as an "
                "optional download.",
                confidence="medium",
                mechanism="PDF extraction is unreliable and many fetchers skip binaries entirely. "
                          "Facts that exist only in a datasheet or brochure are effectively "
                          "unavailable to an assistant answering a question about them.",
                urls=list({d["from"] for d in docs})[:8]))

    # ---------------------------------------------------------------- 6. interaction-gated text
    for p in ok[:12]:
        controls = set(re.findall(r'aria-controls=["\']([^"\']+)["\']', p["html"]))
        if len(controls) < 3:
            continue
        present = {c for c in controls if re.search(r'id=["\']%s["\']' % re.escape(c), p["html"])}
        missing = controls - present
        if len(missing) >= max(3, len(controls) * 0.6):
            out.append(finding(
                "RX-TABBED-CONTENT-NOT-IN-HTML",
                "Tab / accordion panels are not present in the served HTML", "high",
                "%s has %d aria-controls references but only %d of the referenced panel IDs exist "
                "in the HTML; %d panels are created or fetched only on interaction."
                % (p["url"], len(controls), len(present), len(missing)),
                "Render every tab and accordion panel in the HTML and hide the inactive ones with "
                "CSS, rather than fetching them on click.",
                mechanism="FAQ answers, specifications and shipping terms are commonly hidden in "
                          "accordions. A crawler never clicks, so content that only arrives on "
                          "interaction is never read — and these panels usually hold exactly the "
                          "question-shaped answers assistants look for.",
                urls=[p["url"]],
                verification="curl -s <url> | grep -c '<text from a collapsed panel>' > 0"))
            break

    # ---------------------------------------------------------------- 7. document structure
    no_h1 = [p for p in ok if not p["extract"]["h1s"]]
    multi_h1 = [p for p in ok if len(p["extract"]["h1s"]) > 2]
    if no_h1 and len(no_h1) >= max(2, len(ok) * 0.3):
        out.append(finding(
            "RX-NO-H1", "Pages have no H1 heading", "medium",
            "%d of %d crawled pages contain no <h1>, e.g. %s (title: %r)."
            % (len(no_h1), len(ok), no_h1[0]["url"], (no_h1[0]["extract"]["title"] or "")[:70]),
            "Give every page exactly one H1 that states the page's subject in plain words.",
            mechanism="The H1 is the strongest cue for what a page is about. Without it, "
                      "extraction falls back to the title tag or guesswork, which weakens the "
                      "match between a user's question and this page.",
            urls=[p["url"] for p in no_h1][:10], effort="low"))
    if multi_h1:
        out.append(finding(
            "RX-MULTIPLE-H1", "Pages declare several competing H1 headings", "low",
            "%d pages have more than two <h1> elements, e.g. %s has %d."
            % (len(multi_h1), multi_h1[0]["url"], len(multi_h1[0]["extract"]["h1s"])),
            "Keep one H1 per page and demote the rest to H2/H3 in reading order.",
            mechanism="Several H1s leave no single statement of the page's subject, so the "
                      "extracted topic is diluted.",
            urls=[p["url"] for p in multi_h1][:8], effort="low"))
    no_semantic = [p for p in ok if not p["extract"]["has_main"] and not p["extract"]["has_article"]
                   and p["extract"]["word_count"] > 300]
    if len(no_semantic) >= max(2, len(ok) * 0.6):
        out.append(finding(
            "RX-NO-MAIN-LANDMARK", "No <main> or <article> element marks the primary content",
            "low",
            "%d of %d content pages use neither <main> nor <article>, e.g. %s."
            % (len(no_semantic), len(ok), no_semantic[0]["url"]),
            "Wrap the page's own content in <main> (and each item in <article> on listing pages).",
            mechanism="Extractors use landmarks to separate the answer from navigation, cookie "
                      "notices and footers. Without them the quotable text is mixed with chrome, "
                      "which lowers the quality of any snippet taken from the page.",
            urls=[p["url"] for p in no_semantic][:8], effort="low"))

    # ---------------------------------------------------------------- 8. missing alt text
    alt_stats = [(p, [i for i in p["extract"]["images"] if not i["in_chrome"]]) for p in ok]
    total_img = sum(len(v) for _, v in alt_stats)
    # An explicit alt="" marks a decorative image and is correct practice, so only
    # a missing alt attribute counts here.
    missing_alt = sum(len([i for i in v if not i["has_alt"]]) for _, v in alt_stats)
    if total_img >= 8 and missing_alt >= total_img * 0.5:
        out.append(finding(
            "RX-IMAGE-ALT-MISSING", "Most content images have no alt text", "medium",
            "%d of %d body images across %d pages have no alt attribute at all "
            "(an explicit alt=\"\" is treated as a correct decorative marker and not counted)."
            % (missing_alt, total_img, len(ok)),
            "Write alt text that states what the image shows; for images that carry data, also "
            "publish that data as text.",
            category="discoverability",
            mechanism="Alt text is the only textual description of an image available to a "
                      "machine, and it is also what a screen reader announces. Missing alt makes "
                      "image-borne meaning unreadable to both.",
            urls=[p["url"] for p, v in alt_stats if v][:8], effort="low"))

    # ---------------------------------------------------------------- 9. quotable self-definition
    head = home["extract"]["text_head"][:700]
    h1 = " ".join(home["extract"]["h1s"])[:200]
    title = home["extract"]["title"]
    desc = home["extract"]["meta"].get("description", "")
    brand_token = re.split(r"\W+", brand)[0].lower()
    # A definition counts wherever it is extractable: heading, opening copy, meta
    # description or the Organization description — all are served in the HTML.
    org_desc = ""
    for raw in home["extract"]["jsonld_raw"]:
        m = re.search(r'"description"\s*:\s*"([^"]{20,400})"', raw)
        if m:
            org_desc = m.group(1)
            break
    candidates = [c for c in (h1, head[:400], desc, org_desc, title) if c]

    def names_brand(c):
        low = c.lower()
        if brand_token and brand_token in low:
            return True
        if not brand_token:
            return False
        # Initialisms: "San Francisco Museum of Modern Art" names SFMOMA, so the
        # initials of every word are checked, not only the capitalised ones.
        words = re.findall(r"[A-Za-z]+", c)
        variants = {"".join(w[0] for w in words).lower(),
                    "".join(w[0] for w in words if w[0].isupper()).lower()}
        return any(brand_token in v for v in variants if v)

    # A definition is extractable if it names the brand and says what kind of thing
    # it is — via a linking verb, an appositive ("Brand: the … shoes"), or a
    # category noun. An organisation whose own name states its category (a museum,
    # a bakery) satisfies this through its heading or title alone.
    def defines(c):
        """True when the brand mention and what-kind-of-thing marker sit together.

        Proximity matters: a brand name in the navigation and an unrelated "is"
        four paragraphs later is not a definition, and treating it as one would
        make this check pass on almost any page.
        """
        marker = (DEFINITION_RX.search(c) or APPOSITIVE_RX.search(c) or CATEGORY_RX.search(c))
        if not marker:
            return False
        if c in (h1, title) and CATEGORY_RX.search(c):
            return True          # the organisation's own name states its category
        if not names_brand(c):
            return False
        low, bt = c.lower(), brand_token
        positions = [m.start() for m in re.finditer(re.escape(bt), low)] if bt in low else [0]
        return any(abs(marker.start() - pos) <= 120 for pos in positions)

    has_definition = any(defines(c) for c in candidates)
    if not has_definition:
        out.append(finding(
            "RX-NO-QUOTABLE-DEFINITION",
            "No plain sentence on the homepage says what the organisation is", "high",
            "Homepage H1 is %r; meta description is %r; Organization description is %r. None of "
            "them states '%s is a <category> that <does what> for <whom>' in extractable text."
            % ((h1 or "(none)")[:80], (desc or "(none)")[:100], (org_desc or "(none)")[:100],
               brand),
            "Put one literal sentence near the top of the homepage: '%s is a <category> that "
            "<does what> for <whom>', and repeat the same wording in the meta description, the "
            "Organization schema description and the About page." % brand,
            mechanism="Assistants answer 'what is X' by quoting a sentence that already exists. "
                      "Slogans and abstract value statements give them nothing to lift, so the "
                      "answer gets assembled from third-party descriptions the brand does not "
                      "control — or the brand is skipped for a competitor that states it plainly.",
            detail="Write it as a fact, not marketing: category noun, what it does, who it serves, "
                   "and where it operates if that is a differentiator. Keep the wording identical "
                   "everywhere it appears so independent sources reinforce one description.",
            urls=[home["url"]], effort="low",
            verification="Search the homepage HTML for the sentence; it should appear verbatim in "
                         "the served markup, not only after rendering."))
    else:
        na.append({"check_id": "RX-NO-QUOTABLE-DEFINITION",
                   "reason": "homepage states the organisation's category in extractable text"})

    # ---------------------------------------------------------------- 10. page-type facts
    def has(rx, p):
        return bool(rx.search(p["extract"]["text"]))

    for p in [q for q in ok if q["type"] == "pricing"]:  # legal/* is typed separately
        if not has(PRICE_RX, p):
            gated = re.search(r"(contact (us|sales)|request (a )?(quote|demo|pricing)|talk to sales|"
                              r"get in touch|custom pricing|book a demo)", p["extract"]["text"], re.I)
            out.append(finding(
                "RX-PRICE-NOT-IN-TEXT",
                "Pricing page contains no price in machine-readable text", "medium",
                "%s has %d words and %d images but no currency amount in its text.%s"
                % (p["url"], p["extract"]["word_count"], len(p["extract"]["images"]),
                   " The page directs visitors to contact sales instead." if gated else ""),
                "Publish at least a starting price, a price range or a worked example in text, and "
                "mirror it in Offer structured data."
                if not gated else
                "If pricing must stay quote-based, still publish an anchor in text — a starting "
                "price, a typical range, or the pricing model (per seat / per project / per hour).",
                confidence="medium",
                mechanism="Cost is one of the most common questions asked of assistants. With no "
                          "number anywhere in the text, the assistant either omits the brand or "
                          "repeats a third-party guess at its pricing.",
                urls=[p["url"]]))
            break

    # Assessed across the whole crawl: a "talk to sales" page is legitimately just a
    # form, so the question is whether the details appear anywhere in text at all.
    contact_pages = [q for q in ok if q["type"] == "contact"]
    if contact_pages:
        site_text = "\n".join(q["extract"]["text"] for q in ok)
        missing = [name for name, rx in (("phone number", PHONE_RX), ("email address", EMAIL_RX),
                                         ("street address", ADDRESS_RX), ("postcode", POSTCODE_RX))
                   if not rx.search(site_text)]
        p = contact_pages[0]
        if len(missing) >= 3:
            out.append(finding(
                "RX-CONTACT-DETAILS-NOT-IN-TEXT",
                "No contact details appear as text anywhere on the site", "high",
                "Across %d crawled pages (including the contact page %s) there is no %s in text. "
                "The contact page has %d form field(s) and %d image(s)."
                % (len(ok), p["url"], ", ".join(missing),
                   len(p["extract"]["inputs"]), len(p["extract"]["images"])),
                "Publish the postal address, phone number and email as plain text on the contact "
                "page and in the site footer, and mirror them in Organization/LocalBusiness schema.",
                mechanism="Contact details are the highest-intent facts a machine can extract. "
                          "Hidden behind a form or drawn inside an image, they cannot be surfaced "
                          "in an answer, so the assistant sends the user to a directory listing "
                          "instead — which is often out of date.",
                urls=[q["url"] for q in contact_pages][:5], effort="low"))
        else:
            na.append({"check_id": "RX-CONTACT-DETAILS-NOT-IN-TEXT",
                       "reason": "contact details are published as text somewhere on the site"})

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "rendering_available": rendered_available,
            "render_note": meta.get("capabilities", {}).get("render_note"),
            "brand_name_inferred": brand,
            "median_words_per_page": sorted(p["extract"]["word_count"] for p in ok)[len(ok) // 2],
            "pages_analysed": len(ok),
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
