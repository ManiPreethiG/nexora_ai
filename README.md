# Nexora AI — Autonomous SEO & Citation Optimization Agent

> **Marketing & Content | SEO & Citation Agent**  
> An autonomous AI Visibility & Citation Optimization Agent with persistent episodic memory powered by **Vectorize Hindsight**.

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Memory Layer: Hindsight](https://img.shields.io/badge/Memory-Vectorize%20Hindsight-purple.svg)](https://hindsight.vectorize.io/)

---

## 1. Overview & Problem Statement

Modern search has fundamentally shifted from keyword indexers to **AI Retrieval and Answer Engines** (ChatGPT Search, Perplexity, Google Gemini, Claude, and Copilot). To be quoted as an authoritative citation, a brand or website must navigate an unbroken chain of machine extractability:

```
Bot Access  →  Render Extractability  →  Structured Schema  →  Fact Corroboration  →  Answer Precision  →  Citation
```

### The Problem: The Stateless Auditor Trap
Traditional SEO platforms and AI-readiness auditors are **stateless**:
- **Amnesia Across Runs:** Every audit begins with zero knowledge of prior work. The tool cannot tell if an issue was discovered today or has persisted through six months of engineering sprints.
- **No Verification Loop:** When a developer fixes a `robots.txt` disallow or adds missing `Organization` schema, stateless tools cannot verify whether the fix resolved the underlying blocker.
- **Blind to Regressions:** If an automated deployment overwrites metadata or blocks AI crawlers, stateless tools treat the failure as an ordinary defect rather than an urgent regression of previously working functionality.
- **Static Checklists:** Stateless analyzers generate repetitive, generic recommendations rather than adapting to what historically improved discoverability.

### The Solution: Nexora AI
SEO is a long-term discipline. **Nexora AI** bridges the gap between deep deterministic auditing and continuous longitudinal learning. By integrating **Vectorize Hindsight** as its durable episodic memory layer, Nexora AI remembers past audits, logs user remediation efforts, verifies fix effectiveness upon re-audit, tracks chronic debt, and instantly flags regressions.

---

## 2. System Architecture

Nexora AI is built as a modular multi-agent system combining a deterministic audit backbone with a longitudinal memory and reasoning system:

```
                            USER / DEVELOPER
                                   │
                                   ▼
                            Website URL
                                   │
                                   ▼
                          Nexora Orchestrator
                                   │
                  ┌────────────────┴────────────────┐
                  │                                 │
                  ▼                                 ▼
           Memory Agent (Recall)              Audit Engine
           (Hindsight Memory Bank)            (Single Crawl & Parse)
                  │                                 │
                  │                   ┌─────────────┴─────────────┐
                  │                   ▼                           ▼
                  │             Crawl Access               Structured Data
                  │             Render Engine              Answer Coverage
                  │             Architecture               Trust & Freshness...
                  │                   │                           │
                  │                   └─────────────┬─────────────┘
                  │                                 │
                  └────────────────┬────────────────┘
                                   │
                                   ▼
                        Longitudinal Comparison
                        (Resolved, Persistent, Regressed)
                                   │
                                   ▼
                        Recommendation Agent
                        (Debt & Regression Prioritization)
                                   │
                  ┌────────────────┴────────────────┐
                  │                                 │
                  ▼                                 ▼
           Memory Agent (Retain)             Reporting Engine
           (Durable Snapshot & Events)       (report.json & report.md)
```

### Core Components

1. **Nexora Orchestrator (`nexora.orchestrator`):**
   Coordinates the end-to-end audit lifecycle. Enforces single-crawl efficiency, runs all specialist skills against the cached crawl bundle, and passes historical context to downstream agents.

2. **Memory Agent (`nexora.memory.agent`):**
   Manages interactions with **Vectorize Hindsight**. Generates unique, normalized bank IDs (`site_{domain}`) for each property, executes pre-audit recall of historical snapshots, and persists structured audit summaries.

3. **Comparison Engine (`nexora.analysis.comparison`):**
   Performs deterministic differential analysis between the current audit and the baseline or previous snapshot. Categorizes all findings into:
   - **Resolved:** Defects present previously but confirmed absent in the current crawl.
   - **Persistent:** Ongoing issues, tracked with cumulative cycle counters.
   - **New:** Issues observed for the first time.
   - **Regressed:** Critical alerts for defects previously resolved that have reappeared.

4. **Recommendation Engine (`nexora.recommendations.agent`):**
   Dynamically weights and ranks action items based on persistence debt and regression severity rather than static severity scores alone.

---

## 3. Persistent Memory Architecture with Hindsight

Nexora AI leverages **Vectorize Hindsight** through three fundamental operations:

```
             ┌────────────────────────────────────────────────────────┐
             │                  Vectorize Hindsight                   │
             │           Memory Bank: site_{normalized_domain}        │
             └───────┬───────────────────────────────▲────────────────┘
                     │                               │
              RECALL │                        RETAIN │
     (Historical Context, Fixes)         (Snapshots, Impact, Deltas)
                     │                               │
                     ▼                               │
             ┌───────────────┐               ┌───────────────┐
             │ Pre-Audit Run │               │ Post-Audit Run│
             └───────┬───────┘               └───────▲───────┘
                     │                               │
                     └───────────────►───────────────┘
                                  REFLECT
                    (Regression Detection & Debt Analysis)
```

- **`recall(bank_id, query)`:** Before crawling, retrieves historical snapshots, verified resolutions, and pending user-confirmed implementations.
- **`retain(bank_id, content)`:** Stores durable audit representations, score transitions, and remediation event logs.
- **`reflect(bank_id, prompt)`:** Derives higher-order insights across audit cycles to answer: *Which fixes yielded measurable score gains? Which defects recur most frequently?*

### Graceful Offline Fallback
If remote Hindsight credentials are not configured, Nexora AI automatically activates an internal structured snapshot store (`.nexora/`), guaranteeing zero data loss and uninterrupted local operation.

---

## 4. The 10-Skill Deterministic Audit Engine

Nexora AI evaluates websites against 10 specialized, read-only audit skills:

| Skill | Focus Area | Checks & Metrics |
| :--- | :--- | :--- |
| **`crawl-access-audit`** | Bot Accessibility | robots.txt policies, AI fetchers (OAI-SearchBot, Claude-SearchBot), HTTP status codes, latency, sitemap validity. |
| **`render-extractability-audit`** | Content Readability | Client-side JS rendering gaps, app shells, iframe encapsulation, text-to-code ratios. |
| **`structured-data-audit`** | Identity & Schema | JSON-LD schema validity, `Organization` entity anchors (`sameAs` Wikidata/LinkedIn), breadcrumbs, product schema. |
| **`corroboration-freshness-audit`** | Fact Integrity | Content staleness, publication dates, contradictory entity statements, off-site corroboration signals. |
| **`engagement-audit`** | Landing Experience | Layout stability, mobile usability, interstitials, deep-page orientation, readability. |
| **`site-architecture-audit`** | Discoverability Graph | Orphaned URLs, internal linking structure, redirect chains, crawl depth efficiency. |
| **`answer-coverage-audit`** | Citation Relevancy | Question-shaped headings (`H2`/`H3`), direct factual answers, summary tables, FAQ structures. |
| **`trust-legitimacy-audit`** | Authority & Proof | Authorship attribution, editorial policy, privacy/terms disclosures, contact channels. |
| **`duplicate-canonicalization-audit`** | Authority Dilution | Self-referencing canonicals, duplicate title tags, URL parameter sprawl. |
| **`local-presence-audit`** | Geographic Entity | NAP (Name, Address, Phone) consistency, LocalBusiness schema, Google Maps references. |

---

## 5. Installation & Setup

### Prerequisites
- Python 3.10 or higher
- Git

### 1. Clone the Repository
```bash
git clone https://github.com/ManiPreethiG/nexora_ai.git
cd nexora_ai
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
# Or install core packages directly:
pip install hindsight-client beautifulsoup4 python-dotenv requests
```

### 3. Configure Environment Variables
Copy the sample environment file:
```bash
cp .env.example .env
```

Configure your credentials in `.env`:
```ini
# Managed Hindsight Cloud (https://hindsight.vectorize.io)
HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io
HINDSIGHT_API_KEY=your_hindsight_api_key_here

# Request Timeout
HINDSIGHT_TIMEOUT=5.0
```

---

## 6. CLI Usage Guide

### 1. Execute an AI Visibility Audit
Run a complete audit with longitudinal memory recall and retention:
```bash
python nexora.py audit https://example.com --out ./audit_results
```
*Key Options:*
- `--out <dir>`: Output directory for `report.json` and `report.md` (default: `./audit`).
- `--max-pages <int>`: Maximum pages to crawl (default: `30`).
- `--delay <float>`: Polite delay between requests in seconds (default: `1.0`).
- `--no-history`: Disable Hindsight memory integration and run as a standalone audit.

### 2. Inspect Historical Timeline & Memory
Retrieve past audit snapshots, score trajectories, and learned insights for any domain:
```bash
python nexora.py history https://example.com
```

### 3. Log a User-Confirmed Remediation Action
Record an engineering fix deployed to address a specific audit finding:
```bash
python nexora.py record-fix https://example.com \
    --fix CA-AI-RETRIEVAL-BLOCKED \
    --notes "Updated robots.txt to allow AI retrieval bots (OAI-SearchBot, Claude-SearchBot)"
```

### 4. Compare Two Existing Audit Reports
Perform a differential comparison between two standalone audit directories:
```bash
python nexora.py compare --audit1 ./audit_run_1 --audit2 ./audit_run_2
```

### 5. Run Multi-Cycle Learning Simulation
Execute a simulated sequence demonstrating the complete memory lifecycle (Baseline $\to$ Fix Verification $\to$ Regression Detection):
```bash
python nexora.py simulate
```

---

## 7. Audit Report Output

Every audit produces two standardized deliverables in the designated output directory:

### `report.json`
A machine-readable artifact containing the comprehensive crawl inventory, raw evidence for every finding, deterministic scores, and historical memory metadata:
```json
{
  "site": "example.com",
  "audited_at": "2026-09-29T08:00:00Z",
  "summary": {
    "ai_discoverability_score": 72,
    "on_site_engagement_score": 85,
    "total_findings": 2
  },
  "historical_context": {
    "is_first_audit": false,
    "audit_number": 2,
    "score_changes": {
      "ai_discoverability_score": 21
    },
    "resolved_findings": ["CA-AI-RETRIEVAL-BLOCKED", "SD-NO-ORGANIZATION"],
    "persistent_findings": ["AQ-NO-QUESTION-CONTENT"],
    "regressions": []
  }
}
```

### `report.md`
An executive scorecard formatted in GitHub-flavored Markdown featuring:
- Score gauges and categorized health indicators.
- Longitudinal trajectory tables showing progress across cycles.
- Verified resolution confirmations and persistence debt warnings.
- Prescriptive remediation steps ranked by impact.

---

## 8. Verification & Quality Assurance

Nexora AI includes a strict, automated verification suite:

```bash
# 1. Validate skill catalog manifest and schema integrity
python tests/validate-marketplace.py

# 2. Execute defect detection self-test against local seeded fixture
python tests/run_selftest.py

# 3. Run unit and scenario test suite (Scenarios A through G)
python -m unittest tests/test_nexora.py
```

### Validated Behavioral Scenarios:
- **Scenario A:** First-audit baseline initialization (no prior state, zero synthetic diffs).
- **Scenario B:** Resolved defect detection and evidence retirement.
- **Scenario C:** Persistent defect tracking with consecutive recurrence counters.
- **Scenario D:** Newly introduced barrier identification.
- **Scenario E:** Regression detection across sequential audit states.
- **Scenario F:** Non-causal score delta attribution.
- **Scenario G:** Separation between user-reported assertions and empirical crawler verification.

---

## 9. Safety, Governance & Compliance

- **Read-Only Inspection:** Nexora AI never performs modifying network requests, mutations, form submissions, or authentication bypasses.
- **Strict Crawl Politeness:** Enforces a minimum 1.0-second request interval, respects `robots.txt` directives, honors `Crawl-delay`, and caps recursive BFS crawl depth.
- **Data Privacy:** Raw page bodies and HTML payloads are processed locally and discarded. Only anonymized, structured findings and score metrics are persisted to Hindsight memory banks.
- **Evidence-First Truth Model:** Memory provides historical context and prioritizes recommendations; empirical crawler evidence always takes precedence over historical memory.

---

## 10. License

This project is licensed under the [MIT License](LICENSE).
