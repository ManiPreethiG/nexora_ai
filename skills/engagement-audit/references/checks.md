# engagement-audit — check reference

Stage 5: does the visitor a citation delivers find their answer and a reason to
stay? Implemented in `scripts/check_engagement.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `EN-NO-ARRIVAL-ORIENTATION` | 50%+ of substantive interior pages have neither breadcrumbs nor the brand in heading, title or opening text | Breadcrumbs or brand context present; legal pages excluded | high |
| `EN-NO-NEXT-STEP` | 40%+ of substantive interior pages have under 5 in-body links or no recognisable call to action | Onward paths present | high |
| `EN-INTERRUPTING-OVERLAY` | Newsletter, subscribe, exit-intent or paywall overlay markup | No such markup | medium |
| `EN-CONSENT-WALL` | A consent platform plus full-screen overlay markup on 80%+ of pages | Consent notice without a blocking layer | medium |
| `EN-PAGE-WEIGHT` | Median HTML over 500 KB or 25+ external scripts (`high` at 900 KB / 40 scripts) | Within budget | med/high |
| `EN-RENDER-BLOCKING` | Median 4+ synchronous scripts without `async`/`defer` | Scripts deferred | medium |
| `EN-NO-VIEWPORT-META` | Any page lacks a viewport declaration | All pages declare one | high |
| `EN-UNSIZED-IMAGES` | 10+ images and 70%+ lack width/height | Dimensions set | low |
| `EN-NO-LAZY-LOADING` | 20+ images and 90%+ lack `loading="lazy"` | Lazy loading used | low |
| `EN-THIN-KEY-PAGES` | A pricing, product, about, contact, case-study or FAQ page under 120 words | Substantive pages | medium |
| `EN-HARD-TO-SCAN` | 40%+ of long prose pages have 26+ word average sentences, 3+ paragraphs over 120 words, or ≤1 subheading over 800 words | The page is legal, a homepage, a product page or a category grid — none of which is prose | medium |
| `EN-VAGUE-ABOVE-FOLD` | Homepage first screen has 2+ abstract marketing terms and no concrete category noun | A category noun is present | medium |
| `EN-GATED-FACTS` | Pricing or substance withheld pending contact or a form | Facts published openly | medium |
| `EN-STATE-NOT-IN-URL` | Filter/sort controls present but no internal link anywhere carries a query string | State is reflected in URLs | medium |
| `EN-NO-SITE-SEARCH` | No search input across a site of 12+ pages | Search present, or a small site | low |
| `EN-ACCESSIBILITY-BASELINE` | Missing `lang`, unlabelled form fields, or 10+ unnamed links that are also 20%+ of all links | Attributes present | low/med |

## The model, and why it changes the checks

An assistant that cites a site sends people to **a deep page, not the
homepage**, with a specific question already in mind and none of the context a
designed funnel assumes. They did not choose this site; something suggested it.

So the question this skill asks is not "is the site well designed" but "does an
arbitrary interior page stand on its own?" That reframing is what produces
`EN-NO-ARRIVAL-ORIENTATION` and `EN-NO-NEXT-STEP`, which are the two highest-
severity checks here and which a conventional UX review does not surface,
because from the homepage inward the same pages read perfectly well.

The manual test, worth running on three pages during every audit: open the page
in a private window and ask whether a stranger can name the company, name the
subject, and find one next step within five seconds without scrolling.

## Checks that improve both halves at once

Marked `category: "both"` and counted against both scores:

- **Orientation and breadcrumbs** — context a human needs to know where they
  are is the same context an extractor needs to know what the page is about.
- **Scannable structure** — subheadings let a visitor find the passage they came
  for, and let an extractor quote that passage instead of the whole page.
- **State in the URL** — a filtered view that cannot be linked cannot be cited,
  bookmarked or returned to after a refresh. The visitor loses their work and no
  assistant can ever send anyone to the view that answers the question.
- **Thin key pages** — nothing to quote and nothing to read.
- **Accessibility attributes** — `lang`, labels and link names are what both
  assistive technology and text extractors use to know what an element is.
- **Gated facts** — the fact cannot be cited at all, and the visitor who arrives
  anyway hits a form instead of an answer.

## Two checks written as trade-offs, not defects

`EN-GATED-FACTS` and `EN-CONSENT-WALL` describe deliberate decisions. Gating
lead capture is a business model; consent is often a legal requirement. Both
findings state the cost and leave the decision with the business — for gating,
publish an anchor value openly and keep the form for the detail; for consent,
fix the implementation (a non-blocking banner) rather than removing it.
Findings written as accusations get dismissed along with the accurate ones
around them.
