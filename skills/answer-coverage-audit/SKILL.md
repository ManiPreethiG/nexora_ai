---
name: answer-coverage-audit
description: >-
  Check whether the site's content actually contains an answer worth quoting
  for the questions people ask before choosing a brand — question-shaped
  headings paired with a real answer beneath them, comparison content against
  named alternatives, and coverage of the standard purchase objections
  (refunds, guarantees, security). Distinct from render-extractability-audit
  (can an existing fact be read) and structured-data-audit's FAQ-opportunity
  check (is existing Q&A content marked up): this asks whether the
  question-and-answer content exists at all. Reads a crawl bundle and emits
  findings JSON. Use whenever a site is technically crawlable and well marked
  up but still rarely appears in answers to comparison or objection-shaped
  queries.
license: MIT
allowed-tools: Bash, Read
metadata:
  stage: 7
  marketplace: brand-ai-readiness-audit
---

# Answer coverage audit

## When to use

After the pipeline's earlier stages pass — the site is reachable, readable
and identifies itself unambiguously — and the brand still does not appear in
answers to the questions that actually decide a purchase or signup: "is it
worth it", "X vs Y", "can I get a refund", "is it secure". Those answers do
not exist on the site to begin with, no matter how well the existing pages
are marked up.

## Inputs

A crawl bundle directory produced by `audit-orchestrator/scripts/crawl.py`
(contract: `audit-orchestrator/references/crawl-bundle.md`) and
`bundle/profile.json` for site-type gating. This skill performs no network
requests of its own.

## Procedure

```bash
python3 scripts/check_answers.py --bundle ./bundle --json-out findings-answers.json
```

The script runs the checks documented in `references/checks.md`. In summary:

1. **No question content at all** — zero question-shaped headings anywhere,
   and no FAQPage/QAPage/HowTo structured data. A content gap, not an
   extraction or markup gap.
2. **Question posed, not answered** — a question-shaped heading exists but
   the page carries almost no words per question, meaning the heading is a
   placeholder.
3. **No comparison content** (saas/ecommerce, opportunity-level) — no page
   compares the brand against a named alternative.
4. **No objection handling** (saas/ecommerce) — no mention anywhere of a
   refund/cancellation policy, a guarantee, or security/compliance practice.

## Avoiding false positives

- `AQ-NO-QUESTION-CONTENT` excludes `media` and `docs` site types outright —
  an encyclopedia entry or a documentation page already answers the reader's
  implicit question through ordinary prose, and the suggested action is
  written for a commercial buying decision that does not apply there.
- The question-heading pattern is identical to `structured-data-audit`'s
  `QUESTION_HEADING`, so the two skills agree on what counts as a question
  and do not produce contradictory findings from different definitions.
- Comparison and objection-handling checks are gated to `saas`/`ecommerce`
  site types — a brochure or nonprofit site is not expected to publish "X vs
  Y" content, and demanding it there would be exactly the kind of false
  positive this marketplace treats as the main risk.
- The thin-answer check only evaluates pages that already carry a
  question-shaped heading; it cannot fire on a page with none, which keeps it
  from double-counting the same defect as the no-question-content check.

## Output

`{"skill", "site", "findings": [...], "not_applicable": [...], "observations": {...}}`.
Each finding carries `check_id`, `title`, `severity`, `confidence`, `evidence`
(with observed values), `mechanism`, `affected_urls` and `suggested_action`
(`summary`, `detail`, `priority`, `effort`, `verification`).
