---
name: corroboration-freshness-audit
description: >-
  Check whether what a site says is current, internally consistent and repeated
  by sources outside itself — stale copyright and content, undated pages,
  expired "coming soon" announcements, contradictory contact details and
  self-descriptions, uncited statistics and superlatives, brand names likely to
  collide with other entities, and the absence of independent profiles that
  could corroborate the brand. Combines deterministic on-site checks with a
  live-search protocol for the off-site half. Use when assistants describe a
  brand with outdated or wrong facts, confuse it with something else, or ignore
  it in favour of better-corroborated competitors.
license: MIT
allowed-tools: Bash, Read, WebSearch, WebFetch
metadata:
  stage: 4
  marketplace: brand-ai-readiness-audit
---

# Corroboration and freshness audit

## When to use

Stage four: the page is readable and self-describing — but is it *believed*?
Machines weight a fact by how many independent sources repeat it and how recent
it looks. A brand described only by its own website, in language that changes
from page to page, with no dates and no registry presence, is fragile even when
everything technical is perfect.

This is also the stage that catches misrepresentation: a brand that is cited but
described wrongly usually has an entity problem, not a crawling problem.

## Inputs

A crawl bundle, plus (for the off-site half) a web-search tool. The two halves
are deliberately separated: the script covers what can be established
deterministically, the protocol covers what needs judgement.

## Procedure

### Part 1 — on-site (deterministic)

```bash
python3 scripts/check_freshness.py --bundle ./bundle --json-out findings-freshness.json
```

Checks: stale copyright; substantive pages with no publication or update date;
nothing updated in over a year; a blog that has visibly stopped; announcements
that still say "coming in <past year>"; several competing phone numbers or
contact addresses; a self-description that differs between the meta description
and the Organization schema; no links to any independent identity or review
source; superlatives and statistics with no citation; brand names that are
ordinary words with no registry anchor; sitemap `lastmod` values that are really
build timestamps. Detail and thresholds in `references/checks.md`.

### Part 2 — off-site (agent, live search)

Follow `references/offsite-protocol.md`. It is a fixed sequence of searches and
an evidence rule for each possible finding: whether independent sources exist,
whether they agree with the site, whether the name collides with another entity,
and what assistants currently say when asked about the brand.

Write the results as findings JSON in the same shape the scripts emit and pass
it to the entrypoint with `--agent-findings`.

**If no search tool is available, skip Part 2 entirely** and say so. The
composer records it in `limitations`. Never infer an off-site finding from
on-site data — "no LinkedIn link in the footer" is not evidence that no LinkedIn
page exists.

## Avoiding false positives

- Dates are expected on published content (articles, docs, case studies) and on
  very long pages — not on homepages, pricing, legal, product or contact pages.
- Descriptions are compared on word stems, so "payment" and "payments" agree.
- The Organization description is compared, not the first `description` string
  found in any JSON-LD node on any page.
- Off-site anchors are only judged when the homepage was actually retrieved,
  since footers carry those links.
- Name-ambiguity is reported as a *risk* at `confidence: medium`, with the
  instruction to confirm the collision off-site before acting.
- Claim thresholds are set so that ordinary marketing copy does not trip them.

## Output

The findings JSON shape described in
`audit-orchestrator/references/composition.md`. Off-site findings set
`observations.offsite_checked: true` so the composer knows the gap was closed.
