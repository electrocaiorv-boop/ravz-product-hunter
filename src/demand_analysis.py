"""Deterministic Demand Analysis layer.

This module knows NOTHING about HTTP, Apify, Mercado Livre, or any
integration -- it only imports `src.demand_models`. Given the same
`DemandSignals`, it always produces the same `DemandAnalysisResult`.
No LLM, no randomness, no wall-clock dependency.

== Demand Score vs Confidence Score ==

These answer two different questions and must never be collapsed into
one number:

    Demand Score     -- "how strong does demand appear, based on the
                         evidence we have?"
    Confidence Score  -- "how much evidence do we actually have to
                         support that conclusion?"

A Demand Score of 80 backed by a single, thin source (low Confidence)
is NOT the same situation as a Demand Score of 80 backed by multiple
consistent, well-populated sources (high Confidence).

== Data completeness vs. source independence (modeling fix) ==

These are different things and must not be blended as if they were the
same kind of evidence:

    Data completeness   -- how much of what ONE source family could
                            tell us did we actually receive? (e.g. did
                            the trend source return its trend level,
                            its related queries, AND its regional
                            breakdown, or only some of those?)
    Source independence  -- how many DIFFERENT, uncorrelated source
                            families corroborate the finding?

`interest_over_time`, `related_queries`, and `interest_by_region` are
all derived from the SAME underlying Google Trends signal via the SAME
Actor call. A query having all three populated is good *completeness*
-- it is NOT three independent witnesses confirming demand; it is one
witness whose testimony we heard in full. Only a genuinely different
source family (e.g. Mercado Livre) is a second, independent witness.
Completeness can make a single-source Confidence Score look deceptively
high if it isn't explicitly bounded by source coverage -- that is
exactly the bug this version fixes (a live run with ONLY the trend
source available previously produced Confidence 67.5, which reads as
much stronger multi-source evidence than it actually was).

== Demand Score (0-100) -- PROVISIONAL, not validated against outcomes ==

Four components, each 0-100, blended by a WEIGHTED AVERAGE computed
ONLY over the components that are actually available -- missing
components are excluded entirely (never defaulted to a neutral value,
and NEVER scored as zero just because a section was unavailable), and
weights are renormalized over whatever remains. If none are available,
the Demand Score is None.

    trend_contribution       (base weight 0.40):
        0.6 * recent_search_interest
      + 0.4 * direction_score   (growing=100, stable=50, declining=0,
                                  unknown/missing -> excluded)

    breadth_contribution       (base weight 0.25):
        None if the trend provider's related-query section was
        unavailable (see src/trend_models.py TrendData.related_queries_available)
        -- an empty section is NOT scored as zero breadth. Otherwise:
        weighted_count = top_related_count + rising_count * RISING_QUERY_WEIGHT
        scaled against BREADTH_SATURATION_COUNT, clamped to [0, 100].

    regional_contribution      (base weight 0.20):
        None if the trend provider's regional section was unavailable
        (TrendData.regional_interest_available) -- same rule as above.
        Otherwise: regions showing interest, scaled against
        EXPECTED_BR_REGION_COUNT.

    marketplace_contribution   (base weight 0.15):
        ALWAYS None for now. `marketplace_sample_size` is a page-capped
        item count (see src/demand_models.py), not a total marketplace
        result count -- a page size is not a demand signal, so it is
        intentionally excluded from scoring until a genuine total-result
        field is available from the Mercado Livre integration. The
        weight slot is kept so this can be re-enabled later without
        restructuring the formula.

One weak or saturated proxy cannot dominate: each component is capped
at its own base weight's share of the total, and no component is ever
backfilled with a guessed value.

== Confidence Score (0-100) -- always computable, PROVISIONAL ==

Two-stage model, so that a single source family's data being complete
and voluminous can NEVER be mistaken for multi-source corroboration:

    1. internal_quality_score (0-100) -- how good is the evidence we
       actually received, from whichever source(s) contributed:
           0.6 * completeness_score   (how many of the 4 components above
                                        are non-null)
         + 0.4 * volume_score          (trend_observation_count against
                                        EXPECTED_OBSERVATION_COUNT)

    2. coverage_cap = 100 * source_coverage -- a HARD CAP derived from
       source INDEPENDENCE, not quality. With 1 of 2 source families
       (source_coverage=0.5), confidence can never exceed 50, no matter
       how complete or voluminous that one source's data is. With 2 of
       2, the cap is 100 and internal_quality_score alone determines
       the result.

    confidence_score = min(internal_quality_score, coverage_cap)

This directly encodes the example rule from the Phase 5 hardening
review: ~50 max for 1-of-2 source families, up to 100 for 2-of-2
(bounded further by actual completeness/volume). All weights/scales/
caps are module-level constants, meant to be recalibrated later against
real outcomes -- not treated as final.
"""

from dataclasses import dataclass, field

from src.demand_models import DemandSignals, EXPECTED_BR_REGION_COUNT

WEIGHT_TREND = 0.40
WEIGHT_BREADTH = 0.25
WEIGHT_REGIONAL = 0.20
WEIGHT_MARKETPLACE = 0.15

TREND_LEVEL_WEIGHT = 0.6
TREND_DIRECTION_WEIGHT = 0.4
DIRECTION_SCORES = {"growing": 100.0, "stable": 50.0, "declining": 0.0}

BREADTH_SATURATION_COUNT = 20.0
RISING_QUERY_WEIGHT = 0.5

