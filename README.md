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

## Phase 6 scope

Phase 6 adds a deterministic **Competition Analysis** layer. It answers
*"how difficult does this market appear for a new seller?"* — the
opposite question from Demand ("how popular does it appear?"). No AI
agent; deterministic analytics over one marketplace sample.

### Source evaluation (done before writing the scoring formula)

Only `MercadoLivreItem` fields are usable: `price`, `seller_id`,
`condition`, `free_shipping`, `title`, and the sample size itself.
There is only **one** conceivable source family for competition in this
project (no Google-Trends-equivalent second source exists for
competition specifically) — a structurally different situation from
Phase 5's two-family model. Mercado Livre is still `403` live, same
blocker as every prior phase.

### Data completeness vs. sample independence (Phase 5 lesson, re-applied)

Five features (seller mix, price stats, shipping, condition, title
duplication) are all computed from the **same ~10-item page** of one
API call. Computing five things from one block of one street does not
mean five independent surveys were taken — it means one block was
looked at from five angles. Confidence is therefore bounded by *sample
adequacy*, not by how many features were successfully extracted.

### `marketplace_sample_size` vs. `total_result_count` (corrected)

`len(items)` is a page-capped sample, never a total — `marketplace_sample_size`
stays in `Observed` for transparency but never scores anything.
`total_result_count` is **always `None`** right now. An earlier version
of this phase inferred `total_result_count = marketplace_sample_size`
whenever the sample came back smaller than the requested `limit`,
reasoning "the API returned fewer than we asked for, so that must be
everything." **That inference was removed** — it assumed a guarantee
our abstraction doesn't make: `search_products()` returns *mapped*
`MercadoLivreItem` objects, not the provider's raw result list or its
paging metadata, so the mapped count isn't guaranteed to equal the
provider's raw count; and even a short page doesn't by itself prove the
search was exhaustive unless the provider says so explicitly. See
"Hardening pass" below.

### Formula (see `src/competition_analysis.py` module docstring for full detail)

| Component | Base weight | From | Direction |
|---|---|---|---|
| Seller concentration | 0.30 | `100 * (1 - unique_seller_ratio)` | fewer distinct sellers in the SAMPLE → harder for a newcomer |
| Listing saturation | 0.25 | **always excluded** | disabled — see "Hardening pass" below |
| Price crowding | 0.20 | `100 * (1 - normalized price dispersion)` | tightly clustered prices → commoditized/crowded; widely dispersed → segmented market, not automatically "more competitive" |
| Duplicate listings | 0.15 | exact-normalized-title duplicate ratio | weak proxy, deliberately low-weighted |
| Shipping | 0.10 | free-shipping prevalence | weak proxy, deliberately the lowest weight |

Every component above describes the **sample**, never the marketplace
as a whole. Confidence: `min(0.6 * completeness + 0.4 * sample_adequacy, 55)`
if the source succeeded at all, else `0`. The 55 cap mirrors Phase 5's
~50-55 ceiling for "1 of 2 source families" — reinterpreted here as
"this is our only witness, and that witness only saw one block." **This
cap is a documented, provisional anchor, not an empirically validated
figure.**

### Hardening pass (pre-commit correction)

Two modeling bugs were found and fixed before committing:

1. **Listing saturation scored our own request parameter.** The
   formula compared `marketplace_sample_size` to the requested `limit`
   and scored a full page as "more saturated" — exactly the signal the
   Phase 6 source evaluation itself said not to use
   (`marketplace_sample_size` is capped by *our own* `limit`, not a
   market-size signal). Fixed: `listing_saturation_contribution` is now
   **always `None`**, permanently excluded from the Competition Score
   (weight slot kept for future reinstatement, same treatment Phase 5
   gave its own disabled marketplace component). Confirmed with a
   regression test: samples of 5, 10, and 50 items with otherwise
   identical features now produce the **exact same** Competition Score.
2. **`total_result_count` inference wasn't actually valid.** Removed
   entirely — see above. `total_result_count` stays `None`
   unconditionally until a genuine provider total/paging field is
   extracted and mapped (it currently is not).

### What's new

- `src/competition_models.py` — `CompetitionSignals`, `build_competition_signals()`
- `src/competition_analysis.py` — `CompetitionAnalysisResult`, `analyze_competition()`
- `src/main.py` — CLI option `5. Analyze Competition`
- `tests/test_competition_models.py`, `tests/test_competition_analysis.py`

### Run it

```bash
python -m src.main
```
Choose option `5` and enter a search term.

### Important design rule

The Competition Score is **not** fed into the Phase 1 Opportunity
Scoring Engine yet (which already treats competition as a negative
dimension on manually-entered data) — this phase only builds and
validates Competition Analysis in isolation.

### Limitations

- Mercado Livre is currently unreachable live — expect `Competition
  Score: not available`, `Confidence: 0.00` in this environment, not a
  fabricated number.
- A single marketplace sample (capped at 10 items by default) is never
  a representative market survey — every score here describes "this
  one page," not "the market."
- `total_result_count` is always unknown right now — there is no safe
  way to infer it from sample size alone in this abstraction (see
  Hardening pass above).
- Price-dispersion direction (low = crowded, high = segmented) is a
  documented judgment call, not an empirically validated rule.
- The 55 single-source confidence cap is a provisional anchor, not
  empirically validated.
- Neither score has been validated against real outcomes.

## Phase 7 scope

Phase 7 adds a deterministic **Margin Analysis** layer. It answers
*"after all KNOWN costs, how much money appears to remain from each
sale?"* — distinct from Demand (market interest) and Competition
(competitive difficulty). This phase works **without** any Mercado
Livre access: it is a provider-neutral unit-economics calculator over
explicit, user-supplied inputs, not a live marketplace lookup.

