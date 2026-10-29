import pytest

from src.demand_models import DemandSignals, build_demand_signals
from src.integrations.mercadolivre import MercadoLivreItem
from src.trend_analysis import TrendMetrics
from src.trend_models import RelatedQuery, TrendData, TrendPoint, TrendRegion


def make_trend_data(
    regions=None,
    top=None,
    rising=None,
    points=None,
    related_queries_available=None,
    regional_interest_available=None,
    interest_over_time_available=None,
):
    regions = regions or []
    top = top or []
    rising = rising or []
    points = points if points is not None else [TrendPoint(date="2026-01-01", value=50, formatted_value="50")]

    kwargs = dict(
        query="bebedouro para gatos",
        geo="BR",
        timeframe="today 12-m",
        retrieved_at="2026-10-29T12:00:00Z",
        interest_over_time=points,
        interest_by_region=regions,
        related_top_queries=top,
        related_rising_queries=rising,
        source="apify:themineworks/google-trends-pro",
    )
    # Mirror the real integration layer's default rule (available iff
    # non-empty) unless the test explicitly overrides it, to simulate
    # an Actor that reported a section as unreliable despite an empty
    # list looking the same as a genuine zero.
    kwargs["related_queries_available"] = (
        related_queries_available if related_queries_available is not None else (len(top) > 0 or len(rising) > 0)
    )
    kwargs["regional_interest_available"] = (
        regional_interest_available if regional_interest_available is not None else len(regions) > 0
    )
    kwargs["interest_over_time_available"] = (
        interest_over_time_available if interest_over_time_available is not None else len(points) > 0
    )
    return TrendData(**kwargs)


def make_trend_metrics(**overrides):
    base = dict(
        observation_count=52,
        average_interest=60.0,
        recent_average=65.0,
        previous_average=55.0,
        percentage_change=18.18,
        direction="growing",
        volatility=10.0,
        provisional_trend_score=70.0,
        notes=[],
    )
    base.update(overrides)
    return TrendMetrics(**base)


def make_item(price):
    return MercadoLivreItem(
        item_id="MLB1",
        title="Bebedouro",
        price=price,
        currency_id="BRL",
        seller_id=1,
        category_id="MLB123",
        condition="new",
        permalink=None,
        free_shipping=None,
        available_quantity=None,
    )


def test_build_demand_signals_with_both_sources():
    regions = [
        TrendRegion(region_code="BR-SP", region_name="Sao Paulo", value=100),
        TrendRegion(region_code="BR-RJ", region_name="Rio de Janeiro", value=0),
        TrendRegion(region_code="BR-MG", region_name="Minas Gerais", value=None),
    ]
    top = [RelatedQuery(query="q1", value=10, formatted_value="10", link=None)]
    rising = [
        RelatedQuery(query="q2", value=20, formatted_value="20", link=None),
        RelatedQuery(query="q3", value=30, formatted_value="30", link=None),
    ]
    trend_data = make_trend_data(regions=regions, top=top, rising=rising)
    trend_metrics = make_trend_metrics()
    marketplace_items = [make_item(10.0), make_item(20.0), make_item(None)]

    signals = build_demand_signals(
        "bebedouro para gatos",
        "BR",
        trend_data=trend_data,
        trend_metrics=trend_metrics,
        marketplace_items=marketplace_items,
    )

    assert signals.trend_score == 70.0
    assert signals.trend_direction == "growing"
    assert signals.average_search_interest == 60.0
    assert signals.recent_search_interest == 65.0
    assert signals.trend_observation_count == 52
    assert signals.related_query_count == 3  # 1 top + 2 rising
    assert signals.rising_query_count == 2
    assert signals.regional_spread == 1  # only Sao Paulo has value > 0
    assert signals.marketplace_sample_size == 3
    assert signals.price_dispersion == pytest.approx(5.0)  # pstdev([10, 20])
    assert signals.source_coverage == pytest.approx(1.0)


def test_build_demand_signals_trend_only():
    trend_data = make_trend_data()
    trend_metrics = make_trend_metrics()

    signals = build_demand_signals(
        "bebedouro para gatos", "BR", trend_data=trend_data, trend_metrics=trend_metrics
    )

    assert signals.marketplace_sample_size is None
    assert signals.price_dispersion is None
    assert signals.source_coverage == pytest.approx(0.5)
    assert any("marketplace" in note for note in signals.notes)


def test_build_demand_signals_nothing_available():
    signals = build_demand_signals("bebedouro para gatos", "BR")

    assert signals.trend_score is None
    assert signals.trend_observation_count == 0
    assert signals.related_query_count is None
    assert signals.regional_spread is None
    assert signals.marketplace_sample_size is None
    assert signals.source_coverage == pytest.approx(0.0)
    assert any("trend" in note for note in signals.notes)
    assert any("marketplace" in note for note in signals.notes)


