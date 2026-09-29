---
name: crawl-access-audit
description: >-
  Check whether an AI retrieval agent can reach a site's pages at all — robots.txt
  policy for retrieval versus training crawlers, edge/WAF bot blocking that
  rejects non-browser clients, missing or broken sitemaps, error and soft-404
  responses, noindex and nosnippet directives, canonical mistakes that collapse a
  site into one URL, redirect chains, and server latency high enough to trip a
  fetcher's timeout. Reads a crawl bundle and emits findings JSON. Use as the
  first stage of an AI-readiness audit, or on its own when a site is completely
  absent from AI answers and search results and the cause is unknown.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 1
  marketplace: brand-ai-readiness-audit
---

# Crawl and access audit

## When to use

Stage one of the pipeline, and the right skill on its own whenever a brand is
*entirely* missing rather than merely ranked poorly. Nothing downstream matters
if this stage fails: content that cannot be fetched cannot be read, marked up,
corroborated or engaged with.

## Inputs

A crawl bundle directory produced by
`audit-orchestrator/scripts/crawl.py` (contract:
`audit-orchestrator/references/crawl-bundle.md`). This skill performs no network
requests of its own — the bundle already contains the robots.txt, the sitemap
documents, the user-agent probe matrix, and every fetched response.

## Procedure

```bash
python3 scripts/check_access.py --bundle ./bundle --json-out findings-access.json
```

The script runs the checks documented in `references/checks.md`. In summary:

1. **robots.txt** — parsed with full `Allow`/`Disallow` longest-match semantics,
   then evaluated separately for retrieval agents and training crawlers. The
   distinction is the point: blocking `GPTBot` is a content-licensing decision,
   blocking `OAI-SearchBot` or `Claude-User` removes the site from live answers.
   `references/ai-crawlers.md` lists which is which.
2. **Edge blocking** — compares the homepage fetched with a browser user-agent
   against the same URL fetched with this audit's own self-identifying
   user-agent (what a real AI retrieval agent also sends) and, separately, a
   bare client with no identifying UA at all. A 200 for the browser and a
   403/429/503 for the self-identifying UA is a WAF rule that rejects AI
   fetchers while the site looks perfect in a browser — `critical`. A block on
   the anonymous UA alone, with the self-identifying UA let through, is
   reported at `low` severity as a targeted anti-abuse rule, not conflated
   with an AI-fetcher block.
3. **Sitemaps** — presence, declaration in robots.txt, fetchability, `lastmod`
   coverage.
4. **Responses** — 4xx/5xx on internally linked URLs, network failures, soft
   404s (a 200 for a URL that does not exist), catch-all redirects to the
   homepage, redirect chains.
5. **Indexing directives** — `noindex` and `nosnippet`/`max-snippet:0` in meta
   robots and the `X-Robots-Tag` header. `nosnippet` deserves attention: it
   explicitly forbids quoting the page, which is precisely what a citation is.
6. **Canonicals** — missing, cross-host, or pointing every page at the homepage.
7. **Latency** — median full-response time against a fetcher-timeout budget.
8. **Opportunity** — `/llms.txt`, reported as `info`, never as a defect.

## Avoiding false positives

- Utility URLs (internal search, filters, thank-you pages) are excluded from the
  noindex check; `noindex` there is correct.
- A training-crawler block is reported at `low` severity for confirmation, with
  the trade-off stated — it is a legitimate business choice.
- Canonicals between `example.com` and `www.example.com` are the same site.
- Latency, broken links and canonicals only fire against measured thresholds
  with the counts shown in the evidence.
- A failed homepage fetch is reported separately, because it degrades several
  other checks and the report must say so rather than blame the site.

## Output

`{"skill", "site", "findings": [...], "not_applicable": [...], "observations": {...}}`.
Each finding carries `check_id`, `title`, `severity`, `confidence`, `evidence`
(with observed values), `mechanism`, `affected_urls` and `suggested_action`
(`summary`, `detail`, `priority`, `effort`, `verification`). `not_applicable`
records checks that were evaluated and deliberately did not fire, with the
reason — the entrypoint puts these in the report so a reader can tell the
difference between "clean" and "not looked at".
