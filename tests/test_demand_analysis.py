import pytest

from src.demand_analysis import analyze_demand
from src.demand_models import DemandSignals


def make_signals(**overrides):
    base = dict(
        query="bebedouro para gatos",
        geo="BR",
        trend_score=None,
        trend_direction=None,
        average_search_interest=None,
        recent_search_interest=None,
        trend_observation_count=0,
        related_query_count=None,
        rising_query_count=None,
        regional_spread=None,
        marketplace_sample_size=None,
        price_dispersion=None,
        source_coverage=0.0,
        notes=[],
    )
    base.update(overrides)
    return DemandSignals(**base)


def test_strong_demand_low_confidence():
    """Strong single-source signal, but little evidence volume/breadth -> low confidence."""
    signals = make_signals(
        trend_direction="growing",
        recent_search_interest=90,
        trend_observation_count=5,
        source_coverage=0.5,
    )
    result = analyze_demand(signals)

    assert result.demand_score == pytest.approx(94.0, abs=0.01)
    assert result.confidence_score == pytest.approx(18.85, abs=0.1)
    assert result.confidence_score < 25
    assert result.marketplace_contribution is None
    assert "marketplace listing/price data (total result count not available)" in result.unavailable


def test_weak_demand():
    signals = make_signals(
        trend_direction="declining",
        recent_search_interest=10,
        trend_observation_count=52,
        related_query_count=2,
        rising_query_count=0,
        regional_spread=3,
        marketplace_sample_size=5,
        source_coverage=1.0,
    )
    result = analyze_demand(signals)

    assert result.demand_score == pytest.approx(8.38, abs=0.05)
    assert result.demand_score < 20
    assert result.marketplace_contribution is None


def test_growing_but_niche_demand():
    signals = make_signals(
        trend_direction="growing",
        recent_search_interest=30,
        trend_observation_count=52,
        related_query_count=1,
        rising_query_count=1,
        regional_spread=2,
        source_coverage=0.5,
    )
    result = analyze_demand(signals)

    # Growth pulls the score up, but thin breadth/regional spread keeps
    # it well below "strong" -- neither signal is allowed to dominate.
    assert 15 < result.demand_score < 45


def test_stable_broad_demand():
    signals = make_signals(
        trend_direction="stable",
        recent_search_interest=55,
        trend_observation_count=52,
        related_query_count=16,
        rising_query_count=2,
        regional_spread=24,
        marketplace_sample_size=20,
        source_coverage=1.0,
    )
    result = analyze_demand(signals)

    assert result.demand_score == pytest.approx(67.92, abs=0.05)
    # Completeness can never reach 100% while marketplace is excluded
    # from scoring (3 of 4 component groups max) -- confidence reflects
    # that honestly rather than claiming full certainty.
    assert result.confidence_score == pytest.approx(85.0, abs=0.01)


def test_sparse_data_yields_low_confidence():
    signals = make_signals(
        trend_direction=None,
        recent_search_interest=50,
        trend_observation_count=3,
        source_coverage=0.5,
    )
    result = analyze_demand(signals)

    assert result.demand_score == pytest.approx(50.0, abs=0.01)
    assert result.confidence_score < 20


def test_missing_marketplace_data_does_not_change_demand_score():
    """Marketplace never contributes to Demand Score now (page-size != total count)."""
    common = dict(
        trend_direction="stable",
        recent_search_interest=50,
        trend_observation_count=52,
        related_query_count=10,
        rising_query_count=2,
        regional_spread=10,
    )
    with_marketplace = make_signals(**common, marketplace_sample_size=25, source_coverage=1.0)
    without_marketplace = make_signals(**common, marketplace_sample_size=None, source_coverage=0.5)

    result_with = analyze_demand(with_marketplace)
    result_without = analyze_demand(without_marketplace)

    assert result_without.marketplace_contribution is None
    assert result_with.marketplace_contribution is None
    # Demand Score must be IDENTICAL -- marketplace presence/absence
    # cannot move it at all, since it never contributes.
    assert result_without.demand_score == pytest.approx(result_with.demand_score, abs=1e-9)
    # But Confidence must still differ: one more independent source
    # family raises the coverage cap.
    assert result_without.confidence_score < result_with.confidence_score


def test_empty_signals_produce_no_demand_score():
    signals = make_signals()
    result = analyze_demand(signals)

    assert result.demand_score is None
    assert result.confidence_score == pytest.approx(0.0)
    assert len(result.unavailable) == 4
    assert any("no demand signals available" in note for note in result.notes)


@pytest.mark.parametrize(
    "overrides",
    [
        {"recent_search_interest": 150},
        {"regional_spread": -5},
        {"source_coverage": 2.0},
    ],
)
def test_invalid_signal_values_rejected_at_construction(overrides):
    with pytest.raises(ValueError):
        make_signals(**overrides)


# --- Confidence: source independence must bound data completeness ---------


def test_one_source_family_with_complete_data_cannot_produce_high_confidence():
    """Regression for the hardening review: completeness/volume alone must
    never push confidence past the source-coverage cap."""
    signals = make_signals(
        trend_direction="growing",
        recent_search_interest=90,
        trend_observation_count=52,
        related_query_count=18,
        rising_query_count=3,
        regional_spread=25,
        marketplace_sample_size=None,
        source_coverage=0.5,  # only the trend source family available
    )
    result = analyze_demand(signals)

    # Demand looks strong...
    assert result.demand_score > 85
    # ...but confidence is hard-capped by source coverage, not allowed
    # to look like strong multi-source corroboration.
    assert result.confidence_score == pytest.approx(50.0, abs=0.01)
    assert result.confidence_score <= 55


def test_two_source_families_produce_materially_higher_confidence():
    signals = make_signals(
        trend_direction="growing",
        recent_search_interest=90,
        trend_observation_count=52,
        related_query_count=18,
        rising_query_count=3,
        regional_spread=25,
        marketplace_sample_size=40,
        source_coverage=1.0,  # trend AND marketplace both contributed data
    )
    result = analyze_demand(signals)

    assert result.confidence_score == pytest.approx(85.0, abs=0.01)
    assert result.confidence_score > 50 + 20  # materially higher than the 1-family cap


def test_marketplace_sample_size_never_contributes_regardless_of_magnitude():
    """A page-capped sample size must never be scored as a total result count,
    no matter how large it looks."""
    small = make_signals(marketplace_sample_size=1, source_coverage=0.5)
    large = make_signals(marketplace_sample_size=1000, source_coverage=0.5)

    result_small = analyze_demand(small)
    result_large = analyze_demand(large)

    assert result_small.marketplace_contribution is None
    assert result_large.marketplace_contribution is None
    assert result_small.demand_score == result_large.demand_score  # both None here
