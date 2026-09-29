---
name: audit-orchestrator
description: >-
  Audit any website for the problems that stop AI assistants finding, reading,
  trusting and citing it, and that stop the visitors those citations deliver
  from staying — crawler and edge blocking, JavaScript render gaps, facts locked
  in images, iframes, PDFs or click-to-open panels, missing or contradictory
  structured data, entity ambiguity, stale and uncorroborated claims, dead-end
  internal linking, missing answer/comparison content, weak on-site trust
  signals, duplicate or uncanonicalized URLs, inconsistent local business
  details, and interior pages that leave a cold arrival with no orientation or
  next step.
  Produces one structured report of evidence-backed findings with severities and
  prioritised, mechanism-sound fixes. This is the entrypoint of the
  brand-ai-readiness-audit marketplace: it crawls once, runs every other skill
  against that single crawl, and composes their output into the final report.
  Use when asked why a brand is invisible, stale or misrepresented in AI
  assistants, why cited traffic bounces, or for a general "audit this site for
  AI readiness / AI SEO / GEO" request.
license: MIT
allowed-tools: Bash, Read, Write, Glob, Grep, WebFetch, WebSearch
metadata:
  role: entrypoint
  marketplace: brand-ai-readiness-audit
  version: 1.0.0
---

# Brand AI-readiness audit — orchestrator

## When to use

A user gives you a website and wants to know why AI assistants do not find,
cite or correctly describe it, and why the visitors who do arrive leave again.
Also use for open-ended "audit this site" requests where AI discoverability or
engagement is the concern.

Do **not** use this to change a site. Everything here is read-only.

## Inputs

| Input | Required | Default |
|---|---|---|
| `url` — the site to audit (domain or full URL) | yes | — |
| `max_pages` | no | 30 |
| `out_dir` — where the bundle and report are written | no | `./audit` |
| `render` — `auto` uses a headless browser if one exists, `off` skips it | no | `auto` |

## Safety rules — these are not negotiable

1. **Recommend only.** No skill in this marketplace ever modifies the audited
   site. The output is a report.
2. **Read-only requests.** `GET` only. Never submit a form, never follow a link
   matching logout, cart, checkout, admin, account, login, signup or `action=`.
   `crawl.py` enforces this with a URL denylist.
3. **Respect robots.txt** for this agent's own user-agent. Disallowed URLs are
   recorded as skipped, never fetched anyway.
4. **Be polite.** One request at a time, ≥1s apart, honouring `Crawl-delay` up
   to 5s. Hard caps on pages, page size and wall-clock time.
5. **Never enter authenticated areas**, even if the user supplies credentials.
6. **Never fabricate evidence.** Every finding quotes an observed value. If a
   check could not run, it belongs in `limitations`, not in `findings`.

## Procedure

### 1. Normalise the input
Accept `example.com` or `https://example.com/path`. Resolve to an origin. If the
host does not resolve or returns nothing at all, stop and report that — do not
emit a report full of findings caused by the site being down.

### 2. Build the crawl bundle — one crawl, shared by every skill
```bash
python3 skills/audit-orchestrator/scripts/crawl.py "$URL" \
    --out "$OUT/bundle" --max-pages 30 --delay 1.0 --budget 210 --render auto
```
Every analysis skill reads this bundle rather than fetching anything itself. That
is what keeps the audit polite (one request per URL), deterministic (every check
sees identical bytes) and inside the runtime budget.
Contract: `references/crawl-bundle.md`.

### 3. Profile the site before judging it
```bash
python3 skills/audit-orchestrator/scripts/profile.py --bundle "$OUT/bundle"
```
Writes `profile.json`: site type, brand name, and the signals behind both. Every
downstream check consults it. **This step is what prevents the single largest
source of false positives** — holding a site to expectations that belong to a
different kind of site.

### 4. Run the analysis skills
Each reads the bundle and writes findings JSON. They are independent and may run
in any order:

