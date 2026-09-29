# Severity model

Severity answers one question: **how much of the pipeline does this break?**
It is not a measure of how annoying the problem is, or how hard it is to fix.

Retrieval and citation happen in order. Each stage depends on the one before it,
so a failure early in the chain is worth more than several failures late in it.

| Severity | Definition | Examples |
|---|---|---|
| `critical` | The content cannot be reached or read by AI retrieval **at all**. Everything downstream is moot. | robots.txt blocking retrieval agents; a WAF returning 403 to non-browser clients; a fully client-rendered site with no server HTML; sitewide `noindex`. |
| `high` | The content is reachable, but a key fact is not extractable, or a major trust/identity signal is absent. The page can be found and still not be usable as a source. | Facts only in images or iframes; no quotable definition of the brand; `nosnippet`; no `sameAs` identity anchors; interior pages with no orientation. |
| `medium` | Materially reduces the chance of being selected, or the chance a visitor stays — but neither is prevented. | Missing breadcrumbs; undated content; heavy pages; thin key pages; gated facts. |
| `low` | Narrow scope, or a weak signal. Worth fixing when nearby work is happening. | Stale copyright year; unsized images; a training-crawler block to confirm. |
| `info` | No defect. An opportunity that would strengthen discoverability or engagement. | `/llms.txt`; publishing an original citable data asset. |

## Confidence is separate from severity

`confidence` records how sure the *detection* is, and never adjusts the
severity — a critical problem detected at medium confidence is still critical if
real, and the reader needs both numbers to decide what to verify first.

| Confidence | When |
|---|---|
| `high` | Directly observed: a status code, a parsed directive, a counted absence. |
| `medium` | Inferred from a proxy, or measured under a degraded capability — a render gap inferred without a browser, a name collision inferred from the name alone. |
| `low` | Pattern-matched heuristics on prose. Used sparingly; a `low`-confidence finding must say what would confirm it. |

## Scoring

Two scores, because the two halves fail independently and the fixes belong to
different teams.

```
score = max(0, 100 - Σ (severity_weight × confidence_factor))

severity_weight:   critical 25 · high 12 · medium 5 · low 2 · info 0
confidence_factor: high 1.0 · medium 0.7 · low 0.4
```

`ai_discoverability_score` counts findings whose `category` is
`discoverability` or `both`; `on_site_engagement_score` counts `engagement` or
`both`. Findings marked `both` are counted in each, deliberately: a page that
gives a visitor no context also gives an extractor no context, and the cost is
paid twice.

The score is a summary for a non-expert, not a measurement. The findings are the
deliverable.

## Priority, effort and sequence

`suggested_action.priority` mirrors severity. `suggested_action.effort`
(`low`/`medium`/`high`) is an independent estimate, so that within one severity
band the cheap fixes surface first.

The `action_plan` in the report is sequenced by pipeline stage rather than
sorted by severity: reachable → readable → unambiguous → corroborated → worth
staying for. Adding structured data to a page a crawler is blocked from is
wasted work, and the plan should never suggest it before the block is cleared.
