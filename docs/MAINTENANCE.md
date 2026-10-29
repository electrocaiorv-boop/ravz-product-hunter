# MAINTENANCE.md — External Integration & Dependency Maintenance

This project depends on systems it does not control: the Mercado Livre
API, the Apify platform and the third-party Actor it runs on our
behalf, and various Python packages. Those systems can change
independently of this codebase at any time — an endpoint can be
deprecated, a response field can be renamed, a rate limit can tighten, a
package can release a breaking version, a third-party Actor can be
abandoned by its author. This document is a **checklist only**. It does
not implement automation, cron jobs, GitHub Actions, or monitoring —
that belongs to a later phase (see `CLAUDE.md` roadmap).

## Weekly Integration Check

### Mercado Livre

- [ ] Mercado Livre official API documentation checked
- [ ] Endpoints used by the project are still valid
- [ ] Authentication requirements checked
- [ ] Response fields/schema checked
- [ ] Deprecation notices checked
- [ ] Rate limits checked when documented
- [ ] `requests` dependency checked

### Apify / Google Trends (`themineworks/google-trends-pro`)

- [ ] Apify platform availability checked
- [ ] Actor `themineworks/google-trends-pro` availability checked
- [ ] Actor last update date checked
- [ ] Actor pricing checked
- [ ] Actor output schema checked (field names/shape unchanged)
- [ ] Actor output checked for PER-SECTION consistency (not just overall
      success) — confirm `interest_over_time`, `interest_by_region`,
      and `related_queries` are ALL non-trivially populated in the same
      run; a run can return `HTTP 2xx` with some sections correct and
      others empty/malformed (see 2026-10-29 incident below)
- [ ] Actor rate-limit/degradation notices checked
- [ ] Google Trends' own behavior/access changes checked
- [ ] `APIFY_API_TOKEN` validity checked (without printing/logging it)
- [ ] Live smoke test run (`bebedouro para gatos`, geo `BR`), run at
      least twice back-to-back to catch intermittent per-section failures
- [ ] `requests`, `python-dotenv` dependency versions checked

### Demand Analysis inputs (Phase 5)

> **Corrected after a modeling review (see incident below):** two
> checklist items below were rewritten because the original
> expectations described the bug being fixed, not the correct
> behavior. Specifically: an empty `related_queries`/
> `interest_by_region` section must produce an EXCLUDED
> (`None`) component, never a `0` contribution; and
> `marketplace_result_count` was renamed to `marketplace_sample_size`
> because it is a page-capped count, not a total result count.

- [ ] Both demand input sources checked for availability (trend via
      Apify; marketplace via Mercado Livre) — note which succeeded
- [ ] `DemandSignals` schema still matches what `build_demand_signals()`
      actually populates (no silent field drift between the two)
- [ ] `TrendData.interest_over_time_available` /
      `related_queries_available` / `regional_interest_available`
      still reflect reality: re-confirm the Actor gives us no explicit
      per-section success/failure flag, so "non-empty list = available"
      remains the best available heuristic (see docs/LEARNING.md Fase 5
      hardening addendum for why this is a deliberately conservative
      choice, not a guess)
- [ ] `marketplace_sample_size` still honestly labeled as a page-capped
      count, not a total result count — re-check if Mercado Livre
      search ever becomes reachable again: does its response expose a
      genuine total/paging field we could extract instead?
- [ ] Scoring constants in `src/demand_analysis.py` reviewed (still
      provisional — recalibrate only against real outcome data, not
      vibes)
- [ ] Confidence logic reviewed: `source_coverage` still reflects the
      true number of reachable source families (currently 1 of 2), and
      the `coverage_cap = 100 * source_coverage` hard cap is still being
      applied (not silently reverted to an additive/uncapped formula)
- [ ] Live smoke test run via CLI option `4` (`bebedouro para gatos`,
      geo `BR`) — confirm Demand Score/Confidence Score are both
      produced (or honestly `None`/low) without crashing
- [ ] Data sparsity checked: does a low-observation-count run correctly
      yield a low Confidence Score, not a misleadingly high one?
- [ ] Source inconsistency checked: does a run with `interest_over_time`
      populated but `related_queries`/`interest_by_region` empty still
      produce a sane report (that component EXCLUDED/"not available",
      never a fabricated `0` or a crash)?

