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
