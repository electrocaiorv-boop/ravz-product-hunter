"""Deterministic Competition Analysis layer.

This module knows NOTHING about HTTP, Apify, Mercado Livre, or any
integration -- it only imports `src.competition_models`. No LLM, no
embeddings, no randomness, no wall-clock dependency. Given the same
`CompetitionSignals`, it always produces the same
`CompetitionAnalysisResult`.

== What Competition Score answers (and does not) ==

    "How difficult does this market appear for a new seller/product?"

NOT "how popular is the product?" (that is Demand, Phase 5). A query
can have strong Demand and weak Competition (opportunity), or weak
Demand and strong Competition (avoid), or any other combination --
these two scores are computed from different evidence and must never
be merged here.

== The "one street block" problem (source independence, re-applied) ==

Phase 5 established: correlated evidence from one source family must
not be mistaken for independent corroboration. Competition has a
different shape of the same problem. There is only ONE conceivable
source family here (Mercado Livre) -- so the risk is not "1 of 2
families," it's that multiple features (seller mix, price stats,
shipping, title duplication) are all computed from the SAME small,
page-capped sample from ONE API call. Computing several things from
one block of one street does not mean you have surveyed several
blocks. Confidence here is bounded by (a) whether the one source even
succeeded, and (b) how adequate that one sample's SIZE is -- never
inflated just because many features were successfully extracted from
it (that is completeness, not independence).

== CORRECTED (hardening review) -- sample size is not a competition
signal, and it never was ==

An earlier version of this module scored `listing_saturation` from
`marketplace_sample_size` vs. the requested page limit, reasoning "a
full page suggests more listings exist." This violated the project's
own modeling rule from the Phase 6 source evaluation:
`marketplace_sample_size` is capped by OUR OWN requested `limit` -- a
full page only ever tells us "at least `limit` items were mapped," and
scoring that number scores our own request parameter, not the market.
`listing_saturation_contribution` is now ALWAYS `None` and is
permanently excluded from the Competition Score, the same way Phase 5
permanently excluded its own page-capped marketplace count. The weight
slot is kept (not deleted) so this can be re-enabled later, honestly,
if a genuine provider total/paging field is ever mapped.
`marketplace_sample_size` still appears in `observed` for transparency
-- it is evidence of what we looked at, never a scoring input.

== Competition Score (0-100) -- PROVISIONAL, not validated against outcomes ==

0 = low apparent competition. 100 = very high apparent competition.
Four SAMPLE-LEVEL components, each 0-100, blended by weighted average
over whichever are actually available (missing components excluded,
weights renormalized over whatever remains -- never defaulted, never
scored as a fabricated zero). Every component below describes the
~10-item SAMPLE, never the marketplace as a whole:

    seller_concentration  (base weight 0.30):
        100 * (1 - unique_seller_ratio). Few distinct sellers WITHIN
        THE SAMPLE (low ratio) is scored as HARDER for a newcomer --
        incumbents likely have reputation/supply advantages. This
        directional choice is a judgment call, documented as such; it
        is NOT a market-share claim, only a SAMPLE-level observation
        (see src/competition_models.py: "sample concentration", never
        "marketplace dominance").

    price_crowding          (base weight 0.20):
        100 * (1 - clamp(price_dispersion / MAX_EXPECTED_CV, 0, 1)).
        LOW price dispersion WITHIN THE SAMPLE (tightly clustered
        prices) is scored as MORE crowded/commoditized -- sellers
        competing on near-identical price points, harder to
        differentiate. HIGH dispersion is treated as a segmented
        market (variants, bundles, quality tiers), not automatically
        "more competitive". This is the conservative interpretation
        the project chose; see docs/LEARNING.md Fase 6 for the
        reasoning.

    duplicate_listing_pressure (base weight 0.15):
        100 * duplicate_title_ratio (within the sample). A weak proxy
        for commoditized, templated listings -- deliberately
        low-weighted.

    shipping_competitiveness (base weight 0.10):
        100 * free_shipping_ratio (within the sample). A weak proxy
        for baseline seller expectations a newcomer would need to
        match -- deliberately the lowest-weighted component, per the
        Phase 6 instruction not to over-weight it.

    listing_saturation (base weight 0.25): ALWAYS None. See above.

== Confidence Score (0-100) -- always computable, PROVISIONAL ==

    0 if the marketplace source did not succeed at all (source_coverage
      == 0) -- no usable evidence, never a guessed number.

    Otherwise: min(internal_quality_score, MAX_CONFIDENCE_SINGLE_SOURCE)

        internal_quality_score = 0.6 * completeness_score + 0.4 * sample_adequacy_score
            completeness_score     = how many of the 5 conceptual component
                                      groups are non-null, out of 5 -- the
                                      denominator stays 5 (not 4) even
                                      though listing_saturation can never
                                      be non-null, so completeness can
                                      never claim more than 80%: an
                                      honest, permanent reminder that one
                                      piece of the picture is structurally
                                      missing, the same choice Phase 5
                                      made for its own disabled component.
            sample_adequacy_score   = 100 * min(marketplace_sample_size, requested_limit) / requested_limit
                                      -- this use of sample size is about
                                      CONFIDENCE (how much evidence do we
                                      have), never about the Competition
                                      Score itself (what does the evidence
                                      say). Conflating the two was exactly
                                      the bug this review fixed.

        MAX_CONFIDENCE_SINGLE_SOURCE = 55 is a PROVISIONAL, DOCUMENTED
        ANCHOR, not an empirically validated figure -- chosen to mirror
        Phase 5's ~50-55 cap for "1 of 2 source families", reinterpreted
        for a domain where there is structurally only one source. It
        should be revisited once real outcome data exists; until then,
        treat it as "clearly bounded well below full certainty", not as
        a precise number.

All weights/scales/caps are module-level constants, meant to be
recalibrated later against real outcomes -- not treated as final. This
Competition Score is NOT wired into the Phase 1 Opportunity Scoring
Engine yet.

== Fase 13: this module's scoring math did NOT change ==

`src/competition_models.build_competition_signals_from_category_sample()`
builds `CompetitionSignals` from a working, differently-shaped source
(top-N category best-sellers and their real seller offers) instead of
the policy-blocked `/sites/MLB/search`. Every weighted component above
reads `CompetitionSignals` fields exactly as before -- `unique_seller_ratio`
and `price_dispersion` just arrive computed as per-product averages
now (see that function's docstring), and `duplicate_title_ratio`
arrives permanently `None` for that source, which this module already
handles the same way it handles `listing_saturation_contribution` being
permanently `None`: exclude from the weighted average, renormalize over
what remains, and let `completeness_score` honestly reflect it.

The ONE real change here is `sample_adequacy_score`'s denominator --
see `analyze_competition()`'s docstring for why `requested_limit`
(a page-size limit) doesn't apply to a sample shaped around
`requested_top_n` (how many catalog entries were asked for).
"""

