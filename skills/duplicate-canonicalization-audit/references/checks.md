# duplicate-canonicalization-audit — check reference

Whether the site's own content competes against itself across URLs.
`scripts/check_duplicates.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `DC-DUPLICATE-TITLE-OR-DESCRIPTION` | 2+ distinct URLs (not related by canonical) share an identical, non-generic title | Titles are unique, or the pages already declare a canonical relating them | medium |
| `DC-NEAR-DUPLICATE-PAGES` | Two same-type pages, both 30+ words, share 85%+ word-stem overlap with no canonical relating them | Pages are too short to compare meaningfully, differ in type, or are already canonically related | medium |
| `DC-PARAM-VARIANT-NOT-CANONICALIZED` | A crawled URL carries a query string and its canonical is empty or still contains the query string | No crawled URL carried query parameters, or parameterised URLs already declare a clean canonical | medium |

## Why this needs to compare pages, not just read one

`crawl-access-audit`'s canonical checks (`CA-CANONICAL-MISSING`,
`CA-CANONICAL-TO-HOMEPAGE`, `CA-CANONICAL-CROSS-HOST`) each read a single
page's own `rel=canonical` value in isolation — they can tell a canonical is
missing or wrong, but not that two *different* URLs happen to serve the same
content without either one declaring a relationship to the other. That
requires comparing pages against each other, which is what this skill adds:
a duplicate pair where neither page's canonical is technically "wrong" is
invisible to a single-page check and is exactly what this skill exists to
catch.

## Why word-stem overlap, not exact text match

Two pages are rarely byte-identical even when they are the same content —
timestamps, related-item widgets and ad slots differ. Comparing the set of
4+ character word stems in the main content (the same technique
`corroboration-freshness-audit` uses for `CF-INCONSISTENT-BOILERPLATE`)
tolerates that noise while still catching genuine duplication.