EXPECTED_OBSERVATION_COUNT = 52.0

CONFIDENCE_COMPLETENESS_WEIGHT = 0.6
CONFIDENCE_VOLUME_WEIGHT = 0.4
TOTAL_COMPONENT_GROUPS = 4  # trend, breadth, regional, marketplace


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


@dataclass
class DemandAnalysisResult:
    """Deterministic output of analyze_demand(). Both scores are PROVISIONAL."""

    query: str
    demand_score: float | None
    confidence_score: float
    trend_contribution: float | None
    breadth_contribution: float | None
    regional_contribution: float | None
    marketplace_contribution: float | None
    observed: dict
    derived: dict
    unavailable: list[str]
    notes: list[str] = field(default_factory=list)


def _trend_contribution(signals: DemandSignals) -> float | None:
    parts = []
    weights = []
    if signals.recent_search_interest is not None:
        parts.append(_clamp(signals.recent_search_interest))
        weights.append(TREND_LEVEL_WEIGHT)
    direction_score = DIRECTION_SCORES.get(signals.trend_direction or "")
    if direction_score is not None:
        parts.append(direction_score)
        weights.append(TREND_DIRECTION_WEIGHT)
    if not parts:
        return None
    total_weight = sum(weights)
    return sum(p * w for p, w in zip(parts, weights)) / total_weight


def _breadth_contribution(signals: DemandSignals) -> float | None:
    # related_query_count is None both when the trend source failed
    # entirely AND when its related-query section was unavailable --
    # either way, there is nothing trustworthy to score, so exclude it.
    if signals.related_query_count is None:
        return None
    rising_count = signals.rising_query_count or 0
    top_count = max(signals.related_query_count - rising_count, 0)
    weighted_count = top_count + rising_count * RISING_QUERY_WEIGHT
    return _clamp(100 * weighted_count / BREADTH_SATURATION_COUNT)


def _regional_contribution(signals: DemandSignals) -> float | None:
    if signals.regional_spread is None:
        return None
    return _clamp(100 * signals.regional_spread / EXPECTED_BR_REGION_COUNT)


def _marketplace_contribution(signals: DemandSignals) -> float | None:
    # Intentionally always None: marketplace_sample_size is a
    # page-capped item count, not a total marketplace result count --
    # scoring it would score our own `limit` parameter, not demand. See
    # module docstring and src/demand_models.py. Re-enable only once a
    # genuine total-result-count field is extracted from Mercado Livre.
    return None


def analyze_demand(signals: DemandSignals) -> DemandAnalysisResult:
    """Compute a deterministic, provisional Demand Score and Confidence Score."""
    trend_c = _trend_contribution(signals)
    breadth_c = _breadth_contribution(signals)
    regional_c = _regional_contribution(signals)
    marketplace_c = _marketplace_contribution(signals)

    components = (
        (trend_c, WEIGHT_TREND),
        (breadth_c, WEIGHT_BREADTH),
        (regional_c, WEIGHT_REGIONAL),
        (marketplace_c, WEIGHT_MARKETPLACE),
    )
    available = [(c, w) for c, w in components if c is not None]

    notes = list(signals.notes)
    unavailable = []
    if trend_c is None:
        unavailable.append("trend/search-interest data")
    if breadth_c is None:
        unavailable.append("related-query breadth data")
    if regional_c is None:
        unavailable.append("regional interest data")
    unavailable.append("marketplace listing/price data (total result count not available)")

    if not available:
        demand_score = None
        notes.append("no demand signals available at all; Demand Score cannot be computed")
    else:
        total_weight = sum(w for _, w in available)
        demand_score = _clamp(sum(c * w for c, w in available) / total_weight)

    present_groups = sum(1 for c in (trend_c, breadth_c, regional_c, marketplace_c) if c is not None)
    completeness_score = 100 * present_groups / TOTAL_COMPONENT_GROUPS
    volume_score = _clamp(100 * signals.trend_observation_count / EXPECTED_OBSERVATION_COUNT)

    internal_quality_score = (
        CONFIDENCE_COMPLETENESS_WEIGHT * completeness_score
        + CONFIDENCE_VOLUME_WEIGHT * volume_score
    )
    coverage_cap = 100 * signals.source_coverage
    confidence_score = _clamp(min(internal_quality_score, coverage_cap))

    observed = {
        "trend_observation_count": signals.trend_observation_count,
        "related_query_count": signals.related_query_count,
        "rising_query_count": signals.rising_query_count,
        "regional_spread": signals.regional_spread,
        "marketplace_sample_size": signals.marketplace_sample_size,
    }
    derived = {
        "trend_score": signals.trend_score,
        "trend_direction": signals.trend_direction,
        "average_search_interest": signals.average_search_interest,
        "recent_search_interest": signals.recent_search_interest,
        "price_dispersion": signals.price_dispersion,
        "trend_contribution": trend_c,
        "breadth_contribution": breadth_c,
        "regional_contribution": regional_c,
        "marketplace_contribution": marketplace_c,
    }

    return DemandAnalysisResult(
        query=signals.query,
        demand_score=demand_score,
        confidence_score=confidence_score,
        trend_contribution=trend_c,
        breadth_contribution=breadth_c,
        regional_contribution=regional_c,
        marketplace_contribution=marketplace_c,
        observed=observed,
        derived=derived,
        unavailable=unavailable,
        notes=notes,
    )
