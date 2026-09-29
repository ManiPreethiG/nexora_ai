# trust-legitimacy-audit — check reference

On-site signals of an identifiable, accountable source, independent of
off-site corroboration. `scripts/check_trust.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `TL-NO-HSTS` | Seed is https:// and the http→https redirect response has no Strict-Transport-Security header | Seed is http://, or HSTS is present | low |
| `TL-NO-AUTHOR-BYLINE` | 2+ article pages crawled and 60%+ carry no byline text or JSON-LD author | Fewer than 2 article pages, or bylines/author schema present | medium |
| `TL-NO-LEGAL-PAGES-LINKED` | No link's href or text matches a privacy/terms/legal/cookie-policy pattern anywhere, and no page is typed `legal` | A matching link or a legal-typed page is found | medium |
| `TL-NO-BUSINESS-IDENTITY-DISCLOSED` | Site is ecommerce/nonprofit and no registration/tax-ID/charity-number pattern found in text | Site type is not ecommerce/nonprofit, or a disclosure was found | medium |

## Why this is separate from corroboration-freshness-audit

`corroboration-freshness-audit` asks whether independent third parties
repeat what the site says about itself — an off-site, cross-source question.
This skill asks a narrower, on-site question: does the site's own presentation
carry the concrete signals of an accountable operator? A site can have
excellent off-site corroboration (many independent listings agree on its
name and address) while its own pages carry no visible legal entity, no
author attribution, and a plain-HTTP-adjacent transport configuration — three
findings a corroboration check, which reads off-site sources, cannot produce.

## Why these four and not a general trust score

A subjective "does this feel trustworthy" score would violate the
marketplace's evidence rules — every finding here is instead a specific,
regex- or field-detectable signal with a stated false-positive guard, in
keeping with the rest of the marketplace's design commitments.