from dataclasses import dataclass, field

from src.competition_models import CompetitionSignals

WEIGHT_SELLER_CONCENTRATION = 0.30
WEIGHT_LISTING_SATURATION = 0.25  # unused weight slot -- see module docstring
WEIGHT_PRICE_CROWDING = 0.20
WEIGHT_DUPLICATE_TITLE = 0.15
WEIGHT_SHIPPING = 0.10

MAX_EXPECTED_CV = 0.5  # coefficient of variation at/above which price dispersion is treated as "fully segmented" (0 crowding contribution)

CONFIDENCE_COMPLETENESS_WEIGHT = 0.6
CONFIDENCE_SAMPLE_WEIGHT = 0.4
MAX_CONFIDENCE_SINGLE_SOURCE = 55.0
TOTAL_COMPONENT_GROUPS = 5  # includes the permanently-disabled saturation group -- see module docstring

# Mirrors mercadolivre_catalog.DEFAULT_TOP_N. Duplicated, not imported --
# this module stays provider-neutral (imports only src.competition_models).
# Used only as sample_adequacy_score's denominator when signals came from
# the Fase 13 category-catalog sample (signals.products_sampled is not
# None); see analyze_competition() below.
DEFAULT_CATEGORY_TOP_N = 5


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))


@dataclass
class CompetitionAnalysisResult:
    """Deterministic output of analyze_competition(). Both scores are PROVISIONAL."""

    query: str
    competition_score: float | None
    confidence_score: float
    seller_concentration_contribution: float | None
    listing_saturation_contribution: float | None  # always None -- see module docstring
    price_crowding_contribution: float | None
    duplicate_listing_contribution: float | None
    shipping_contribution: float | None
    observed: dict
    derived: dict
    unavailable: list[str]
    notes: list[str] = field(default_factory=list)