#### Incident (2026-10-29) — modeling bugs found and fixed before first commit

A pre-commit review of the Phase 5 design found three real modeling
bugs, all fixed in the same pass (no live schema change involved):

1. An empty `related_queries`/`interest_by_region` section was scored
   as a literal `0`, even though Phase 4 already proved the Actor can
   return one section empty while others succeed on the same call.
   Fixed by adding section-availability flags to `TrendData`.
2. Confidence Score reached 67.5 with only ONE source family
   available (a live run) — read as much stronger evidence than it
   was, because completeness/volume from a single source were summed
   additively with no real ceiling tied to source independence. Fixed
   with a hard `coverage_cap = 100 * source_coverage`.
3. `marketplace_result_count` was `len(search_products(...))`, which is
   capped by the `limit` parameter (default 10) — a page size, not a
   total marketplace result count. Renamed to `marketplace_sample_size`
   and permanently excluded from Demand Score scoring.

Live re-validation after the fix (`bebedouro para gatos`, `BR`):
`related_queries` came back empty again (further confirming the Actor's
inconsistency is ongoing, not resolved), but this time Breadth was
correctly reported as "not available" rather than scoring `0`. Demand
Score 60.40, Confidence Score 50.00 (exactly at the 1-of-2-families
cap) — verified by hand against the formula.

### Competition Analysis inputs (Phase 6)

> **Corrected after a pre-commit modeling review:** two checklist items
> below were rewritten because the original expectations described the
> bugs being fixed, not correct behavior. `listing_saturation` must
> NEVER be scored from sample size vs. requested limit (it is now
> permanently disabled), and `total_result_count` must NEVER be
> inferred from `sample_size < limit` (it is now always `None`). See
> the incident record below.

- [ ] Mercado Livre competition-relevant fields checked (`price`,
      `seller_id`, `condition`, `free_shipping`, `title`) — any renamed,
      removed, or newly added?
- [ ] Pagination semantics re-checked: does the live response now
      include a genuine total/paging field we could extract and map,
      distinct from the mapped-item count? (If yes, this is the ONLY
      legitimate way to populate `total_result_count` or re-enable
      `listing_saturation` — see incident below.)
- [ ] `total_result_count` re-confirmed as always `None` unless a
      genuine provider total/paging field has been mapped — re-check
      that no code path re-introduces a sample-size-based inference
- [ ] `listing_saturation_contribution` re-confirmed as always `None`
      — re-check that no code path re-introduces sample-size-based
      scoring of the Competition Score itself
- [ ] `seller_id` availability checked — still present on items when
      the search succeeds?
- [ ] Price-field quality checked — still numeric, still present on
      most items when the search succeeds?
- [ ] Shipping-field quality checked — still a plain boolean?
- [ ] Schema drift checked generally (any new/renamed fields on the
      raw Mercado Livre item that `_map_item()` in
      `src/integrations/mercadolivre.py` should pick up)
- [ ] Confidence logic reviewed: `MAX_CONFIDENCE_SINGLE_SOURCE` (55) and
      the completeness/sample-adequacy blend still match the "one
      street block" reasoning in `src/competition_analysis.py` —
      re-state that this cap is provisional, not empirically validated
- [ ] Sample-bias risk re-stated: a ~10-item page is never treated as
      a market survey anywhere in the code or the CLI report
- [ ] Live smoke test run via CLI option `5` (any search term) —
      confirm a clean "unavailable" report (not a crash, not a
      fabricated score) if Mercado Livre is still blocked, or a sane
      real report if it has recovered
- [ ] 403/auth status re-confirmed (same check as the Mercado Livre
      section above — Competition Analysis depends on the exact same
      blocked endpoint)

#### Incident (pre-commit, Phase 6) — two modeling bugs found and fixed

1. `listing_saturation_contribution` scored `marketplace_sample_size`
   against the requested `limit` — directly scoring our own query
   parameter, which the Phase 6 source evaluation itself had already
   flagged as invalid. Fixed: permanently `None`, excluded from the
   Competition Score (weight slot kept for future reinstatement).
2. `total_result_count` was inferred as `marketplace_sample_size`
   whenever the sample came back smaller than the requested `limit`.
   This assumed a guarantee the integration doesn't make:
   `search_products()` returns *mapped* items, not the provider's raw
   result count or paging metadata, so the mapped count isn't
   guaranteed to equal the provider's true count — and a short page
   doesn't by itself prove the search was exhaustive. Fixed: always
   `None` until a genuine provider total/paging field is mapped.

