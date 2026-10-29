# RAVZ Product Hunter

An AI-powered product research and validation system for Mercado Livre
Brazil. It evaluates ecommerce product opportunities across demand, trend,
competition, margin, supplier viability, logistics, and risk, and produces an
explainable **Opportunity Score (0-100)**.

This project is built both as a real research tool and as a portfolio piece
demonstrating AI agents, APIs, automation, and software engineering
practices in Python.

**Core principle:** the system never claims a product is guaranteed to
sell. It only produces a measurable, explainable score based on the data it
is given.

## Phase 1 scope

Phase 1 validates the architecture and scoring engine before any live data
integration. It intentionally does **not** include marketplace scraping,
API integrations, agents, a database, or automation (n8n/MCP) — those come
in later phases.

What Phase 1 provides:

- `src/models.py` — `Product`, `ComponentScores`, and `OpportunityResult`
  data models
- `src/scoring.py` — the weighted scoring engine and opportunity
  classification
- `tests/test_scoring.py` — unit tests covering the scoring math

All scores are supplied manually (e.g. in a script or test) rather than
fetched from a marketplace.

## Phase 2 scope

Phase 2 adds a manual input path on top of the Phase 1 scoring engine: a
terminal CLI that asks the user for a product's data and scores, then
prints a full opportunity report. It still does **not** include any
marketplace scraping, API integrations, agents, a database, or automation
— it reuses the existing `Product`, `ComponentScores`, and
`score_opportunity()` from Phase 1 without duplicating any scoring logic.

What Phase 2 provides:

- `src/main.py` — the Manual Product Analyzer CLI (presentation layer
  only): prompts for product name, category, and the seven component
  scores; validates and re-asks on invalid input; builds and prints the
  final report.
- `tests/test_main.py` — unit tests for the CLI's reusable
  parsing/validation/formatting functions, using an injectable
  `input_func` instead of mocking the real `input()`.

### Run the analyzer

```bash
python -m src.main
```

### Example

```
RAVZ Product Hunter -- Manual Product Analyzer
Enter the product details and scores below.

Product name: Wireless Mouse
Category: Electronics
Demand score (0-100): 85
Trend score (0-100): 70
Competition score (0-100): 40
Margin score (0-100): 60
Supplier score (0-100): 55
Logistics score (0-100): 90
Risk score (0-100): 15

==================================================
OPPORTUNITY REPORT
==================================================
Product: Wireless Mouse
Category: Electronics

Component scores:
  Demand:      85.0
  Trend:       70.0
  Competition: 40.0
  Margin:      60.0
  Supplier:    55.0
  Logistics:   90.0
  Risk:        15.0

Weighted breakdown:
  Demand       contributes 25.5
  Trend        contributes 14.0
  Competition  contributes 9.0
  Margin       contributes 9.0
  Supplier     contributes 5.5
  Logistics    contributes 4.5
  Risk         contributes 4.25

Opportunity Score: 71.75
Classification: Worth deeper investigation

Recommendation: Investigate further before committing.
==================================================
```

If you type an invalid score (non-numeric, or outside 0-100), the CLI
prints `Invalid input: ...` and asks the same question again instead of
crashing.

## Phase 3 scope

Phase 3 adds the project's first real external data integration: a
Mercado Livre client that retrieves, validates, maps, and displays real
marketplace search results. It intentionally does **not** compute an
Opportunity Score from this data yet, and does **not** add a database,
agents, scraping, n8n, or MCP — those come later. The goal of this phase
is only to build a reliable, well-tested boundary between the application
and an external API before any agent depends on it.

What Phase 3 provides:

- `src/integrations/mercadolivre.py` — the only module that knows about
  HTTP, JSON, or the Mercado Livre API. Exposes a single public function,
  `search_products(query, limit=10)`, that returns a list of
  `MercadoLivreItem` (a dataclass distinct from the Phase 1
  `Product`/`ComponentScores`/`OpportunityResult` models). Every other
  module only ever imports this function, never `requests` directly.
- `tests/test_mercadolivre_integration.py` — unit tests using a fake
  `requests.get` (no live network calls), covering success, missing
  optional fields, empty results, timeout, connection failure, every
  non-200 status code, malformed JSON, a missing `results` field, and
  invalid `query`/`limit` arguments.
- A new CLI menu in `src/main.py`:
  ```
  1. Manual Product Analyzer
  2. Search Mercado Livre
  ```
