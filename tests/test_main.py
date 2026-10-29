import pytest

from src.integrations.mercadolivre import MercadoLivreItem, MercadoLivreResponseError
from src.main import (
    ask,
    collect_product,
    collect_scores,
    format_report,
    format_search_results,
    parse_menu_choice,
    parse_non_empty_text,
    parse_score,
    recommend,
    run_mercado_livre_search,
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


def test_parse_menu_choice_accepts_valid_options():
    assert parse_menu_choice("1") == 1
    assert parse_menu_choice("2") == 2
    assert parse_menu_choice(" 2 ") == 2


@pytest.mark.parametrize("raw", ["0", "3", "abc", ""])
def test_parse_menu_choice_rejects_invalid_options(raw):
    with pytest.raises(ValueError):
        parse_menu_choice(raw)


def test_format_search_results_handles_empty_list():
    assert format_search_results([]) == "No results found."


def test_format_search_results_shows_only_available_fields():
    item = MercadoLivreItem(
        item_id="MLB123",
        title="Bebedouro Automatico para Gatos",
        price=89.9,
        currency_id="BRL",
        seller_id=42,
        category_id="MLB1234",
        condition="new",
        permalink="https://produto.mercadolivre.com.br/MLB123",
        free_shipping=True,
        available_quantity=15,
    )
    report = format_search_results([item])

    assert "Bebedouro Automatico para Gatos" in report
    assert "MLB123" in report
    assert "89.9" in report
    assert "BRL" in report
    assert "MLB1234" in report
    assert "available quantity (reference, not exact stock): 15" in report


def test_format_search_results_omits_missing_fields():
    item = MercadoLivreItem(
        item_id="MLB999",
        title="Produto sem detalhes",
        price=None,
        currency_id=None,
        seller_id=None,
        category_id=None,
        condition=None,
        permalink=None,
        free_shipping=None,
        available_quantity=None,
    )
    report = format_search_results([item])

    assert "price" not in report
    assert "category" not in report
    assert "condition" not in report


def test_run_mercado_livre_search_reports_errors_without_crashing(monkeypatch, capsys):
    def fake_search_products(query, limit=10):
        raise MercadoLivreResponseError(status_code=403, message="Forbidden")

    monkeypatch.setattr("src.main.search_products", fake_search_products)
    fake_input = make_input(["bebedouro automatico gatos"])

    run_mercado_livre_search(fake_input)

    captured = capsys.readouterr()
    assert "Mercado Livre search failed" in captured.out