### Why Decimal, not float

Money uses `decimal.Decimal` throughout, never `float`. Binary floating
point cannot exactly represent most decimal fractions (`0.1 + 0.2 !=
0.3` in float), and those tiny errors compound across financial
calculations in ways that are hard to reproduce and impossible to
justify to someone reconciling real currency. Every monetary/rate
input is coerced via `Decimal(str(value))` (never `Decimal(float)`
directly) to avoid importing a float's binary representation error.
Rounding uses `ROUND_HALF_UP` to 2 decimal places — a documented policy
choice (the everyday rounding convention) applied to each individually
meaningful amount as soon as it's computed, not just once at the very
end.

### Core concepts, worked example

```
Sale price = 100        Product cost = 50
Marketplace fee = 15    Shipping = 10

Gross profit        = 100 - 50 = 50
Gross margin        = 50 / 100 = 50%
Markup               = 50 / 50  = 100%        <- NOT the same as margin
Contribution profit  = 100 - 50 - 15 - 10 = 25
Contribution margin  = 25 / 100 = 25%
```

**Margin ≠ markup**: margin is profit over *sale price*; markup is
profit over *cost*. The same R$50 of profit is a 50% margin and a 100%
markup here. **Gross profit ≠ contribution profit ≠ net profit**: gross
profit only subtracts product cost; contribution profit subtracts every
*known* variable cost tied to the sale; neither is net profit, which
would also need fixed company expenses (salaries, rent, software) this
module never sees or estimates — the term "net profit" is never used
to label a value anywhere in this codebase.

### Missing cost ≠ zero cost

`seller_shipping_cost = Decimal("0")` means "we know shipping is free."
`seller_shipping_cost = None` means "we don't know." An unknown category
is **excluded** from `total_variable_cost`'s sum, never added as 0.

### Cost Completeness, not "Confidence"

Phase 5/6's "Confidence" existed to bound noisy, externally-sampled,
correlated evidence. Margin's missing data is a different kind of
thing — it's simply "how many of the 8 optional cost categories did
the user supply," with no sampling bias or source-independence question
to bound. So this phase does **not** reuse that formula:

```
cost_completeness_score = 100 * known_optional_categories / 8
```

### Margin Score — only when defensible

`gross_profit`/`gross_margin_percent`/`markup_percent` only need
`sale_price` + `product_cost` (always known) and are always computed.
`contribution_profit`/`contribution_margin_percent` are also always
computed from known costs, labeled "known costs only" everywhere. The
single 0-100 `margin_score`, however, is withheld (`None`) unless
`cost_completeness_score` reaches **50%** (at least 4 of 8 categories)
— below that, presenting one confident number would overstate how much
is actually known.

Piecewise-linear interpolation over `contribution_margin_percent`
(PROVISIONAL business heuristic, not empirically validated):

| Margin | Score |
|---|---|
| ≤ -10% | 0 |
| 0% | 15 |
| 5% | 35 |
| 10% | 55 |
| 20% | 75 |
| 30% | 90 |
| ≥ 50% | 100 |

### Break-even price

Naively summing all costs is wrong whenever a cost is a *percentage* of
price (raising the price to cover a % fee also raises that fee).
Correct derivation: solving `contribution_profit(P) = 0` for `P`:

```
P = fixed_known_costs / (1 - sum_of_known_percentage_rates)
```

If the denominator is ≤ 0 (known percentage costs alone consume 100%+
of revenue), `break_even_price` is `None` with a clear note — never a
crash, never a negative/nonsensical number.

### Marketplace fees and taxes: configurable, never hardcoded

No current Mercado Livre fee table or Brazilian tax rate is hardcoded
anywhere. `marketplace_fee_amount`/`marketplace_fee_rate`/`fixed_marketplace_fee`
and `tax_amount`/`tax_rate` are all explicit, optional inputs. Supplying
`marketplace_fee_amount` together with `marketplace_fee_rate` or
`fixed_marketplace_fee` (or `tax_amount` with `tax_rate`) raises a clear
`ValueError` — mixing an override with the components it would
otherwise be computed from risks double-counting, so there is no silent
precedence order. `marketplace_fee_rate` and `fixed_marketplace_fee`
**may** coexist (a real percentage-plus-flat-fee structure).

### What's new

- `src/margin_models.py` — `MarginInputs`
- `src/margin_analysis.py` — `MarginAnalysisResult`, `analyze_margin()`
- `src/main.py` — CLI option `6. Analyze Margin`
- `tests/test_margin_models.py`, `tests/test_margin_analysis.py`

### Run it

```bash
python -m src.main
```
Choose option `6`. Only product name, sale price, and product cost are
mandatory; every other cost prompt accepts a blank answer for "unknown."

### Important design rule

The Margin Score is **not** fed into the Phase 1 Opportunity Scoring
Engine yet (which already treats margin as a positive dimension on
manually-entered data) — this phase only builds and validates Margin
Analysis in isolation.

### Limitations

- `margin_score` requires ≥50% cost-category completeness — a
  provisional, documented threshold, not empirically validated.
- The score anchors and the 50% threshold are configurable heuristics,
  not proven business rules.
- `payment_cost` is modeled as a flat amount only (no rate variant yet).
- Return/refund reserve must be explicitly supplied — no default
  percentage is ever assumed.
- Not validated against real outcomes.

## Phase 8 scope

