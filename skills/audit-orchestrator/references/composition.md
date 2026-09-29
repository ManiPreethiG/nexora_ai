# How the marketplace composes

## Why it is split this way

The decomposition follows the causal chain that decides whether a brand appears
in an AI answer. Each stage is a different failure mode with a different fix and
a different owner, and each is only reachable if the one before it succeeds:

```
reached → led around → read → understood → answerable → believed → trusted → not diluted → locally consistent → worth staying for
   │           │          │         │            │           │          │           │                │                   │
crawl-      site-      render-  structured-   answer-   corroboration- trust-    duplicate-        local-           engagement-
access   architecture  extract     data       coverage    freshness  legitimacy canonicalization  presence            audit
```

A site can pass every stage but one and still be invisible. That is the whole
argument for splitting them: "the brand does not appear in AI answers" is one
symptom with ten unrelated causes, and a single skill that mixes them produces
a report where the reader cannot tell which one they have. Five of the ten
(`site-architecture`, `answer-coverage`, `trust-legitimacy`,
`duplicate-canonicalization`, `local-presence`) sharpen a stage the original
five skills only covered coarsely or not at all — see each skill's own
`references/checks.md` for exactly what it adds and why it could not simply be
one more check inside the skill it sits next to.

The boundaries are load-bearing, not cosmetic:

- **Different evidence.** `crawl-access` reads response metadata;
  `site-architecture` diffs the sitemap against the link graph;
  `render-extractability` diffs two renderings of the same page;
  `structured-data` parses JSON-LD; `answer-coverage` counts words per
  question; `corroboration-freshness` needs off-site search;
  `trust-legitimacy` reads security headers and bylines;
  `duplicate-canonicalization` compares pages pairwise; `local-presence`
  cross-checks text against schema; `engagement` reads the page as a visitor.
- **Different fixes and owners.** robots.txt and WAF rules are infrastructure.
  Internal linking is information architecture. Render gaps are the front-end
  build. Structured data is templates. Answer content is copywriting.
  Corroboration is marketing and PR. Trust disclosures are legal/ops.
  Canonicalization is templates and redirects. Local listings are ops.
  Engagement is content and design. A report that separates them can be
  handed to ten people; one that does not goes to nobody.
- **Different severity meaning.** An early-stage failure (reachability) voids
  everything downstream; a late-stage one (engagement) costs value on traffic
  that is otherwise working.
- **Independently useful.** `crawl-access-audit` alone answers "why are we
  invisible". `engagement-audit` alone answers "why doesn't cited traffic
  convert". `local-presence-audit` alone answers "why do our map listings
  disagree with our site". Each is a valid standalone invocation.

## What the entrypoint actually does

Composition is not "call five things and concatenate". The entrypoint owns five
jobs no individual skill can do:

1. **Crawl once.** Ten skills fetching independently would be ten times the
   requests, ten inconsistent views of a changing site, and ten times the
   runtime. The bundle is the shared substrate.
2. **Profile first.** The site type is computed once, before any check runs, and
   every skill consults it. Correct expectations are the difference between an
   audit and a checklist.
3. **Resolve overlap.** `SUPERSEDES` folds symptoms into causes: a site-wide
   `Disallow: /` explains the missing sitemap; `SD-NONE` explains every other
   schema finding; a render gap explains the missing H1 and the missing links.
   Without this the severity counts inflate and the real fix is buried.
4. **Sequence the plan.** The `action_plan` orders work by pipeline stage, not
   by severity, because fixing structured data on pages a crawler is blocked
   from is wasted effort.
5. **State the limits.** Only the entrypoint knows which capabilities were
   available, which skills ran, and which checks were suppressed — so only it
   can honestly describe what the report does not cover.

## Findings contract

Every skill emits:

```json
{
  "skill": "crawl-access-audit",
  "site": "example.com",
  "findings": [{
    "check_id": "CA-AI-RETRIEVAL-BLOCKED",
    "title": "robots.txt blocks the agents that fetch pages to cite them",
    "category": "discoverability | engagement | both",
    "concern": "crawl-access-audit",
    "severity": "critical | high | medium | low | info",
    "confidence": "high | medium | low",
    "evidence": "…observed values…",
    "affected_urls": ["…"],
    "mechanism": "…why this breaks retrieval or the visit…",
    "suggested_action": {
      "summary": "…what to change…",
      "detail": "…how…",
      "priority": "high",
      "effort": "low | medium | high",
      "verification": "…how to confirm it worked…"
    }
  }],
  "not_applicable": [{"check_id": "…", "reason": "…why it did not apply…"}],
  "observations": {"…skill-specific measurements…": "…"}
}
```

`id` (`F-nnn`) is assigned by the composer, never by a skill — ids must be
stable across the whole report and ordered by priority, which only the composer
can see.

## Adding a skill

1. Create `skills/<name>/SKILL.md` satisfying the agentskills.io spec.
2. Read the bundle; do not fetch. If a check genuinely needs the network, put it
   in a protocol document for the agent, as `corroboration-freshness-audit`
   does, rather than adding requests to a script.
3. Emit the contract above. Populate `not_applicable` — it is how the report
   distinguishes clean from unchecked.
4. Register it in `marketplace.json`.
5. Add any cause/symptom relationship to `SUPERSEDES` in `compose_report.py`.
6. Add its true positives to `tests/fixture-site` and `tests/run-selftest.sh`.