def _seller_concentration_contribution(signals: CompetitionSignals) -> float | None:
    """Fase 13 fix: the category-catalog builder reports
    `seller_concentration_index` (already in "harder when high" units
    -- see `competition_models.build_competition_signals_from_category_sample`'s
    docstring for why `unique_seller_ratio` could not be reused here).
    The flat-sample builder never sets that field, so it falls through
    to the original `unique_seller_ratio`-based formula, unchanged.
    """
    if signals.seller_concentration_index is not None:
        return _clamp(100 * signals.seller_concentration_index)
    if signals.unique_seller_ratio is None:
        return None
    return _clamp(100 * (1 - signals.unique_seller_ratio))


def _listing_saturation_contribution(signals: CompetitionSignals) -> float | None:
    # Intentionally always None: marketplace_sample_size is capped by
    # our own requested `limit` and is not a market-size or saturation
    # signal -- scoring it would score our own query parameter, not
    # the market. See module docstring. Re-enable only once a genuine
    # provider total/paging field is mapped.
    return None


def _price_crowding_contribution(signals: CompetitionSignals) -> float | None:
    if signals.price_dispersion is None:
        return None
    normalized = _clamp(signals.price_dispersion / MAX_EXPECTED_CV, 0, 1)
    return _clamp(100 * (1 - normalized))


def _duplicate_listing_contribution(signals: CompetitionSignals) -> float | None:
    if signals.duplicate_title_ratio is None:
        return None
    return _clamp(100 * signals.duplicate_title_ratio)


def _shipping_contribution(signals: CompetitionSignals) -> float | None:
    if signals.free_shipping_ratio is None:
        return None
    return _clamp(100 * signals.free_shipping_ratio)


