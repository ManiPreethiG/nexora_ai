# site-architecture-audit — check reference

The internal link graph, once a crawler is already let in.
`scripts/check_architecture.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `SA-DEAD-END-PAGES` | 50%+ of interior (non-home, non-legal) pages carry ≤1 in-body link to another internal page | Pages carry onward links, or there are fewer than 2 interior pages | medium–high |
| `SA-ORPHAN-SITEMAP-URLS` | 30%+ (min 3) of declared sitemap URLs never appear as an `<a href>` on any crawled page | Sitemap has under 5 URLs, or is more than 15× the crawled page count (a shallow sample of a large site cannot support this conclusion), or URLs are reachable through links | medium |
| `SA-PAGES-MISSING-FROM-SITEMAP` | 30%+ (min 2) of crawled, linked pages are absent from the sitemap | Sitemap has under 5 URLs, or crawled pages are all declared | low |
| `SA-INTERNAL-LINKS-TO-REDIRECTING-URLS` | An internal link's href matches a URL that redirected during this crawl | No crawled URL redirected, or no internal link targets the pre-redirect form | low |

## Why this is a separate concern from crawl-access-audit

`crawl-access-audit` asks whether a crawler is let in at the gate: robots.txt,
WAF rules, response codes. This skill asks what happens after it is inside —
whether the site's own links lead it to everything else. A site can pass
every crawl-access check and still have three-quarters of its pages
practically undiscoverable because nothing on the site links to them. The
fixes are different too: crawl-access failures are infrastructure and
robots.txt; these are template and content-architecture decisions (related
content, category links, "see also"), which is why the two are not folded
into one skill.

## Why proportions, not counts

A site with 200 pages and 5 orphaned sitemap URLs is healthy; a site with 10
pages and 5 orphaned ones has lost half its coverage. Both checks report the
proportion with the denominator shown, matching the evidence rules the rest
of the marketplace follows.

## Why the orphan check is gated on crawl coverage

A crawl capped at, say, 20 pages will always look like most of a 1,000-URL
sitemap is "orphaned" — not because the site's link graph is broken, but
because 20 pages cannot possibly link to most of 1,000 URLs regardless of how
healthy the site is. Comparing a small sample against a much larger sitemap
would report a sampling artifact as if it were an observation about the
site's actual link graph, which is exactly what the evidence rules forbid.
The check only fires when the sitemap is within a plausible multiple (15×)
of the crawled page count; otherwise it is recorded `not_applicable` with the
reason, and a fuller crawl is the honest way to actually check it.
