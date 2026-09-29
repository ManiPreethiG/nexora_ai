# answer-coverage-audit — check reference

Does the site's own content contain an answer worth quoting, independent of
whether existing content is readable or marked up. `scripts/check_answers.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `AQ-NO-QUESTION-CONTENT` | Zero question-shaped headings across the crawl and no FAQPage/QAPage/HowTo structured data | Site is media/docs, any page carries a question-shaped heading, or FAQ/HowTo schema exists | medium |
| `AQ-THIN-ANSWER-PAGE` | A page has question-shaped heading(s) with under 20 words of page content per question | No question-shaped headings exist to evaluate, or the answers are substantive | medium |
| `AQ-NO-COMPARISON-CONTENT` | Site is saas/ecommerce and no page mentions vs/versus/alternative/compare | Site type is not saas/ecommerce, or comparison content already exists | info |
| `AQ-NO-OBJECTION-HANDLING` | Site is saas/ecommerce and no page mentions refunds, guarantees, cancellation or security/compliance | Site type is not saas/ecommerce, or objection-handling content already exists | medium |

## Why this is separate from structured-data-audit's FAQ check

`structured-data-audit` fires `SD-FAQ-OPPORTUNITY` when question-shaped Q&A
content already exists on the page but is not marked up as `FAQPage`. That
check cannot fire — and should not be expected to — on a site where the
content itself does not exist. `AQ-NO-QUESTION-CONTENT` and
`SD-FAQ-OPPORTUNITY` are mutually exclusive by construction: a page counted
by one cannot also be counted by the other, because the second requires
three or more question-shaped headings to already be present. Marking up
content that has not been written yet fixes nothing, which is the reason
this is a distinct skill rather than one more structured-data check.

## Why the no-question-content check excludes media and docs sites

An encyclopedia entry or a documentation page is already organised around
answering the reader's implicit question — "what is this", "how do I do
this" — through ordinary prose and headings, not through literal
question-shaped headings ending in "?". Firing this check on a reference site
would recommend FAQ framing it does not need and, worse, would surface a
suggested action written for a commercial buying decision ("questions people
ask before buying") on a site making no sale at all — precisely the kind of
context-mismatched finding that makes a reader stop trusting the rest of the
report. `site_type in (media, docs)` is excluded entirely rather than merely
downgraded.

## Why comparison and objection checks are site-type gated

Demanding a "vs" page from a brochure site or a nonprofit would be exactly
the kind of context-free expectation this marketplace's design commitments
warn against. Both checks are scoped to `saas` and `ecommerce`, the two site
types where a competing-alternative decision and a refund/security objection
are the default shape of the buying question.