- `docs/MAINTENANCE.md` — a recurring checklist for keeping this
  integration (and its dependencies) healthy over time, since external
  APIs change independently of this codebase.

### Endpoint used

```
GET https://api.mercadolibre.com/sites/MLB/search?q=<query>&limit=<limit>
```

### Documentation status (re-verified — corrected from this phase's first draft)

The current official "Itens e Buscas" documentation
(developers.mercadolivre.com.br/pt_br/itens-e-buscas, last updated by
Mercado Livre on **2026-08-31**) documents `/sites/{SITE_ID}/search`
**only** for `nickname` and `seller_id` lookups, and every example for
that endpoint sends `Authorization: Bearer ACCESS_TOKEN`.

**A free-text `q` parameter against this endpoint is NOT part of that
documented contract.** The officially documented `q` parameter belongs
to a different endpoint, `/products/search` (a catalog/GTIN lookup used
for publishing flows, out of scope here) — not to
`/sites/{SITE_ID}/search`.

**Classification: experimental / not officially documented**, kept only
because it's useful for this learning phase to practice safe HTTP, error
handling, and data mapping end to end — not because Mercado Livre
guarantees this behavior. It may change shape, stop working, or be
restricted further at any time without notice.

### Authentication

Not previously verified correctly — corrected here: because every
current official example for `/sites/{SITE_ID}/search` requires
`Authorization: Bearer ACCESS_TOKEN`, authentication should be treated
as **expected** by Mercado Livre for this endpoint family, even though
it's unverified for this module's undocumented `q` usage specifically.
This client sends `Authorization: Bearer <token>` automatically if
`MERCADO_LIVRE_ACCESS_TOKEN` is set in the environment; it still runs
without one (never hardcoded, never committed — see `.env.example`), but
a request without a token is more likely to fail.

### `available_quantity` is a reference bucket, not exact stock

Mercado Livre's public item/search resources report `available_quantity`
as a **reference bucket**: a real stock count inside a range is rounded
down to that range's floor before being published (e.g. a real stock of
51-100 units is returned as the reference value `50`). This project
treats it as "at least roughly this many," never as precise inventory,
and the CLI labels it accordingly
(`available quantity (reference, not exact stock)`).

### Manual validation result (re-run for this correction pass)

With no `MERCADO_LIVRE_ACCESS_TOKEN` configured, a direct call to this
endpoint with `q=bebedouro automatico gatos` returned:

```
status_code: 403
body: {"message":"forbidden","error":"forbidden","status":403,"cause":[]}
```

No token was used (none is configured in this environment), and no
results were returned. The integration layer surfaced this as a clear,
handled `MercadoLivreResponseError` — not a raw traceback — but the
failure means this phase could **not** demonstrate a live successful
`q` search. Whether a valid token and/or a non-blocked network would
succeed is unverified; see `docs/MAINTENANCE.md` for what to re-check.

### Run a search

```bash
python -m src.main
```
Then choose option `2` and enter a search term, e.g. `bebedouro automatico gatos`.

### Limitations of this phase

- No automatic Opportunity Score is computed from Mercado Livre results —
  this phase only proves safe retrieval, validation, mapping, and display.
- Only fields actually present in the API response are shown; anything
  Mercado Livre doesn't return for an item is simply omitted, never
  guessed.
- The free-text `q` search used here is **experimental and undocumented**
  for this endpoint — see "Documentation status" above. Do not treat it
  as a stable contract.
- Live calls in this environment currently return `403 Forbidden`
  without a token; this has not been re-tested with a valid token or from
  a different network (see `docs/MAINTENANCE.md`).
- `available_quantity`, when returned, is a rounded reference bucket, not
  exact stock — see above.

## Phase 4 scope

Phase 4 adds the project's first **trend-data** source, intended to
eventually feed the Trend dimension of the Phase 1 Opportunity Scoring
Engine (it does **not** do so yet — see "Engineering rule" below). It
also introduces a deterministic, provider-independent trend-analysis
layer and a provisional (unvalidated) Trend Score.

### Source evaluation (done before writing any code)

Three candidates were evaluated for Brazil-relevant, product-level
search-interest data:

1. **Google Trends official API** — rejected: still a closed, invite-only
   alpha (announced July 2025); no general access exists.
