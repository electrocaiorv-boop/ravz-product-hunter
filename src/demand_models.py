"""Provider-neutral internal data model for demand signals.

`DemandSignals` holds only derived/observed counts and scores -- never
raw provider objects (`TrendPoint`, `MercadoLivreItem`, etc.) -- so that
`src/demand_analysis.py` stays completely decoupled from how any of
these numbers were obtained. If a new signal source is added later
(a Demand Agent, a different marketplace), only `build_demand_signals()`
needs to change.

Two source FAMILIES are modeled for now:

  - "trend"        : Google Trends search-interest data, via the Apify
                      integration (Phase 4).
  - "marketplace"   : Mercado Livre listing/price data (Phase 3) --
                      currently unreachable (HTTP 403) in this
                      project's environment; see docs/MAINTENANCE.md.

Fields are None whenever the underlying signal is genuinely
unavailable -- never fabricated, never defaulted to a plausible-looking
placeholder. Never computable at all (sales volume, buyers, revenue,
conversion rate, absolute search volume) are not represented here --
they simply do not exist as fields.

== Observed zero vs. unavailable (hardened after the Phase 4/5 Actor
inconsistency incidents) ==

`trend_data.related_queries_available` and
`trend_data.regional_interest_available` (see `src/trend_models.py`)
are read here, not re-derived from list length, because the integration
layer is the only place with enough context to judge whether an empty
section is a confirmed zero or a silent failure. When a section is
unavailable, this module reports `None` for it -- NEVER `0` -- so that
`src/demand_analysis.py` excludes it from scoring instead of scoring a
possibly-fake zero.

== Marketplace sample size is NOT a total result count ==

`marketplace_sample_size` is `len(marketplace_items)` -- the number of
items `search_products()` returned for ONE page, capped at whatever
`limit` was passed to it (currently defaults to 10). It is NOT the
total number of marketplace listings for the query, and must never be
treated as a demand or competition signal on its own (a page cap tells
us nothing about whether 10 or 10,000 listings exist beyond the page).
It is kept here for evidence/transparency display only; see
`src/demand_analysis.py` for why it never contributes to scoring.
"""

import statistics
from dataclasses import dataclass, field

TOTAL_SOURCE_FAMILIES = 2

# Rough number of Brazilian state-level regions the Apify Actor's
# interest_by_region has been observed to return (confirmed live: 27).
# Used only to scale "how many regions show interest" into a 0-100-ish
# breadth number -- NOT an authoritative count of Brazilian states, and
# should be revisited if the Actor's regional granularity changes.
EXPECTED_BR_REGION_COUNT = 27


def _validate_range(name: str, value, lo: float, hi: float) -> None:
    if value is not None and not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}, got {value}")


def _validate_non_negative(name: str, value) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")


@dataclass
class DemandSignals:
    """Demand-relevant signals for one query, from whichever sources succeeded."""

    query: str
    geo: str

    # Trend-derived (Phase 4). trend_score/trend_direction are carried
    # over for display/evidence purposes only -- demand_analysis.py
    # computes its own trend_contribution from the more atomic
    # recent_search_interest + trend_direction fields, to avoid
    # double-counting Phase 4's already-blended provisional score.
    trend_score: float | None
    trend_direction: str | None
    average_search_interest: float | None
    recent_search_interest: float | None
    trend_observation_count: int
    related_query_count: int | None
    rising_query_count: int | None
    regional_spread: int | None

    # Marketplace-derived (Phase 3). marketplace_sample_size is a
    # page-capped item count, NOT a total result count -- see module
    # docstring. Always None while Mercado Livre search is unreachable.
    marketplace_sample_size: int | None
    price_dispersion: float | None

    # How many of the TOTAL_SOURCE_FAMILIES actually contributed data.
    source_coverage: float

    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_range("average_search_interest", self.average_search_interest, 0, 100)
        _validate_range("recent_search_interest", self.recent_search_interest, 0, 100)
        _validate_range("trend_score", self.trend_score, 0, 100)
        _validate_range("source_coverage", self.source_coverage, 0, 1)
        _validate_non_negative("trend_observation_count", self.trend_observation_count)
        _validate_non_negative("related_query_count", self.related_query_count)
        _validate_non_negative("rising_query_count", self.rising_query_count)
        _validate_non_negative("regional_spread", self.regional_spread)
        _validate_non_negative("marketplace_sample_size", self.marketplace_sample_size)
        _validate_non_negative("price_dispersion", self.price_dispersion)
        if self.trend_direction is not None and self.trend_direction not in (
            "growing",
            "stable",
            "declining",
            "unknown",
        ):
            raise ValueError(f"unrecognized trend_direction: {self.trend_direction}")