Regression tests added: identical competition features at sample sizes
5/10/50 now produce the exact same Competition Score; varying
`requested_limit` alone (5/10/50) with identical signals also produces
the same score; an empty sample with nothing else known now correctly
yields `None` (no defensible components), not a fabricated `0`.

### Shared

- [ ] `pytest` dependency checked
- [ ] Other project dependencies checked
- [ ] Full test suite executed (`python -m pytest -v` and `pytest -v`)
- [ ] README updated if API behavior changed
- [ ] LEARNING.md updated if a new technical concept was learned
- [ ] MAINTENANCE.md updated if the maintenance process itself changes

## Recommended cadence

- **During active development:** Weekly.
- **After the project becomes stable:** Every 2 to 4 weeks, depending on
  the external services used.

## Current integration status

### Mercado Livre (corrected after independent re-check, Phase 3)

A previous draft of this document incorrectly stated that free-text `q`
search on `/sites/MLB/search` was "the current documented endpoint for
free-text item search" and that authentication was "optional" per the
docs. Both statements were corrected after re-checking the current
official documentation. This section reflects the corrected findings.

- **Endpoint called:** `GET https://api.mercadolibre.com/sites/MLB/search?q=...`
- **Official documentation (source of truth):**
  developers.mercadolivre.com.br/pt_br/itens-e-buscas ("Itens e Buscas"),
  last updated by Mercado Livre on **2026-08-31**.
- **What that documentation actually says:** `/sites/{SITE_ID}/search` is
  documented **only** for `nickname` and `seller_id` lookups. Every
  example shown for this endpoint sends
  `Authorization: Bearer ACCESS_TOKEN`. A free-text `q` parameter is
  **not** part of this endpoint's documented contract — the officially
  documented `q` parameter belongs to the separate `/products/search`
  catalog/GTIN endpoint, which this project does not use.
- **Classification:** this project's `q`-based call is **experimental /
  not officially documented** — not "officially documented and
  supported," and not confirmed as "working live" either (see below).
  Kept only for this phase's learning value; not a stable contract.
- **Authentication:** treat as **expected** for this endpoint family
  (every documented example requires a bearer token), even though this
  is unverified for the undocumented `q` usage specifically. The client
  sends `Authorization: Bearer <token>` only if
  `MERCADO_LIVRE_ACCESS_TOKEN` is set; it is never hardcoded and never
  required to import/call the module.
- **`available_quantity` field:** documented as a **reference bucket**,
  not exact stock — a real quantity in a range is rounded down to that
  range's floor before being published (e.g. a real 51-100 in stock is
  returned as the reference value `50`). Never present this field as
  precise inventory.
- **Observed behavior during manual validation (no token configured):**
  a direct call with `q=bebedouro automatico gatos` returned
  `HTTP 403` with body
  `{"message":"forbidden","error":"forbidden","status":403,"cause":[]}`.
  No results were returned. This does not confirm or rule out whether a
  valid bearer token would succeed, nor whether the block is specific to
  this network/IP — both are open questions for the next check.
- **Known risk:** if Mercado Livre fully removes free-text search access
  for third parties, or if a token becomes strictly required, only
  `src/integrations/mercadolivre.py` needs to change — no other module
  touches the API directly.

### Apify / Google Trends (`themineworks/google-trends-pro`, Phase 4)

- **Platform endpoint called:**
  `POST https://api.apify.com/v2/actors/themineworks~google-trends-pro/run-sync-get-dataset-items`
  — official Apify REST API, documented at
  https://docs.apify.com/api/v2/act-run-sync-get-dataset-items-post.
- **Actor:** `themineworks/google-trends-pro` — a third-party,
  **unofficial** Google Trends scraper running on Apify's own
  infrastructure. Apify-the-platform is low-risk (official, funded,
  documented); this specific Actor is medium-risk (no versioned schema
  guarantee, could be abandoned or broken by its author at any time).
- **Authentication:** `Authorization: Bearer <APIFY_API_TOKEN>` header,
  loaded from `.env` via `python-dotenv` (`src/config.py`). Required —
  calls fail fast with `ApifyTrendsConfigurationError` if missing.