Phase 8 adds a deterministic **Supplier Analysis** layer. It answers
*"can I realistically source this product from this supplier under
acceptable commercial and operational conditions?"* — distinct from
Demand, Competition, and Margin. No scraping, no supplier integration
yet: every field is explicit, manually-supplied input, same strategy
as Phase 7.

### A Mercado Livre seller is NOT a supplier

A retail marketplace listing is never proof of wholesale availability,
dropshipping support, stable supply, resale authorization, stock
continuity, invoice issuance, or acceptable lead time. Neither
`src/supplier_models.py` nor `src/supplier_analysis.py` imports
anything from `src.integrations` — this is an architectural guardrail,
not just a comment.

### Boolean tri-state, preserved throughout

Every yes/no field is `True` / `False` / `None` — verified-yes,
verified-no, or unknown. `invoice_available = False` means "we checked,
they don't issue invoices"; `None` means "we haven't checked." Unknown
booleans are **excluded** from scoring, never scored as a negative.

### Supplier Score vs. Evidence Completeness

Same separation as every prior phase's two-score pattern:
`Supplier Score: 85, Evidence Completeness: 35` means the little we
know looks excellent; `Supplier Score: 50, Evidence Completeness: 95`
means we know a lot and it's mediocre. Completeness here is
**weighted**, not a flat count — knowing the supplier's name matters
far less than knowing MOQ, stock, dispatch timing, dropshipping
capability, or invoice status, so those get the highest of 16 weights
summing to exactly 1.0.

### Hard blockers shown alongside the score, never hidden inside it

```
Supplier Score: 82
Operational Status: BLOCKED
Reason: stock_quantity (10) is below moq_units (500)
```
Two conditions are true hard blockers: known-zero/unavailable stock,
and known stock below a known MOQ. `dropshipping_supported == False`
is deliberately **not** a blocker (bulk purchase + self-fulfillment
remains viable) — it lowers `fulfillment_capability_score` instead.

### Lead time: no double counting

`dispatch_time_days` (time before shipment leaves) ≠
`delivery_time_days` (transport time after) ≠ `lead_time_days` (the
total). If both dispatch and delivery are known, they're summed. An
explicit `lead_time_days` supplied together with *both* is rejected at
construction — ambiguous double representation of the same total.

### Rating credibility — a 5.0 with 2 reviews ≠ a 4.8 with 10,000

```
credibility = piecewise-linear over review_count (0/unknown -> 0.1, 200+ -> 1.0)
effective_rating = 50 + credibility * (normalized_rating - 50)
```
A high rating with few/unknown reviews shrinks toward the neutral
midpoint instead of being trusted at face value — a simple,
deterministic confidence adjustment, not fabricated statistics.

### Score dimensions (base weights, renormalized over what's known)

| Dimension | Weight | From |
|---|---|---|
| Order flexibility | 0.25 | MOQ and/or minimum order value |
| Operational speed | 0.20 | derived lead time |
| Stock viability | 0.20 | stock quantity/availability vs. MOQ |
| Fulfillment capability | 0.15 | dropshipping (50%) / blind shipping (25%) / tracking (25%) |
| Trust/compliance | 0.20 | invoice/return policy/verification/contact + credibility-adjusted rating |

### What's new

- `src/supplier_models.py` — `SupplierInputs`
- `src/supplier_analysis.py` — `SupplierAnalysisResult`, `analyze_supplier()`
- `src/main.py` — CLI option `7. Analyze Supplier`
- `tests/test_supplier_models.py`, `tests/test_supplier_analysis.py`

### Run it

```bash
python -m src.main
```
Choose option `7`. Only product name and supplier name are mandatory;
every other prompt accepts `y`/`n`/blank or a blank number for unknown.

### Important design rule

The Supplier Score is **not** fed into the Phase 1 Opportunity Scoring
Engine yet — this phase only builds and validates Supplier Analysis in
isolation. It also never duplicates Margin Analysis: `unit_cost` is
recorded as sourcing evidence only, never turned into a profitability
verdict here.

### Limitations

- `supplier_score` requires ≥35% weighted evidence completeness — a
  provisional, documented, independently-chosen threshold (different
  from Phase 7's 50%, since supplier evidence is inherently sparser).
- All score anchors, weights, and the blocker set are configurable
  heuristics, explicitly not proven business rules.
- `price_stability`/`catalog_stability`/`historical_fulfillment_rate`
  are intentionally unimplemented — no historical observations exist
  to support them; never inferred from a single snapshot.
- Not validated against real outcomes.

## Phase 9 scope

Phase 9 adds a deterministic **Logistics Analysis** layer. It answers
*"how operationally difficult is this product to move from source to
customer — can we store, handle, ship, and deliver it efficiently and
safely?"* — distinct from Demand, Competition, Margin (financial
viability), and Supplier (sourcing reliability). No carrier integration
yet: every field is explicit, manually-supplied input, same strategy as
Phase 7/8.

### Score direction is inverted from the other phases' internal framing

`logistics_score`: **0 = operationally difficult, 100 = easy/favorable**
— matching Phase 1's existing convention of treating logistics as a
positive dimension. Internally, several sub-scores are computed as an
"ease" value directly from anchors (never a "burden" computed first and
left un-inverted), documented per dimension in
`src/logistics_analysis.py`.

### Customer delivery time ≠ supplier lead time

`estimated_delivery_days` here is the **last-mile** leg (seller/warehouse
to customer) — a different leg of the journey from Phase 8's
`lead_time_days`/`dispatch_time_days`/`delivery_time_days` (supplier to
seller). `src/logistics_models.py` and `src/logistics_analysis.py` never
import anything from `src.supplier_models`/`src.supplier_analysis`, and
there is no `sale_price` field at all — so a margin/profitability
calculation is architecturally impossible here, not just discouraged.

