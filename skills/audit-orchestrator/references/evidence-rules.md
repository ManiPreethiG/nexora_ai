# Evidence rules

Every finding is a claim about a specific site. These rules exist so the report
can be trusted, and so a reader can verify any line of it without re-running the
audit.

## 1. Every finding contains at least one observed value

An `evidence` string must contain a count, a status code, a measurement, a URL,
or a quoted fragment of the page. If a check cannot produce one, it does not
fire.

- Good: `"4 of 7 crawled pages are marked noindex, e.g. https://x.com/about (`noindex, nosnippet`)."`
- Bad: `"The site has indexing problems."`

## 2. State the denominator

`"66 of 74 body images"` tells a reader how widespread the problem is.
`"66 images"` does not, and invites a reader to over- or under-react.

## 3. Never report an inference as an observation

If the render gap was inferred from app-shell markers because no browser was
available, the evidence says so *inside the evidence string*, and the finding
carries `confidence: medium`. The reader must not have to consult the
limitations section to learn what was actually measured.

## 4. Record what was checked and did not fire

`not_applicable` entries carry the check id and the reason. Without them, a
short report is ambiguous — a reader cannot tell a clean site from a shallow
audit. They also document the false-positive guards: "no product pages were
found on this site" is the reason `Product` markup was not demanded.

## 5. One defect, one finding

If two checks describe the same underlying problem, the causal one is reported
and the other is folded into it (`SUPERSEDES` in `compose_report.py`). Reporting
a cause and three of its symptoms as four findings inflates the severity counts
and buries the fix that matters.

## 6. Say why it matters, mechanically

Every finding carries a `mechanism`: the specific way this defect interferes
with retrieval, citation or the visit. Not "this is best practice" — the actual
causal chain. A fix that is not mechanism-sound is guesswork, and a reader who
understands the mechanism can adapt the fix to their own stack.

## 7. Make the fix checkable

`suggested_action.verification` states how to confirm the fix worked, in terms
the reader can run — a `curl` command, a validator, a re-fetch. A
recommendation nobody can verify is a recommendation nobody will finish.

## 8. Where a defect is a trade-off, say so

Gated pricing, blocked training crawlers and consent walls are decisions, not
mistakes. Report the cost, state the trade-off, and let the business decide.
Findings written as accusations get dismissed along with the accurate ones
around them.
