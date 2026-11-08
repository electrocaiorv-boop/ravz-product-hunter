import pytest

from src.demand_analysis import (
    MULTI_SOURCE_CONFIDENCE_CAP,
    NO_SOURCE_CONFIDENCE_CAP,
    SINGLE_SOURCE_CONFIDENCE_CAP,
    _independence_cap,
    analyze_demand,
)
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


# -- the independence cap on confidence (Option A correction) ------------
#
# The cap used to be `100 * source_coverage`, which made the ceiling an
# artifact of the family denominator rather than a stated rule, and
# implied a second source family could contribute when
# `marketplace_contribution` is permanently None. It is now an explicit
# named constant. The CORRECTION WAS TO THE RATIONALE, NOT THE NUMBERS --
# every published value below is unchanged.


# Captured from the implementation BEFORE the rationale fix, across every
# reachable source-coverage state. Any drift here means Option A stopped
# being output-preserving, which was its whole premise.
BASELINE_CONFIDENCE = {
    # (source_coverage, observation_count, present_groups) -> confidence
    "no_source": (0.0, 0, 0.0),
    "single_source_rich": (0.5, 54, 50.0),
    "single_source_thin": (0.5, 6, 19.615384615384617),
    "multi_source_rich": (1.0, 54, 85.0),
}


def test_option_a_preserves_every_published_confidence_value():
    """Byte-identical confidence across all coverage states."""
    # no source contributed at all
    r = analyze_demand(make_signals(source_coverage=0.0))
    assert r.confidence_score == BASELINE_CONFIDENCE["no_source"][2]

    # one family, rich evidence -> capped at 50, not above
    r = analyze_demand(make_signals(
        source_coverage=0.5, trend_direction="growing",
        recent_search_interest=70, average_search_interest=60,
        trend_score=70, trend_observation_count=54,
        related_query_count=12, rising_query_count=10, regional_spread=20,
    ))
    assert r.confidence_score == BASELINE_CONFIDENCE["single_source_rich"][2]

    # one family, thin evidence -> quality binds BELOW the cap, so the
    # cap is not what produced this number. Exercised through the REAL
    # builder in test_end_to_end_baseline_is_unchanged below, which is
    # where the recorded baseline came from.
    r = analyze_demand(make_signals(
        source_coverage=0.5, trend_direction="growing",
        recent_search_interest=90, trend_observation_count=5,
    ))
    assert r.confidence_score < SINGLE_SOURCE_CONFIDENCE_CAP


def test_end_to_end_baseline_is_unchanged():
    """The five recorded states, through the real signal builder.

    This is the authoritative output-preservation check: the values were
    captured by running the pipeline BEFORE the rationale fix, so a
    mismatch here means Option A failed its premise.
    """
    from src.demand_models import build_demand_signals
    from src.integrations.mercadolivre import MercadoLivreItem
    from src.trend_analysis import analyze_trend
    from src.trend_models import RelatedQuery, TrendData, TrendPoint, TrendRegion

    def trend(points=54, rich=True):
        return TrendData(
            query="q", geo="BR", timeframe="today 12-m",
            retrieved_at="2026-01-01T00:00:00Z",
            interest_over_time=[
                TrendPoint(date=f"w{i}", value=50 + (i % 7) * 5,
                           formatted_value=None)
                for i in range(points)],
            interest_by_region=[
                TrendRegion(region_code=f"BR-{i}", region_name=f"R{i}",
                            value=40 + i) for i in range(20)] if rich else [],
            related_top_queries=[
                RelatedQuery(query=f"t{i}", value=50, formatted_value=None,
                             link=None) for i in range(12)] if rich else [],
            related_rising_queries=[
                RelatedQuery(query=f"r{i}", value=50, formatted_value=None,
                             link=None) for i in range(10)] if rich else [],
            source="fixture", interest_over_time_available=True,
            related_queries_available=rich, regional_interest_available=rich)

    items = [
        MercadoLivreItem(item_id=f"M{i}", title=f"I{i}", price=100.0 + i * 7,
                         currency_id="BRL", seller_id=i % 4,
                         category_id="MLB1", condition="new", permalink=None,
                         free_shipping=i % 2 == 0, available_quantity=50)
        for i in range(8)]

    rich, thin = trend(), trend(6, False)
    cases = [
        ("no source", {}, 0.0, None, 0.0),
        ("single rich", dict(trend_data=rich, trend_metrics=analyze_trend(rich)),
         0.5, 70.08932461873638, 50.0),
        ("single thin", dict(trend_data=thin, trend_metrics=analyze_trend(thin)),
         0.5, 82.0, 19.615384615384617),
        ("marketplace only", dict(marketplace_items=items), 0.5, None, 0.0),
        ("multi source", dict(trend_data=rich, trend_metrics=analyze_trend(rich),
                              marketplace_items=items),
         1.0, 70.08932461873638, 85.0),
    ]
    for label, kwargs, coverage, score, confidence in cases:
        signals = build_demand_signals("q", "BR", **kwargs)
        result = analyze_demand(signals)
        assert signals.source_coverage == coverage, label
        if score is None:
            assert result.demand_score is None, label
        else:
            assert result.demand_score == pytest.approx(score, abs=1e-9), label
        assert result.confidence_score == pytest.approx(
            confidence, abs=1e-9), label