- **Observed quirk (2026-10-29 live validation):** this endpoint returns
  `HTTP 201 Created` on success, not `200`. The integration treats any
  `2xx` as success; this was caught by running a real live query during
  implementation, not assumed.
- **Known risk — document explicitly:** the Actor reports **degraded
  reliability since 2026-07-30 due to Google-side rate limiting**. This
  is exactly why the Actor must remain fully replaceable behind
  `src/integrations/apify_trends.py` without requiring any change to
  `src/trend_analysis.py` or `src/trend_models.py` — confirmed by
  Phase 4's architecture (trend-analysis logic never imports Apify).
- **Cost (confirmed live):** $0.0025 per keyword report, within Apify's
  free $5/month credit (~2,000 free reports/month for this project's
  current usage).
- **Data semantics:** `interest_over_time` values are a 0-100 *relative*
  index, not absolute search volume — never compare raw values across
  unrelated keywords.
- **Observed behavior for a long-tail query:** `bebedouro automatico
  gatos` returned a technically successful response but with almost no
  signal (1 non-zero point out of 53) — a real data limitation (not
  enough search volume for that exact phrase), not an integration
  failure. The broader query `bebedouro para gatos` returned rich,
  varied data (53 points, 12 top + 2 rising related queries, 27
  regions).
- **Incident (2026-10-29) — per-section inconsistency, not a
  deterministic schema change:** a live CLI run for `bebedouro para
  gatos` returned `related_queries` and `interest_by_region`
  successfully but mapped `interest_over_time` to zero observations
  with no error. Four immediate follow-up live calls all returned the
  expected `interest_over_time` shape correctly — one later call
  returned `interest_over_time` correctly but `related_queries` empty.
  **Conclusion: the Actor is internally inconsistent across sections
  within a single run**, not a one-time schema migration. Treat this as
  ongoing, not resolved — a single "it worked" smoke test is not
  sufficient evidence the Actor is healthy; check per-section
  consistency as its own checklist item (added above). Hardened in
  `src/integrations/apify_trends.py`: a list-wrapped interest value
  (`[36]` instead of `36`, a known real Google Trends raw-API shape) is
  now unwrapped automatically; and non-empty `interest_over_time` that
  fails to parse into any numeric value now raises
  `ApifyTrendsDataError` instead of silently reporting zero
  observations.
- **Further corroboration (Phase 5, same day):** during Phase 5 live
  validation, one call returned an explicit Actor error row
  (`errorMessage: "No data returned"`, raised as
  `ApifyTrendsActorError`) for the exact same query that had succeeded
  moments earlier with full data. Handled correctly (no crash, clean
  message) by both the integration layer and `run_demand_analysis()`.
  This is additional evidence for "internally inconsistent across
  calls," not a new failure mode — no code change was needed here.

## How to perform the check

### Mercado Livre

1. Re-read developers.mercadolivre.com.br/pt_br/itens-e-buscas and
   confirm whether `/sites/{SITE_ID}/search` still documents only
   `nickname`/`seller_id`, or whether a free-text `q` parameter has been
   added to its documented contract. Note the page's "last updated" date.
2. If a valid `MERCADO_LIVRE_ACCESS_TOKEN` becomes available, re-run
   `python -m src.main`, choose option 2, search
   `bebedouro automatico gatos`, and record the exact status code and
   whether results came back — with and without the token.
3. Compare the response shape against the fields `_map_item()` in
   `src/integrations/mercadolivre.py` currently extracts
   (`id`, `title`, `price`, `currency_id`, `seller.id`, `category_id`,
   `condition`, `permalink`, `shipping.free_shipping`,
   `available_quantity`). Re-verify the `available_quantity` bucket
   values are unchanged. Update the mapping if fields were renamed,
   removed, or if the bucket values changed.

### Apify / Google Trends

1. Confirm the Apify account/token is still active (check
   `apify_token_configured()` via `src/config.py` — never print the
   value) and check Apify's status page for platform-wide incidents.
2. Open the Actor's page (`apify.com/themineworks/google-trends-pro`)
   and check: last update date, current pricing, open issues/reviews
   mentioning breakage, and any note about Google-side rate limiting
   beyond what's already recorded above.