### Package volume, dimensional weight, and "reference" billable weight

```
package_volume_cm3 = length_cm * width_cm * height_cm   (all 3 or none)
volume_liters       = package_volume_cm3 / 1000
dimensional_weight_kg = package_volume_cm3 / dimensional_weight_divisor
                        (only if an explicit divisor is supplied —
                        never a hardcoded universal constant; real
                        carriers use different divisors, e.g. 5000/6000)
reference_billable_weight_kg = max(weight_kg, dimensional_weight_kg)
                        (explicitly labeled "reference" everywhere —
                        NEVER presented as a real carrier charge)
```

### Observed rate vs. inferred risk indicator — never blended

`observed_damage_rate` / `observed_return_rate` are real historical
observations (e.g. "3 of 40 shipments arrived damaged" → 0.075).
`fragile`/`hazardous`/etc. are property flags that inform
`handling_ease_score`, a risk *indicator* — never a probability. The two
never feed each other: a `fragile=True` flag never fabricates a damage
rate, and an observed rate is never derived from a property flag.

### Hard blockers: none are currently reachable, by design

A hard blocker must mean "we have evidence the operation is currently
**impossible**," not "we have evidence the operation went badly." An
earlier draft of this phase treated an observed damage/return rate ≥
50% as a blocker — a hardening-review correction caught this as a
semantic bug: a 55% observed damage rate means "historical performance
here is extremely poor," not "shipping is impossible" (the 45% that
*did* arrive fine is direct proof otherwise). Compare with Phase 8's
`stock_quantity == 0`, which *is* a genuine blocker — zero stock really
does make a sale currently impossible, no exceptions.

`_detect_blockers()` therefore always returns an empty list today, and
`BLOCKED` is consequently **unreachable** from any current input
combination — kept in the status vocabulary as a reserved extension
point for a future field that can genuinely prove impossibility, not
removed outright. A severe (≥ 50%) observed damage/return rate instead
produces a **warning** and forces `operational_status` to at least
`CAUTION`, without touching `logistics_score`'s own calculation. Every
other risky combination (e.g. `temperature_sensitive=True` with a long
`estimated_delivery_days`) also produces a warning, never a blocker —
same "prefer CAUTION over an unproven BLOCKED" principle, applied
consistently. A severe warning is shown **alongside** the score, same
as Phase 8's blocker pattern — a high `logistics_score` next to
`Operational Status: CAUTION` is honest (the measurable dimensions
looked fine; a real observed failure rate still means this needs
attention).

### Score dimensions (base weights, renormalized over what's known)

| Dimension | Weight | From |
|---|---|---|
| Physical ease | 0.30 | weight/size (prefers reference billable weight over raw weight when both volume and weight are known) |
| Handling ease | 0.25 | fragile/liquid/hazardous/perishable/temperature-sensitive/special-handling/stackable |
| Delivery convenience | 0.20 | estimated_delivery_days (customer-facing) |
| Fulfillment support | 0.15 | supplier/seller fulfilled, warehouse required |
| Shipping support | 0.10 | tracking/insurance available |

### What's new

- `src/logistics_models.py` — `LogisticsInputs`
- `src/logistics_analysis.py` — `LogisticsAnalysisResult`, `analyze_logistics()`
- `src/main.py` — CLI option `8. Analyze Logistics`
- `tests/test_logistics_models.py`, `tests/test_logistics_analysis.py`

### Run it

```bash
python -m src.main
```
Choose option `8`. Only product name is mandatory; every other prompt
accepts `y`/`n`/blank or a blank number for unknown.

### Important design rule

The Logistics Score is **not** fed into the Phase 1 Opportunity Scoring
Engine yet — this phase only builds and validates Logistics Analysis in
isolation. It never duplicates Supplier Analysis (no lead-time fields)
or Margin Analysis (no `sale_price` field, no profitability math).

### Limitations