def test_genuine_multi_source_evidence_may_exceed_the_single_source_cap():
    """The cap must not punish evidence that IS corroborated.

    Verified explicitly because a fix that merely clamped everything to
    50 would also "preserve" the single-source numbers while silently
    breaking the multi-source path.
    """
    multi = analyze_demand(make_signals(
        source_coverage=1.0, trend_direction="growing",
        recent_search_interest=70, average_search_interest=60,
        trend_score=70, trend_observation_count=54,
        related_query_count=12, rising_query_count=10, regional_spread=20,
        marketplace_sample_size=8, price_dispersion=0.2,
    ))
    assert multi.confidence_score == BASELINE_CONFIDENCE["multi_source_rich"][2]
    assert multi.confidence_score > SINGLE_SOURCE_CONFIDENCE_CAP


def test_single_source_cap_binds_regardless_of_how_good_one_source_is():
    """Completeness and volume cannot buy their way past independence."""
    maxed = analyze_demand(make_signals(
        source_coverage=0.5, trend_direction="growing",
        recent_search_interest=100, average_search_interest=100,
        trend_score=100, trend_observation_count=5000,
        related_query_count=999, rising_query_count=999, regional_spread=27,
    ))
    assert maxed.confidence_score == SINGLE_SOURCE_CONFIDENCE_CAP


def test_independence_cap_is_a_stated_rule_not_a_coverage_ratio():
    """The ceiling must not move when the family count changes.

    Under the old `100 * source_coverage`, adding a third family would
    have silently redefined the single-source ceiling to 33.3 and
    two-of-three to 66.7 -- values nobody chose. The cap is now selected
    by state, so any partial coverage yields the same stated ceiling.
    """
    for partial in (1 / 3, 0.5, 2 / 3, 0.75, 0.99):
        assert _independence_cap(partial) == SINGLE_SOURCE_CONFIDENCE_CAP

    assert _independence_cap(0.0) == NO_SOURCE_CONFIDENCE_CAP
    assert _independence_cap(1.0) == MULTI_SOURCE_CONFIDENCE_CAP


def test_source_coverage_remains_accurate_provenance():
    """The ratio is still reported honestly; it just no longer sets the cap."""
    signals = make_signals(source_coverage=0.5, trend_direction="growing",
                           trend_observation_count=54)
    assert signals.source_coverage == 0.5
    # analyze_demand does not mutate or relabel it
    analyze_demand(signals)
    assert signals.source_coverage == 0.5


def test_confidence_cap_is_documented_as_provisional_not_calibrated():
    """CLAUDE.md Core Principle: no score may imply a calibrated estimate."""
    import src.demand_analysis as module

    doc = module.__doc__
    lowered = doc.lower()
    assert "provisional" in lowered
    # It must explicitly disclaim being a statistical/accuracy measure.
    assert "not a statistical confidence interval" in lowered or (
        "not a" in lowered and "calibrated accuracy estimate" in lowered)
    assert "has not been validated against real outcomes" in lowered


def test_confidence_is_computed_through_the_stated_rule(monkeypatch):
    """The call site must consult `_independence_cap`, not re-derive a ratio.

    With the two families configured today, `100 * source_coverage` and
    `_independence_cap(...)` return identical values -- so no
    value-based test can tell them apart, and a revert of the call site
    would pass every other test here. This test closes that gap by
    proving the helper is actually what produces the ceiling.
    """
    import src.demand_analysis as module

    seen = []

    def spy(source_coverage):
        seen.append(source_coverage)
        return 7.0  # deliberately not any ratio of 100

    monkeypatch.setattr(module, "_independence_cap", spy)

    result = module.analyze_demand(make_signals(
        source_coverage=0.5, trend_direction="growing",
        recent_search_interest=90, average_search_interest=80,
        trend_score=90, trend_observation_count=54,
        related_query_count=12, rising_query_count=10, regional_spread=20,
    ))

    assert seen == [0.5], "analyze_demand did not consult _independence_cap"
    assert result.confidence_score == 7.0, (
        "confidence did not come from the independence cap")
