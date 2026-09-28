#!/usr/bin/env python3
"""Build the crawl bundle every analysis skill in this marketplace reads.

Read-only and polite by construction:
  * obeys robots.txt for its own user-agent, and never retries a disallowed URL
  * one request at a time, with a configurable delay (default 1.0s)
  * GET only; never submits forms, never follows logout/cart/auth links
  * hard caps on page count, page size and total wall-clock time

Usage:
    python3 crawl.py https://example.com --out ./bundle [--max-pages 30]

Writes:  bundle/meta.json, robots.json, sitemap.json, index.json,
         pages/<id>.html, pages/<id>.extract.json, pages/<id>.rendered.extract.json
"""

import argparse
import datetime as dt
import gzip
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit, urlunsplit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import htmlx  # noqa: E402

UA = ("BrandAIReadinessAudit/1.0 (+read-only site audit; obeys robots.txt)")
UA_BROWSER = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")
UA_PLAIN = "python-urllib/3"

# Retrieval agents fetch a page *at answer time* to cite it. Blocking these
# removes the site from live AI answers. Training crawlers are listed
# separately because blocking them is a legitimate policy choice, not a defect.
AI_AGENTS_RETRIEVAL = [
    "OAI-SearchBot", "ChatGPT-User", "Claude-User", "Claude-SearchBot",
    "PerplexityBot", "Perplexity-User", "Google-Extended", "Bingbot",
    "Googlebot", "Amazonbot", "DuckAssistBot", "MistralAI-User",
]
AI_AGENTS_TRAINING = [
    "GPTBot", "ClaudeBot", "anthropic-ai", "CCBot", "Applebot-Extended",
    "Bytespider", "meta-externalagent", "FacebookBot", "cohere-ai",
    "Diffbot", "omgili", "Timpibot", "AI2Bot",
]

SKIP_EXT = re.compile(
    r"\.(zip|gz|tgz|rar|7z|exe|dmg|pkg|msi|apk|mp4|mov|avi|mkv|mp3|wav|ogg|"
    r"woff2?|ttf|eot|ico|css|js|json|xml|rss|atom|svg|png|jpe?g|gif|webp|avif|bmp|tiff?)$",
    re.I)
DOC_EXT = re.compile(r"\.(pdf|docx?|pptx?|xlsx?|csv)(\?|$)", re.I)
# Never touch anything that could mutate state or enter an authenticated area.
UNSAFE_PATH = re.compile(
    r"(logout|signout|sign-out|log-out|/cart|/checkout|/basket|add-to-cart|"
    r"/admin|/wp-admin|/account|/dashboard|/billing|delete|remove|/api/|"
    r"unsubscribe|/print/|\?add|action=|/login|/signin|/sign-in|/register|/signup)",
    re.I)

PAGE_TYPE_RULES = [
    # Legal first: /legal/pricingpolicy is a contract, not a pricing page, and
    # holding it to a pricing page's expectations produces a false positive.
    ("legal",      r"/(legal|privacy|terms|cookie|gdpr|imprint|impressum|accessibility|"
                   r"policies|policy|compliance|dpa|sla|licen[cs]e)"),
    ("pricing",    r"/(pricing|plans|prices|subscribe|tarif)"),
    ("product",    r"/(product|products|shop|store|item|sku)/[^/]+"),
    ("category",   r"/(category|categories|collections?|shop|catalog|browse)(/|$)"),
    ("blog_post",  r"/(blog|news|insights|articles?|stories|press|resources)/[^/]+/$"),
    ("blog_index", r"/(blog|news|insights|articles?|stories|press|updates)/$"),
    ("docs",       r"/(docs?|documentation|developers?|api|reference|guides?|help|support|kb|knowledge)"),
    ("faq",        r"/(faq|faqs|questions|q-and-a)"),
    ("about",      r"/(about|about-us|company|team|who-we-are|our-story|mission)"),
    ("contact",    r"/(contact|contact-us|get-in-touch|locations?|stores?|find-us)"),
    ("careers",    r"/(careers?|jobs|hiring|work-with-us)"),
    ("case_study", r"/(case-stud|customers?|success|testimonial|portfolio)"),
]
# Types worth spending crawl budget on.
TYPE_QUOTA = {
    "home": 1, "pricing": 2, "product": 4, "about": 1, "contact": 1,
    "docs": 3, "blog_post": 3, "category": 2, "faq": 1, "case_study": 2,
    "blog_index": 1, "careers": 1, "legal": 1, "other": 5,
}
MAX_BYTES = 3_000_000


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
class _Redirects(urllib.request.HTTPRedirectHandler):
    def __init__(self):
        self.chain = []

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        self.chain.append({"from": req.full_url, "to": newurl, "status": code})
        if len(self.chain) > 8:
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _headers(resp):
    return {k.lower(): v for k, v in resp.headers.items()}


