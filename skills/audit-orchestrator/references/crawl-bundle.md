# Crawl bundle contract

Written once by `scripts/crawl.py`, read by every analysis skill. Nothing else
in the marketplace makes network requests, which is what keeps the audit polite
(one request per URL), deterministic (every check sees identical bytes) and
inside the runtime budget (checks run against local JSON).

```
bundle/
  meta.json                      site, timing, capabilities, probes, crawl config
  robots.json                    raw text, parsed groups, per-agent verdicts
  sitemap.json                   documents tried, URLs found, lastmod coverage
  profile.json                   written by profile.py: site type, brand, signals
  index.json                     {"pages": [...], "rendered": {...}}
  pages/
    p000.html                    raw response body as served
    p000.extract.json            parsed extract (see below)
    p000.rendered.html           post-JavaScript DOM, only if a browser was available
    p000.rendered.extract.json   extract of the rendered DOM
```

## `meta.json`

| Field | Meaning |
|---|---|
| `site`, `origin`, `seed_url`, `registrable_domain` | Identity of what was audited |
| `audited_at` | UTC ISO-8601, used verbatim in the report |
| `capabilities.network` | Whether anything was fetched successfully |
| `capabilities.rendering`, `.render_note` | Whether a headless browser ran, and why not if it did not |
| `probes.user_agent_matrix` | Homepage fetched as browser / audit agent / plain client — the edge-blocking evidence |
| `probes.not_found` | Response to a deliberately invalid URL — the soft-404 evidence |
| `probes.llms_txt`, `probes.http_to_https` | Opportunity and transport probes |
| `pages_crawled`, `pages_by_type` | Crawl coverage, reported in the report's `scope` |
| `skipped_by_robots` | URLs deliberately not fetched, with the rule that disallowed them |
| `linked_documents` | PDF/Office links found, with the page that linked them |
| `notes` | Anything that degraded the crawl, e.g. a time budget being reached |

## `index.json` → `pages[]`

`id`, `url`, `final_url`, `status`, `depth`, `type`, `bytes`, `elapsed_ms`,
`content_type`, `redirects[]`, `error`, `is_html`, selected response `headers`,
and for HTML pages `word_count`, `title`, `h1_count`, `jsonld_blocks`.

`type` is one of: `home`, `pricing`, `product`, `category`, `blog_post`,
`blog_index`, `docs`, `faq`, `about`, `contact`, `legal`, `careers`,
`case_study`, `other`. Assigned from the URL path, then corrected using the
page's title and structured data — `/legal/pricingpolicy` is a legal document,
not a pricing page, and typing it correctly is what stops a pricing check firing
on a contract.

## `pages/<id>.extract.json`

Produced by `htmlx.py`, stdlib only. Fields used by the checks:

`title`, `lang`, `meta{}`, `og{}`, `twitter{}`, `canonical`, `alternates[]`,
`hreflangs[]`, `feeds[]`, `headings[]` (level, text, `in_chrome`), `h1s[]`,
`links_internal[]` / `links_external[]` (href, text, rel, `aria_label`,
`nofollow`), `images[]` (src, alt, `has_alt`, loading, width, height,
`in_chrome`), `iframes[]`, `scripts_external[]`, `scripts_inline_count`,
`scripts_blocking`, `stylesheets[]`, `framework_hints[]`, `spa_roots[]`,
`preloaded_state`, `jsonld_raw[]`, `jsonld_types[]`, `microdata_types[]`,
`rdfa_types[]`, `forms`, `inputs[]`, `buttons[]`, `tables`, `lists`,
`details_blocks`, `time_tags[]`, `consent_vendors[]`, `overlay_hints[]`,
`fixed_fullscreen_inline`, `has_main`, `has_article`, `has_nav`, `has_h1`,
`tag_counts{}`, `text`, `main_text`, `text_head`, `word_count`,
`main_word_count`, `sentence_count`, `avg_sentence_words`, `long_sentences`,
`paragraph_count`, `long_paragraphs`, `html_bytes`, `text_ratio`,
`raw_text_len`.

Two details worth knowing when writing a new check:

- `in_chrome` marks elements inside `<nav>`, `<header>`, `<footer>` or `<aside>`
  so that navigation is not mistaken for content.
- Sentences are measured per line, and only lines containing a terminator count.
  Headings and button labels carry no full stop and would otherwise be glued
  into one enormous "sentence", making every marketing page look unreadable.

## Politeness and safety, enforced in `crawl.py`

`GET` only · one request at a time · ≥1s apart, honouring `Crawl-delay` to 5s ·
robots.txt obeyed for this agent · URL denylist covering logout, cart, checkout,
admin, account, login, signup and `action=` · 3 MB per response · caps on pages,
depth and wall-clock time · no form submission, ever.
