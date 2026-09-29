---
name: site-architecture-audit
description: >-
  Check whether a crawler that is let in can actually find the rest of the
  site — dead-end pages with no onward links, sitemap URLs that are never
  linked from any crawled page, crawled pages that are missing from the
  sitemap, and internal links that still point at pre-redirect URLs. Distinct
  from crawl-access-audit (which asks whether the crawler is let in at all):
  this asks whether the internal link graph actually leads it around once it
  is inside. Reads a crawl bundle and emits findings JSON. Use alongside
  crawl-access-audit whenever some pages of a site are cited or indexed and
  others, with no obvious access block, are not.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 6
  marketplace: brand-ai-readiness-audit
---

# Site architecture audit

## When to use

Whenever the entry point works (robots.txt allows it, the homepage returns
200) but coverage is patchy — some pages are found and cited, others never
are, with no robots or WAF block to explain the difference. That pattern is
usually the internal link graph, not access control.

## Inputs

A crawl bundle directory produced by `audit-orchestrator/scripts/crawl.py`
(contract: `audit-orchestrator/references/crawl-bundle.md`). This skill
performs no network requests of its own.

## Procedure

```bash
python3 scripts/check_architecture.py --bundle ./bundle --json-out findings-architecture.json
```

The script runs the checks documented in `references/checks.md`. In summary:

1. **Dead-end pages** — interior pages with at most one in-body link to
   another internal page. A crawler discovers new URLs by following links out
   of pages it has already read; a page with nowhere to go is a leaf that
   teaches the crawler nothing else about the site.
2. **Orphaned sitemap URLs** — URLs the sitemap declares that no crawled page
   links to. A sitemap is a hint, not a substitute for a link graph.
3. **Pages missing from the sitemap** — crawled, linked pages the sitemap
   does not declare, which costs them the `<lastmod>` re-crawl signal.
4. **Internal links to redirecting URLs** — links that still point at a
   pre-redirect URL rather than the final destination, costing every fetcher
   an avoidable hop.

## Avoiding false positives

- The sitemap-comparison checks require at least 5 declared URLs before
  drawing any conclusion; a missing or tiny sitemap is `crawl-access-audit`'s
  concern (`CA-SITEMAP-MISSING`), not this skill's.
- Legal pages (privacy, terms) are excluded from the dead-end check — they
  are reference documents, not navigation hubs, and are not expected to link
  onward.
- Orphan and missing-from-sitemap thresholds are proportions with the
  denominator shown, not raw counts, so a large site with a handful of stray
  URLs is not flagged the same as one where a third of the sitemap is
  disconnected.

## Output

`{"skill", "site", "findings": [...], "not_applicable": [...], "observations": {...}}`.
Each finding carries `check_id`, `title`, `severity`, `confidence`, `evidence`
(with observed values), `mechanism`, `affected_urls` and `suggested_action`
(`summary`, `detail`, `priority`, `effort`, `verification`).
