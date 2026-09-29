#!/usr/bin/env python3
"""Stage 1 of the audit: can an AI retrieval agent reach the page at all?

Reads a crawl bundle (built by audit-orchestrator/scripts/crawl.py) and emits
findings JSON on stdout. Every finding carries observed values as evidence;
checks that do not apply are reported in `not_applicable` rather than fired at
low confidence.

Usage: python3 check_access.py --bundle ./bundle [--json-out findings.json]
"""

import argparse
import json
import os
import re
import statistics
import sys
from urllib.parse import urlsplit


def same_site(a, b):
    """www.example.com and example.com are one site, not a cross-host canonical."""
    strip = lambda h: h.lower().split(":")[0].removeprefix("www.")
    return strip(a) == strip(b)

SKILL = "crawl-access-audit"

# Agents that fetch a page at answer time in order to cite it. Blocking these
# is what removes a site from live AI answers.
# The dominant citation paths. Losing any one of these is a material loss of AI
# visibility, because each fronts an assistant (or a search index an assistant
# queries) with enough reach to matter on its own.
MAJOR_RETRIEVAL = ["OAI-SearchBot", "ChatGPT-User", "Claude-User", "Claude-SearchBot",
                   "PerplexityBot", "Perplexity-User", "Googlebot", "Bingbot"]
# Real retrieval agents with far smaller reach. Blocking only these narrows the
# surface without removing the site from the answers that matter, so it must not
# be reported at the same severity as losing ChatGPT, Claude, Perplexity or the
# search indexes.
SECONDARY_RETRIEVAL = ["DuckAssistBot", "MistralAI-User", "Amazonbot"]
RETRIEVAL_AGENTS = MAJOR_RETRIEVAL + SECONDARY_RETRIEVAL
# Agents that collect corpora for model training. Blocking these is a defensible
# business decision with a discoverability cost, not a misconfiguration.
# Google-Extended belongs here, not above: it is not a crawler and fetches
# nothing. It is a robots.txt token governing whether content Googlebot already
# fetched may train or ground Gemini. Google Search and AI Overviews are
# controlled by Googlebot instead, so blocking it costs no search visibility.
TRAINING_AGENTS = ["GPTBot", "ClaudeBot", "anthropic-ai", "CCBot", "Applebot-Extended",
                   "Bytespider", "meta-externalagent", "FacebookBot", "cohere-ai",
                   "Diffbot", "omgili", "Timpibot", "AI2Bot", "Google-Extended"]
NOT_FOUND_WORDS = re.compile(
    r"(page not found|404|doesn'?t exist|does not exist|cannot be found|"
    r"can'?t find|no longer available|nothing here)", re.I)


# --------------------------------------------------------------------------
def load(bundle):
    def j(name):
        with open(os.path.join(bundle, name)) as fh:
            return json.load(fh)
    meta, idx, robots = j("meta.json"), j("index.json"), j("robots.json")
    try:
        sitemap = j("sitemap.json")
    except FileNotFoundError:
        sitemap = {"documents": [], "urls": [], "declared_in_robots": []}
    for p in idx["pages"]:
        for key, suffix in (("extract", ".extract.json"), ("rendered", ".rendered.extract.json")):
            path = os.path.join(bundle, "pages", p["id"] + suffix)
            p[key] = None
            if os.path.exists(path):
                with open(path) as fh:
                    p[key] = json.load(fh)
    return meta, idx["pages"], robots, sitemap


def finding(check_id, title, severity, evidence, action, *, category="discoverability",
            confidence="high", urls=None, mechanism="", detail="", effort="low",
            verification=""):
    return {
        "check_id": check_id, "title": title, "category": category, "concern": SKILL,
        "severity": severity, "confidence": confidence, "evidence": evidence,
        "affected_urls": urls or [], "mechanism": mechanism,
        "suggested_action": {"summary": action, "detail": detail,
                             "priority": severity, "effort": effort,
                             "verification": verification},
    }


