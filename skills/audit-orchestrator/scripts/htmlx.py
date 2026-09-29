"""Stdlib-only HTML extractor.

Produces a stable, JSON-serialisable "extract" per page. Every analysis skill in
this marketplace reads these extracts instead of re-parsing HTML, so parsing
happens exactly once per page and every check sees identical input.

No third-party dependencies by design: the marketplace must run wherever a
plain Python 3 interpreter exists.
"""

import json
import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse, urlsplit

# Tags whose text content is never visible page copy.
INVISIBLE = {"script", "style", "noscript", "template", "svg", "head", "iframe"}
# Tags that hold chrome rather than the page's own answer content.
CHROME = {"nav", "header", "footer", "aside"}
BLOCK = {
    "p", "div", "section", "article", "main", "li", "tr", "br", "h1", "h2",
    "h3", "h4", "h5", "h6", "td", "th", "blockquote", "pre", "figcaption",
}

CONSENT_HINTS = (
    "cookiebot", "onetrust", "cookieconsent", "cookie-consent", "usercentrics",
    "trustarc", "quantcast", "didomi", "termly", "iubenda", "klaro", "osano",
    "cookieyes", "complianz", "borlabs",
)
OVERLAY_HINTS = (
    "modal", "popup", "pop-up", "overlay", "newsletter", "lightbox", "interstitial",
    "subscribe-", "exit-intent", "paywall", "gdpr", "cookie-banner", "cookie-notice",
)
SPA_ROOT_IDS = {"root", "app", "__next", "__nuxt", "___gatsby", "svelte", "q-app", "main-app"}
FRAMEWORK_HINTS = (
    "/_next/", "/_nuxt/", "webpack", "react", "vue.", "angular", "svelte",
    "ember", "polyfills", "runtime.", "main.bundle", "chunk-", "remix",
)


def _norm_ws(text):
    return re.sub(r"[ \t\r\f\v]+", " ", text).strip()


