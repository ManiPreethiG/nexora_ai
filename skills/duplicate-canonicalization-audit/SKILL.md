---
name: duplicate-canonicalization-audit
description: >-
  Check whether a site's own content is split across two or more near-
  identical URLs that compete with each other rather than one page
  accumulating the signal to be cited — identical page titles on distinct
  URLs, near-duplicate body text between same-type pages, and query-parameter
  URL variants with no clean canonical. Distinct from crawl-access-audit's
  canonical checks (which look at a single page's canonical in isolation):
  this compares pages against each other to find the duplication a
  single-page check cannot see. Reads a crawl bundle and emits findings
  JSON. Use whenever a site has several plausible URLs for what is really one
  answer and it is unclear which one gets cited.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 9
  marketplace: brand-ai-readiness-audit
---

# Duplicate and canonicalization audit

## When to use

Whenever a site has templated or parameterised URLs — tracking parameters,
locale variants, listing pages that reproduce a product's copy — and it is
unclear which single URL a citation or search result would settle on. This
compares pages against each other; `crawl-access-audit`'s canonical checks
look at one page's own `rel=canonical` in isolation and cannot see this
class of problem.

## Inputs

A crawl bundle directory produced by `audit-orchestrator/scripts/crawl.py`
(contract: `audit-orchestrator/references/crawl-bundle.md`). This skill
performs no network requests of its own; the pairwise comparison is O(n²)
over the crawled pages, which is inexpensive at the marketplace's page caps.

## Procedure

```bash
python3 scripts/check_duplicates.py --bundle ./bundle --json-out findings-duplicates.json
```

The script runs the checks documented in `references/checks.md`. In summary:

1. **Duplicate title or description** — two or more distinct, non-canonically-
   related URLs share an identical page title.
2. **Near-duplicate pages** — two same-type pages share 85%+ word-stem
   overlap in their main content, with no canonical relating them.
3. **Param variant not canonicalized** — a URL crawled with a query string
   carries no canonical, or a canonical that still contains the query string.

## Avoiding false positives

- Legal pages are excluded entirely — privacy policies across locales are
  legitimately near-identical boilerplate, not a duplication defect.
- Both the title and near-duplicate checks skip any pair already related by
  a `rel=canonical` — that pair has already declared which URL is
  authoritative, which is the fix this skill would otherwise recommend.
- The near-duplicate check requires both pages to carry at least 30 words of
  main content; comparing two near-empty pages produces a coincidental,
  meaningless overlap score.
- Generic one-word titles ("Home", "Page") are excluded from the title check
  — matching on those would flag unrelated pages that just happen to share a
  conventional label.

## Output

`{"skill", "site", "findings": [...], "not_applicable": [...], "observations": {...}}`.
Each finding carries `check_id`, `title`, `severity`, `confidence`, `evidence`
(with observed values), `mechanism`, `affected_urls` and `suggested_action`
(`summary`, `detail`, `priority`, `effort`, `verification`).