# --------------------------------------------------------------------------
def run(bundle):
    meta, pages, robots, sitemap = load(bundle)
    out, na = [], []
    origin = meta["origin"]
    html_pages = [p for p in pages if p.get("is_html") and p["status"] == 200]
    verdicts = robots.get("agent_verdicts", {})

    # --- robots.txt presence -------------------------------------------
    if robots.get("served_html") and robots.get("status") == 200:
        out.append(finding(
            "CA-ROBOTS-NOT-PLAIN-TEXT",
            "robots.txt returns an HTML page instead of a robots file",
            "medium",
            "GET %s returned status 200 with content-type text/html rather than a robots "
            "file. Crawlers parse this as an unusable robots.txt; behaviour on an unparseable "
            "robots file is inconsistent across fetchers." % robots["url"],
            "Serve /robots.txt as plain text (content-type text/plain) or remove the catch-all "
            "route that swallows it.",
            mechanism="A robots.txt that is not plain text cannot be parsed; crawler behaviour "
                      "on an unparseable robots file is inconsistent and can suppress crawling.",
            verification="curl -sI https://%s/robots.txt shows content-type: text/plain"
                         % meta["site"]))
    elif not robots.get("fetched"):
        out.append(finding(
            "CA-ROBOTS-MISSING", "No robots.txt served", "low",
            "GET %s returned status %s%s." % (robots["url"], robots["status"],
                                              " (" + robots["error"] + ")" if robots.get("error") else ""),
            "Publish a robots.txt that allows AI retrieval agents and declares the sitemap.",
            mechanism="A missing robots.txt is not itself a block, but it is the only place to "
                      "declare sitemaps and to state an explicit AI-crawler policy.",
            detail="Minimum useful file:\nUser-agent: *\nAllow: /\nSitemap: %s/sitemap.xml"
                   % origin,
            verification="curl -s https://%s/robots.txt returns 200 text/plain" % meta["site"]))
    else:
        blanket = robots.get("groups", {}).get("*", {})
        if "/" in blanket.get("disallow", []) and not blanket.get("allow"):
            out.append(finding(
                "CA-BLANKET-DISALLOW", "robots.txt blocks all crawlers from the entire site",
                "critical",
                "robots.txt contains `User-agent: *` with `Disallow: /` and no Allow rules. "
                "Every automated reader, including AI retrieval agents, is told to stay out.",
                "Remove `Disallow: /` from the `User-agent: *` group and disallow only the "
                "paths that genuinely must stay private.",
                mechanism="Step one of retrieval is being let in. A site-wide disallow ends the "
                          "process before any content is read, so the brand cannot be cited.",
                urls=[robots["url"]],
                verification="Re-fetch robots.txt and confirm no site-wide Disallow remains."))

        blocked_retrieval = [a for a in RETRIEVAL_AGENTS
                             if a in verdicts and not verdicts[a]["allowed"]]
        blocked_training = [a for a in TRAINING_AGENTS
                            if a in verdicts and not verdicts[a]["allowed"]]
        if blocked_retrieval:
            # Severity tracks which agents are lost, not how many. A site that
            # blocks one minor fetcher while ChatGPT, Claude, Perplexity and the
            # search indexes are all allowed has not vanished from AI answers,
            # and reporting that as critical is the false positive that makes a
            # reader distrust the rest of the report.
            blocked_major = [a for a in blocked_retrieval if a in MAJOR_RETRIEVAL]
            allowed_major = [a for a in MAJOR_RETRIEVAL
                             if a in verdicts and verdicts[a]["allowed"]]
            if blocked_major:
                sev = "critical"
                title = "robots.txt blocks the agents that fetch pages to cite them"
                mech = ("These agents fetch a page live, at the moment a user asks a question, "
                        "in order to quote and link it. Blocking them removes the site from AI "
                        "answers entirely — a different and larger cost than blocking training "
                        "crawlers.")
            else:
                sev = "medium"
                title = "robots.txt blocks some minor retrieval agents"
                mech = ("These agents fetch a page live in order to quote and link it, so each "
                        "blocked one is a citation path closed. The major paths (%s) are still "
                        "allowed, so the site has not disappeared from AI answers — this narrows "
                        "the surface rather than removing it."
                        % ", ".join(allowed_major[:4] or ["none detected"]))
            out.append(finding(
                "CA-AI-RETRIEVAL-BLOCKED",
                title,
                sev,
                "Blocked at `/`: %s. Matching rules: %s.%s" % (
                    ", ".join(blocked_retrieval),
                    "; ".join(sorted({verdicts[a]["rule"] for a in blocked_retrieval})),
                    "" if blocked_major else
                    " Still allowed: %s." % ", ".join(allowed_major[:6] or ["none"])),
                "Allow the retrieval user-agents (%s) even if training crawlers stay blocked."
                % ", ".join(blocked_retrieval[:4]),
                mechanism=mech,
                detail="Add an explicit allow group above any broad disallow, e.g.\n"
                       + "\n".join("User-agent: %s\nAllow: /\n" % a for a in blocked_retrieval[:4]),
                urls=[robots["url"]],
                verification="Re-check each agent against robots.txt; all retrieval agents "
                             "should resolve to Allow for public pages."))
        if blocked_training:
            out.append(finding(
                "CA-AI-TRAINING-BLOCKED",
                "Training crawlers are blocked (deliberate policy — confirm it is intended)",
                "low", "Blocked at `/`: %s." % ", ".join(blocked_training),
                "Confirm this is a deliberate content policy; if the goal was only to prevent "
                "training use, keep these blocked and make sure retrieval agents stay allowed.",
                confidence="medium",
                mechanism="Blocking training crawlers reduces how well models know the brand from "
                          "memory, but does not by itself prevent live citation. It is a "
                          "legitimate choice, so it is reported for confirmation, not as a defect.",
                urls=[robots["url"]]))
        else:
            na.append({"check_id": "CA-AI-TRAINING-BLOCKED",
                       "reason": "no training-crawler blocks present in robots.txt"})

    # --- bot blocking at the edge (WAF / challenge) ---------------------
    m = meta.get("probes", {}).get("user_agent_matrix", {})
    browser, audit, plain = m.get("browser", {}), m.get("audit", {}), m.get("plain", {})

    def _blocked(v):
        return v.get("status") in (401, 403, 405, 406, 429, 503) or v.get("error")

    if browser.get("status") == 200:
        # A real AI retrieval agent always sends a descriptive, self-identifying
        # user-agent string (its published policy requires it). `audit` mimics
        # that; `plain` deliberately does not — it is the bare library default
        # with no identification at all. A site that rejects only `plain` is
        # very often applying a sensible, targeted anti-abuse rule against
        # anonymous traffic, which says nothing about how it treats an agent
        # that identifies itself. Only a block on `audit` is real evidence that
        # self-identifying, non-browser clients are rejected.
        if _blocked(audit):
            out.append(finding(
                "CA-EDGE-BOT-BLOCK",
                "Non-browser user-agents are blocked at the edge, even when self-identified",
                "critical",
                "Homepage fetched with a browser user-agent returned 200 (%d chars of text); "
                "fetched again with a plain-text, self-identifying user-agent it returned %s. %s"
                % (browser.get("text_len", 0),
                   audit.get("status") or audit.get("error", "network error"),
                   ("Server header: %s. " % browser.get("server")) if browser.get("server") else ""),
                "Allowlist the published AI retrieval user-agents in the WAF/CDN bot rules, or "
                "relax the rule that rejects requests without browser-like headers.",
                mechanism="Bot-protection rules that key off user-agent or JavaScript challenges "
                          "reject AI fetchers the same way they reject scrapers, even when the "
                          "fetcher identifies itself exactly as its published policy requires. "
                          "The site looks perfectly normal in a browser while being unreachable "
                          "to every agent that would cite it.",
                detail="Verify by fetching the homepage with a published AI agent UA string; it "
                       "should return the same HTML a browser receives. Managed rule sets "
                       "(Cloudflare 'Bot Fight Mode', AWS WAF bot control) are the usual cause.",
                urls=[meta["seed_url"]],
                verification="curl -A 'OAI-SearchBot/1.0' -s -o /dev/null -w '%%{http_code}' %s "
                             "returns 200" % meta["seed_url"]))
        elif _blocked(plain):
            out.append(finding(
                "CA-ANONYMOUS-UA-BLOCKED",
                "Requests with no identifying user-agent are rejected", "low",
                "Homepage fetched with a browser user-agent returned 200; fetched again with no "
                "identifying user-agent string it returned %s. A request carrying this audit's "
                "own descriptive user-agent succeeded (status %s)."
                % (plain.get("status") or plain.get("error", "network error"),
                   audit.get("status")),
                "No action needed if this is deliberate: rejecting anonymous, unidentified "
                "traffic while allowing self-identifying clients is a reasonable anti-abuse "
                "policy, not a discoverability defect.",
                confidence="medium",
                mechanism="Every published AI retrieval agent sends a descriptive, "
                          "self-identifying user-agent string, so rejecting only anonymous "
                          "requests does not by itself block them. This is reported for "
                          "awareness rather than as a defect — treat CA-EDGE-BOT-BLOCK, not this "
                          "finding, as the signal that AI agents are actually affected.",
                urls=[meta["seed_url"]]))
        else:
            na.append({"check_id": "CA-EDGE-BOT-BLOCK",
                       "reason": "a self-identifying non-browser request received the same "
                                 "status as a browser request"})

        if audit.get("status") == 200 and browser.get("text_len", 0) > 400 and \
                audit.get("text_len", 0) < browser.get("text_len", 0) * 0.4:
            out.append(finding(
                "CA-UA-CONTENT-VARIES",
                "Non-browser user-agents receive substantially less content",
                "high",
                "Browser user-agent received %d characters of text; the audit user-agent received "
                "%d from the same URL." % (browser.get("text_len", 0), audit.get("text_len", 0)),
                "Serve the same HTML regardless of user-agent; move any bot-specific handling to "
                "caching rather than content differences.",
                confidence="medium",
                mechanism="If a fetcher receives a thinner page than a browser does, the facts an "
                          "assistant could quote are missing from the copy it actually sees.",
                urls=[meta["seed_url"]]))
    elif browser.get("status") not in (200, 0):
        out.append(finding(
            "CA-HOMEPAGE-NOT-200", "Homepage does not return 200 to an ordinary GET", "critical",
            "GET %s with a browser user-agent returned status %s." % (
                meta["seed_url"], browser.get("status")),
            "Fix the homepage response so an unauthenticated GET returns 200 with the page HTML.",
            mechanism="If the entry URL does not return content, nothing downstream can be "
                      "crawled, read or cited.",
            urls=[meta["seed_url"]]))

    # --- sitemap --------------------------------------------------------
    good_docs = [d for d in sitemap.get("documents", []) if d.get("ok")]
    declared = sitemap.get("declared_in_robots", [])
    if not good_docs:
        out.append(finding(
            "CA-SITEMAP-MISSING", "No usable XML sitemap", "medium",
            "Tried %s — none returned a parseable sitemap." % (
                ", ".join(d["url"] + " (" + str(d["status"]) + ")"
                          for d in sitemap.get("documents", [])) or "/sitemap.xml"),
            "Publish an XML sitemap listing every canonical public URL with an accurate "
            "<lastmod>, and declare it in robots.txt.",
            mechanism="A sitemap is how a crawler learns which URLs exist and which changed "
                      "recently. Without one, discovery depends entirely on internal links, so "
                      "weakly-linked pages are never fetched.",
            urls=[origin + "/sitemap.xml"],
            verification="curl -s %s/sitemap.xml | head returns <urlset> and robots.txt names it"
                         % origin))
    else:
        if not declared:
            out.append(finding(
                "CA-SITEMAP-NOT-DECLARED", "Sitemap exists but is not declared in robots.txt",
                "low",
                "%s is reachable but robots.txt contains no `Sitemap:` line." % good_docs[0]["url"],
                "Add `Sitemap: %s` to robots.txt." % good_docs[0]["url"],
                mechanism="Crawlers that do not guess /sitemap.xml rely on the robots.txt "
                          "declaration to find it.",
                urls=[robots["url"]]))
        total = sum(d.get("urls", 0) for d in good_docs)
        with_lastmod = sum(d.get("with_lastmod", 0) for d in good_docs)
        if total and with_lastmod < total * 0.5:
            out.append(finding(
                "CA-SITEMAP-NO-LASTMOD", "Sitemap entries lack <lastmod> dates", "low",
                "%d of %d sitemap URLs carry a <lastmod> value." % (with_lastmod, total),
                "Emit an accurate <lastmod> for every URL, updated when the page content changes.",
                mechanism="<lastmod> is the cheapest signal a crawler has for deciding what to "
                          "re-fetch. Without it, updated pages are re-read late or not at all.",
                urls=[good_docs[0]["url"]]))
    broken_declared = [d for d in sitemap.get("documents", [])
                       if d["url"] in declared and not d.get("ok")]
    if broken_declared:
        out.append(finding(
            "CA-SITEMAP-DECLARED-BROKEN", "A sitemap declared in robots.txt is not fetchable",
            "medium",
            "; ".join("%s → status %s" % (d["url"], d["status"]) for d in broken_declared),
            "Fix or remove the broken Sitemap declaration in robots.txt.",
            urls=[d["url"] for d in broken_declared],
            mechanism="A dead sitemap reference wastes the crawler's only structured hint about "
                      "the site and can leave large sections undiscovered."))

    # --- response status of crawled pages ------------------------------
    errors = [p for p in pages if p["status"] >= 400]
    net_fail = [p for p in pages if p["status"] == 0]
    if errors:
        by_status = {}
        for p in errors:
            by_status.setdefault(p["status"], []).append(p["url"])
        sev = "high" if len(errors) > max(2, len(pages) * 0.15) else "medium"
        out.append(finding(
            "CA-BROKEN-INTERNAL-URLS", "Internally linked URLs return error statuses", sev,
            "%d of %d fetched URLs returned 4xx/5xx: %s" % (
                len(errors), len(pages),
                "; ".join("%s → %s" % (v[0], k) for k, v in list(by_status.items())[:5])),
            "Fix or redirect the broken URLs and remove the internal links that point at them.",
            mechanism="Broken internal links waste crawl budget and break the path to the pages "
                      "behind them; a fetcher that lands on one has nothing to quote.",
            urls=[u for v in by_status.values() for u in v][:10]))
    seed_failed = [p for p in net_fail if p["url"] == meta.get("seed_url")]
    if seed_failed:
        out.append(finding(
            "CA-HOMEPAGE-FETCH-FAILED", "The homepage could not be fetched reliably", "high",
            "GET %s failed even after a retry: %s. Other pages on the same host responded, so "
            "this is intermittent rather than a hard outage."
            % (meta["seed_url"], seed_failed[0]["error"]),
            "Investigate intermittent timeouts on the homepage — usually an origin that is slow "
            "under cache misses, or an edge rule that rate-limits non-browser clients.",
            confidence="medium",
            mechanism="A fetcher that times out does not retry. Intermittent homepage failures "
                      "mean the brand is randomly absent from answers rather than consistently "
                      "present, which is harder to notice and just as costly.",
            urls=[meta["seed_url"]]))
    other_fail = [p for p in net_fail if p["url"] != meta.get("seed_url")]
    if other_fail:
        out.append(finding(
            "CA-FETCH-FAILURES", "Some URLs could not be fetched at all",
            "medium" if len(other_fail) >= 3 else "low",
            "%d URL(s) failed at the network layer: %s" % (
                len(other_fail),
                "; ".join("%s (%s)" % (p["url"], p["error"]) for p in other_fail[:4])),
            "Investigate TLS, DNS or timeout errors on these URLs — they are invisible to every "
            "automated reader.",
            confidence="medium", urls=[p["url"] for p in other_fail][:10]))

    # --- soft 404 -------------------------------------------------------
    nf = meta.get("probes", {}).get("not_found", {})
    if nf:
        if nf.get("status") == 200 and not nf.get("redirected_to_home"):
            out.append(finding(
                "CA-SOFT-404", "Missing pages return HTTP 200 instead of 404", "medium",
                "A deliberately invalid URL returned status 200 with %d characters of text."
                % nf.get("text_len", 0),
                "Return a real 404 (or 410) status for URLs that do not exist.",
                mechanism="Soft 404s let an unlimited number of junk URLs enter the index as "
                          "'valid' pages, diluting crawl budget and letting assistants cite URLs "
                          "that contain no answer.",
                urls=[nf.get("final_url", "")],
                verification="curl -o /dev/null -w '%%{http_code}' %s/does-not-exist returns 404"
                             % origin))
        elif nf.get("redirected_to_home"):
            out.append(finding(
                "CA-404-REDIRECTS-HOME", "Missing pages redirect to the homepage", "medium",
                "An invalid URL redirected to %s and returned status %s."
                % (nf.get("final_url"), nf.get("status")),
                "Replace the catch-all redirect with a 404 response and a helpful not-found page.",
                mechanism="Redirecting every unknown URL to the homepage makes broken links "
                          "invisible to monitoring and teaches crawlers that any URL 'exists', "
                          "which suppresses re-crawl of the URLs that matter.",
                urls=[nf.get("final_url", "")]))

    # --- indexing directives -------------------------------------------
    noindex, nosnippet, xrobots = [], [], []
    for p in html_pages:
        directives = (p["extract"]["meta"].get("robots", "") if p.get("extract") else "").lower()
        header = (p.get("headers", {}).get("x-robots-tag", "") or "").lower()
        combined = directives + " " + header
        if "noindex" in combined or "none" in combined:
            noindex.append((p["url"], (directives or header).strip()))
        if "nosnippet" in combined or "max-snippet:0" in combined.replace(" ", ""):
            nosnippet.append((p["url"], (directives or header).strip()))
        if header:
            xrobots.append((p["url"], header))
    content_noindex = [(u, d) for u, d in noindex
                       if not re.search(r"/(search|filter|tag|cart|thank|preview)", u, re.I)]
    if content_noindex:
        sev = "critical" if len(content_noindex) >= max(2, len(html_pages) * 0.5) else "high"
        out.append(finding(
            "CA-NOINDEX-ON-CONTENT", "Content pages carry a noindex directive", sev,
            "%d of %d crawled HTML pages are marked noindex, e.g. %s (`%s`)." % (
                len(content_noindex), len(html_pages), content_noindex[0][0], content_noindex[0][1]),
            "Remove noindex from pages that should be findable; keep it only on utility URLs "
            "(internal search results, filtered duplicates, thank-you pages).",
            mechanism="noindex removes the page from the search indexes that AI assistants query "
                      "for candidate sources, so the page is never a candidate to cite.",
            urls=[u for u, _ in content_noindex][:10],
            verification="View source on each page and confirm no `noindex` in meta robots or the "
                         "X-Robots-Tag header."))
    if nosnippet:
        out.append(finding(
            "CA-NOSNIPPET", "Pages forbid snippet extraction", "high",
            "%d pages carry nosnippet or max-snippet:0, e.g. %s (`%s`)."
            % (len(nosnippet), nosnippet[0][0], nosnippet[0][1]),
            "Remove `nosnippet` / `max-snippet:0`, or raise the limit to at least 160 characters.",
            mechanism="These directives explicitly forbid quoting text from the page. An "
                      "assistant that cannot quote a fact will use a competitor's page that it "
                      "can quote, even when this page ranks higher.",
            urls=[u for u, _ in nosnippet][:10]))

    # --- canonicals -----------------------------------------------------
    missing_canonical, cross_host, to_home = [], [], []
    for p in html_pages:
        ex = p.get("extract")
        if not ex:
            continue
        c = ex.get("canonical", "")
        if not c:
            missing_canonical.append(p["url"])
            continue
        ch, ph = urlsplit(c).netloc.lower(), urlsplit(p["url"]).netloc.lower()
        if ch and not same_site(ch, ph):
            cross_host.append((p["url"], c))
        elif urlsplit(c).path.rstrip("/") == "" and urlsplit(p["url"]).path.rstrip("/") != "":
            to_home.append((p["url"], c))
    if to_home:
        out.append(finding(
            "CA-CANONICAL-TO-HOMEPAGE", "Inner pages declare the homepage as their canonical",
            "high",
            "%d pages point rel=canonical at the site root, e.g. %s → %s."
            % (len(to_home), to_home[0][0], to_home[0][1]),
            "Set each page's canonical to its own URL.",
            mechanism="A canonical pointing at the homepage tells indexers this page is a "
                      "duplicate of the homepage, collapsing the whole site to one URL. The "
                      "specific page that answers a question then never surfaces.",
            urls=[u for u, _ in to_home][:10]))
    if cross_host:
        out.append(finding(
            "CA-CANONICAL-CROSS-HOST", "Pages canonicalise to a different hostname", "high",
            "%d pages, e.g. %s → %s." % (len(cross_host), cross_host[0][0], cross_host[0][1]),
            "Point canonicals at this site's own URLs unless the content genuinely lives "
            "elsewhere; if it does, consolidate rather than duplicating.",
            confidence="medium",
            mechanism="Cross-host canonicals hand indexing credit to another domain; citations "
                      "then name that domain rather than the brand's own site.",
            urls=[u for u, _ in cross_host][:10]))
    if missing_canonical and len(missing_canonical) >= max(2, len(html_pages) * 0.5):
        out.append(finding(
            "CA-CANONICAL-MISSING", "Most pages declare no canonical URL", "low",
            "%d of %d crawled HTML pages have no rel=canonical link."
            % (len(missing_canonical), len(html_pages)),
            "Emit a self-referencing rel=canonical on every page.",
            mechanism="Without canonicals, parameterised and duplicate URLs compete with each "
                      "other, splitting the signals that decide which URL gets cited.",
            urls=missing_canonical[:10]))
    elif not missing_canonical:
        na.append({"check_id": "CA-CANONICAL-MISSING",
                   "reason": "every crawled page declares a canonical"})

    # --- redirects ------------------------------------------------------
    chains = [p for p in pages if len(p.get("redirects", [])) >= 3]
    if chains:
        out.append(finding(
            "CA-REDIRECT-CHAINS", "Long redirect chains on internal URLs", "low",
            "%d URLs redirect 3+ times, e.g. %s → %s (%d hops)."
            % (len(chains), chains[0]["url"], chains[0]["final_url"], len(chains[0]["redirects"])),
            "Collapse chains to a single 301 to the final URL and update the internal links.",
            mechanism="Some fetchers cap redirect depth or drop the request; every extra hop is "
                      "latency on a request that already has a short timeout.",
            urls=[p["url"] for p in chains][:10]))

    # --- latency --------------------------------------------------------
    timings = [p["elapsed_ms"] for p in pages if p["status"] == 200 and p["elapsed_ms"] > 0]
    if len(timings) >= 3:
        med = statistics.median(timings)
        worst = max(timings)
        if med > 2500:
            out.append(finding(
                "CA-SLOW-RESPONSES", "Server responses are slow enough to risk fetcher timeouts",
                "high" if med > 5000 else "medium",
                "Median full-response time across %d pages was %d ms (slowest %d ms)."
                % (len(timings), med, worst),
                "Bring median server response under ~1s: add full-page caching / CDN edge caching "
                "for anonymous requests and fix the slowest templates first.",
                mechanism="AI fetchers use short timeouts and rarely retry. A page that answers "
                          "the question perfectly but responds slowly is dropped from the "
                          "candidate set before it is read.",
                urls=[p["url"] for p in sorted(pages, key=lambda x: -x["elapsed_ms"])[:3]],
                verification="Re-measure with curl -w '%{time_total}' on the slowest URLs."))
        else:
            na.append({"check_id": "CA-SLOW-RESPONSES",
                       "reason": "median response time %d ms is within budget" % med})

    # --- discovery gap ---------------------------------------------------
    linked = set()
    for p in html_pages:
        if p.get("extract"):
            linked.update(l["href"] for l in p["extract"]["links_internal"])
    sm_total = sum(d.get("urls", 0) for d in good_docs)
    if sm_total >= 25 and len(linked) < 10:
        out.append(finding(
            "CA-LINK-DISCOVERY-GAP", "Pages are barely reachable through in-page links", "high",
            "The sitemap declares %d URLs, but only %d distinct internal links were found in the "
            "HTML of %d crawled pages." % (sm_total, len(linked), len(html_pages)),
            "Render primary navigation and listing links as real <a href> elements in the "
            "server HTML, not as click handlers built after load.",
            confidence="medium",
            mechanism="Crawlers walk <a href> links. Navigation built entirely in JavaScript "
                      "leaves the site's own pages unreachable except through the sitemap, and "
                      "unlinked pages accumulate almost no ranking signal.",
            urls=[meta["seed_url"]]))

    # --- transport ------------------------------------------------------
    hp = meta.get("probes", {}).get("http_to_https")
    if hp and not hp.get("final_https") and hp.get("status"):
        out.append(finding(
            "CA-HTTP-NOT-REDIRECTED", "http:// URLs are not redirected to https://", "low",
            "GET http://%s/ returned status %s and did not end on an https URL."
            % (meta["site"], hp["status"]),
            "301-redirect all http traffic to https and enable HSTS.",
            mechanism="Duplicate http/https URLs split signals, and some fetchers refuse "
                      "insecure origins outright."))

    # --- proactive -------------------------------------------------------
    lt = meta.get("probes", {}).get("llms_txt", {})
    if lt and (lt.get("status") != 200 or lt.get("is_html")):
        out.append(finding(
            "CA-NO-LLMS-TXT", "No /llms.txt summary file published", "info",
            "GET %s/llms.txt returned status %s." % (origin, lt.get("status")),
            "Publish /llms.txt: a short Markdown file naming the brand, what it does in one "
            "sentence, and links to the canonical pages for its main answers.",
            confidence="medium", effort="low",
            mechanism="Adoption is still emerging, so this is an opportunity rather than a "
                      "defect. It costs one file, and the exercise of writing a canonical "
                      "one-sentence description and a curated link list improves the on-page "
                      "content regardless of who reads the file.",
            detail="Keep it factual: brand name, one-line definition, key URLs with a short "
                   "gloss each, and a contact/press link."))

    return {
        "skill": SKILL, "bundle": os.path.abspath(bundle), "site": meta["site"],
        "findings": out, "not_applicable": na,
        "observations": {
            "robots_fetched": robots.get("fetched"),
            "retrieval_agents_allowed": [a for a in RETRIEVAL_AGENTS
                                         if verdicts.get(a, {}).get("allowed", True)],
            "sitemap_urls": sum(d.get("urls", 0) for d in good_docs),
            "pages_fetched": len(pages), "pages_ok": len(html_pages),
            "median_response_ms": int(statistics.median(timings)) if timings else None,
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
