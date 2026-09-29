# structured-data-audit — check reference

Stage 3: does the page state what it is, and identify the brand unambiguously?
Implemented in `scripts/check_schema.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `SD-NONE` | No JSON-LD, microdata or RDFa on any crawled page | Any markup present | high |
| `SD-MICRODATA-ONLY` | Microdata/RDFa present but no JSON-LD | JSON-LD present | low |
| `SD-INVALID-JSON` | A `ld+json` block does not parse | All blocks parse | high |
| `SD-NO-CONTEXT` | A JSON-LD block omits `@context` | `@context` present | medium |
| `SD-NO-ORGANIZATION` | Markup exists but no Organization/LocalBusiness node anywhere | An org node exists, or `SD-NONE` already fired | high |
| `SD-ORGANIZATION-INCOMPLETE` | The org node lacks `name`, `url`, `logo` or `description` | All four present | medium |
| `SD-NO-SAMEAS` | The org node declares no `sameAs` | Any `sameAs` present | high |
| `SD-WEAK-SAMEAS` | `sameAs` present but none is registry-grade | A registry reference is present | medium |
| `SD-CONFLICTING-ORG-NAMES` | Org nodes across the site use different `name` values | One consistent name | medium |
| `SD-MISSING-EXPECTED-TYPES` | A type required by the site profile is absent | The signal for that type is absent (no products, no address, no articles); `Organization` already reported; `BreadcrumbList` has its own check; `SD-NONE` fired | med/high |
| `SD-INCOMPLETE-<TYPE>` | A node of a known type lacks a required property | Stub `Product`/`Offer` nodes on listing pages — only detail pages must be complete | med/high |
| `SD-CONTRADICTS-PAGE` | Offer price absent from the page's own prices, or structured `name`/`headline` sharing under two words with the heading and title | Values agree | high |
| `SD-NO-BREADCRUMBS` | Pages 3+ levels deep with no `BreadcrumbList` | No deep pages, or breadcrumbs present | medium |
| `SD-FAQ-OPPORTUNITY` | A page has 3+ question-shaped headings and no `FAQPage`/`QAPage` | No question headings, or already marked up | medium |
| `SD-NO-WEBSITE-NODE` | Markup present but no `WebSite` node | Present, or `SD-NONE` fired | low |

## Why the profile gates most of these

Demanding `Product` markup from a consultancy, or opening hours from a SaaS
company, is the fastest way to make an audit untrustworthy: a reader who finds
one obviously wrong finding stops believing the accurate ones around it. So
expectations come from `bundle/profile.json`, and every suppression is recorded
in `not_applicable` with its reason, which doubles as the audit's own account of
why it did not fire.

The expected-type table is deliberately minimal — only types whose absence is a
genuine defect for that kind of site. Everything merely desirable
(`SoftwareApplication`, `OpeningHoursSpecification`, `FAQPage`) is raised as a
proactive recommendation instead.

## The check most audits skip: markup versus visible page

Presence and validity are easy to check and commonly checked. Agreement is not.
A price of `49.00` in JSON-LD on a page showing £79 is worse than no markup at
all: consumers that detect the contradiction discount the markup, and some
discount the domain. It happens whenever structured data is hand-maintained or
hard-coded in a template instead of generated from the same source that renders
the page — which is also the fix.

## Entity identity is the part that fixes misrepresentation

`sameAs` is how a page says "the thing I am describing is this known entity".
Without it, a brand whose name resembles a common word, a product, or a
better-known company gets conflated with them, and answers about the brand
carry facts belonging to something else. That is a different failure from being
missing, and more damaging, because it looks like an answer.

Registry-grade references disambiguate — Wikidata, Wikipedia, Crunchbase, a
LinkedIn company page, a company registry. Social handles barely do: they are
trivially duplicated and are weak evidence of identity. Two independent
registry references beat five social links.
