import pytest

from src.integrations.apify_trends import ApifyTrendsResponseError
from src.integrations.mercadolivre import MercadoLivreItem, MercadoLivreResponseError
from src.main import (
    ask,
    ask_with_default,
    collect_product,
    collect_scores,
    format_report,
    format_search_results,
    format_trend_report,
    parse_menu_choice,
    parse_non_empty_text,
    parse_score,
    recommend,
    run_mercado_livre_search,
    run_trend_analysis,
)
from src.models import ComponentScores, Product
from src.scoring import score_opportunity
from src.trend_analysis import analyze_trend
from src.trend_models import RelatedQuery, TrendData, TrendPoint, TrendRegion


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
    assert parse_menu_choice(" 3 ") == 3


@pytest.mark.parametrize("raw", ["0", "4", "abc", ""])
def test_parse_menu_choice_rejects_invalid_options(raw):
    with pytest.raises(ValueError):
        parse_menu_choice(raw)


def test_ask_with_default_returns_default_on_empty_input():
    fake_input = make_input([""])
    assert ask_with_default("Geo: ", "BR", fake_input) == "BR"


def test_ask_with_default_returns_provided_value():
    fake_input = make_input(["US"])
    assert ask_with_default("Geo: ", "BR", fake_input) == "US"


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


def _make_trend_data():
    points = [
        TrendPoint(date="2026-01-01", value=10, formatted_value="10"),
        TrendPoint(date="2026-02-01", value=90, formatted_value="90"),
    ]
    regions = [
        TrendRegion(region_code="BR-SP", region_name="Sao Paulo", value=100),
        TrendRegion(region_code="BR-RJ", region_name="Rio de Janeiro", value=80),
    ]
    top = [RelatedQuery(query="bebedouro para gatos", value=100, formatted_value="100", link=None)]
    rising = [RelatedQuery(query="bebedouro eletrico", value=250, formatted_value="+250%", link=None)]
    return TrendData(
        query="bebedouro automatico gatos",
        geo="BR",
        timeframe="today 12-m",
        retrieved_at="2026-10-20T12:00:00Z",
        interest_over_time=points,
        interest_by_region=regions,
        related_top_queries=top,
        related_rising_queries=rising,
        source="apify:themineworks/google-trends-pro",
    )


def test_format_trend_report_contains_key_sections():
    data = _make_trend_data()
    metrics = analyze_trend(data)
    report = format_trend_report(data, metrics)

    assert "bebedouro automatico gatos" in report
    assert "apify:themineworks/google-trends-pro" in report
    assert "Geo: BR" in report
    assert "Number of observations: 2" in report
    assert "Direction: growing" in report
    assert "PROVISIONAL" in report
    assert "Top related searches" in report
    assert "bebedouro para gatos" in report
    assert "Rising related searches" in report
    assert "bebedouro eletrico" in report
    assert "Sao Paulo" in report
    assert (
        "Google Trends values represent relative search interest (0-100), "
        "not absolute search volume." in report
    )


def test_run_trend_analysis_reports_errors_without_crashing(monkeypatch, capsys):
    def fake_fetch_trend_data(query, geo="BR", timeframe="today 12-m"):
        raise ApifyTrendsResponseError(status_code=401, message="Unauthorized")

    monkeypatch.setattr("src.main.fetch_trend_data", fake_fetch_trend_data)
    fake_input = make_input(["bebedouro automatico gatos", "", ""])

    run_trend_analysis(fake_input)

    captured = capsys.readouterr()
    assert "Trend analysis failed" in captured.out