def _read(resp):
    raw = resp.read(MAX_BYTES)
    if (resp.headers.get("Content-Encoding") or "").lower() == "gzip":
        try:
            raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read(MAX_BYTES)
        except Exception:
            pass
    ctype = resp.headers.get("Content-Type", "")
    m = re.search(r"charset=([\w\-]+)", ctype, re.I)
    enc = m.group(1) if m else None
    if not enc:
        m2 = re.search(rb'charset=["\']?([\w\-]+)', raw[:4096], re.I)
        enc = m2.group(1).decode("ascii", "ignore") if m2 else "utf-8"
    try:
        text = raw.decode(enc, "replace")
    except (LookupError, UnicodeDecodeError):
        text = raw.decode("utf-8", "replace")
    return raw, text


def _short(url):
    """Path-only form of a URL, for a progress line that must fit a terminal."""
    parts = urlsplit(url)
    return (parts.path or "/") + (("?" + parts.query) if parts.query else "")


class Progress:
    """Crawl progress on stderr, so stdout stays parseable JSON.

    On a terminal the page counter rewrites one line; when redirected it emits
    plain appended lines, because \r in a log file is noise.
    """

    def __init__(self, enabled=True, stream=None):
        self.stream = stream or sys.stderr
        self.enabled = enabled and not self.stream.closed
        self.tty = self.enabled and self.stream.isatty()
        self._live = False

    def stage(self, msg):
        if not self.enabled:
            return
        self._endline()
        self.stream.write("  %s\n" % msg)
        self.stream.flush()

    def step(self, done, total, detail=""):
        if not self.enabled:
            return
        detail = detail if len(detail) <= 58 else detail[:55] + "..."
        line = "  [%d/%d] %s" % (done, total, detail)
        if self.tty:
            self.stream.write("\r\033[2K" + line)
            self._live = True
        else:
            self.stream.write(line + "\n")
        self.stream.flush()

    def _endline(self):
        if self._live:
            self.stream.write("\n")
            self._live = False

    def done(self, msg=""):
        if not self.enabled:
            return
        self._endline()
        if msg:
            self.stream.write("  %s\n" % msg)
        self.stream.flush()


def fetch(url, ua=UA, timeout=15):
    """Return a response record. Never raises for HTTP or network errors."""
    rec = {"url": url, "final_url": url, "status": 0, "headers": {}, "body": "",
           "bytes": 0, "elapsed_ms": 0, "redirects": [], "error": "",
           "content_type": "", "truncated": False}
    handler = _Redirects()
    opener = urllib.request.build_opener(handler)
    req = urllib.request.Request(url, method="GET", headers={
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip",
        "Connection": "close",
    })
    t0 = time.time()
    try:
        resp = opener.open(req, timeout=timeout)
        raw, body = _read(resp)
        rec.update(status=resp.status, final_url=resp.url, body=body, bytes=len(raw),
                   headers=_headers(resp), truncated=len(raw) >= MAX_BYTES)
    except urllib.error.HTTPError as e:
        try:
            raw, body = _read(e)
        except Exception:
            raw, body = b"", ""
        rec.update(status=e.code, final_url=e.url or url, body=body, bytes=len(raw),
                   headers=_headers(e))
    except Exception as e:
        rec["error"] = "%s: %s" % (type(e).__name__, e)
    rec["elapsed_ms"] = int((time.time() - t0) * 1000)
    rec["redirects"] = handler.chain
    rec["content_type"] = rec["headers"].get("content-type", "")
    return rec


