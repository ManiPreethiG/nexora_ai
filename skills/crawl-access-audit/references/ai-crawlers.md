# AI crawlers: the distinction that matters

Two different kinds of automated client are usually lumped together in
robots.txt, and confusing them produces both false positives in an audit and
expensive mistakes on a site.

## Retrieval agents — fetch a page at answer time, in order to cite it

A user asks a question, the assistant searches, fetches a handful of pages, and
builds the answer from what those pages say — often with links back. These
agents are the citation path.

`OAI-SearchBot` · `ChatGPT-User` · `Claude-User` · `Claude-SearchBot` ·
`PerplexityBot` · `Perplexity-User` · `DuckAssistBot` · `MistralAI-User` ·
`Amazonbot` · and the conventional search crawlers whose indexes these systems
query: `Googlebot`, `Bingbot`.

**Blocking these removes the site from AI answers.** Reported as `critical`.

## Training crawlers — collect corpora for model training

`GPTBot` · `ClaudeBot` · `anthropic-ai` · `CCBot` · `Applebot-Extended` ·
`Bytespider` · `meta-externalagent` · `FacebookBot` · `cohere-ai` · `Diffbot` ·
`omgili` · `Timpibot` · `AI2Bot` · `Google-Extended`

Blocking these reduces how well models know the brand from memory, but does not
prevent live citation. It is a legitimate content-licensing decision — many
publishers make it deliberately.

**Reported at `low` severity, for confirmation, with the trade-off stated.**
Never as a defect.

### `Google-Extended` is a control token, not a crawler

It is the one name on either list that never fetches anything — it will never
appear in a server log. Googlebot does all of Google's fetching; `Google-Extended`
only declares whether what Googlebot already took may train or ground Gemini
apps and the Vertex AI Gemini APIs.

Crucially, it does **not** control Google Search or AI Overviews. Google states
that AI is integral to Search, so `Googlebot` is the control for both. Blocking
`Google-Extended` therefore costs a site no search visibility and no AI Overview
presence, which is exactly why it is classed as a training control here and
reported at `low`.

Treating it as a retrieval agent produces a false `critical` on any site that
opted out of Gemini training — a common and deliberate choice, and the default
in Cloudflare's managed robots.txt.

## Why the distinction produces a common, expensive mistake

A site that wants to keep its content out of training data copies a blocklist
from somewhere and blocks everything AI-shaped. The training crawlers were the
target; the retrieval agents were collateral. The brand then disappears from AI
answers entirely, and because the site still ranks normally in search, nobody
connects the two.

The correct shape is to allow retrieval and deny training:

```
User-agent: OAI-SearchBot
Allow: /

User-agent: Claude-User
Allow: /

User-agent: PerplexityBot
Allow: /

User-agent: GPTBot
Disallow: /

User-agent: ClaudeBot
Disallow: /

Sitemap: https://example.com/sitemap.xml
```

## Notes on interpretation

- Agent names and their published behaviour change. `check_access.py` evaluates
  whatever robots.txt actually says for each listed agent rather than
  pattern-matching the word "bot", so a new name is a one-line list addition.
- robots.txt is not access control. A site that must not be read publicly needs
  authentication, not a `Disallow`.
- Blocking at the edge (WAF, CDN bot rules) is invisible in robots.txt and is a
  far more common cause of total invisibility than robots.txt itself. That is
  why the crawler fetches the homepage with three different user-agents and
  compares the results — a 200 for a browser and a 403 for everything else is
  the signature.