2. **pytrends** (unofficial Google Trends client) — rejected for two
   independent reasons: its GitHub repo was archived by its maintainers
   on 2025-04-17 (unmaintained, frequent `429`s from cloud IPs), **and**
   its hard dependency on `pandas` could not even be imported in this
   project's Windows environment (`pandas`'s native extension was
   blocked by a local Application Control Policy) — confirmed by
   actually trying it, not assumed.
3. **Wikipedia Pageviews API** — official, free, stable, no auth, and
   confirmed working in this environment, but it measures pageviews on
   a Wikipedia *article*, not search interest for an arbitrary product
   query — rejected as not fit-for-purpose for ecommerce product terms
   (most products have no Wikipedia article).
4. **Apify Actor `themineworks/google-trends-pro`** — **selected**.
   Apify's own REST API is official, documented, and callable with
   plain `requests`/JSON (confirmed working in this environment). The
   specific Actor is a third-party, unofficial Google Trends scraper
   running on Apify's infrastructure (not ours) — real but isolated
   risk, tracked in `docs/MAINTENANCE.md`.

### Source used

- **Platform:** Apify REST API (official, documented) —
  `POST https://api.apify.com/v2/actors/themineworks~google-trends-pro/run-sync-get-dataset-items`
- **Actor:** `themineworks/google-trends-pro` — **unofficial**, third-party,
  wraps Google Trends. Apify-the-platform is low-risk; this specific
  Actor is medium-risk (could break or be abandoned without notice,
  no versioned schema guarantee).
- **Authentication:** `Authorization: Bearer <APIFY_API_TOKEN>` header.
  The token is loaded from a local `.env` file via `python-dotenv`
  (`src/config.py`), never hardcoded, never logged, never committed —
  only `APIFY_API_TOKEN=` (empty) lives in `.env.example`.
- **Observed quirk:** this endpoint returns `HTTP 201 Created` on
  success, not `200` — the integration treats any `2xx` as success.
- **Cost:** pay-per-event, confirmed live at **$0.0025 per keyword
  report**, within Apify's free $5/month platform credit (~2,000 free
  reports/month) — effectively free for this project's current usage.

### Data semantics (read before trusting any number)

Google Trends values are a **relative interest index from 0 to 100**,
scaled to the peak interest within that keyword's own result set. They
are **not** absolute search volume, not a number of searches, not
market size, and not a number of buyers. A value of 100 for one keyword
and 100 for a different keyword do not represent the same real search
volume — never compare raw values across unrelated keywords.

### Architecture

```
User / CLI
  -> src/integrations/apify_trends.py   (HTTP/JSON, Apify-specific, isolated)
  -> src/trend_models.py                 (provider-neutral internal data)
  -> src/trend_analysis.py               (deterministic, no HTTP/Apify knowledge)
  -> Trend metrics + provisional Trend Score
  -> (later phase) Opportunity Scoring Engine
```

`src/trend_analysis.py` only ever imports `src.trend_models` — never
Apify, `requests`, or tokens — so the data source can later be swapped
(official Google API, a different Actor, another provider) without
touching the analysis logic.

### Provisional Trend Score — NOT validated, NOT wired into scoring

A deterministic 0-100 score is computed from `average_interest`,
`recent_average`, `previous_average`, `percentage_change`, `direction`,
and `volatility` (see `src/trend_analysis.py` module docstring for the
exact formula and all weight/scale constants). It intentionally
combines more than raw average interest: recent-vs-previous growth, a
sustained-direction bonus/penalty, the current interest level, and a
volatility penalty for erratic series. It is explicitly labeled
**PROVISIONAL** everywhere it's shown — it has not been validated
against real sales outcomes, and the Phase 1 Opportunity Scoring
Engine's weights are unchanged by this phase.

### Run it

```bash
python -m src.main
```
Choose option `3`, enter a search term, and optionally override the
default `geo` (`BR`) and `timeframe` (`today 12-m`).

### Live validation performed

| Query | Result |
|---|---|
| `bebedouro automatico gatos` (long-tail, exact phrase from the task) | Succeeded, but nearly all zero interest (1 non-zero point out of 53) — an honest "not enough search volume for this exact phrase," not a failure |
| `bebedouro para gatos` (broader, still ecommerce-relevant) | Succeeded with real, varied data: 53 points, 12 related "top" queries, 2 "rising" queries, 27 regions |

Both are genuine live Apify runs — nothing here is fabricated or mocked.

