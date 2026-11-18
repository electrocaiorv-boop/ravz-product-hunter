import pytest

from src.competition_analysis import analyze_competition
from src.competition_models import CompetitionSignals


def make_signals(**overrides):
    base = dict(
        query="x",
        marketplace_sample_size=None,
        total_result_count=None,
        seller_count=None,
        unique_seller_ratio=None,
        price_min=None,
        price_max=None,
        price_mean=None,
        price_median=None,
        price_dispersion=None,
        free_shipping_ratio=None,
        condition_distribution=None,
        duplicate_title_ratio=None,
        source_coverage=0.0,
        notes=[],
    )
    base.update(overrides)
    return CompetitionSignals(**base)


def test_high_competition_sample():
    signals = make_signals(
        marketplace_sample_size=10,
        unique_seller_ratio=0.2,
        price_dispersion=0.05,
        duplicate_title_ratio=0.8,
        free_shipping_ratio=0.9,
        source_coverage=1.0,
    )
    result = analyze_competition(signals, requested_limit=10)

    assert result.competition_score == pytest.approx(84.0, abs=0.01)
    assert result.listing_saturation_contribution is None


def test_low_competition_sample():
    signals = make_signals(
        marketplace_sample_size=2,
        unique_seller_ratio=1.0,
        price_dispersion=0.6,
        duplicate_title_ratio=0.0,
        free_shipping_ratio=0.0,
        source_coverage=1.0,
    )
    result = analyze_competition(signals, requested_limit=10)

    assert result.competition_score == pytest.approx(0.0, abs=0.01)


