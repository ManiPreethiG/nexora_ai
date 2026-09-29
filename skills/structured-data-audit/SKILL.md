---
name: structured-data-audit
description: >-
  Check whether a page states its meaning explicitly and identifies the brand
  unambiguously — presence and validity of JSON-LD/microdata, @context and JSON
  syntax errors, required schema.org properties, the types a site of this kind
  needs, Organization identity and sameAs entity anchors, conflicting
  organisation names, missing breadcrumbs, unmarked Q&A content, and
  contradictions between the structured data and the visible page. Reads a crawl
  bundle and emits findings JSON. Use when a brand is confused with another
  entity, described with facts that belong to something else, or missing from
  comparison and "best X for Y" answers.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 3
  marketplace: brand-ai-readiness-audit
---

# Structured data and entity audit

## When to use

Stage three: the page can be read, but does it *say what it is*? This stage also
owns entity identity — the reason a brand gets confused with a company, a
product or an ordinary word that shares its name.

## Inputs

A crawl bundle, plus `bundle/profile.json` from
`audit-orchestrator/scripts/profile.py`. The profile is what makes expectations
correct: `Product` markup is required of an ecommerce site and irrelevant to a
consultancy. Without it, this skill runs only the type-agnostic checks and
records the rest as not-applicable rather than guessing.

## Procedure

```bash
python3 ../audit-orchestrator/scripts/profile.py --bundle ./bundle   # if not already done
python3 scripts/check_schema.py --bundle ./bundle --json-out findings-schema.json
```

Checks (detail in `references/checks.md`, property requirements in
`references/schema-requirements.md`):

1. **Presence** — no structured data anywhere; microdata/RDFa without JSON-LD.
2. **Validity** — unparseable JSON (silently discards the whole block, so the
   page appears marked up while providing nothing), missing `@context`.
3. **Organization identity** — the node that says who publishes every page, and
   whether it carries `name`, `url`, `logo` and a `description`.
4. **`sameAs` anchors** — whether the brand entity is linked to references a
   machine already trusts. Registry-grade identifiers (Wikidata, Wikipedia,
   Crunchbase, a LinkedIn company page, a company registry) disambiguate;
   social handles barely do.
5. **Expected types by site type** — only types whose absence is a genuine
   defect for that kind of site.
6. **Required properties** — a node missing them is often dropped entirely.
7. **Markup versus visible page** — offer price against prices shown on the
   page, structured name against the heading. A contradiction is worse than an
   omission: consumers that detect it discount the markup and sometimes the
   domain.
8. **Breadcrumbs** on deep pages — which help extraction and orientation at once.
9. **FAQ opportunity** — question-shaped headings with no `FAQPage` markup.
10. **WebSite node** — what supplies the site's display name.

## Avoiding false positives

- Expectations come from the profile, so a site with no product pages is never
  asked for `Product`, and a SaaS company is never asked for opening hours.
- `SD-NONE` suppresses every downstream schema finding; "no markup" and "missing
  the expected types" are one defect, not eight.
- Stub `Product` nodes on listing pages are ignored; only product detail pages
  must be complete.
- Contradiction checks run at `confidence: medium` because price formatting
  varies legitimately.

## Output

The findings JSON shape described in `audit-orchestrator/references/composition.md`.