3. Run a live smoke test: `python -m src.main`, choose option `3`,
   search `bebedouro para gatos`, geo `BR`, timeframe `today 12-m`.
   Confirm the response still has `interest_over_time`,
   `interest_by_region`, and `related_queries.top`/`related_queries.rising`
   in the shape `_map_report_row()` in `src/integrations/apify_trends.py`
   expects. Note the exact HTTP status code returned (it was `201`, not
   `200`, as of this phase).
4. Check the run's actual cost via
   `GET https://api.apify.com/v2/actors/themineworks~google-trends-pro/runs`
   (field `usageTotalUsd`) and compare against the $0.0025/report
   recorded above.

### Margin Analysis inputs (Phase 7)

Phase 7 has NO live external dependency (no HTTP, no Mercado Livre, no
Apify) -- `src/margin_models.py` and `src/margin_analysis.py` operate
entirely on explicit user input. The checks below are therefore about
money precision, architectural discipline, and regression coverage,
not source availability.

- [ ] Money precision: confirm every monetary/rate field on
      `MarginInputs` is still `Decimal`, never `float` -- re-check any
      new field added since this review uses `_to_decimal()` /
      `Decimal(str(value))`, never `Decimal(value)` directly on a float
- [ ] Rounding policy: confirm `ROUND_HALF_UP` to 2 decimal places is
      still applied to each individually meaningful monetary amount as
      soon as it's computed (not only once at the very end) --
      `src/margin_analysis.py` `_round_money()`/`_round_percent()`
- [ ] **Marketplace fee assumption rule**: confirm NO current Mercado
      Livre fee table/percentage is hardcoded anywhere in
      `src/margin_analysis.py` or `src/margin_models.py`. Marketplace
      fees change over time by category/listing type/price/plan --
      they must remain a configurable input (`marketplace_fee_amount`
      / `marketplace_fee_rate` / `fixed_marketplace_fee`) until a
      dedicated, explicitly-versioned fee adapter is built as a
      SEPARATE module that still only ever produces a `MarginInputs`
      (see "Future marketplace-fee adapter" below)
- [ ] **Tax assumption rule**: confirm NO Brazilian tax regime or fixed
      percentage is hardcoded anywhere. Tax depends on business
      structure/regime/context -- `tax_amount`/`tax_rate` must remain
      optional, user-supplied inputs
- [ ] Fee amount vs. rate precedence: confirm
      `marketplace_fee_amount` + (`marketplace_fee_rate` OR
      `fixed_marketplace_fee`) together still raises `ValueError`
      (same for `tax_amount` + `tax_rate`) -- this must never silently
      pick a winner
- [ ] Cost completeness logic: confirm `cost_completeness_score` is
      still a plain `100 * known / 8` count, NOT Phase 5/6's
      coverage-cap formula (the semantics genuinely differ here -- see
      docs/LEARNING.md Fase 7)
- [ ] Score thresholds: `MIN_COST_COMPLETENESS_FOR_SCORE` (50%) and
      `MARGIN_SCORE_ANCHORS` are provisional, documented, and
      adjustable -- re-confirm they are still labeled as such
      everywhere they're displayed (CLI, README)
- [ ] Break-even denominator: confirm `denominator <= 0` (not just
      `< 0`) is still handled safely (no crash, `break_even_price =
      None` with a note) -- exact-zero is a real, reachable case
- [ ] Missing vs. zero semantics: re-run
      `test_explicit_zero_shipping_differs_from_unknown_shipping` and
      `test_explicit_zero_marketplace_fee_rate_differs_from_unknown_fee`
      specifically after any refactor -- these are the two regression
      tests most likely to silently break if someone "simplifies" the
      None-handling later
- [ ] **Future marketplace-fee adapter rule**: if/when Mercado Livre
      access is restored and a fee-lookup adapter is eventually built,
      it MUST live in `src/integrations/` (or similar), know nothing
      about `src/margin_analysis.py`'s formulas, and produce nothing
      but a populated `MarginInputs` -- the architecture is
      `marketplace rules/fee integration -> MarginInputs ->
      deterministic Margin Analysis`, same direction as every other
      phase's `integration -> models -> analysis` pipeline. The
      deterministic engine must never be taught to call out to a fee
      API directly.
- [ ] **Future tax adapter rule**: same architectural rule as above,
      for any future tax-rate lookup.
- [ ] Regression tests: full suite still passing
      (`python -m pytest -v` and `pytest -v`), including the
      Decimal-precision and rounding tests in
      `tests/test_margin_analysis.py`

