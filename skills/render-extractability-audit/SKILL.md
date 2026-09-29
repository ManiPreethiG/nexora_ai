---
name: render-extractability-audit
description: >-
  Check whether a machine can actually read a fetched page and pick a specific
  fact out of it — JavaScript render gaps between the served HTML and the
  browser DOM, single-page-app shells, content delivered in third-party iframes,
  facts locked in images or PDFs, tab and accordion panels that only exist after
  a click, missing headings and landmarks, and the absence of a plain quotable
  sentence saying what the organisation is. Reads a crawl bundle and emits
  findings JSON. Use when a site is indexed but assistants still describe it
  vaguely, wrongly, or not at all.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 2
  marketplace: brand-ai-readiness-audit
---

# Render and extractability audit

## When to use

Stage two: the page was fetched, so now — is the fact *in* what came back? This
is the stage that explains the most common confusing symptom, a site that looks
complete to every human who opens it and empty to every machine that reads it.

## Inputs

A crawl bundle. When the bundle contains rendered captures (`*.rendered.extract.json`,
present only if a headless browser was available), the render gap is measured
directly. When it does not, the gap is inferred and every such finding is
emitted at `confidence: medium` with the limitation stated inside the evidence
string. Never claim a measured gap that was not measured.

## Procedure

```bash
python3 scripts/check_render.py --bundle ./bundle --json-out findings-render.json
```

Checks, with the mechanism each rests on (detail in `references/checks.md`):

1. **Render gap** — served HTML versus rendered DOM: word count, H1, JSON-LD and
   internal links. Many fetchers never execute JavaScript, so anything that
   appears only after hydration is invisible to them.
2. **App shell** (fallback when no browser) — few words plus a known root
   element plus framework bundles.
3. **`<noscript>`-only content** — extraction pipelines generally ignore it.
4. **Content in iframes** — an iframe is a separate document, so its content is
   attributed to the third-party origin, not to this page. Common with booking
   engines, menus, job boards and store locators.
5. **Facts locked in images** — price tables, spec sheets, menus and hours drawn
   as pictures. Text in an image is not extractable at all.
6. **Facts only in PDFs** — binary extraction is unreliable and often skipped.
7. **Interaction-gated panels** — `aria-controls` references whose target IDs do
   not exist in the served HTML. FAQ answers and specifications hide here, and a
   crawler never clicks.
8. **Document structure** — missing or duplicated H1, no `<main>`/`<article>`,
   missing `alt` attributes.
9. **Quotable self-definition** — whether one extractable sentence says
   "<brand> is a <category> that <does what> for <whom>". Assistants answer
   "what is X" by quoting a sentence that already exists; a slogan gives them
   nothing to lift, so the answer comes from third-party descriptions instead.
10. **Page-type facts** — a pricing page with no price in text; contact details
    that appear nowhere on the site as text.

## Avoiding false positives

- `alt=""` is the correct marker for a decorative image and is never counted as
  a missing alt.
- The shell finding needs two pages or the homepage; one thin interior page
  proves nothing.
- Analytics, consent, video and tag-manager iframes are excluded.
- Contact details are judged across the whole site, not one "talk to sales" page
  that is legitimately just a form.
- The self-definition check accepts a linking verb, an appositive
  ("Brand: the world's most comfortable shoes") or a self-describing name
  ("San Francisco Museum of Modern Art"), and requires the brand mention and the
  definition to sit within 120 characters of each other.
- Legal documents are typed separately and are not held to marketing-page
  expectations.

## Output

The findings JSON shape described in `audit-orchestrator/references/composition.md`.
