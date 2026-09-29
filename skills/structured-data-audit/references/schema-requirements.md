# Required properties by type

Properties without which a node cannot answer the question it exists to answer.
A node missing them is frequently dropped by consumers entirely — which is why
incomplete markup is worse than absent markup: the page looks marked up while
providing nothing extractable.

| Type | Required here | The question it answers |
|---|---|---|
| `Organization` | `name`, `url` | Who publishes this |
| `LocalBusiness` | `name`, `address`, `telephone` | Where they are and how to reach them |
| `Product` | `name`, `offers` | What it is and what it costs |
| `Offer` | `price`, `priceCurrency`, `availability` | Can I buy it, for how much, right now |
| `Article` / `BlogPosting` / `NewsArticle` | `headline`, `datePublished`, `author` | Who said this and when |
| `TechArticle` | `headline`, `datePublished` | Is this documentation current |
| `Event` | `name`, `startDate`, `location` | When and where |
| `FAQPage` | `mainEntity` | The question/answer pairs themselves |
| `BreadcrumbList` | `itemListElement` | Where this page sits |
| `Person` | `name` | Who |
| `Recipe` | `name`, `recipeIngredient`, `recipeInstructions` | What do I need and what do I do |
| `JobPosting` | `title`, `datePosted`, `hiringOrganization` | What role, when, with whom |

## Expected types by site type

From `profile.py`. Only types whose absence is a genuine defect.

| Site type | Expected | Classified by |
|---|---|---|
| `ecommerce` | Organization, Product, Offer, BreadcrumbList | Cart/checkout signals with product pages, or `Product` markup |
| `local_business` | LocalBusiness, PostalAddress | Address + phone + opening hours, with at most one product page |
| `saas` | Organization, WebSite | A pricing page, or a trial/demo call to action |
| `media` | Organization, Article | 3+ article pages, outnumbering documentation |
| `docs` | Organization, WebSite | 3+ documentation pages |
| `nonprofit` | Organization | Donation/charity language with no commerce checkout |
| `brochure` | Organization, WebSite | No commerce, publishing or documentation signals |

Classification is ordered most-specific-first and the first match wins. The
reason is recorded in `profile.json.classification_reason` and printed in the
report, so a reader can see — and challenge — the assumption every downstream
expectation rests on.

## The Organization node earns its keep

One block in the site-wide template does most of the work for brand identity:

```json
{
  "@context": "https://schema.org",
  "@type": "Organization",
  "@id": "https://example.com/#organization",
  "name": "Example",
  "url": "https://example.com/",
  "logo": "https://example.com/logo.png",
  "description": "Example is a <category> that <does what> for <whom>.",
  "sameAs": [
    "https://www.wikidata.org/wiki/Q…",
    "https://www.linkedin.com/company/example",
    "https://github.com/example"
  ]
}
```

The `description` should be the same sentence used in the meta description and
on the About page — identically, not paraphrased. Repetition across places is
what makes one description the one that gets returned.
