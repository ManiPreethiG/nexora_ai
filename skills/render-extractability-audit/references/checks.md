# render-extractability-audit — check reference

Stage 2: is the fact present in what came back, as text? Implemented in
`scripts/check_render.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `RX-RENDER-GAP` | With a browser: rendered text exceeds served text by 150+ words and served is under 40% of rendered | The two match within tolerance | high/crit |
| `RX-RENDER-GAP-SIGNALS` | On a gap page, H1, JSON-LD or 3+ internal links exist only after rendering | Signals present in served HTML | high |
| `RX-CLIENT-RENDERED-SHELL` | No browser: under 120 words, an app-shell marker, 3+ external scripts — on the homepage or 2+ pages | One thin interior page only, or pages already carry text | med/high |
| `RX-NOSCRIPT-FALLBACK-ONLY` | 60+ words inside `<noscript>` with under 150 words of ordinary text | Ordinary text present | high |
| `RX-CONTENT-IN-IFRAME` | A content iframe on a page with under 250 words of its own | The iframe is analytics, consent, tag manager, recaptcha, or a video player | high |
| `RX-FACTS-LOCKED-IN-IMAGES` | A fact-bearing page type with 3+ body images and under 220 words; or image filenames/alt matching price, menu, spec, hours, comparison | Text-rich pages | high |
| `RX-FACTS-ONLY-IN-DOCUMENTS` | 3+ linked PDFs/Office files whose linking pages carry under 250 words | Few documents, or text-rich hosts | medium |
| `RX-TABBED-CONTENT-NOT-IN-HTML` | 3+ `aria-controls` references with 60%+ of the target IDs absent from the served HTML | Panels present in HTML and hidden with CSS | high |
| `RX-NO-H1` | 30%+ of pages have no `<h1>` | Pages have one | medium |
| `RX-MULTIPLE-H1` | A page has more than two `<h1>` elements | One or two | low |
| `RX-NO-MAIN-LANDMARK` | 60%+ of pages over 300 words use neither `<main>` nor `<article>` | Landmarks present | low |
| `RX-IMAGE-ALT-MISSING` | 8+ body images and half or more have **no alt attribute at all** | `alt=""` — the correct decorative marker | medium |
| `RX-NO-QUOTABLE-DEFINITION` | No candidate string names the brand near a definition marker | A linking verb, an appositive, or a self-describing name | high |
| `RX-PRICE-NOT-IN-TEXT` | A pricing page with no currency amount in text | The page is not typed `pricing` (e.g. `/legal/pricingpolicy`) | medium |
| `RX-CONTACT-DETAILS-NOT-IN-TEXT` | A contact page exists and 3+ of phone/email/street/postcode appear nowhere on the **site** as text | The details appear anywhere in text | high |

## The render gap is the highest-value check here

It explains the most confusing symptom in this whole domain: a page that is
complete to every human who opens it and empty to every machine that reads it.
Many fetchers read the raw HTTP response and never execute JavaScript, so a
product name, price or description that is injected after hydration does not
exist for them.

The fix is not "stop using JavaScript". It is to server-render or pre-render
the routes that carry answerable facts — product, pricing, docs, location — and
leave the rest client-rendered.

Without a headless browser the gap can only be inferred, so the finding drops to
`confidence: medium` and the evidence string says so. Inferring is better than
skipping: an app shell has a recognisable signature (very little text, a known
root element id, framework bundles) and missing the defect entirely is a worse
error than reporting it with a stated caveat.

## Why "no quotable definition" is a `high`

Assistants answer "what is X" by quoting a sentence that already exists
somewhere. A site whose homepage says only "Wildly comfortable. Super natural."
has supplied nothing to lift, so the answer is assembled from whatever third
parties say — descriptions the brand does not control and cannot correct. The
fix costs one sentence and is often the highest-leverage line on the site.
