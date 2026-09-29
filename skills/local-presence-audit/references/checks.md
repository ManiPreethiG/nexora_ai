# local-presence-audit — check reference

NAP consistency and hours machine-readability, gated to `site_type ==
"local_business"`. `scripts/check_local.py`.

| Check id | Fires when | Deliberately does not fire when | Sev |
|---|---|---|---|
| `LP-NAP-INCONSISTENT` | 2+ distinct street addresses or 2+ distinct phone numbers found across the site | Site is not local_business, or at most one of each is found | high |
| `LP-HOURS-NOT-IN-SCHEMA` | Hours text found on the site but no openingHours/openingHoursSpecification in any JSON-LD | Site is not local_business, no hours text exists, or schema already has hours | medium |
| `LP-NO-MAP-EMBED-OR-LINK` | No link or iframe to a recognised map provider found anywhere | Site is not local_business, or a map link/embed exists | medium |

## Why this is gated so hard, and why it exists at all

Every check here fires only when `profile.json` classifies the site as
`local_business` (address, phone and opening hours present, with few or no
product pages) — the same false-positive discipline `structured-data-audit`
applies to `Product`/`Offer` markup. A generic corroboration check
(`corroboration-freshness-audit`'s `CF-INCONSISTENT-PHONE`) already flags
3+ phone numbers site-wide regardless of business type; this skill exists
because a local business's NAP mechanism is stricter (even 2 addresses is a
real defect, because local answers are matched against directory listings
field-by-field) and because hours-in-schema and map-anchor presence are
signals no generic check evaluates at all.
