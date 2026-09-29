# Off-site corroboration protocol

The half of the corroboration signal that cannot be established from the site's
own bytes. Run by the agent with a web-search tool, after
`scripts/check_freshness.py`.

**Rule for the whole protocol: report what you observed, quoted, with the query
that produced it. If a step cannot run, skip it and record the gap. Never infer
an off-site fact from on-site data.**

Inputs you already have: `bundle/profile.json` gives `brand_name`, `site_type`
and `declared_same_as`; the freshness script's `observations` gives the
authority links found on-site.

## Step 1 — Does the brand exist as a resolvable entity?

Search: `"<brand>"`, then `"<brand>" <category>` (category from the site type or
the homepage definition).

Record which of these exist and carry this site's domain as the official URL:
Wikipedia · Wikidata · LinkedIn company page · Crunchbase · a company registry ·
the dominant review or directory site for this category (G2 or Capterra for
software, Google Maps or Yelp or TripAdvisor for local, an industry directory
otherwise).

- None found → **`CF-NOT-DISCOVERABLE-OFFSITE`**, `high`. Evidence: the queries
  run and what came back instead.
- Found but not linked from the site and absent from `sameAs` → **`CF-UNLINKED-PROFILES`**,
  `medium`. The profiles exist but nothing connects them to the site, so the
  corroboration is not attached to the entity.

## Step 2 — Is the name ambiguous?

Search the bare brand name and look at the first page of results.

- Another organisation, a product, or an ordinary-word meaning dominates →
  **`CF-ENTITY-COLLISION`**, `high`. Evidence: name the competing entity and
  quote what ranks above the brand.
- Confirms or refutes the script's `CF-NAME-AMBIGUITY-RISK`. If refuted, say so
  in `not_applicable` so the composer drops the risk finding.

Fix, when confirmed: pair the name with a category descriptor everywhere
("<brand>, the <category> for <audience>"), create or correct a Wikidata item
carrying this domain as the official website, and add registry-grade `sameAs`
links. Disambiguation is an identity problem; more content does not solve it.

## Step 3 — Do independent sources agree with the site?

Read the top three third-party descriptions of the brand.

- They describe the brand differently from the site's own one-sentence
  definition → **`CF-DESCRIPTION-DRIFT`**, `medium`. Evidence: quote the site's
  description and each third-party one.
- They contain facts that are out of date (old pricing, discontinued products,
  a former name, a departed founder) → **`CF-STALE-FACTS-OFFSITE`**, `high`.
  Evidence: quote the stale claim, its source, and the current truth from the
  site. This is the direct cause of an assistant confidently saying something
  wrong about the brand.

## Step 4 — What do assistants actually say?

Ask the questions the brand's customers would ask. At minimum:

1. `What is <brand>?`
2. `Who are <brand>'s competitors?` / `What are alternatives to <brand>?`
3. `How much does <brand> cost?`
4. `Is <brand> any good?` — or the equivalent for the category
5. A question the brand should own: `best <category> for <audience>`

For each, record: was the brand mentioned; was the description accurate; which
sources were cited; which competitors appeared instead.

- Brand absent where it should appear → **`CF-NOT-CITED`**, `high`. Evidence:
  the question, the answer's substance, and the brands cited instead.
- Brand present but described wrongly → **`CF-MISREPRESENTED`**, `high`.
  Evidence: quote the incorrect claim and the source it came from. Then trace
  it: a misrepresentation nearly always resolves to a specific stale page, an
  uncorrected third-party profile, or an entity collision found in step 2 — and
  the fix belongs to whichever it is.

This step is the only one that measures the outcome the whole audit is about.
Treat a single run as one sample, not a measurement: answers vary between
sessions, and they are personalised by prior context, location and stated
preferences, so a mention in your session does not mean everyone sees it.
State that explicitly in the evidence rather than reporting a single answer as
the brand's standing.

## Step 5 — Emit

```json
{
  "skill": "corroboration-freshness-audit",
  "findings": [ /* the contract in composition.md */ ],
  "not_applicable": [{"check_id": "CF-NAME-AMBIGUITY-RISK",
                      "reason": "searched the bare name; no competing entity ranks above the brand"}],
  "observations": {"offsite_checked": true, "queries_run": ["…"],
                   "profiles_found": ["…"], "assistant_probes": 5}
}
```

Setting `offsite_checked: true` is what tells the composer the gap was closed;
without it the report states in `limitations` that off-site corroboration was
not verified.

## Scope and conduct

Search and read public pages only. Do not create, claim, edit or submit anything
anywhere — that includes directory listings, Wikidata items and review profiles.
The recommendation to create them goes in the report; the brand does it.
