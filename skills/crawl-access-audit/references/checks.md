# crawl-access-audit — check reference

Stage 1: can an AI retrieval agent reach the page at all? Implemented in
`scripts/check_access.py`. Severity definitions: `audit-orchestrator/references/severity-model.md`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `CA-BLANKET-DISALLOW` | `User-agent: *` has `Disallow: /` with no `Allow` rules | Any `Allow` narrows it | critical |
| `CA-AI-RETRIEVAL-BLOCKED` | Any retrieval agent (see `ai-crawlers.md`) resolves to disallowed at `/` | Only training crawlers are blocked | critical |
| `CA-AI-TRAINING-BLOCKED` | A training crawler is blocked | No training blocks present | low |
| `CA-EDGE-BOT-BLOCK` | Homepage returns 200 to a browser UA and 401/403/405/406/429/503 or a network error to this audit's own **self-identifying** UA | The self-identifying UA gets the same status as the browser (an anonymous-only block is `CA-ANONYMOUS-UA-BLOCKED` instead) | critical |
| `CA-ANONYMOUS-UA-BLOCKED` | The self-identifying UA succeeds but a bare, unidentified client (no UA string identifying the tool) is rejected | The anonymous client also succeeds, or the self-identifying UA is itself blocked (that is `CA-EDGE-BOT-BLOCK`) | low |
| `CA-UA-CONTENT-VARIES` | Non-browser UA gets 200 but under 40% of the text a browser gets | Text lengths are comparable | high |
| `CA-HOMEPAGE-NOT-200` | Browser UA gets a non-200, non-zero status on the seed | Homepage responds normally | critical |
| `CA-HOMEPAGE-FETCH-FAILED` | Seed fails at the network layer even after one retry with a doubled timeout | Interior pages fail (that is `CA-FETCH-FAILURES`) | high |
| `CA-ROBOTS-NOT-PLAIN-TEXT` | robots.txt returns **200** with `text/html` | Any non-200 — that is simply missing | medium |
| `CA-ROBOTS-MISSING` | robots.txt is not fetchable | It parses | low |
| `CA-SITEMAP-MISSING` | No declared or conventional sitemap parses | Any sitemap parses | medium |
| `CA-SITEMAP-NOT-DECLARED` | A sitemap is reachable but robots.txt has no `Sitemap:` line | It is declared | low |
| `CA-SITEMAP-DECLARED-BROKEN` | A sitemap named in robots.txt does not fetch | Declared sitemaps all work | medium |
| `CA-SITEMAP-NO-LASTMOD` | Under half of sitemap URLs carry `<lastmod>` | Most carry it | low |
| `CA-BROKEN-INTERNAL-URLS` | Internally linked URLs return 4xx/5xx; `high` above 15% of the crawl | No error responses | med/high |
| `CA-FETCH-FAILURES` | Non-seed URLs fail at the network layer; `medium` at 3+ | Only the seed failed | low/med |
| `CA-SOFT-404` | A deliberately invalid URL returns 200 | It returns 404/410 | medium |
| `CA-404-REDIRECTS-HOME` | An invalid URL redirects to the homepage | It 404s | medium |
| `CA-REDIRECT-CHAINS` | 3+ redirect hops on internal URLs | Fewer hops | low |
| `CA-NOINDEX-ON-CONTENT` | `noindex` in meta robots or `X-Robots-Tag` on content pages; `critical` at half the crawl | The URL is a search, filter, tag, cart, thank-you or preview page | high/crit |
| `CA-NOSNIPPET` | `nosnippet` or `max-snippet:0` present | Neither present | high |
| `CA-CANONICAL-TO-HOMEPAGE` | Inner pages canonicalise to the site root | Self-referencing canonicals | high |
| `CA-CANONICAL-CROSS-HOST` | Canonical points at a different registrable host | www ↔ apex of the same domain | high |
| `CA-CANONICAL-MISSING` | Half or more of crawled pages have no canonical | Every page declares one | low |
| `CA-SLOW-RESPONSES` | Median full response over 2.5s (`high` over 5s), 3+ samples | Median within budget | med/high |
| `CA-LINK-DISCOVERY-GAP` | Sitemap declares 25+ URLs but under 10 distinct internal links appear in the HTML | Normal link density | high |
| `CA-HTTP-NOT-REDIRECTED` | `http://` does not end on an `https://` URL | It redirects | low |
| `CA-NO-LLMS-TXT` | No `/llms.txt` | It exists as non-HTML | info |

## Notes on checks that are easy to get wrong

**Anonymous vs. self-identifying non-browser blocks.** Every published AI
retrieval agent sends a descriptive user-agent string identifying itself, per
its own published policy — this is not optional for a real agent. A site that
rejects a bare, unidentified client (Python's default `urllib` UA, curl with
no `-A`) while accepting one that identifies itself is applying a targeted,
often reasonable anti-abuse rule, not blocking AI agents. Treating both cases
identically — as an earlier version of this check did — reports `critical`
against sites like Wikipedia, whose documented policy is exactly "identify
yourself and you're welcome in." Only a block on the self-identifying probe
is real evidence that a named AI agent would also be rejected.

**robots.txt matching.** Longest-match wins and `Allow` breaks ties at equal
length — the naive "any Disallow blocks it" reading produces false positives on
every site that uses `Disallow: /admin` with `Allow: /admin/public`. `*` and `$`
are supported. The agent-specific group wins over `*` when the agent name
appears in a group name.

**`nosnippet` is underrated.** It rarely appears in SEO audits because it does
not affect ranking. It affects citation directly: it forbids quoting text from
the page, and an assistant that cannot quote a fact uses a competitor's page it
can quote, however well this one ranks.