# --------------------------------------------------------------------------
# robots.txt
# --------------------------------------------------------------------------
def parse_robots(text):
    """Parse into {agent: {'allow': [...], 'disallow': [...], 'crawl_delay': x}}."""
    groups, sitemaps, current = {}, [], []
    pending_agent = True
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        field, _, value = line.partition(":")
        field, value = field.strip().lower(), value.strip()
        if field == "user-agent":
            if not pending_agent:
                current = []
            pending_agent = True
            agent = value.lower()
            current.append(agent)
            groups.setdefault(agent, {"allow": [], "disallow": [], "crawl_delay": None})
        elif field == "sitemap":
            sitemaps.append(value)
        elif field in ("allow", "disallow") and current:
            pending_agent = False
            for a in current:
                groups[a][field].append(value)
        elif field == "crawl-delay" and current:
            pending_agent = False
            for a in current:
                try:
                    groups[a]["crawl_delay"] = float(value)
                except ValueError:
                    pass
    return groups, sitemaps


def _rule_match(path, pattern):
    """robots.txt path matching with * and $ support. Returns match length or None."""
    if pattern == "":
        return None
    rx = re.escape(pattern).replace(r"\*", ".*")
    if rx.endswith(r"\$"):
        rx = rx[:-2] + "$"
    try:
        m = re.match(rx, path)
    except re.error:
        return None
    return len(pattern) if m else None


def robots_allows(groups, agent, path):
    """Return (allowed, matched_rule). Longest match wins; Allow breaks ties."""
    agent_l = agent.lower()
    grp = None
    for name in groups:
        if name and name != "*" and name in agent_l:
            grp = groups[name]
            break
    if grp is None:
        grp = groups.get("*")
    if grp is None:
        return True, "no matching group"
    best = (0, True, "default allow (no matching rule)")
    for kind in ("allow", "disallow"):
        for pat in grp[kind]:
            n = _rule_match(path, pat)
            if n is None:
                continue
            is_allow = kind == "allow"
            if n > best[0] or (n == best[0] and is_allow and not best[1]):
                best = (n, is_allow, "%s: %s" % (kind.title(), pat))
    return best[1], best[2]


# --------------------------------------------------------------------------
# sitemaps
# --------------------------------------------------------------------------
def parse_sitemap(text):
    is_index = "<sitemapindex" in text.lower()
    blocks = re.findall(r"(?is)<(?:url|sitemap)>(.*?)</(?:url|sitemap)>", text)
    urls = []
    for b in blocks:
        def g(tag, blk=b):
            m = re.search(r"(?is)<%s>\s*(.*?)\s*</%s>" % (tag, tag), blk)
            return m.group(1).strip() if m else ""
        if g("loc"):
            urls.append({"loc": g("loc"), "lastmod": g("lastmod"),
                         "changefreq": g("changefreq"), "priority": g("priority")})
    if not urls:
        urls = [{"loc": m.group(1).strip(), "lastmod": "", "changefreq": "", "priority": ""}
                for m in re.finditer(r"(?is)<loc>\s*(.*?)\s*</loc>", text)]
    return urls, is_index


# --------------------------------------------------------------------------
# crawl
# --------------------------------------------------------------------------
def normalise(url):
    try:
        s = urlsplit(url)
    except ValueError:
        return ""
    if s.scheme not in ("http", "https"):
        return ""
    path = re.sub(r"/{2,}", "/", s.path) or "/"
    query = "&".join(q for q in s.query.split("&")
                     if q and not re.match(r"(utm_|fbclid|gclid|mc_|_ga)", q, re.I))
    return urlunsplit((s.scheme, s.netloc.lower(), path, query, ""))