### Supplier Analysis inputs (Phase 8)

Phase 8, like Phase 7, has NO live external dependency -- no HTTP, no
Mercado Livre, no Apify, no scraping. `src/supplier_models.py` and
`src/supplier_analysis.py` operate entirely on explicit user input.

- [ ] **`SupplierInputs` schema**: re-confirm all 20 optional fields
      still match `src/supplier_models.py`'s field list and docstring
      if the model is ever extended
- [ ] **MOQ semantics**: `moq_units >= 1` if given (0 is not a
      meaningful minimum) -- re-confirm this validation still holds
- [ ] **Stock semantics**: `stock_quantity` (a count) and
      `stock_available` (a tri-state boolean) remain two SEPARATE
      fields, never merged -- re-confirm `stock_quantity < moq_units`
      is still allowed to CONSTRUCT (it's a real blocker condition,
      not an input-representation conflict) while fee/lead-time-style
      ambiguous representations are still rejected
- [ ] **Lead-time derivation**: `lead_time_days` explicit vs.
      `dispatch_time_days + delivery_time_days` -- re-confirm supplying
      an explicit total together with BOTH components is still
      rejected at construction (no double counting), while supplying
      only one component alongside an explicit total is still allowed
- [ ] **Boolean tri-state handling**: re-run
      `test_fulfillment_boolean_tristate_excludes_unknown` and
      `test_trust_boolean_tristate_excludes_unknown` after any
      refactor -- these are the tests most likely to silently break if
      someone "simplifies" `None`-handling into `False` later
- [ ] **Blocker logic**: re-confirm `stock_quantity == 0` /
      `stock_available is False` / `stock_quantity < moq_units` are
      still the ONLY hard blockers, and that `dropshipping_supported
      == False` still does NOT block (documented as a deliberate
      choice -- bulk sourcing remains viable)
- [ ] **Score weights**: `WEIGHT_ORDER_FLEXIBILITY` (0.25) /
      `WEIGHT_OPERATIONAL_SPEED` (0.20) / `WEIGHT_STOCK_VIABILITY`
      (0.20) / `WEIGHT_FULFILLMENT_CAPABILITY` (0.15) / `WEIGHT_TRUST`
      (0.20) and all piecewise-linear anchors are provisional,
      documented, recalibrate only against real outcome data
- [ ] **Completeness weights**: re-verify `EVIDENCE_WEIGHTS` in
      `src/supplier_analysis.py` still sums to exactly 1.0 after any
      edit (`sum(EVIDENCE_WEIGHTS.values()) == 1.0`) -- this is easy to
      silently break by adding/removing a field without rebalancing
- [ ] **Rating/review semantics**: `supplier_rating` is a 0-5 scale
      input CONTRACT (not a universal provider behavior) --
      re-confirm out-of-range values are still rejected; re-confirm
      `RATING_CREDIBILITY_ANCHORS` still shrinks low-review-count
      ratings toward neutral (50) rather than trusting them at face
      value
- [ ] **Future supplier adapters**: if/when a real supplier directory,
      B2B marketplace API, or crawler is integrated, it MUST live in
      `src/integrations/` (or similar), know nothing about
      `src/supplier_analysis.py`'s formulas, and produce nothing but a
      populated `SupplierInputs` -- same `integration -> models ->
      analysis` direction as every other phase
- [ ] **Future scraping/API integration boundary**: any future
      automated supplier-data collection must still never let
      `src/supplier_analysis.py` import HTTP/Apify/Mercado
      Livre/browser-automation code directly
- [ ] **No "Mercado Livre seller == supplier" assumption**: re-confirm
      `src/supplier_models.py` and `src/supplier_analysis.py` still
      import NOTHING from `src.integrations` (`grep -n "^import\|^from"
      src/supplier_*.py` should show only `dataclasses`/`decimal`) --
      this is the single most important rule in this phase
- [ ] Regression tests: full suite still passing
      (`python -m pytest -v` and `pytest -v`)

### Shared

1. Check `pip list --outdated` for `requests`, `python-dotenv`, and
   `pytest`.
2. Run `python -m pytest -v` and `pytest -v` — both must pass.
3. Update `README.md`, `docs/LEARNING.md`, and this file if anything
   changed.