def test_concentrated_sellers_score_high():
    signals = make_signals(unique_seller_ratio=0.1, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.seller_concentration_contribution == pytest.approx(90.0)


def test_diverse_sellers_score_low():
    signals = make_signals(unique_seller_ratio=1.0, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.seller_concentration_contribution == pytest.approx(0.0)


def test_tightly_clustered_prices_score_as_crowded():
    signals = make_signals(price_dispersion=0.0, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.price_crowding_contribution == pytest.approx(100.0)


def test_highly_dispersed_prices_score_as_not_crowded():
    signals = make_signals(price_dispersion=1.0, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.price_crowding_contribution == pytest.approx(0.0)


def test_missing_prices_excludes_price_crowding():
    signals = make_signals(marketplace_sample_size=5, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.price_crowding_contribution is None
    assert "price dispersion data" in result.unavailable


def test_missing_sellers_excludes_seller_concentration():
    signals = make_signals(marketplace_sample_size=5, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.seller_concentration_contribution is None
    assert "seller concentration data" in result.unavailable


def test_missing_shipping_excludes_shipping_contribution():
    signals = make_signals(marketplace_sample_size=5, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.shipping_contribution is None
    assert "free-shipping data" in result.unavailable


def test_duplicate_titles_contribute_proportionally():
    signals = make_signals(duplicate_title_ratio=0.5, source_coverage=1.0)
    result = analyze_competition(signals)

    assert result.duplicate_listing_contribution == pytest.approx(50.0)


def test_source_failure_yields_no_score_and_zero_confidence():
    signals = make_signals(source_coverage=0.0)
    result = analyze_competition(signals)

    assert result.competition_score is None
    assert result.confidence_score == pytest.approx(0.0)
    assert any("no marketplace evidence at all" in note for note in result.notes)


def test_no_competition_evidence_produces_none_score():
    """Explicit regression for the 'never fabricate a score' failure-behavior rule."""
    signals = make_signals(source_coverage=0.0)
    result = analyze_competition(signals)

    assert result.competition_score is None


def test_observed_zero_vs_unavailable_for_shipping():
    zero_ratio = make_signals(free_shipping_ratio=0.0, source_coverage=1.0)
    unavailable_ratio = make_signals(free_shipping_ratio=None, source_coverage=1.0)

    result_zero = analyze_competition(zero_ratio)
    result_unavailable = analyze_competition(unavailable_ratio)

    assert result_zero.shipping_contribution == pytest.approx(0.0)
    assert result_unavailable.shipping_contribution is None


def test_confidence_with_one_source_family_is_capped():
    """Even a fully complete, full-size sample cannot exceed the single-source cap."""
    signals = make_signals(
        marketplace_sample_size=10,
        unique_seller_ratio=0.5,
        price_dispersion=0.2,
        duplicate_title_ratio=0.3,
        free_shipping_ratio=0.4,
        source_coverage=1.0,
    )
    result = analyze_competition(signals, requested_limit=10)

    assert result.confidence_score == pytest.approx(55.0, abs=0.01)


@pytest.mark.parametrize(
    "overrides",
    [
        {"unique_seller_ratio": 1.5},
    ],
)
def test_invalid_signal_values_rejected_at_construction(overrides):
    with pytest.raises(ValueError):
        make_signals(**overrides)


# --- Hardening review regressions: sample size / limit must not drive score ---


def test_listing_saturation_contribution_is_always_none():
    """Regression for the Phase 6 hardening bug: a full page must never
    be scored as 'the market is saturated' -- it only ever tells us
    'at least this many items were mapped'."""
    full_page = make_signals(marketplace_sample_size=10, source_coverage=1.0)
    small_page = make_signals(marketplace_sample_size=1, source_coverage=1.0)
    no_sample_info = make_signals(source_coverage=1.0)

    for signals in (full_page, small_page, no_sample_info):
        result = analyze_competition(signals)
        assert result.listing_saturation_contribution is None


def test_sample_size_alone_cannot_change_competition_score():
    """Identical defensible features, three different sample sizes -> identical score."""
    common = dict(
        unique_seller_ratio=0.3,
        price_dispersion=0.3,
        duplicate_title_ratio=0.4,
        free_shipping_ratio=0.5,
        source_coverage=1.0,
    )
    small = make_signals(marketplace_sample_size=5, **common)
    medium = make_signals(marketplace_sample_size=10, **common)
    large = make_signals(marketplace_sample_size=50, **common)

    score_small = analyze_competition(small).competition_score
    score_medium = analyze_competition(medium).competition_score
    score_large = analyze_competition(large).competition_score

    assert score_small == score_medium == score_large


def test_requested_limit_alone_cannot_change_competition_score():
    """The requested_limit parameter affects Confidence only, never the Competition Score."""
    signals = make_signals(
        marketplace_sample_size=10,
        unique_seller_ratio=0.3,
        price_dispersion=0.3,
        duplicate_title_ratio=0.4,
        free_shipping_ratio=0.5,
        source_coverage=1.0,
    )

    score_5 = analyze_competition(signals, requested_limit=5).competition_score
    score_10 = analyze_competition(signals, requested_limit=10).competition_score
    score_50 = analyze_competition(signals, requested_limit=50).competition_score

    assert score_5 == score_10 == score_50


def test_total_result_count_remains_none_without_provider_metadata():
    """CompetitionSignals built with no total_result_count must stay None through analysis."""
    signals = make_signals(marketplace_sample_size=10, total_result_count=None, source_coverage=1.0)
    result = analyze_competition(signals, requested_limit=10)

    assert result.observed["total_result_count"] is None
    assert any("total marketplace result count" in item for item in result.unavailable)


def test_empty_sample_with_no_defensible_components_yields_none_score():
    """With listing_saturation disabled, an empty sample has nothing left
    to score from -- Competition Score must be None, not a fabricated 0."""
    signals = make_signals(marketplace_sample_size=0, source_coverage=1.0)
    result = analyze_competition(signals, requested_limit=10)

    assert result.competition_score is None
    assert result.listing_saturation_contribution is None
    assert any("no defensible components" in note for note in result.notes)


def test_result_does_not_expose_market_wide_fields():
    """Naming hygiene: nothing on the result should imply a market-wide claim."""
    signals = make_signals(unique_seller_ratio=0.3, source_coverage=1.0)
    result = analyze_competition(signals)

    forbidden = {"market_share", "total_sellers", "marketplace_dominance", "total_competitors"}
    assert not (forbidden & set(vars(result).keys()))


# --- Fase 13: category-catalog sample_adequacy branch -----------------------


def test_sample_adequacy_uses_products_sampled_over_top_n_when_present():
    """When signals came from the category-catalog builder
    (products_sampled is not None), sample_adequacy must use
    products_sampled/requested_top_n, NOT marketplace_sample_size/requested_limit.
    marketplace_sample_size is set here to a deliberately misleading value
    (50 offers, way over requested_limit=10) to prove the old path is not
    the one being used.
    """
    signals = make_signals(
        marketplace_sample_size=50,
        products_sampled=2,
        unique_seller_ratio=0.5,
        source_coverage=1.0,
    )
    result = analyze_competition(signals, requested_limit=10, requested_top_n=5)
    # completeness: seller + price(None here) + duplicate(None) + shipping(None)
    # -> only seller_c present = 1/5 groups = 20%; sample_adequacy = 2/5 = 40%
    # confidence = min(0.6*20 + 0.4*40, 55) = min(28, 55) = 28
    assert result.confidence_score == pytest.approx(28.0)


def test_sample_adequacy_full_products_sampled_caps_at_full_adequacy():
    signals = make_signals(
        marketplace_sample_size=3,  # would read as low adequacy on the OLD path
        products_sampled=5,
        unique_seller_ratio=0.5,
        price_dispersion=0.1,
        free_shipping_ratio=0.5,
        source_coverage=1.0,
    )
    result = analyze_competition(signals, requested_limit=10, requested_top_n=5)
    # completeness: seller + price + shipping present, duplicate+saturation
    # permanently absent -> 3/5 = 60%; sample_adequacy = 5/5 = 100%
    # confidence = min(0.6*60 + 0.4*100, 55) = min(76, 55) = 55 (anchor cap)
    assert result.confidence_score == pytest.approx(55.0)


def test_sample_adequacy_falls_back_to_marketplace_sample_size_when_products_sampled_is_none():
    """The flat-sample path (products_sampled is None) is untouched."""
    signals = make_signals(
        marketplace_sample_size=10,
        unique_seller_ratio=0.5,
        source_coverage=1.0,
    )
    result = analyze_competition(signals, requested_limit=10, requested_top_n=5)
    # Same as before this change: sample_adequacy = min(10,10)/10 = 100%
    # completeness: only seller present = 1/5 = 20%
    # confidence = min(0.6*20 + 0.4*100, 55) = min(52, 55) = 52
    assert result.confidence_score == pytest.approx(52.0)


def test_duplicate_listing_pressure_excluded_renormalizes_like_listing_saturation():
    """A category-catalog signals object (duplicate_title_ratio permanently
    None) must score identically to a flat-sample signals object with the
    same other components and duplicate_title_ratio explicitly None --
    the weighted average renormalizes over available components either way.
    """
    common = dict(
        unique_seller_ratio=0.4,
        price_dispersion=0.1,
        free_shipping_ratio=0.6,
        duplicate_title_ratio=None,
        source_coverage=1.0,
    )
    flat_signals = make_signals(marketplace_sample_size=10, **common)
    catalog_signals = make_signals(marketplace_sample_size=10, products_sampled=5, **common)

    flat_result = analyze_competition(flat_signals, requested_limit=10)
    catalog_result = analyze_competition(catalog_signals, requested_limit=10, requested_top_n=5)

    assert flat_result.competition_score == pytest.approx(catalog_result.competition_score)
    assert catalog_result.duplicate_listing_contribution is None


def test_observed_exposes_category_catalog_provenance():
    signals = make_signals(
        marketplace_sample_size=5,
        category_id="MLB196208",
        category_name="Fones de Ouvido",
        products_sampled=2,
        product_names=["Produto A", "Produto B"],
        source_coverage=1.0,
    )
    result = analyze_competition(signals)
    assert result.observed["category_id"] == "MLB196208"
    assert result.observed["category_name"] == "Fones de Ouvido"
    assert result.observed["products_sampled"] == 2
    assert result.observed["product_names"] == ["Produto A", "Produto B"]


# --- Fase 13 fix: seller_concentration_index (not unique_seller_ratio) ----


def test_seller_concentration_prefers_the_index_when_present():
    """Regression for the live bug found 2026-11-17: a single-seller
    product must score as MAXIMALLY concentrated (near 100), not as
    "no concentration". `seller_concentration_index` is already in
    "harder when high" units -- no (1 - x) inversion here.
    """
    signals = make_signals(
        marketplace_sample_size=1,
        seller_concentration_index=1.0,  # one seller per sampled product
        unique_seller_ratio=0.0,  # deliberately contradictory decoy
        source_coverage=1.0,
    )
    result = analyze_competition(signals)
    assert result.seller_concentration_contribution == pytest.approx(100.0)


def test_seller_concentration_falls_back_to_unique_seller_ratio_when_index_absent():
    """The flat-sample path (seller_concentration_index is None) is untouched."""
    signals = make_signals(
        marketplace_sample_size=10,
        unique_seller_ratio=0.2,
        source_coverage=1.0,
    )
    result = analyze_competition(signals)
    assert result.seller_concentration_contribution == pytest.approx(80.0)


def test_observed_exposes_product_table():
    rows = [object(), object()]
    signals = make_signals(
        marketplace_sample_size=3,
        product_table=rows,
        source_coverage=1.0,
    )
    result = analyze_competition(signals)
    assert result.observed["product_table"] is rows