def test_build_demand_signals_price_dispersion_none_with_fewer_than_two_prices():
    trend_data = make_trend_data()
    signals = build_demand_signals(
        "bebedouro para gatos",
        "BR",
        trend_data=trend_data,
        trend_metrics=make_trend_metrics(),
        marketplace_items=[make_item(10.0), make_item(None)],
    )

    assert signals.price_dispersion is None


def test_build_demand_signals_marketplace_sample_size_is_not_renamed_as_total():
    """Regression: a small page sample must never be mistaken for a total count."""
    signals = build_demand_signals(
        "bebedouro para gatos",
        "BR",
        marketplace_items=[make_item(10.0) for _ in range(10)],  # looks like a "full page"
    )

    assert signals.marketplace_sample_size == 10
    assert any("page-limited" in note for note in signals.notes)


# --- Section availability: observed zero vs. unavailable -------------------


def test_related_queries_unavailable_when_actor_section_empty():
    """An empty related_queries section is NOT a confirmed zero."""
    trend_data = make_trend_data(top=[], rising=[], related_queries_available=False)
    signals = build_demand_signals(
        "bebedouro para gatos", "BR", trend_data=trend_data, trend_metrics=make_trend_metrics()
    )

    assert signals.related_query_count is None
    assert signals.rising_query_count is None
    assert any("related-query breadth unavailable" in note for note in signals.notes)


def test_regional_interest_unavailable_when_actor_section_empty():
    """An empty interest_by_region section is NOT a confirmed zero."""
    trend_data = make_trend_data(regions=[], regional_interest_available=False)
    signals = build_demand_signals(
        "bebedouro para gatos", "BR", trend_data=trend_data, trend_metrics=make_trend_metrics()
    )

    assert signals.regional_spread is None
    assert any("regional interest unavailable" in note for note in signals.notes)


def test_both_subsections_unavailable_simultaneously():
    trend_data = make_trend_data(
        top=[], rising=[], regions=[], related_queries_available=False, regional_interest_available=False
    )
    signals = build_demand_signals(
        "bebedouro para gatos", "BR", trend_data=trend_data, trend_metrics=make_trend_metrics()
    )

    assert signals.related_query_count is None
    assert signals.regional_spread is None
    # trend-level signals (from trend_metrics) remain available even
    # though both trend_data subsections are unreliable.
    assert signals.trend_score == 70.0


def test_genuine_observed_zero_is_preserved_when_section_available():
    """When the section IS available, a real zero must be reported as 0, not None."""
    regions = [
        TrendRegion(region_code="BR-SP", region_name="Sao Paulo", value=0),
        TrendRegion(region_code="BR-RJ", region_name="Rio de Janeiro", value=0),
    ]
    trend_data = make_trend_data(regions=regions, regional_interest_available=True)
    signals = build_demand_signals(
        "bebedouro para gatos", "BR", trend_data=trend_data, trend_metrics=make_trend_metrics()
    )

    assert signals.regional_spread == 0  # observed zero, not unavailable
    assert not any("regional interest unavailable" in note for note in signals.notes)


@pytest.mark.parametrize(
    "overrides",
    [
        {"average_search_interest": 150},
        {"recent_search_interest": -1},
        {"trend_score": 101},
        {"source_coverage": 1.5},
        {"trend_observation_count": -1},
        {"related_query_count": -1},
        {"regional_spread": -1},
        {"marketplace_sample_size": -1},
        {"price_dispersion": -1},
    ],
)
def test_demand_signals_rejects_invalid_values(overrides):
    base = dict(
        query="x",
        geo="BR",
        trend_score=50.0,
        trend_direction="stable",
        average_search_interest=50.0,
        recent_search_interest=50.0,
        trend_observation_count=10,
        related_query_count=5,
        rising_query_count=1,
        regional_spread=5,
        marketplace_sample_size=5,
        price_dispersion=5.0,
        source_coverage=0.5,
    )
    base.update(overrides)
    with pytest.raises(ValueError):
        DemandSignals(**base)


def test_demand_signals_rejects_unknown_direction():
    with pytest.raises(ValueError):
        DemandSignals(
            query="x",
            geo="BR",
            trend_score=None,
            trend_direction="sideways",
            average_search_interest=None,
            recent_search_interest=None,
            trend_observation_count=0,
            related_query_count=None,
            rising_query_count=None,
            regional_spread=None,
            marketplace_sample_size=None,
            price_dispersion=None,
            source_coverage=0.0,
        )