| Skill | Question it answers |
|---|---|
| `crawl-access-audit` | Can an AI retrieval agent reach the page at all? |
| `site-architecture-audit` | Once in, can it find the rest of the site? |
| `render-extractability-audit` | Once fetched, can a machine read it and pick a fact out? |
| `structured-data-audit` | Does the page state what it is, and identify the brand unambiguously? |
| `answer-coverage-audit` | Does an answer actually exist to quote? |
| `corroboration-freshness-audit` | Are the facts current, self-consistent and repeated elsewhere? |
| `trust-legitimacy-audit` | Do the site's own facts carry signals of an accountable source? |
| `duplicate-canonicalization-audit` | Is the content split across competing URLs? |
| `local-presence-audit` | For a local business, does the site agree with itself on NAP and hours? |
| `engagement-audit` | Does the visitor a citation delivers find their answer and a reason to stay? |

```bash
for s in crawl-access-audit site-architecture-audit render-extractability-audit \
         structured-data-audit answer-coverage-audit corroboration-freshness-audit \
         trust-legitimacy-audit duplicate-canonicalization-audit local-presence-audit \
         engagement-audit; do
  script=$(ls skills/$s/scripts/check_*.py)
  python3 "$script" --bundle "$OUT/bundle" --json-out "$OUT/findings-$s.json"
done
```

### 5. Do the parts that need judgement (agent work, not scripts)

**5a. Off-site corroboration.** Follow
`skills/corroboration-freshness-audit/references/offsite-protocol.md`. It uses
web search to establish whether independent sources describe the brand the same
way the site does, whether the name collides with another entity, and what
assistants currently say. Write the findings to `agent-findings.json` in the same
shape the scripts emit. If no search tool is available, skip it and say so —
the composer records the gap in `limitations`.

**5b. Read three pages as a cold arrival.** Open the homepage and two interior
pages from the bundle (`bundle/pages/*.html`, or fetch them). For each, answer in
one line: can a stranger name the company, name the subject of the page, and
find one next step, without scrolling? A "no" that the scripts did not already
catch is a finding — the scripts detect structural absence, you detect
incoherence. Follow the evidence rules below: quote the text you judged.

### 6. Compose the report
```bash
python3 skills/audit-orchestrator/scripts/compose_report.py \
    --bundle "$OUT/bundle" --findings "$OUT"/findings-*.json \
    --agent-findings "$OUT/agent-findings.json" \
    --out "$OUT/report.json" --markdown "$OUT/report.md"
```
The composer de-duplicates, folds symptoms into their cause (`SUPERSEDES`),
assigns `F-nnn` in priority order, scores each half separately, sequences the
fix plan, adds site-type-appropriate proactive recommendations, and writes the
limitations.

`scripts/run_audit.py <url> --out ./audit` runs steps 2, 3, 4 and 6 in one
command; use it, then add step 5 and re-compose.

### 7. Check the report before returning it
- Every finding has an `evidence` string containing at least one observed value
  (a count, a status code, a quoted string, a URL). Delete any that does not.
- No finding contradicts another. If two describe the same defect, keep the
  causal one.
- Severities follow `references/severity-model.md`, not intuition.
- `limitations` names everything that could not be checked.

Then give the user the headline, the critical and high findings with their
fixes, and the path to the full report.

## Output

`report.json` against `references/report-schema.json`. Required by the contest
brief and always present: `site`, `audited_at`, `summary` with counts by
severity, and `findings[]` where each entry has `id`, `title`, `severity`,
`evidence` and `suggested_action`.

This marketplace adds, because a report a non-expert can act on needs them:
`site_profile`, `scope`, per-finding `category` / `confidence` / `mechanism` /
`affected_urls`, `suggested_action.detail` / `.effort` / `.verification`,
`action_plan` (staged fix order), `proactive_recommendations`,
`checks_not_applicable` (what was evaluated and deliberately not fired) and
`limitations`.

`report.md` is the same content for a human reader.

## Degraded modes — never silently

| Missing | Behaviour |
|---|---|
| Headless browser | Render gaps inferred from app-shell markers; those findings drop to `confidence: medium` and the limitation is recorded. |
| Web search | Off-site protocol skipped; on-site corroboration signals still run; limitation recorded. |
| robots.txt / sitemap | Treated as findings in their own right, not as errors. |
| A check script fails | Report the others; name the failure in `limitations`. Never emit a partial report that looks complete. |

## Runtime

Budgeted under five minutes for a typical site: ~30 pages at 1s spacing plus
probes is 40–70s of crawling, rendering (when available) adds up to 60s for six
pages, and all ten check scripts together run in under a second because they
read the bundle rather than the network.