def page_type(url, extract=None):
    path = urlsplit(url).path.lower()
    if path.rstrip("/") == "":
        return "home"
    probe = path if path.endswith("/") else path + "/"
    for name, rx in PAGE_TYPE_RULES:
        if re.search(rx, probe):
            return name
    if extract:
        legal_title = re.search(
            r"\b(agreement|terms of (?:service|use)|privacy policy|cookie policy|"
            r"acceptable use|licen[cs]e agreement|data processing|disclaimer)\b",
            (extract.get("title", "") or "") + " " + " ".join(extract.get("h1s", [])), re.I)
        if legal_title:
            return "legal"
        types = [t.lower() for t in extract.get("jsonld_types", [])]
        if "product" in types:
            return "product"
        if {"article", "blogposting", "newsarticle"} & set(types):
            return "blog_post"
    return "other"


def _jsonld_types(blocks):
    types = []
    for raw in blocks:
        try:
            data = json.loads(raw)
        except Exception:
            continue
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                t = node.get("@type")
                if isinstance(t, str):
                    types.append(t)
                elif isinstance(t, list):
                    types.extend(x for x in t if isinstance(x, str))
                stack.extend(v for v in node.values() if isinstance(v, (dict, list)))
            elif isinstance(node, list):
                stack.extend(node)
    return types


