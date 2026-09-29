# corroboration-freshness-audit — check reference

Stage 4: is what the site says current, self-consistent and repeated elsewhere?
On-site checks are in `scripts/check_freshness.py`; the off-site half is
`offsite-protocol.md`.

## On-site (deterministic)

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `CF-STALE-COPYRIGHT` | Newest copyright year found is 2+ years old | Current or last year | low |
| `CF-NO-VISIBLE-DATES` | 60%+ of dated-content pages expose no date in text, `<time>`, meta or structured data | The page is a homepage, pricing, legal, contact, about, careers, product or category page — none of which claims recency | medium |
| `CF-CONTENT-STALE` | Newest date anywhere is 18+ months old | Anything newer | high |
| `CF-PUBLISHING-STALLED` | A blog/news section exists and its newest item is 9+ months old | No blog, or recent posts | medium |
| `CF-EXPIRED-FORWARD-PROMISES` | "coming soon / launching in / join us on" paired with a past year | No expired promises | medium |
| `CF-INCONSISTENT-PHONE` | 3+ distinct phone numbers across the crawl | One or two | medium |
| `CF-INCONSISTENT-CONTACT-EMAIL` | 4+ general-purpose contact addresses | Fewer | low |
| `CF-INCONSISTENT-BOILERPLATE` | Homepage description and the **Organization** description share under 12% of word stems, both 40+ chars | They overlap, or no org description exists | medium |
| `CF-NO-OFFSITE-ANCHORS` | No external link to any identity or review source and no `sameAs` — **and the homepage was retrieved** | Anchors present, or the homepage failed (footers carry these links) | high |
| `CF-UNSOURCED-CLAIMS` | 5+ superlative/statistical claims with under 2 citable external links | Fewer claims, or citations present | medium |
| `CF-NAME-AMBIGUITY-RISK` | Brand name is an ordinary English word or ≤4 characters, **and** no registry-grade `sameAs` | A distinctive name, or registry anchors present | high |
| `CF-LASTMOD-UNIFORM` | 10+ sitemap entries all share one `lastmod` date | Varied dates | low |
| `CF-NO-CITABLE-ASSET` | No research, benchmark, dataset, survey or reference resource in navigation or link text | Such an asset exists | info |

## Off-site (agent, live search)

`CF-NOT-DISCOVERABLE-OFFSITE` · `CF-UNLINKED-PROFILES` · `CF-ENTITY-COLLISION` ·
`CF-DESCRIPTION-DRIFT` · `CF-STALE-FACTS-OFFSITE` · `CF-NOT-CITED` ·
`CF-MISREPRESENTED`. Protocol and evidence rules in `offsite-protocol.md`.

## Why corroboration is treated as a first-class signal

Machines treat a fact as more trustworthy when many independent places say the
same thing. A claim that lives in exactly one spot is fragile; a claim repeated
consistently across unrelated sources is far more likely to be believed and
repeated back. That has two consequences an audit has to act on:

1. **A brand described only by its own website has nothing reinforcing it.**
   No amount of on-page optimisation substitutes for existing elsewhere. This is
   why `CF-NO-OFFSITE-ANCHORS` is `high` even on a technically flawless site.
2. **Consistency is the lever the brand actually controls.** It cannot make
   other sites talk about it on demand, but it can make every place it already
   appears say the same sentence. Several competing self-descriptions divide the
   signal between them so none accumulates weight — which is why
   `CF-INCONSISTENT-BOILERPLATE` matters more than its severity suggests.

## Why freshness is a trust signal, not a vanity metric

Recency is one of the few quality signals available for an unfamiliar page.
Given two pages that answer a question equally well, the one with a visible
recent date gets cited; an undated page is treated as unknown age, which is
scored much like old. Sites that never change are also re-crawled less often, so
even corrections take a long time to propagate into what assistants say.

The two failure modes worth separating:

- **Undated** — the page may be current, but nothing says so.
- **Stale** — the page says something that has stopped being true, most
  damagingly in the forward tense ("launching in 2024"). This produces
  confidently wrong answers, because the assistant repeats the page's own
  framing.

Note the honest caveat built into the fix: `dateModified` that moves on every
deploy carries no information and is discounted. Update it when the content
changes, not when the build runs.