class Extractor(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.base_href = base_url
        self.stack = []
        self._invisible_depth = 0
        self._chrome_depth = 0
        self._main_depth = 0
        self._capture = None          # buffer name for text currently being captured
        self._buf = []

        self.title = ""
        self.lang = ""
        self.metas = {}
        self.og = {}
        self.twitter = {}
        self.links_rel = []           # <link rel=...>
        self.headings = []            # [{level, text}]
        self.links = []               # [{href, text, rel, nofollow}]
        self.images = []              # [{src, alt, has_alt, loading, dims}]
        self.scripts = []             # [{src, type, inline_len, module}]
        self.jsonld = []              # raw strings
        self.microdata_types = []
        self.rdfa_types = []
        self.iframes = []             # [{src, title}]
        self.forms = 0
        self.inputs = []              # [{type, name, has_label_hint}]
        self.buttons = []             # button/CTA text
        self.text_parts = []
        self.main_text_parts = []
        self.tag_counts = {}
        self.has_main = False
        self.has_article = False
        self.has_nav = False
        self.has_h1 = False
        self.spa_roots = []
        self.consent_hits = set()
        self.overlay_hits = set()
        self.time_tags = []
        self.tables = 0
        self.lists = 0
        self.preloaded_state = False
        self.inline_style_fixed_full = 0
        self.details_blocks = 0

    # -- helpers -------------------------------------------------------
    def _abs(self, href):
        if not href:
            return ""
        href = href.strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
            return href
        try:
            return urljoin(self.base_href, href)
        except ValueError:
            return href

    def _class_id_blob(self, attrs):
        return " ".join(
            v for k, v in attrs.items()
            if k in ("class", "id", "data-testid", "aria-label", "role") and v
        ).lower()

    # -- parser hooks --------------------------------------------------
    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        self.tag_counts[tag] = self.tag_counts.get(tag, 0) + 1
        blob = self._class_id_blob(a)
        for hint in OVERLAY_HINTS:
            if hint in blob:
                self.overlay_hits.add(hint)
        style = a.get("style", "").lower().replace(" ", "")
        if "position:fixed" in style and ("width:100" in style or "inset:0" in style or "height:100" in style):
            self.inline_style_fixed_full += 1

        # An icon link is often named by an aria-label on a child element (or by
        # an <svg><title>, which the capture buffer already picks up).
        if self._capture and self._capture.startswith("a:") and a.get("aria-label"):
            self._buf.append(" " + a["aria-label"])

        if tag in INVISIBLE:
            self._invisible_depth += 1
        if tag in CHROME:
            self._chrome_depth += 1
        if tag in ("main", "article"):
            self._main_depth += 1

        if tag == "base" and a.get("href"):
            self.base_href = urljoin(self.base_url, a["href"])
        elif tag == "html":
            self.lang = a.get("lang", "")
        elif tag == "title":
            self._capture, self._buf = "title", []
        elif tag == "meta":
            name = (a.get("name") or a.get("property") or a.get("http-equiv") or "").lower()
            content = a.get("content", "")
            if name:
                if name.startswith("og:"):
                    self.og[name] = content
                elif name.startswith("twitter:"):
                    self.twitter[name] = content
                else:
                    self.metas.setdefault(name, content)
            if a.get("charset"):
                self.metas.setdefault("charset", a["charset"])
        elif tag == "link":
            rel = (a.get("rel") or "").lower()
            self.links_rel.append({
                "rel": rel, "href": self._abs(a.get("href")),
                "type": a.get("type", ""), "hreflang": a.get("hreflang", ""),
                "as": a.get("as", ""), "media": a.get("media", ""),
            })
        elif tag == "script":
            src = a.get("src", "")
            stype = (a.get("type") or "").lower()
            self.scripts.append({
                "src": self._abs(src), "raw_src": src, "type": stype,
                "module": a.get("type", "") == "module",
                "async": "async" in a, "defer": "defer" in a,
            })
            low = (src or "").lower() + " " + blob
            for hint in CONSENT_HINTS:
                if hint in low:
                    self.consent_hits.add(hint)
            if "ld+json" in stype:
                self._capture, self._buf = "jsonld", []
                self._invisible_depth -= 1  # capture JSON-LD text despite <script>
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            if tag == "h1":
                self.has_h1 = True
            self._capture, self._buf = "heading:" + tag, []
        elif tag == "a":
            self._capture, self._buf = "a:" + json.dumps({
                "href": self._abs(a.get("href")), "raw_href": a.get("href", ""),
                "rel": (a.get("rel") or "").lower(),
                "target": a.get("target", ""),
                "aria_label": a.get("aria-label", "") or a.get("title", ""),
            }), []
        elif tag == "img":
            # An icon link's accessible name often lives in a nested img's alt.
            if self._capture and self._capture.startswith("a:") and a.get("alt"):
                self._buf.append(" " + a["alt"])
            self.images.append({
                "src": self._abs(a.get("src") or a.get("data-src")),
                "alt": a.get("alt", ""), "has_alt": "alt" in a,
                "loading": a.get("loading", ""),
                "width": a.get("width", ""), "height": a.get("height", ""),
                "srcset": bool(a.get("srcset")),
                "in_chrome": self._chrome_depth > 0,
            })
        elif tag == "iframe":
            self.iframes.append({
                "src": self._abs(a.get("src") or a.get("data-src")),
                "title": a.get("title", ""), "in_main": self._main_depth > 0,
                "loading": a.get("loading", ""),
            })
        elif tag == "form":
            self.forms += 1
        elif tag in ("input", "select", "textarea"):
            self.inputs.append({
                "tag": tag, "type": a.get("type", "text"), "name": a.get("name", ""),
                "id": a.get("id", ""), "aria_label": a.get("aria-label", ""),
                "placeholder": a.get("placeholder", ""),
                "labelledby": a.get("aria-labelledby", ""),
            })
        elif tag == "button":
            self._capture, self._buf = "button", []
        elif tag == "time":
            self.time_tags.append({"datetime": a.get("datetime", "")})
        elif tag == "table":
            self.tables += 1
        elif tag in ("ul", "ol"):
            self.lists += 1
        elif tag == "details":
            self.details_blocks += 1
        elif tag == "nav":
            self.has_nav = True

        if tag == "main":
            self.has_main = True
        if tag == "article":
            self.has_article = True

        itemtype = a.get("itemtype")
        if itemtype:
            self.microdata_types.append(itemtype)
        typeof = a.get("typeof")
        if typeof:
            self.rdfa_types.append(typeof)

        el_id = a.get("id", "").lower()
        if el_id in SPA_ROOT_IDS or a.get("data-reactroot") is not None:
            self.spa_roots.append(el_id or "data-reactroot")

        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        # void elements: undo the depth bookkeeping the start handler applied
        if tag in INVISIBLE:
            self._invisible_depth -= 1
        if tag in CHROME:
            self._chrome_depth -= 1
        if tag in ("main", "article"):
            self._main_depth -= 1
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        # Only end the capture if this void element is the one that opened it;
        # a nested <img/> or <br/> must not terminate the enclosing <a>.
        if tag in ("a", "button", "h1", "h2", "h3", "h4", "h5", "h6"):
            if self._capture and self._capture.startswith(("a:", "heading:", "button")):
                self._capture = None

    def handle_endtag(self, tag):
        cap, self._capture = self._capture, None
        buf = self._buf
        text = _norm_ws("".join(buf))
        self._buf = []
        if cap:
            if cap == "title" and tag == "title":
                self.title = text
            elif cap == "jsonld" and tag == "script":
                self.jsonld.append(text)
                self._invisible_depth += 1  # restore the balance taken on start
            elif cap.startswith("heading:") and tag == cap.split(":", 1)[1]:
                self.headings.append({"level": int(tag[1]), "text": text[:300],
                                      "in_chrome": self._chrome_depth > 0})
            elif cap.startswith("a:") and tag == "a":
                meta = json.loads(cap[2:])
                meta["text"] = text[:200]
                meta["nofollow"] = "nofollow" in meta.get("rel", "")
                self.links.append(meta)
            elif cap == "button" and tag == "button":
                if text:
                    self.buttons.append(text[:120])
            else:
                # A nested tag closed inside the capture (e.g. </span> inside an
                # <a>). Keep capturing AND keep the text accumulated so far —
                # dropping it here empties the accessible name of every link,
                # heading and button whose text sits in a child element.
                self._capture, self._buf = cap, buf

        if tag in INVISIBLE:
            self._invisible_depth = max(0, self._invisible_depth - 1)
        if tag in CHROME:
            self._chrome_depth = max(0, self._chrome_depth - 1)
        if tag in ("main", "article"):
            self._main_depth = max(0, self._main_depth - 1)
        sep = "\n" if tag in BLOCK else " "
        self.text_parts.append(sep)
        if self._main_depth > 0:
            self.main_text_parts.append(sep)
        while self.stack:
            if self.stack.pop() == tag:
                break

    def handle_data(self, data):
        if self._capture:
            self._buf.append(data)
        if self._invisible_depth > 0:
            if self._capture != "jsonld" and "__NEXT_DATA__" in data[:200]:
                self.preloaded_state = True
            return
        if not data.strip():
            return
        self.text_parts.append(data)
        if self._main_depth > 0:
            self.main_text_parts.append(data)


def _clean_text(parts):
    raw = "".join(parts)
    lines = [_norm_ws(ln) for ln in raw.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _words(text):
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9'’\-]*", text)


def extract(html, url):
    """Parse `html` fetched from `url` into the analysis extract dict."""
    p = Extractor(url)
    try:
        p.feed(html)
        p.close()
    except Exception:  # malformed markup must not abort an audit
        pass

    text = _clean_text(p.text_parts)
    main_text = _clean_text(p.main_text_parts) or ""
    words = _words(text)
    # Sentences are measured per line: headings, buttons and nav fragments carry no
    # terminator and would otherwise be glued into one enormous "sentence".
    sentences = []
    for line in text.split("\n"):
        if re.search(r"[.!?]", line):
            sentences.extend(x for x in re.split(r"(?<=[.!?])\s+", line) if len(x.split()) > 2)
    paragraphs = [ln for ln in text.split("\n") if len(ln.split()) > 8]

    host = urlsplit(url).netloc.lower()
    reg = _registrable(host)
    internal, external = [], []
    for ln in p.links:
        href = ln.get("href", "")
        if not href or href.startswith(("javascript:", "mailto:", "tel:", "#", "data:")):
            continue
        h = urlsplit(href).netloc.lower()
        if not h or _registrable(h) == reg:
            internal.append(ln)
        else:
            external.append(ln)

    canonical = ""
    alternates, feeds, hreflangs, preloads = [], [], [], []
    for lr in p.links_rel:
        rel = lr["rel"]
        if "canonical" in rel and not canonical:
            canonical = lr["href"]
        if "alternate" in rel:
            alternates.append(lr)
            if "rss" in lr.get("type", "") or "atom" in lr.get("type", ""):
                feeds.append(lr["href"])
            if lr.get("hreflang"):
                hreflangs.append(lr["hreflang"])
        if rel in ("preload", "modulepreload", "prefetch"):
            preloads.append(lr)

    ext_scripts = [s for s in p.scripts if s["src"] and "ld+json" not in s["type"]]
    inline_script_count = len([s for s in p.scripts if not s["src"] and "ld+json" not in s["type"]])
    framework = sorted({h for s in ext_scripts for h in FRAMEWORK_HINTS if h in s["src"].lower()})

    stylesheets = [lr["href"] for lr in p.links_rel if "stylesheet" in lr["rel"]]

    return {
        "url": url,
        "title": p.title,
        "lang": p.lang,
        "meta": p.metas,
        "og": p.og,
        "twitter": p.twitter,
        "canonical": canonical,
        "alternates": alternates,
        "hreflangs": sorted(set(hreflangs)),
        "feeds": feeds,
        "headings": p.headings,
        "h1s": [h["text"] for h in p.headings if h["level"] == 1],
        "links_internal": internal,
        "links_external": external,
        "images": p.images,
        "iframes": p.iframes,
        "scripts_external": [s["src"] for s in ext_scripts],
        "scripts_inline_count": inline_script_count,
        "scripts_blocking": len([s for s in ext_scripts if not s["async"] and not s["defer"]]),
        "stylesheets": stylesheets,
        "preloads": len(preloads),
        "framework_hints": framework,
        "spa_roots": sorted(set(p.spa_roots)),
        "preloaded_state": p.preloaded_state,
        "jsonld_raw": p.jsonld,
        "microdata_types": p.microdata_types,
        "rdfa_types": p.rdfa_types,
        "forms": p.forms,
        "inputs": p.inputs,
        "buttons": p.buttons,
        "tables": p.tables,
        "lists": p.lists,
        "details_blocks": p.details_blocks,
        "time_tags": p.time_tags,
        "consent_vendors": sorted(p.consent_hits),
        "overlay_hints": sorted(p.overlay_hits),
        "fixed_fullscreen_inline": p.inline_style_fixed_full,
        "has_main": p.has_main,
        "has_article": p.has_article,
        "has_nav": p.has_nav,
        "has_h1": p.has_h1,
        "tag_counts": p.tag_counts,
        "text": text,
        "main_text": main_text,
        "text_head": text[:4000],
        "word_count": len(words),
        "main_word_count": len(_words(main_text)),
        "sentence_count": len(sentences),
        "avg_sentence_words": round(sum(len(s.split()) for s in sentences) / len(sentences), 1) if sentences else 0.0,
        "long_sentences": len([s for s in sentences if len(s.split()) > 34]),
        "paragraph_count": len(paragraphs),
        "long_paragraphs": len([q for q in paragraphs if len(q.split()) > 120]),
        "html_bytes": len(html.encode("utf-8", "ignore")),
        "text_ratio": round(len(text) / max(1, len(html)), 4),
    }


def _registrable(host):
    """Approximate registrable domain: last two labels, or three for common ccSLDs."""
    host = (host or "").split(":")[0].lower().lstrip(".")
    parts = [x for x in host.split(".") if x]
    if len(parts) <= 2:
        return ".".join(parts)
    two = ".".join(parts[-2:])
    ccslds = {
        "co.uk", "org.uk", "ac.uk", "gov.uk", "com.au", "net.au", "org.au",
        "co.nz", "co.jp", "co.in", "net.in", "org.in", "co.za", "com.br",
        "com.sg", "com.hk", "com.mx", "co.kr", "com.tr", "com.cn",
    }
    if two in ccslds and len(parts) >= 3:
        return ".".join(parts[-3:])
    return two


def registrable(host_or_url):
    if "//" in host_or_url:
        host_or_url = urlparse(host_or_url).netloc
    return _registrable(host_or_url)


def strip_tags(html):
    """Very small helper for raw-HTML text length comparisons."""
    html = re.sub(r"(?is)<(script|style|noscript|template|svg)[^>]*>.*?</\1>", " ", html)
    return _norm_ws(unescape(re.sub(r"(?s)<[^>]+>", " ", html)))
