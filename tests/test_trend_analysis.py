import pytest

from src.trend_analysis import analyze_interest_series, analyze_trend
from src.trend_models import TrendData, TrendPoint


def make_points(values):
    return [
        TrendPoint(date=f"2026-01-{i + 1:02d}", value=v, formatted_value=str(v))
        for i, v in enumerate(values)
    ]


def test_strongly_growing_series():
    metrics = analyze_interest_series(make_points([10, 10, 10, 10, 90, 90, 90, 90]))

    assert metrics.observation_count == 8
    assert metrics.previous_average == pytest.approx(10.0)
    assert metrics.recent_average == pytest.approx(90.0)
    assert metrics.percentage_change == pytest.approx(800.0)
    assert metrics.direction == "growing"
    assert metrics.provisional_trend_score is not None
    assert metrics.provisional_trend_score > 70


def test_mildly_growing_series():
    metrics = analyze_interest_series(make_points([50, 50, 56, 56]))

    assert metrics.previous_average == pytest.approx(50.0)
    assert metrics.recent_average == pytest.approx(56.0)
    assert metrics.percentage_change == pytest.approx(12.0)
    assert metrics.direction == "growing"
    assert metrics.provisional_trend_score is not None


def test_stable_series():
    metrics = analyze_interest_series(make_points([50, 52, 49, 51]))

    assert metrics.percentage_change == pytest.approx(-1.9608, abs=1e-3)
    assert metrics.direction == "stable"


def test_declining_series():
    metrics = analyze_interest_series(make_points([90, 90, 90, 90, 10, 10, 10, 10]))

    assert metrics.percentage_change == pytest.approx(-88.8889, abs=1e-3)
    assert metrics.direction == "declining"
    assert metrics.provisional_trend_score is not None
    assert metrics.provisional_trend_score < 30


def test_volatile_series():
    values = [0, 100, 0, 100, 0, 100, 0, 100]
    metrics = analyze_interest_series(make_points(values))

    assert metrics.previous_average == pytest.approx(50.0)
    assert metrics.recent_average == pytest.approx(50.0)
    assert metrics.percentage_change == pytest.approx(0.0)
    assert metrics.direction == "stable"
    assert metrics.volatility == pytest.approx(50.0)
    # base = 0.6*50 + 0.4*50 = 50; direction_adjustment = 0;
    # volatility_penalty = min(50*0.4, 15) = 15 -> score = 35
    assert metrics.provisional_trend_score == pytest.approx(35.0)


def test_short_series_single_observation():
    metrics = analyze_interest_series(make_points([42]))

    assert metrics.observation_count == 1
    assert metrics.average_interest == pytest.approx(42.0)
    assert metrics.recent_average == pytest.approx(42.0)
    assert metrics.previous_average is None
    assert metrics.percentage_change is None
    assert metrics.direction == "unknown"
    assert metrics.provisional_trend_score is None
    assert metrics.notes


def test_empty_series():
    metrics = analyze_interest_series([])

    assert metrics.observation_count == 0
    assert metrics.average_interest is None
    assert metrics.recent_average is None
    assert metrics.previous_average is None
    assert metrics.percentage_change is None
    assert metrics.direction == "unknown"
    assert metrics.volatility is None
    assert metrics.provisional_trend_score is None
    assert metrics.notes


def test_zero_valued_series():
    metrics = analyze_interest_series(make_points([0, 0, 0, 0, 0, 0]))

    assert metrics.previous_average == pytest.approx(0.0)
    assert metrics.recent_average == pytest.approx(0.0)
    assert metrics.percentage_change is None
    assert metrics.direction == "stable"
    assert metrics.volatility == pytest.approx(0.0)
    # growth_score falls back to neutral 50 (percentage_change undefined);
    # level_score = 0; base = 0.6*50 + 0.4*0 = 30; no adjustments -> 30
    assert metrics.provisional_trend_score == pytest.approx(30.0)
    assert any("zero" in note for note in metrics.notes)


def test_series_with_missing_values_are_excluded():
    points = make_points([10, 10, 90, 90])
    points.insert(2, TrendPoint(date="2026-01-03", value=None, formatted_value=None))

    metrics = analyze_interest_series(points)

    assert metrics.observation_count == 4
    assert metrics.direction == "growing"


def test_analyze_trend_delegates_to_interest_series():
    points = make_points([10, 10, 90, 90])
    data = TrendData(
        query="bebedouro automatico gatos",
        geo="BR",
        timeframe="today 12-m",
        retrieved_at="2026-10-20T12:00:00Z",
        interest_over_time=points,
        interest_by_region=[],
        related_top_queries=[],
        related_rising_queries=[],
        source="apify:themineworks/google-trends-pro",
    )

    assert analyze_trend(data) == analyze_interest_series(points)