- `logistics_score` requires ≥40% weighted evidence completeness — a
  provisional, independently-chosen threshold (different from Phase 7's
  50% and Phase 8's 35%).
- All score anchors, weights, and the severe-warning threshold are
  configurable heuristics, explicitly not proven carrier/business rules.
- `BLOCKED` is currently unreachable (see "Hard blockers" above) —
  not a missing feature, a deliberate consequence of what this phase's
  fields can and cannot prove.
- `dimensional_weight_divisor` must be explicitly supplied by the user;
  no universal divisor is assumed.
- Not validated against real outcomes.

## Phase 10 scope

Phase 10 adds a deterministic **Risk Analysis** layer. It answers *"what
could make this product opportunity fail, become unstable, or create
disproportionate downside — even if the other dimensions look good?"*
— distinct from Demand, Competition, Margin, Supplier, and Logistics.
No orchestration yet: every field is explicit, manually-supplied input,
same strategy as Phase 7/8/9.

### Risk Score direction is the opposite of Supplier/Logistics/Margin

`risk_score`: **0 = low apparent risk, 100 = high apparent risk** —
matching Phase 1's existing convention of treating Risk as an inverted
negative dimension. This is intentionally the *opposite* contract from
Supplier Score, Logistics Score, and Margin Score (where higher is
better). Every anchor table in `src/risk_analysis.py` is written to
increase directly with badness, so there is no internal "goodness"
framing to invert — removing an entire class of the direction bug
fixed in Phase 9's hardening review.

### Risk vs. uncertainty

`supplier_count = 1` is OBSERVED concentration risk. `supplier_count =
None` is UNCERTAINTY — we simply don't know, and that is never scored
as if it were evidence of anything. This is why every result carries
both a `risk_score` AND a separate `evidence_completeness_score`.

### Dependency risk: supplier_count and dependency-percent are complementary

`supplier_count` (how many known alternatives exist) and
`primary_supplier_dependency_percent` (how much volume is actually
concentrated in the largest one) measure related but different things.
5 known suppliers where one still accounts for 95% of volume is still
highly concentrated — so both are kept as separate sub-signals, with
the percent weighted higher (1.5) since it's the more precise, direct
measure.

### Hard blockers: none are reachable, applying the Phase 9 lesson from day one

Nothing in `RiskInputs` can prove an opportunity is currently
*impossible* — a 100% observed return rate, a known recall, or an
unresolved regulatory flag are all severe risk **evidence**, not proof
of impossibility. `_detect_blockers()` always returns `[]`; `BLOCKED`
stays in the vocabulary as a reserved extension point, never invented.
Severe evidence instead flows into the ordinary weighted dimension
scores and produces an explanatory warning.

### Risk dimensions (base weights, renormalized over what's known)

| Dimension | Weight | From |
|---|---|---|
| Dependency risk | 0.25 | supplier count / primary supplier dependency / platform dependency / advertising dependency |
| Supply continuity risk | 0.20 | historical stockout rate / replacement supplier / alternative fulfillment |
| Volatility risk | 0.20 | observed price volatility / seasonality level |
| Operational history risk | 0.20 | observed return rate / observed damage rate / recall history |
| Compliance/IP uncertainty risk | 0.15 | regulatory uncertainty / brand-IP uncertainty (weighted lowest — an unresolved flag is a weaker claim than directly observed evidence) |

### Regulatory/brand-IP uncertainty: investigation flags, never legal conclusions

`regulatory_uncertainty=True` means "unresolved compliance question
requiring investigation" — **not** "this product is illegal."
`brand_ip_uncertainty=True` means "unresolved trademark/IP concern" —
**not** "this infringes." Both contribute 70 (not 100) to their
dimension when `True`, reflecting that an un-investigated flag is a
weaker signal than a proven fact.

### Rate semantics: 0-1 fractions, with one explicit exception

Every percentage/rate field is a fraction in `[0, 1]`, consistent with
every prior phase's CLI convention. The one deliberate exception is
`seasonality_level`, an integer on a `[0, 100]` scale by definition —
called out explicitly in its validation message and CLI prompt so the
two conventions are never confused.

### Future orchestration boundary

`src/risk_models.py` and `src/risk_analysis.py` import nothing from any
prior analysis module (`src.demand_analysis`, `src.trend_analysis`,
`src.competition_analysis`, `src.margin_analysis`,
`src.supplier_analysis`, `src.logistics_analysis`) or `src.integrations`
— not because `src.integrations` is empty (it already contains the
Mercado Livre integration since Phase 3 and the Apify/Google Trends
integration since Phase 4), but because Risk Analysis must stay
decoupled from how any upstream data was obtained or computed. No
external integration currently populates `RiskInputs` — its inputs are
explicit/manual today, same as Phase 7/8/9's own models before any
integration existed for them. A future orchestrator may one day compose
normalized outputs from those already-integrated phases into a
`RiskInputs` instance — Risk Analysis itself stays deterministic and
decoupled from how any of those scores are computed internally.

### What's new

- `src/risk_models.py` — `RiskInputs`
- `src/risk_analysis.py` — `RiskAnalysisResult`, `analyze_risk()`
- `src/main.py` — CLI option `9. Analyze Risk`
- `tests/test_risk_models.py`, `tests/test_risk_analysis.py`

### Run it

```bash
python -m src.main
```
Choose option `9`. Only product name is mandatory; every other prompt
accepts `y`/`n`/blank or a blank number for unknown.

### Important design rule

The Risk Score is **not** fed into the Phase 1 Opportunity Scoring
Engine yet — this phase only builds and validates Risk Analysis in
isolation. It never duplicates Competition/Margin/Supplier/Logistics
formulas (no imports from any of those modules).

### Limitations

- `risk_score` requires ≥35% weighted evidence completeness — chosen
  to match Phase 8's threshold (risk evidence, like supplier evidence,
  is dominated by investigative/relationship-based information rather
  than directly measurable physical facts), not copied mechanically.
- All score anchors, weights, and warning thresholds are configurable
  heuristics, explicitly not proven business rules.
- `BLOCKED` is currently unreachable — a deliberate consequence of what
  this phase's fields can and cannot prove, not a missing feature.
- `seasonality_level` and future demand-variability signals are
  currently manual judgment calls pending a real Trend Analysis
  integration.
- Not validated against real outcomes.

## Phase 11 scope

Phase 11 is the **composition layer**: it takes the real outputs of the
seven independent domain engines (Phases 4–10) and combines them into
one explainable Opportunity analysis — without destroying the semantic
guarantees each earlier phase established.

It is **composition, not orchestration**. Nothing here fetches,
schedules, or decides what to analyze; a future Orchestrator phase will
do that and feed its results into this layer.

```
Domain Analysis Result -> Domain Adapter -> OpportunityComponent
                                                 -> Composition Engine
```

### The central finding: Demand and Trend are not independent evidence

Before wiring anything, every component's evidence was traced back to
its raw source. Demand and Trend both descend from **one** Apify Google
Trends Actor call:

