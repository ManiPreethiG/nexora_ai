---
name: engagement-audit
description: >-
  Check whether the visitor an AI citation delivers finds their answer and a
  reason to stay — interior pages that give a cold arrival no orientation or next
  step, interrupting overlays and consent walls, page weight and render-blocking
  scripts, missing mobile viewport, thin key pages, unscannable prose, abstract
  above-the-fold copy, facts gated behind forms, filtered views with no shareable
  URL, missing site search, and baseline accessibility attributes. Reads a crawl
  bundle and emits findings JSON. Use when a site is cited or found but the
  traffic does not convert, bounces immediately, or never goes beyond one page.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 5
  marketplace: brand-ai-readiness-audit
---

# On-site engagement audit

## When to use

Stage five, and the half of the problem that structural SEO checks miss
entirely. Run it whenever the question is "they arrive, so why don't they stay".

## The model this skill is built on

An assistant that cites a site sends people to **a deep page, not the
homepage**, with a specific question already in mind and none of the context a
designed funnel assumes. They did not choose this site; something suggested it.

So engagement is assessed as: *does an arbitrary interior page stand on its
own?* Can a stranger landing cold tell where they are, get the fact they came
for, and see what to do next — before anything blocks or slows them.

That framing is why the checks below look different from a generic UX
checklist, and why several of them improve discoverability at the same time: a
page that orients a human also gives an extractor the context it needs.

## Inputs

A crawl bundle, plus `bundle/profile.json` where available.

## Procedure

```bash
python3 scripts/check_engagement.py --bundle ./bundle --json-out findings-engagement.json
```

Checks (detail in `references/checks.md`):

1. **Arrival orientation** — interior pages with neither breadcrumbs nor the
   brand named in the heading, title or opening text.
2. **Next step** — pages with almost no in-body links and no recognisable call
   to action. The citation worked; the visit ends at one page anyway.
3. **Interrupting overlays** — newsletter and exit-intent layers, and consent
   walls that block the content rather than sitting under it.
4. **Weight and speed** — HTML size, external and render-blocking script counts.
5. **Mobile** — viewport declaration, unsized images, lazy loading.
6. **Thin key pages** — pricing, product, about, contact, FAQ pages that answer
   nothing. These fail twice: nothing to quote, and nothing to read.
7. **Scannability** — sentence length, paragraph length, subheading density, on
   pages whose job is to be read.
8. **Above-the-fold clarity** — abstract marketing language with no concrete
   category noun.
9. **Gated facts** — pricing or substance held behind a form. Reported as a
   trade-off whose cost has changed, not as a mistake.
10. **State in the URL** — filtered and sorted views that cannot be linked,
    cited, bookmarked or returned to after a refresh.
11. **Site search** — the only alternative to going back to the assistant when a
    page is close but not right.
12. **Accessibility baseline** — `lang`, labelled form fields, named links.
    A floor, not an accessibility audit, and stated as such in the finding.

## Avoiding false positives

- Legal pages are excluded from orientation and scannability checks; dense legal
  text is correct.
- Scannability applies to prose pages only — a product grid is not prose.
- Unnamed links must be both numerous and a fifth of all links before firing,
  and a link is considered named by its text, its `title`, its `aria-label`, a
  nested image's `alt`, or an `<svg><title>`.
- Weight and speed thresholds are stated in the evidence, and the evidence says
  plainly that it measured HTML and resource counts rather than total transfer.

## Output

The findings JSON shape described in
`audit-orchestrator/references/composition.md`. Findings that damage both halves
are marked `category: "both"` so the composer counts them against both scores.
