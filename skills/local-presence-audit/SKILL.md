---
name: local-presence-audit
description: >-
  For a site the profile classifies as a local business, check name/address/
  phone (NAP) consistency across the site, whether opening hours mentioned in
  text are mirrored in LocalBusiness structured data, and whether any map
  provider link or embed exists. Every check is gated on the site profile's
  `site_type == local_business` and reports not_applicable with the reason
  otherwise, so it never fires on a site the profile did not classify as
  local. Distinct from structured-data-audit (which checks whether
  LocalBusiness markup exists at all) and corroboration-freshness-audit
  (which checks phone/email consistency generically): this checks the
  specific NAP-and-hours mechanism that off-site local answers are actually
  assembled from. Reads a crawl bundle and emits findings JSON. Use for any
  local business, clinic, restaurant, or storefront site.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 10
  marketplace: brand-ai-readiness-audit
---

# Local presence audit

## When to use

Any site the profile classifies as `local_business` — address, phone and
opening hours present, with few or no product pages. Skip it, or expect
`not_applicable` results, for any other site type; forcing NAP consistency
checks on a SaaS or ecommerce site would be exactly the kind of context-free
expectation this marketplace's design commitments treat as the main risk to
avoid.

## Inputs

A crawl bundle directory produced by `audit-orchestrator/scripts/crawl.py`
(contract: `audit-orchestrator/references/crawl-bundle.md`) and
`bundle/profile.json`, whose `site_type` gates every check in this skill.
This skill performs no network requests of its own.

## Procedure

```bash
python3 scripts/check_local.py --bundle ./bundle --json-out findings-local.json
```

The script runs the checks documented in `references/checks.md`. In summary:

1. **NAP inconsistency** — more than one distinct street address or phone
   number published across the site.
2. **Hours not in schema** — opening-hours text exists but no
   `openingHours`/`openingHoursSpecification` appears in any JSON-LD.
3. **No map embed or link** — no link or iframe to a Google/Apple/Bing/
   OpenStreetMap map was found anywhere.

## Avoiding false positives

- Every check is gated on `profile.site_type == "local_business"`; on any
  other site type all three checks report `not_applicable` with the
  classification reason, never a defect.
- The NAP check only fires on 2+ distinct addresses *or* 2+ distinct phone
  numbers — a single consistent value anywhere on the site clears it.
- The hours-in-schema check only fires when hours text was actually found;
  a local business that simply omits hours entirely is `structured-data-
  audit`'s concern (missing the expected `LocalBusiness` type), not this
  skill's.

## Output

`{"skill", "site", "findings": [...], "not_applicable": [...], "observations": {...}}`.
Each finding carries `check_id`, `title`, `severity`, `confidence`, `evidence`
(with observed values), `mechanism`, `affected_urls` and `suggested_action`
(`summary`, `detail`, `priority`, `effort`, `verification`).
