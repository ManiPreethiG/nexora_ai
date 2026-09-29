---
name: trust-legitimacy-audit
description: >-
  Check on-site signals that a source is identifiable and accountable —
  HSTS enforcement on HTTPS, identifiable authorship on published articles,
  a linked privacy/terms page, and (for commerce and nonprofit sites) a
  disclosed registered business or charity identity. Distinct from
  corroboration-freshness-audit, which checks whether independent third
  parties repeat the site's facts: this checks whether the site's own facts
  carry the baseline signals of coming from an accountable party in the
  first place. Reads a crawl bundle and emits findings JSON. Use alongside
  corroboration-freshness-audit whenever a site's facts are technically
  well-corroborated but the site itself reads as anonymous or unaccountable.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 8
  marketplace: brand-ai-readiness-audit
---

# Trust and legitimacy audit

## When to use

Alongside `corroboration-freshness-audit`, or on its own when a site needs a
quick legitimacy check: does it disclose who operates it, are articles
attributed to a real person, and is the transport layer configured the way a
serious operator configures it. This is deliberately narrower than a general
E-E-A-T review — every check here is a concrete, checkable signal, not a
subjective quality judgement.

## Inputs

A crawl bundle directory produced by `audit-orchestrator/scripts/crawl.py`
(contract: `audit-orchestrator/references/crawl-bundle.md`) and
`bundle/profile.json` for site-type gating. This skill performs no network
requests of its own.

## Procedure

```bash
python3 scripts/check_trust.py --bundle ./bundle --json-out findings-trust.json
```

The script runs the checks documented in `references/checks.md`. In summary:

1. **HSTS** — HTTPS is used but `Strict-Transport-Security` is absent.
2. **Author byline** — two or more articles exist and most carry no
   identifiable author in text or structured data.
3. **Legal pages linked** — no privacy policy, terms or cookie policy link
   found anywhere on the site.
4. **Business identity disclosed** (ecommerce/nonprofit) — no registration
   number, tax ID or registered address found anywhere in text.

## Avoiding false positives

- The HSTS check only evaluates when the seed URL is `https://` — a site
  audited over plain HTTP has no probe to draw the conclusion from, and is
  recorded `not_applicable` rather than assumed to fail.
- The author-byline check requires at least two article pages before it
  fires; one article proves nothing about the site's general practice.
- The business-identity check is scoped to `ecommerce` and `nonprofit`, the
  two site types where a buyer or donor's decision to trust the site with
  money is directly at stake — a SaaS marketing site is not held to the same
  registration-disclosure bar.

## Output

`{"skill", "site", "findings": [...], "not_applicable": [...], "observations": {...}}`.
Each finding carries `check_id`, `title`, `severity`, `confidence`, `evidence`
(with observed values), `mechanism`, `affected_urls` and `suggested_action`
(`summary`, `detail`, `priority`, `effort`, `verification`).
