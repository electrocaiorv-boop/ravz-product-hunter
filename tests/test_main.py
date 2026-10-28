import pytest

from src.main import (
    ask,
    collect_product,
    collect_scores,
    format_report,
    parse_non_empty_text,
    parse_score,
    recommend,
)
from src.models import ComponentScores, Product
from src.scoring import score_opportunity


def make_input(values):
    """Build a fake input_func that returns `values` in order, one per call."""
    iterator = iter(values)

    def fake_input(_prompt):
        return next(iterator)

    return fake_input


def test_parse_score_valid():
    assert parse_score("42") == 42.0
    assert parse_score("0") == 0.0
    assert parse_score("100") == 100.0


def test_parse_score_rejects_non_numeric():
    with pytest.raises(ValueError):
        parse_score("abc")


@pytest.mark.parametrize("raw", ["-1", "101", "-0.01", "100.01"])
def test_parse_score_rejects_out_of_range(raw):
    with pytest.raises(ValueError):
        parse_score(raw)


def test_parse_non_empty_text_valid():
    assert parse_non_empty_text("  Wireless Mouse  ") == "Wireless Mouse"


def test_parse_non_empty_text_rejects_empty():
    with pytest.raises(ValueError):
        parse_non_empty_text("   ")


def test_ask_retries_on_invalid_input():
    fake_input = make_input(["not a number", "-5", "42"])
    assert ask("Score: ", parse_score, fake_input) == 42.0


def test_ask_returns_first_valid_value():
    fake_input = make_input(["7"])
    assert ask("Score: ", parse_score, fake_input) == 7.0


def test_collect_product_builds_product_from_input():
    fake_input = make_input(["  ", "Wireless Mouse", "Electronics"])
    product = collect_product(fake_input)
    assert product == Product(name="Wireless Mouse", category="Electronics")


def test_collect_scores_builds_component_scores_from_input():
    fake_input = make_input(["80", "60", "40", "70", "50", "90", "20"])
    scores = collect_scores(fake_input)
    assert scores == ComponentScores(
        demand=80,
        trend=60,
        competition=40,
        margin=70,
        supplier=50,
        logistics=90,
        risk=20,
    )


def test_format_report_contains_key_sections():
    product = Product(name="Wireless Mouse", category="Electronics")
    scores = ComponentScores(
        demand=80,
        trend=60,
        competition=40,
        margin=70,
        supplier=50,
        logistics=90,
        risk=20,
    )
    result = score_opportunity(product, scores)
    report = format_report(result)

    assert "Wireless Mouse" in report
    assert "Electronics" in report
    assert "Opportunity Score" in report
    assert result.classification in report
    assert "Recommendation" in report


@pytest.mark.parametrize(
    "classification",
    [
        "Strong opportunity",
        "Worth deeper investigation",
        "Weak or uncertain opportunity",
        "Reject",
    ],
)
def test_recommend_has_a_message_for_every_classification(classification):
    assert recommend(classification) != "No recommendation available."


def test_recommend_handles_unknown_classification():
    assert recommend("Something else") == "No recommendation available."
