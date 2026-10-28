import pytest

from src.models import ComponentScores, Product
from src.scoring import calculate_opportunity_score, classify, score_opportunity


def make_scores(**overrides):
    base = dict(
        demand=50,
        trend=50,
        competition=50,
        margin=50,
        supplier=50,
        logistics=50,
        risk=50,
    )
    base.update(overrides)
    return ComponentScores(**base)


def test_perfect_opportunity():
    scores = ComponentScores(
        demand=100,
        trend=100,
        competition=0,
        margin=100,
        supplier=100,
        logistics=100,
        risk=0,
    )
    opportunity_score, _ = calculate_opportunity_score(scores)
    assert opportunity_score == 100
    assert classify(opportunity_score) == "Strong opportunity"


def test_terrible_opportunity():
    scores = ComponentScores(
        demand=0,
        trend=0,
        competition=100,
        margin=0,
        supplier=0,
        logistics=0,
        risk=100,
    )
    opportunity_score, _ = calculate_opportunity_score(scores)
    assert opportunity_score == 0
    assert classify(opportunity_score) == "Reject"


@pytest.mark.parametrize(
    "score, expected",
    [
        (100, "Strong opportunity"),
        (80, "Strong opportunity"),
        (79.99, "Worth deeper investigation"),
        (65, "Worth deeper investigation"),
        (64.99, "Weak or uncertain opportunity"),
        (50, "Weak or uncertain opportunity"),
        (49.99, "Reject"),
        (0, "Reject"),
    ],
)
def test_classification_boundaries(score, expected):
    assert classify(score) == expected


@pytest.mark.parametrize(
    "field",
    ["demand", "trend", "competition", "margin", "supplier", "logistics", "risk"],
)
def test_invalid_score_below_zero_raises(field):
    with pytest.raises(ValueError):
        make_scores(**{field: -1})


@pytest.mark.parametrize(
    "field",
    ["demand", "trend", "competition", "margin", "supplier", "logistics", "risk"],
)
def test_invalid_score_above_hundred_raises(field):
    with pytest.raises(ValueError):
        make_scores(**{field: 101})


def test_competition_and_risk_inversion():
    low_competition_and_risk = make_scores(competition=10, risk=10)
    high_competition_and_risk = make_scores(competition=90, risk=90)

    low_score, _ = calculate_opportunity_score(low_competition_and_risk)
    high_score, _ = calculate_opportunity_score(high_competition_and_risk)

    assert low_score > high_score


def test_weighted_score_calculation():
    scores = ComponentScores(
        demand=80,
        trend=60,
        competition=40,
        margin=70,
        supplier=50,
        logistics=90,
        risk=20,
    )
    expected = (
        80 * 0.30
        + 60 * 0.20
        + (100 - 40) * 0.15
        + 70 * 0.15
        + 50 * 0.10
        + 90 * 0.05
        + (100 - 20) * 0.05
    )
    opportunity_score, _ = calculate_opportunity_score(scores)
    assert opportunity_score == pytest.approx(expected, abs=0.01)


def test_score_opportunity_builds_full_result():
    product = Product(name="Test Product", category="Test Category")
    scores = make_scores()
    result = score_opportunity(product, scores)

    assert result.product is product
    assert result.scores is scores
    assert 0 <= result.opportunity_score <= 100
    assert result.classification in {
        "Strong opportunity",
        "Worth deeper investigation",
        "Weak or uncertain opportunity",
        "Reject",
    }