def try_render(pages, out, timeout=15):
    """Capture the post-JavaScript DOM if a headless browser is available.

    Absence is expected and non-fatal: the render-extractability skill has a
    documented static fallback. Nothing is ever installed.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:
        return {"available": False, "reason": "playwright not installed", "pages": {}}
    result = {}
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            ctx = browser.new_context(user_agent=UA_BROWSER,
                                      viewport={"width": 1280, "height": 900})
            for p in pages:
                try:
                    pg = ctx.new_page()
                    pg.goto(p["final_url"] or p["url"], timeout=timeout * 1000,
                            wait_until="networkidle")
                    html = pg.content()
                    with open(os.path.join(out, "pages", p["id"] + ".rendered.html"), "w", encoding="utf-8", errors="replace") as fh:
                        fh.write(html)
                    ex = htmlx.extract(html, p["final_url"] or p["url"])
                    ex["jsonld_types"] = _jsonld_types(ex["jsonld_raw"])
                    with open(os.path.join(out, "pages", p["id"] + ".rendered.extract.json"), "w", encoding="utf-8") as fh:
                        json.dump(ex, fh)
                    result[p["id"]] = {"ok": True, "word_count": ex["word_count"],
                                       "jsonld_blocks": len(ex["jsonld_raw"]),
                                       "h1s": ex["h1s"], "title": ex["title"]}
                    pg.close()
                except Exception as e:
                    result[p["id"]] = {"ok": False, "error": str(e)[:200]}
            browser.close()
    except Exception as e:
        return {"available": False, "reason": "browser launch failed: %s" % str(e)[:120],
                "pages": result}
    return {"available": True, "reason": "playwright chromium", "pages": result}


def crawl(seed, out, max_pages=30, delay=1.0, timeout=15, budget_s=210, render="auto",
          progress=None):
    os.makedirs(os.path.join(out, "pages"), exist_ok=True)
    pr_ = progress or Progress(enabled=False)
    started = time.time()
    seed = normalise(seed if "//" in seed else "https://" + seed)
    if not seed:
        raise SystemExit("unusable seed URL")
    parts = urlsplit(seed)
    origin = "%s://%s" % (parts.scheme, parts.netloc)
    site = parts.netloc
    reg = htmlx.registrable(site)
    notes = []

    # -- robots ------------------------------------------------------------
    pr_.stage("robots.txt ...")
    r = fetch(urljoin(origin, "/robots.txt"), timeout=timeout)
    served_html = "text/html" in r["content_type"].lower()
    robots_ok = r["status"] == 200 and not served_html
    groups, sitemaps = parse_robots(r["body"]) if robots_ok else ({}, [])
    cd_group = groups.get("brandaireadinessaudit") or groups.get("*") or {}
    crawl_delay = cd_group.get("crawl_delay")
    if crawl_delay:
        delay = max(delay, min(crawl_delay, 5.0))
    robots = {
        "url": r["url"], "status": r["status"], "fetched": robots_ok,
        "served_html": served_html, "raw": r["body"][:20000], "groups": groups,
        "sitemaps": sitemaps, "crawl_delay": crawl_delay, "error": r["error"],
        "agent_verdicts": {
            a: dict(zip(("allowed", "rule"), robots_allows(groups, a, "/")))
            for a in AI_AGENTS_RETRIEVAL + AI_AGENTS_TRAINING
        },
    }
    with open(os.path.join(out, "robots.json"), "w", encoding="utf-8") as fh:
        json.dump(robots, fh, indent=1)

    def allowed(u):
        if not robots_ok or not groups:
            return True
        return robots_allows(groups, UA, urlsplit(u).path or "/")[0]

    # -- sitemaps ----------------------------------------------------------
    pr_.stage("sitemaps ...")
    sm_sources = list(dict.fromkeys(sitemaps + [urljoin(origin, "/sitemap.xml"),
                                                urljoin(origin, "/sitemap_index.xml")]))
    sm = {"declared_in_robots": sitemaps, "documents": [], "urls": [], "total_urls": 0}
    seen_sm = set()
    for su in sm_sources[:6]:
        if su in seen_sm or time.time() - started > budget_s * 0.35:
            continue
        seen_sm.add(su)
        rr = fetch(su, timeout=timeout)
        body = rr["body"]
        if rr["status"] != 200 or "<" not in body[:2000]:
            sm["documents"].append({"url": su, "status": rr["status"], "ok": False,
                                    "urls": 0, "error": rr["error"]})
            time.sleep(delay)
            continue
        urls, is_index = parse_sitemap(body)
        sm["documents"].append({"url": su, "status": rr["status"], "ok": True,
                                "is_index": is_index, "urls": len(urls),
                                "with_lastmod": len([u for u in urls if u["lastmod"]])})
        if is_index:
            for child in urls[:4]:
                if child["loc"] in seen_sm:
                    continue
                seen_sm.add(child["loc"])
                cr = fetch(child["loc"], timeout=timeout)
                if cr["status"] == 200:
                    curls, _ = parse_sitemap(cr["body"])
                    sm["urls"].extend(curls[:400])
                    sm["documents"].append(
                        {"url": child["loc"], "status": 200, "ok": True, "is_index": False,
                         "urls": len(curls),
                         "with_lastmod": len([u for u in curls if u["lastmod"]])})
                time.sleep(delay)
        else:
            sm["urls"].extend(urls[:800])
        time.sleep(delay)
    sm["total_urls"] = len(sm["urls"])
    with open(os.path.join(out, "sitemap.json"), "w", encoding="utf-8") as fh:
        json.dump(sm, fh, indent=1)

    # -- probes ------------------------------------------------------------
    pr_.stage("probes: 3 user-agents, invalid URL, llms.txt ...")
    probes = {"user_agent_matrix": {}}
    for label, agent in (("audit", UA), ("browser", UA_BROWSER), ("plain", UA_PLAIN)):
        pr = fetch(seed, ua=agent, timeout=timeout)
        probes["user_agent_matrix"][label] = {
            "status": pr["status"], "bytes": pr["bytes"], "error": pr["error"],
            "final_url": pr["final_url"], "elapsed_ms": pr["elapsed_ms"],
            "server": pr["headers"].get("server", ""),
            "cf_mitigated": pr["headers"].get("cf-mitigated", ""),
            "text_len": len(htmlx.strip_tags(pr["body"])),
        }
        time.sleep(delay)

    nf = fetch(urljoin(origin, "/brand-ai-readiness-probe-%d" % int(time.time())), timeout=timeout)
    probes["not_found"] = {"status": nf["status"], "bytes": nf["bytes"],
                           "text_len": len(htmlx.strip_tags(nf["body"])),
                           "final_url": nf["final_url"],
                           "redirected_to_home": normalise(nf["final_url"]) == normalise(seed)}
    time.sleep(delay)
    lt = fetch(urljoin(origin, "/llms.txt"), timeout=timeout)
    probes["llms_txt"] = {"status": lt["status"], "bytes": lt["bytes"],
                          "is_html": "text/html" in lt["content_type"].lower()}
    time.sleep(delay)
    probes["http_to_https"] = None
    if seed.startswith("https://"):
        hp = fetch("http://%s/" % parts.netloc, timeout=timeout)
        probes["http_to_https"] = {
            "status": hp["status"], "final_https": hp["final_url"].startswith("https://"),
            "hsts": bool(hp["headers"].get("strict-transport-security"))}
        time.sleep(delay)

    # -- BFS ---------------------------------------------------------------
    queue = [(seed, 0)]
    for u in sm["urls"][:200]:
        n = normalise(u["loc"])
        if n and htmlx.registrable(urlsplit(n).netloc) == reg:
            queue.append((n, 1))
    seen, pages, type_count, skipped, docs_linked = set(), [], {}, [], []

    pr_.stage("crawling pages (max %d, %.1fs apart) ..." % (max_pages, delay))
    while queue and len(pages) < max_pages:
        if time.time() - started > budget_s:
            notes.append("crawl time budget reached after %d pages" % len(pages))
            break
        url, depth = queue.pop(0)
        url = normalise(url)
        if not url or url in seen:
            continue
        if htmlx.registrable(urlsplit(url).netloc) != reg:
            continue
        if UNSAFE_PATH.search(url) or SKIP_EXT.search(urlsplit(url).path):
            continue
        if not allowed(url):
            skipped.append({"url": url, "reason": "disallowed by robots.txt for the audit agent"})
            seen.add(url)
            continue
        ptype = page_type(url)
        if len(pages) > 3 and type_count.get(ptype, 0) >= TYPE_QUOTA.get(ptype, 2):
            continue
        seen.add(url)

        rec = fetch(url, timeout=timeout)
        if rec["status"] != 200 and url == seed:
            # The homepage anchors brand identification, footer links and several
            # sitewide checks. One transient failure there degrades the whole
            # audit, so it alone is retried with a longer timeout.
            time.sleep(delay)
            retry = fetch(url, timeout=timeout * 2)
            if retry["status"] == 200:
                rec = retry
                notes.append("homepage required a retry with a longer timeout")
        time.sleep(delay)
        # A redirect target must not be crawled again under its own URL, or an
        # apex→www hop costs two pages of budget and reports one page twice.
        if rec["final_url"]:
            seen.add(normalise(rec["final_url"]))
        pid = "p%03d" % len(pages)
        is_html = ("html" in rec["content_type"].lower()
                   or (not rec["content_type"] and "<html" in rec["body"][:2000].lower()))
        page = {
            "id": pid, "url": url, "final_url": rec["final_url"], "status": rec["status"],
            "depth": depth, "type": ptype, "bytes": rec["bytes"],
            "elapsed_ms": rec["elapsed_ms"], "content_type": rec["content_type"],
            "redirects": rec["redirects"], "error": rec["error"], "is_html": is_html,
            "headers": {k: v for k, v in rec["headers"].items() if k in (
                "content-type", "cache-control", "x-robots-tag", "content-encoding",
                "server", "vary", "last-modified", "content-security-policy")},
        }
        if is_html and rec["body"]:
            with open(os.path.join(out, "pages", pid + ".html"), "w", encoding="utf-8", errors="replace") as fh:
                fh.write(rec["body"])
            ex = htmlx.extract(rec["body"], rec["final_url"] or url)
            ex["jsonld_types"] = _jsonld_types(ex["jsonld_raw"])
            ex["raw_text_len"] = len(htmlx.strip_tags(rec["body"]))
            page["type"] = page_type(url, ex)
            with open(os.path.join(out, "pages", pid + ".extract.json"), "w", encoding="utf-8") as fh:
                json.dump(ex, fh)
            page.update(word_count=ex["word_count"], title=ex["title"],
                        h1_count=len(ex["h1s"]), jsonld_blocks=len(ex["jsonld_raw"]))
            for ln in ex["links_internal"]:
                nxt = normalise(ln["href"])
                if nxt and nxt not in seen and depth < 3:
                    if DOC_EXT.search(nxt):
                        docs_linked.append({"url": nxt, "text": ln["text"], "from": url})
                    else:
                        queue.append((nxt, depth + 1))
        type_count[page["type"]] = type_count.get(page["type"], 0) + 1
        pages.append(page)
        pr_.step(len(pages), max_pages, "%s %s" % (rec["status"], _short(url)))

    # -- optional rendered capture ----------------------------------------
    rendered = {"available": False, "reason": "rendering disabled (--render off)", "pages": {}}
    if render != "off":
        targets = [p for p in pages if p["is_html"] and p["status"] == 200]
        sample = _render_sample(targets)
        pr_.done("crawled %d page(s) in %ds" % (len(pages), int(time.time() - started)))
        pr_.stage("rendering %d page(s) with a headless browser ..." % len(sample))
        rendered = try_render(sample, out, timeout=timeout)
        if not rendered["available"]:
            pr_.stage("rendering unavailable: %s" % rendered["reason"])
    else:
        pr_.done("crawled %d page(s) in %ds" % (len(pages), int(time.time() - started)))

    meta = {
        "site": site, "registrable_domain": reg, "seed_url": seed, "origin": origin,
        "audited_at": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "crawler_user_agent": UA,
        "config": {"max_pages": max_pages, "delay_s": delay, "timeout_s": timeout,
                   "time_budget_s": budget_s, "render": render},
        "capabilities": {"network": any(p["status"] for p in pages),
                         "rendering": rendered["available"],
                         "render_note": rendered["reason"]},
        "probes": probes,
        "pages_crawled": len(pages),
        "pages_by_type": type_count,
        "skipped_by_robots": skipped,
        "linked_documents": docs_linked[:40],
        "elapsed_s": round(time.time() - started, 1),
        "notes": notes,
    }
    with open(os.path.join(out, "meta.json"), "w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1)
    with open(os.path.join(out, "index.json"), "w", encoding="utf-8") as fh:
        json.dump({"pages": pages, "rendered": rendered["pages"]}, fh, indent=1)
    return meta


def _render_sample(pages):
    """Render the homepage plus one page of each distinct type, up to 6."""
    picked, seen_types = [], set()
    for p in pages:
        if p["type"] in seen_types:
            continue
        seen_types.add(p["type"])
        picked.append(p)
        if len(picked) >= 6:
            break
    return picked


def main():
    ap = argparse.ArgumentParser(description="Build a read-only crawl bundle for the audit.")
    ap.add_argument("url")
    ap.add_argument("--out", default="./bundle")
    ap.add_argument("--max-pages", type=int, default=30)
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--timeout", type=int, default=15)
    ap.add_argument("--budget", type=int, default=210, help="wall-clock seconds for crawling")
    ap.add_argument("--render", choices=["auto", "off"], default="auto")
    ap.add_argument("--quiet", action="store_true", help="suppress progress on stderr")
    a = ap.parse_args()
    meta = crawl(a.url, a.out, a.max_pages, a.delay, a.timeout, a.budget, a.render,
                 progress=Progress(enabled=not a.quiet))
    print(json.dumps({k: meta[k] for k in
                      ("site", "audited_at", "pages_crawled", "pages_by_type",
                       "capabilities", "elapsed_s")}, indent=1))


if __name__ == "__main__":
    main()