```
interest_over_time -> recent_average + direction
                        |-> TrendMetrics.provisional_trend_score
                        |-> DemandAnalysis.trend_contribution  (w 0.40)
related_*_queries     -> DemandAnalysis.breadth_contribution   (w 0.25)
interest_by_region    -> DemandAnalysis.regional_contribution  (w 0.20)
marketplace            -> DemandAnalysis.marketplace_contribution
                          -- permanently None
```

Because the marketplace component is permanently unavailable,
**100% of today's Demand Score is Google-Trends evidence**, and
`recent_average`/`direction` are literally the same two numbers that
dominate the Trend Score. Using the Phase 1 conceptual split
(Demand 30% + Trend 20%) would stake **half** the Opportunity Score on
a single provider call and count that interest series **twice**.

Classification of every overlap found:

| Pair | Class | Decision |
|---|---|---|
| Demand ↔ Trend | **duplicated** | one evidence family, one weighted representative |
| Logistics ↔ Risk | correlated | both kept: Logistics never *scores* the shared observed rates |
| Supplier ↔ Risk | distinct | both kept at full weight |
| Supplier ↔ Margin | distinct | `unit_cost` is unscored evidence in Supplier |
| Competition ↔ Risk | independent | rivals' concentration vs. *our* dependency |
| Supplier ↔ Logistics | distinct | sourcing leg vs. last-mile leg |

### Evidence families

The overlap rule is declared as **data**, not as conditionals in the
engine — `EvidenceFamilyPolicy` in `src/opportunity_models.py` — so a
future refactor cannot quietly reintroduce Trend as an independent
weighted vote without deleting a declared policy object and failing its
tests.

The search-interest family carries **one** weight of 0.30 between both
members. Exactly one member is ever weighted:

- **Demand** is preferred — it consumes the family most completely
  (interest level, direction, related-query breadth, regional spread).
- **Trend** is the fallback, so supplying only a Trend result does not
  leave the family's weight unearned.

The non-elected member is still reported (score, direction, provenance)
with zero weighted contribution and an explicit `overlap_policy` —
visible, but not voting twice.

### Two scoring models, side by side

| Dimension | `legacy-v1` | `integrated-v1` | Layer | Direction |
|---|---|---|---|---|
| Demand | 30% | **30%** (family) | commercial | positive |
| Trend | 20% | folded into the family | commercial | positive |
| Competition | 15% | 15% | commercial | negative |
| Margin | 15% | **20%** | commercial | positive |
| Supplier | 10% | **12%** | operational | positive |
| Logistics | 5% | **8%** | operational | positive |
| Risk | 5% | **15%** | commercial | negative |

`src/scoring.py` is **untouched**: the Phase 1/2 manual API keeps its
own weights, its mandatory-seven `ComponentScores`, and its existing
behaviour. The integrated model is a separate, explicitly versioned
table. `tests/test_legacy_compatibility.py` pins both so neither can
drift into the other.

#### Why integrated-v1 does not inherit legacy's weights

This was the final hardening decision of Phase 11, and it reverses an
earlier draft.

That draft gave the search-interest family 0.50 — legacy's
`Demand 0.30 + Trend 0.20` — reasoning that "removing the double count
should not also re-weight the business judgment." **That reasoning was
wrong.** Legacy's 0.50 was split across what it *believed* were two
independent sources of evidence. Once the audit proved they are one
evidence family fed by one provider call, preserving 0.50 does not
preserve the original judgment — it silently converts

> "half the score comes from two independent demand signals"

into

> "half the score comes from one Google Trends call."

Those are materially different claims, and the second is far more
concentrated than Phase 1 ever intended.

```
legacy business weights  !=  integrated evidence-justified weights
```

So integrated-v1 re-derives each weight from the **marginal information
value** that evidence family actually contributes, given what the
project can observe today:

| Weight | Rationale |
|---|---|
| search-interest **0.30** | Genuine evidence of interest, but currently dependent on a single Google Trends / Apify evidence family, and search interest is **not** observed marketplace sales. Material, not dominant. |
| competition **0.15** | Retains real influence over attractiveness without dominating commercial viability. |
| margin **0.20** | Unit economics are directly material to whether the opportunity is financially viable at all. Deliberately above the family: a product nobody searches for is a weak idea, but a product that loses money per unit is not an opportunity in the first place. |
| supplier **0.12** | Sourcing capability materially determines execution and deserves more than a marginal role. |
| logistics **0.08** | Movement and fulfillment matter, but stay below Margin and Supplier. |
| risk **0.15** | Downside, concentration and instability deserve material influence — tripled from legacy's 0.05, which was too small for a dimension the project treats as mandatory evidence. |

All six are **provisional business heuristics** chosen from documented
reasoning, not calibrated against outcomes. Real outcome data may well
justify recalibrating every one of them — that would be a new model
version, not an edit to this one.

### Commercial attractiveness is not operational readiness

A business can look excellent on paper — lots of customer interest,
acceptable competition, strong margin, manageable risk — while nobody
has checked whether a supplier can actually provide the item or whether
it can be shipped reliably. That opportunity is **commercially
attractive and operationally unvalidated**, and those are different
statements that must not collapse into one.

The seven components are therefore partitioned into two validation
layers, and every component is required for its own layer:

| Layer | Weight | Members | Question |
|---|---|---|---|
| commercial | 0.80 | search-interest family, competition, margin, risk | "is the market/economic case validated?" |
| operational | 0.20 | supplier, logistics | "is execution validated?" |

A family is satisfied when *any* of its members is available; a
non-family component is satisfied only by itself.

`commercial_validation_complete` / `operational_validation_complete`
and the matching `commercial_coverage` / `operational_coverage` are
reported separately, so both questions can be answered independently.