### Limitations

- The provisional Trend Score has no validation against real outcomes —
  treat it as a starting point, not a verdict.
- The Actor is unofficial and third-party; `docs/MAINTENANCE.md` records
  a known degraded-reliability period since 2026-07-30 due to Google-side
  rate limiting.
- Long-tail product phrases may simply have too little Google Trends
  volume to produce a useful signal (as seen above) — this is a
  limitation of the underlying data, not of this integration.
- Windows console output for non-ASCII characters (e.g. "São Paulo")
  may display mangled in some terminals due to codepage, not data
  corruption — the underlying string is correct UTF-8.

## Phase 5 scope

Phase 5 adds a deterministic **Demand Analysis** layer that turns the
signals already available from Phases 3-4 into an explainable,
**provisional** Demand Score — without building an AI agent yet. This
is deterministic analytics over structured data, not an LLM.

### Source evaluation (done before writing the scoring formula)

Checked live, not assumed:

- **Trend/search-interest (Apify, Phase 4):** working. Provides trend
  score, direction, average/recent interest, related-query counts,
  regional spread.
- **Marketplace (Mercado Livre, Phase 3):** still `403 Forbidden` live,
  same blocker documented since Phase 3 — unavailable right now.
- **Never available from any current source, by design:** sales
  volume, number of buyers, revenue, conversion rate, absolute search
  volume. These are never estimated or fabricated — they simply don't
  exist as fields.

Because only one source family is currently reachable, this phase's
Confidence Score is structurally capped until marketplace data returns
— that cap is the point, not a bug.

### Hardening pass (post-implementation correction)

Two modeling bugs were found and fixed after the first live validation:

1. **Empty section ≠ confirmed zero.** The Apify Actor can return
   `related_queries`/`interest_by_region` empty on a call where other
   sections succeed (same Phase 4 inconsistency, observed again here).
   The original code scored an empty section as a literal `0`,
   artificially dragging the Demand Score down. Fixed by adding
   `interest_over_time_available` / `related_queries_available` /
   `regional_interest_available` flags to `TrendData` (set by the
   integration layer, which is the only place with enough context to
   judge this) — `demand_models.py` now reports an unavailable section
   as `None` (excluded, weights renormalized), never `0`.
2. **Confidence was too high for one source family.** A real run with
   only the trend source available produced Confidence 67.5 — looking
   like solid multi-source corroboration when it was one witness's
   testimony, however complete. Fixed with a hard cap: `min(internal
   quality, 100 * source_coverage)`. See "Demand Score vs. Confidence
   Score" below for the formula and the completeness-vs-independence
   distinction behind it.
3. **`marketplace_result_count` was actually a page size.** `len(search_products(...))`
   is capped by the `limit` parameter — it is not a total marketplace
   result count, and scoring it would score our own query parameter,
   not demand. Renamed to `marketplace_sample_size` and permanently
   excluded from the Demand Score until a genuine total-result-count
   field is extracted from Mercado Livre.

### Demand Score vs. Confidence Score

These answer two different questions and are always reported
separately:

- **Demand Score** — "how strong does demand appear, based on the
  evidence we have?"
- **Confidence Score** — "how much evidence do we actually have?"

A Demand Score of 80 backed by one thin source (Confidence 35) is not
the same situation as a Demand Score of 80 backed by multiple
well-populated sources (Confidence 90).