def analyze_competition(
    signals: CompetitionSignals,
    requested_limit: int = 10,
    requested_top_n: int = DEFAULT_CATEGORY_TOP_N,
) -> CompetitionAnalysisResult:
    """Compute a deterministic, provisional Competition Score and Confidence Score.

    `requested_limit`/`requested_top_n` affect ONLY the Confidence
    Score's sample-adequacy term -- neither has any effect on the
    Competition Score, since no Competition Score component depends on
    sample size, limit or top_n.

    Which one is used depends on where `signals` came from, detected by
    `signals.products_sampled` (only the Fase 13 category-catalog
    builder sets it):

    - `signals.products_sampled is not None` (category-catalog sample):
      adequacy = how many of the requested top-N highlighted
      products/items actually yielded usable evidence --
      `products_sampled / requested_top_n`. The old `requested_limit`
      doesn't apply here: it was a page-size limit on a flat search,
      and this sample's "limit" is how many catalog entries we asked
      to look at, not how many offers came back per entry (Mercado
      Livre decides that).
    - otherwise (flat marketplace sample): the original
      `marketplace_sample_size / requested_limit`, unchanged.
    """
    seller_c = _seller_concentration_contribution(signals)
    saturation_c = _listing_saturation_contribution(signals)
    price_c = _price_crowding_contribution(signals)
    duplicate_c = _duplicate_listing_contribution(signals)
    shipping_c = _shipping_contribution(signals)

    components = (
        (seller_c, WEIGHT_SELLER_CONCENTRATION),
        (saturation_c, WEIGHT_LISTING_SATURATION),
        (price_c, WEIGHT_PRICE_CROWDING),
        (duplicate_c, WEIGHT_DUPLICATE_TITLE),
        (shipping_c, WEIGHT_SHIPPING),
    )
    available = [(c, w) for c, w in components if c is not None]

    notes = list(signals.notes)
    unavailable = []
    if seller_c is None:
        unavailable.append("seller concentration data")
    unavailable.append(
        "listing saturation (disabled -- marketplace_sample_size is capped by our "
        "own request limit, not a market-size signal)"
    )
    if price_c is None:
        unavailable.append("price dispersion data")
    if duplicate_c is None:
        unavailable.append("duplicate-title data")
    if shipping_c is None:
        unavailable.append("free-shipping data")
    unavailable.append("total marketplace result count (no provider total/paging field is mapped)")
    unavailable.append("true market share, total sales, seller revenue, advertising spend, conversion rate")

    if signals.source_coverage == 0 or not available:
        competition_score = None
        if signals.source_coverage == 0:
            notes.append("no marketplace evidence at all; Competition Score cannot be computed")
        else:
            notes.append("marketplace sample had no defensible components; Competition Score cannot be computed")
    else:
        total_weight = sum(w for _, w in available)
        competition_score = _clamp(sum(c * w for c, w in available) / total_weight)

    if signals.source_coverage == 0:
        confidence_score = 0.0
    else:
        present_groups = sum(1 for c in (seller_c, saturation_c, price_c, duplicate_c, shipping_c) if c is not None)
        completeness_score = 100 * present_groups / TOTAL_COMPONENT_GROUPS
        if signals.products_sampled is not None:
            sample_adequacy_score = _clamp(
                100 * min(signals.products_sampled, requested_top_n) / requested_top_n
            )
        else:
            sample_size = signals.marketplace_sample_size or 0
            sample_adequacy_score = _clamp(100 * min(sample_size, requested_limit) / requested_limit)
        internal_quality_score = (
            CONFIDENCE_COMPLETENESS_WEIGHT * completeness_score
            + CONFIDENCE_SAMPLE_WEIGHT * sample_adequacy_score
        )
        confidence_score = _clamp(min(internal_quality_score, MAX_CONFIDENCE_SINGLE_SOURCE))

    observed = {
        "marketplace_sample_size": signals.marketplace_sample_size,
        "total_result_count": signals.total_result_count,
        "seller_count": signals.seller_count,
        "price_min": signals.price_min,
        "price_max": signals.price_max,
        "free_shipping_ratio": signals.free_shipping_ratio,
        "condition_distribution": signals.condition_distribution,
        # Fase 13 category-catalog provenance -- None for the flat-sample
        # builder. The report layer uses these to say what the sample
        # represents ("top N best-sellers of category X and their
        # sellers"), never "the whole marketplace".
        "category_id": signals.category_id,
        "category_name": signals.category_name,
        "products_sampled": signals.products_sampled,
        "product_names": signals.product_names,
        # Per-product decision-support rows (name, offer/seller counts,
        # price range, official-store tri-state, free-shipping ratio).
        # Purely descriptive -- see ProductObservation's docstring.
        "product_table": signals.product_table,
    }
    derived = {
        "unique_seller_ratio": signals.unique_seller_ratio,
        "seller_concentration_index": signals.seller_concentration_index,
        "price_mean": signals.price_mean,
        "price_median": signals.price_median,
        "price_dispersion": signals.price_dispersion,
        "duplicate_title_ratio": signals.duplicate_title_ratio,
        "seller_concentration_contribution": seller_c,
        "listing_saturation_contribution": saturation_c,
        "price_crowding_contribution": price_c,
        "duplicate_listing_contribution": duplicate_c,
        "shipping_contribution": shipping_c,
    }

    return CompetitionAnalysisResult(
        query=signals.query,
        competition_score=competition_score,
        confidence_score=confidence_score,
        seller_concentration_contribution=seller_c,
        listing_saturation_contribution=saturation_c,
        price_crowding_contribution=price_c,
        duplicate_listing_contribution=duplicate_c,
        shipping_contribution=shipping_c,
        observed=observed,
        derived=derived,
        unavailable=unavailable,
        notes=notes,
    )