### Score direction, inverted exactly once

`raw_score` is always the domain's own number in the domain's own
direction; `opportunity_score` is re-oriented so higher is always
better. Competition and Risk are inverted (`100 - score`) in
`to_opportunity_oriented()` and **nowhere else** — Risk Analysis
performs no internal inversion, and Logistics deliberately computes
"ease" so it is already high-is-good.

### Missing is missing

A domain that withheld its score is `available=False` with
`raw_score=None` and a specific reason. It is never converted to 0,
never to 50, never to "safe", never to "average". Its weight is simply
not earned.

### False safety from missing negative evidence

Naive renormalization has a dangerous asymmetry. If everything known
scores 90 and Risk (weight 0.15) is unknown:

```
renormalize over available only  -> 90.00
if Risk had been known at 60     -> 82.50
```

The score would **rise** precisely because we know nothing about risk.
Two independent protections:

1. **Gate** (primary): Competition and Risk are commercial
   requirements, so a missing one forces
   `readiness = INCOMPLETE_EVIDENCE` and a withheld classification.
   Unknown risk can never be labelled "Strong opportunity".
2. **Ceiling** (numeric): the aggregate is capped at the value it would
   have if the missing negative dimension were neutral. This is **not**
   `None -> 50` — the component stays explicitly unknown and no
   contribution is fabricated; only the *aggregate* is prevented from
   profiting from ignorance. Because it is a `min()`, it can only lower
   an inflated score, never invent bad news for already-weak evidence.

The guard was **re-verified against the hardened weights**: Competition
and Risk now carry 0.15 each (0.30 combined, up from 0.20), so the
ceiling binds harder than before — the same formula is strictly more
protective, and the earlier 88.0 cap in the all-90s/no-risk example is
now 84.0.

A neutral ceiling is the tightest bound available without fabricating
evidence; the **gate**, not the ceiling, is what guarantees such a
result is never presented as validated.

### Readiness (not a domain status)

| Readiness | Meaning |
|---|---|
| `READY` | both layers complete, no blocker → final classification emitted |
| `OPERATIONALLY_UNVALIDATED` | commercial complete, Supplier and/or Logistics missing → analytical score shown, final classification withheld |
| `INCOMPLETE_EVIDENCE` | a **commercial** requirement is missing → the business case itself cannot be evaluated; analytical score shown, classification withheld |
| `BLOCKED` | a domain reported a hard blocker → checked first; score shown, recommendation withheld |

Precedence is strict:

```
BLOCKED > INCOMPLETE_EVIDENCE > OPERATIONALLY_UNVALIDATED > READY
```

Commercial outranks operational because an unevaluable business case
makes the execution question moot.

`OPERATIONALLY_UNVALIDATED` is deliberately **not** folded into
`INCOMPLETE_EVIDENCE`. They answer different questions, and conflating
them would discard the most actionable thing the system can say: *the
commercial case holds up — go verify sourcing and shipping.*

Despite the unavoidable word overlap, this vocabulary is distinct from
Supplier's/Logistics' `operational_status` and Risk's `risk_status`: it
is an opportunity-level statement about evidence coverage, never a
domain's own verdict.

### Final classification is emitted only when READY

The analytical score is computed and shown whenever any weighted
evidence exists — hiding useful arithmetic would be its own kind of
dishonesty. But the legacy bands are emitted only for `READY`.

Outside READY, `classification` is `None` and `withheld_reason`
explains why. For `OPERATIONALLY_UNVALIDATED` only — the one non-READY
state where the commercial case *is* fully evaluated — an explicitly
non-final band is exposed as `analytical_band_non_final`, so a report
can say "the commercial case scores in the Strong band, but execution
is unvalidated" without ever stamping the opportunity approved. It is
deliberately **not** populated for `INCOMPLETE_EVIDENCE` (the business
case is not evaluable, so a band would mislead) or for `BLOCKED` (the
opportunity is moot while the blocker stands).

Mercado Livre search is unreachable (HTTP 403) in this environment, so
Competition is usually unavailable and **most live integrated results
are therefore withheld**. That is a true statement about the project's
current evidence position, not a defect to engineer around.

### Blockers are never averaged away

A product can score Demand 95 / Margin 90 and still be impossible to
source. Blockers (today: only Supplier's zero-stock and
stock-below-MOQ) are checked **before** any evidence-completeness
question, surfaced namespaced by the domain that found them, and
override publishability regardless of how good everything else looks.
The arithmetic is still shown — what is withheld is the
*recommendation*, not the score.

### Coverage is not confidence

`component_coverage` = known weight ÷ total configured weight. It
answers only "how much of the weight do we have *any* evidence for."
It is **not** confidence, **not** completeness, and **not** accuracy.
`commercial_coverage` and `operational_coverage` are the same measure
restricted to one validation layer.

Each domain's own evidence metric is preserved separately and
**unaveraged** in `EvidenceProfile`: `demand_confidence`,
`competition_confidence`, `margin_cost_completeness`,
`supplier_/logistics_/risk_evidence_completeness`, plus
`trend_observation_count` (Trend has no evidence metric, so none is
invented). Averaging a bounded-confidence figure with a field-count
completeness figure would produce a number with no definable meaning,
so no aggregate is offered.

### Rounding policy

The integrated engine classifies the **exact, unrounded** value: a
score of 79.996 displays as `80.00` but must not become "Strong
opportunity". Legacy `score_opportunity()` has always classified the
already-2dp-rounded total and is left exactly as it was — no proven
bug, and changing it would move previously recorded results. Both
behaviours are pinned by tests so the divergence stays deliberate.