def build_demand_signals(
    query: str,
    geo: str,
    trend_data=None,
    trend_metrics=None,
    marketplace_items=None,
) -> DemandSignals:
    """Assemble DemandSignals from already-fetched, already-mapped data.

    Pass `trend_data` (src.trend_models.TrendData) and/or
    `trend_metrics` (src.trend_analysis.TrendMetrics) when the trend
    source succeeded, and `marketplace_items` (a list of
    MercadoLivreItem) when the marketplace source succeeded. Pass None
    for any source that failed or was never attempted -- its fields are
    represented honestly as unavailable, never guessed.
    """
    notes: list[str] = []
    sources_available = 0

    trend_score = None
    trend_direction = None
    average_search_interest = None
    recent_search_interest = None
    trend_observation_count = 0
    related_query_count = None
    rising_query_count = None
    regional_spread = None

    if trend_metrics is not None:
        trend_score = trend_metrics.provisional_trend_score
        trend_direction = trend_metrics.direction
        average_search_interest = trend_metrics.average_interest
        recent_search_interest = trend_metrics.recent_average
        trend_observation_count = trend_metrics.observation_count
        sources_available += 1
    else:
        notes.append("trend/search-interest signals unavailable (no trend data provided)")

    if trend_data is not None:
        if trend_data.related_queries_available:
            related_query_count = len(trend_data.related_top_queries) + len(
                trend_data.related_rising_queries
            )
            rising_query_count = len(trend_data.related_rising_queries)
        else:
            notes.append(
                "related-query breadth unavailable (the trend provider returned "
                "an empty related_queries section -- treated as unreliable, not "
                "a confirmed zero; see docs/MAINTENANCE.md)"
            )

        if trend_data.regional_interest_available:
            regional_spread = len(
                [r for r in trend_data.interest_by_region if r.value is not None and r.value > 0]
            )
        else:
            notes.append(
                "regional interest unavailable (the trend provider returned an "
                "empty interest_by_region section -- treated as unreliable, not "
                "a confirmed zero; see docs/MAINTENANCE.md)"
            )

    marketplace_sample_size = None
    price_dispersion = None
    if marketplace_items is not None:
        marketplace_sample_size = len(marketplace_items)
        prices = [item.price for item in marketplace_items if item.price is not None]
        if len(prices) >= 2:
            price_dispersion = statistics.pstdev(prices)
        sources_available += 1
        notes.append(
            "marketplace_sample_size is a page-limited item count, not a total "
            "marketplace result count -- see src/demand_analysis.py for why it "
            "does not contribute to the Demand Score"
        )
    else:
        notes.append(
            "marketplace signals unavailable (Mercado Livre search is currently "
            "unreliable in this environment -- see docs/MAINTENANCE.md)"
        )

    source_coverage = sources_available / TOTAL_SOURCE_FAMILIES

    return DemandSignals(
        query=query,
        geo=geo,
        trend_score=trend_score,
        trend_direction=trend_direction,
        average_search_interest=average_search_interest,
        recent_search_interest=recent_search_interest,
        trend_observation_count=trend_observation_count,
        related_query_count=related_query_count,
        rising_query_count=rising_query_count,
        regional_spread=regional_spread,
        marketplace_sample_size=marketplace_sample_size,
        price_dispersion=price_dispersion,
        source_coverage=source_coverage,
        notes=notes,
    )