**Data completeness is not source independence.** `interest_over_time`,
`related_queries`, and `interest_by_region` are all derived from the
same Apify/Google Trends call — having all three populated is good
*completeness* (one witness's testimony heard in full), not three
independent witnesses. Only a genuinely different source family (e.g.
Mercado Livre) is a second witness. Confidence must be bounded by the
number of independent families, not inflated by how much detail one
family provided.

### Formula (see `src/demand_analysis.py` module docstring for full detail)

Four components, each 0-100, blended by weighted average **over
whichever are actually available** (missing/unreliable sections are
excluded and weights renormalized — never defaulted to a neutral guess,
never scored as zero just because a section came back empty):

| Component | Base weight | From |
|---|---|---|
| Trend | 0.40 | recent search interest + trend direction |
| Breadth | 0.25 | related + rising query counts (rising weighted at half — a weaker proxy alone); excluded (not zero) if the provider's related-query section was unreliable |
| Regional | 0.20 | number of BR regions showing interest; excluded (not zero) if the provider's regional section was unreliable |
| Marketplace | 0.15 | **permanently excluded** — `marketplace_sample_size` is a page-capped item count, not a total result count; see Hardening pass above |

**Confidence** is a two-stage model, not a flat weighted sum:

```
internal_quality_score = 0.6 * completeness_score + 0.4 * volume_score
coverage_cap            = 100 * source_coverage
confidence_score        = min(internal_quality_score, coverage_cap)
```

With only 1 of 2 source families available, `coverage_cap = 50` —
confidence can never exceed 50 no matter how complete or voluminous
that one source's data is. With 2 of 2, the cap is 100 and
`internal_quality_score` alone determines the result.

### What's new

- `src/demand_models.py` — `DemandSignals`, `build_demand_signals()`
- `src/demand_analysis.py` — `DemandAnalysisResult`, `analyze_demand()`
- `src/main.py` — CLI option `4. Analyze Demand`
- `tests/test_demand_models.py`, `tests/test_demand_analysis.py`

### Run it

```bash
python -m src.main
```
Choose option `4`, enter a search term, and optionally override `geo`
(default `BR`).

### Important design rule

The Demand Score is **not** fed into the Phase 1 Opportunity Scoring
Engine yet — this phase only builds and validates the Demand Analysis
component in isolation.

### Limitations

- Confidence is structurally capped at 50 right now because only one
  of two source families is reachable — not a defect, an honest
  reflection of current coverage (see Hardening pass above).
- The Apify Actor's known per-section inconsistency (Phase 4) means
  even a successful trend fetch can return an empty related-query or
  regional section on a given call. This is now correctly treated as
  **unavailable** (excluded, not scored), never as a confirmed zero —
  a live run during the hardening pass hit exactly this case
  (`related_queries` empty, `interest_over_time`/`interest_by_region`
  populated) and the report correctly showed "Breadth: not available"
  rather than a misleadingly low number.
- `marketplace_sample_size` is for display/evidence only — it is a
  page-capped count, not a total result count, and never contributes
  to the Demand Score.
- Neither score has been validated against real sales outcomes.

## Architecture direction

The system is designed to grow into an orchestrator coordinating
specialized agents (Demand, Competition, Trend, Supplier, Margin,
Scoring), each with a single responsibility and returning structured data
instead of prose. Phase 1 builds only the data models and the scoring
engine that every later agent will eventually feed into:

```
Product + ComponentScores -> scoring engine -> OpportunityResult
```

Business logic (the scoring math) is kept separate from integrations
(marketplace APIs, suppliers, trends) so the scoring engine can be tested
and trusted independently of any external data source.

### Scoring model

Final score is a weighted combination of seven 0-100 component scores:

| Dimension   | Weight | Direction |
|-------------|--------|-----------|
| Demand      | 30%    | positive  |
| Trend       | 20%    | positive  |
| Competition | 15%    | negative  |
| Margin      | 15%    | positive  |
| Supplier    | 10%    | positive  |
| Logistics   | 5%     | positive  |
| Risk        | 5%     | negative  |

Competition and Risk are **negative dimensions**: a higher score means more
competition or more risk, so each is inverted (`100 - score`) before being
weighted, instead of being added directly.

### Classification

| Opportunity Score | Classification                 |
|--------------------|---------------------------------|
| 80-100             | Strong opportunity              |
| 65-79.99            | Worth deeper investigation      |
| 50-64.99            | Weak or uncertain opportunity   |
| Below 50            | Reject                          |

## Install

Requires Python 3.12.

```bash
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
```

## Run tests

```bash
pytest
```

`pyproject.toml` configures pytest's `pythonpath` to include the project
root, so `src` resolves as a package whether you run `pytest` or
`python -m pytest`.

## Roadmap

1. Project structure
2. Data models
3. Opportunity scoring engine
4. Manual product input
5. First real data integration
6. Demand analysis
7. Competition analysis
8. Margin analysis
9. Supplier research
10. Orchestration
11. Database/history
12. n8n automation
13. Notifications

14. Continuous improvement

Phase 4 (trend data + deterministic trend analysis) and Phase 5
(deterministic Demand Analysis, described above) are layered on top of
steps 5-6 — real external integrations plus the deterministic groundwork
for the eventual Trend Agent and Demand Agent's contributions to the
Opportunity Scoring Engine. Phase 5 is the current phase.