### What's new

- `src/opportunity_models.py` — `EvidenceFamilyPolicy`,
  `OpportunityComponent`, `EvidenceProfile`,
  `OpportunityAnalysisResult`, the integrated weight contract, the two
  validation layers, the readiness vocabulary
- `src/opportunity_integration.py` — seven adapters +
  `compose_opportunity()`
- `src/main.py` — CLI option `10. Integrated Opportunity Analysis`,
  `format_opportunity_report()`
- `tests/test_opportunity_models.py`,
  `tests/test_opportunity_integration.py`,
  `tests/test_legacy_compatibility.py`

### Run it

```bash
python -m src.main
```

Choose option `10`. It takes **no input**: rather than make you retype
every field from options 3–9, it runs the real domain engines over four
clearly-labelled illustrative scenarios — one per readiness state:

| Scenario | Readiness |
|---|---|
| A — complete evidence | `READY` |
| B — commercially attractive, operationally unvalidated | `OPERATIONALLY_UNVALIDATED` |
| C — commercial evidence incomplete (Margin withheld) | `INCOMPLETE_EVIDENCE` |
| D — Supplier blocked (stock below MOQ) | `BLOCKED` |

Those inputs are example values defined in `src/main.py` — explicitly
not fetched, not observed, and not about any real product. The
composition layer performs no HTTP at all.

### Important design rule

The composition layer imports **only** its own canonical contract — no
domain-analysis module, no integration, no HTTP, no LLM, no database.
Adapters translate and relabel; they never recompute a domain's
scoring, never fetch, and never guess a missing value. Layering is
one-directional and enforced by tests: no domain module may import the
opportunity layer.

### Limitations

- The Opportunity Score is a **provisional business heuristic**, not a
  calibrated probability. "82" means "this evidence, under this
  documented weighting, scores 82 of 100" — never an 82% chance of
  anything.
- Integrated weights are provisional heuristics re-derived from
  marginal information value, not calibrated against outcomes. They
  deliberately do **not** inherit legacy's numbers.
- The search-interest family's 0.30 reflects that search interest is
  currently a single-provider signal and is not observed marketplace
  sales. If a genuine total-result-count field is ever mapped (making
  Demand multi-source), that weight should be revisited.
- Competition is usually unavailable in this environment, so most live
  integrated results are withheld.
- The false-safety ceiling is the tightest honest bound, not a
  reconstruction of what the missing evidence would have said.
- There is no orchestration, persistence, or scheduling: domain results
  must be supplied by the caller.
- Not validated against real outcomes.

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

Two scoring models coexist deliberately (see "Phase 11 scope" above).

**`legacy-v1`** (`src/scoring.py`) — seven manually supplied, mandatory
0–100 component scores:

| Dimension   | Weight | Direction |
|-------------|--------|-----------|
| Demand      | 30%    | positive  |
| Trend       | 20%    | positive  |
| Competition | 15%    | negative  |
| Margin      | 15%    | positive  |
| Supplier    | 10%    | positive  |
| Logistics   | 5%     | positive  |
| Risk        | 5%     | negative  |

**`integrated-v1`** (`src/opportunity_integration.py`) — real domain
results, with missing-data semantics, blocker propagation,
correlated-evidence safeguards, and two validation layers. Its weights
are **independently derived from marginal information value**, not
inherited from legacy:

| Dimension   | Weight | Layer       | Direction |
|-------------|--------|-------------|-----------|
| Demand      | 30%    | commercial  | positive  |
| Trend       | (same family weight) | commercial | positive |
| Competition | 15%    | commercial  | negative  |
| Margin      | 20%    | commercial  | positive  |
| Supplier    | 12%    | operational | positive  |
| Logistics   | 8%     | operational | positive  |
| Risk        | 15%    | commercial  | negative  |

Demand and Trend share a **single** 30% evidence-family weight because
they derive from the same provider call, and only one of them is ever
counted.

In both models, Competition and Risk are **negative dimensions**: a
higher score means more competition or more risk, so each is inverted
(`100 - score`) exactly once before being weighted, instead of being
added directly.

### Classification

| Opportunity Score | Classification                 |
|--------------------|---------------------------------|
| 80-100             | Strong opportunity              |
| 65-79.99            | Worth deeper investigation      |
| 50-64.99            | Weak or uncertain opportunity   |
| Below 50            | Reject                          |

In `integrated-v1` these bands are emitted as a **final
classification** only when `readiness == READY`. Outside READY the
classification is withheld, and only the `OPERATIONALLY_UNVALIDATED`
state exposes an explicitly non-final band describing the commercial
case — see "Final classification is emitted only when READY" above.

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

Phases 4–10 built one deterministic domain engine each (Trend, Demand,
Competition, Margin, Supplier, Logistics, Risk) on top of steps 5–9 —
real external integrations plus the groundwork for the eventual
specialized Agents' contributions to the Opportunity Scoring Engine.

**Phase 11 (current) is the composition layer** described above: it
combines those seven engines' real outputs into one explainable
Opportunity analysis, handling score direction, missing data,
correlated evidence, and blocker propagation.

Phase 11 is deliberately **not** step 10 (Orchestration). Composition
answers "given these domain results, what do they support?"
Orchestration — collecting inputs, calling the domain engines, deciding
what to analyze and when — is the next step and is not built yet:

```
            Phase 11 (built)                 Step 10 (next)
  domain results -> adapters -> composition   Agent/Orchestrator
                                                  |
                                                  v
                                          collects inputs,
                                          runs domain engines,
                                          feeds this layer
```
