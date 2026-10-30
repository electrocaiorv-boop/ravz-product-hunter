from decimal import Decimal

import pytest

from src.competition_analysis import analyze_competition
from src.competition_models import CompetitionSignals
from src.demand_analysis import analyze_demand
from src.demand_models import DemandSignals
from src.integrations.apify_trends import ApifyTrendsResponseError
from src.integrations.mercadolivre import MercadoLivreItem, MercadoLivreResponseError
from src.logistics_analysis import analyze_logistics
from src.logistics_models import LogisticsInputs
from src.main import (
    INTEGRATED_DEMO_SCENARIOS,
    ask,
    ask_with_default,
    collect_product,
    collect_scores,
    format_competition_report,
    format_demand_report,
    format_logistics_report,
    format_margin_report,
    format_opportunity_report,
    format_report,
    format_risk_report,
    format_search_results,
    format_supplier_report,
    format_trend_report,
    parse_menu_choice,
    parse_non_empty_text,
    parse_optional_bool,
    parse_optional_int,
    parse_optional_level_0_100,
    parse_optional_money,
    parse_optional_moq,
    parse_optional_positive_money,
    parse_optional_rate,
    parse_optional_rating,
    parse_required_non_negative_money,
    parse_required_positive_money,
    parse_score,
    recommend,
    run_competition_analysis,
    run_demand_analysis,
    run_integrated_opportunity_analysis,
    run_logistics_analysis,
    run_margin_analysis,
    run_mercado_livre_search,
    run_risk_analysis,
    run_supplier_analysis,
    run_trend_analysis,
)
from src.margin_analysis import analyze_margin
from src.margin_models import MarginInputs
from src.models import ComponentScores, Product
from src.opportunity_integration import compose_opportunity
from src.risk_analysis import analyze_risk
from src.risk_models import RiskInputs
from src.scoring import score_opportunity
from src.supplier_analysis import analyze_supplier
from src.supplier_models import SupplierInputs
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
    assert parse_menu_choice(" 7 ") == 7
    assert parse_menu_choice("8") == 8
    assert parse_menu_choice("9") == 9
    # Phase 11 added option 10 (Integrated Opportunity Analysis).
    assert parse_menu_choice("10") == 10
    assert parse_menu_choice(" 10 ") == 10


@pytest.mark.parametrize("raw", ["0", "11", "abc", "", "1.0", "-1"])
def test_parse_menu_choice_rejects_invalid_options(raw):
    with pytest.raises(ValueError):
        parse_menu_choice(raw)


def test_parse_optional_positive_money_blank_is_none():
    assert parse_optional_positive_money("") is None


def test_parse_optional_positive_money_rejects_zero_and_negative():
    with pytest.raises(ValueError):
        parse_optional_positive_money("0")
    with pytest.raises(ValueError):
        parse_optional_positive_money("-5")


def test_parse_optional_int_blank_is_none():
    assert parse_optional_int("") is None


def test_parse_optional_int_rejects_negative():
    with pytest.raises(ValueError):
        parse_optional_int("-1")


def test_parse_optional_moq_rejects_zero():
    with pytest.raises(ValueError):
        parse_optional_moq("0")


def test_parse_optional_moq_accepts_one():
    assert parse_optional_moq("1") == 1


def test_parse_optional_rating_validates_0_to_5_scale():
    assert parse_optional_rating("4.5") == Decimal("4.5")
    with pytest.raises(ValueError):
        parse_optional_rating("6")


def test_parse_optional_bool_tristate():
    assert parse_optional_bool("y") is True
    assert parse_optional_bool("n") is False
    assert parse_optional_bool("") is None
    assert parse_optional_bool("Y") is True


def test_parse_optional_bool_rejects_other_input():
    with pytest.raises(ValueError):
        parse_optional_bool("maybe")


def test_parse_required_positive_money_valid():
    assert parse_required_positive_money("100") == Decimal("100")
    assert parse_required_positive_money(" 99.90 ") == Decimal("99.90")


@pytest.mark.parametrize("raw", ["", "0", "-5", "abc"])
def test_parse_required_positive_money_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_required_positive_money(raw)


def test_parse_required_non_negative_money_allows_zero():
    assert parse_required_non_negative_money("0") == Decimal("0")


@pytest.mark.parametrize("raw", ["", "-1", "abc"])
def test_parse_required_non_negative_money_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_required_non_negative_money(raw)


def test_parse_optional_money_blank_is_none():
    assert parse_optional_money("") is None
    assert parse_optional_money("   ") is None


def test_parse_optional_money_valid():
    assert parse_optional_money("15") == Decimal("15")


def test_parse_optional_money_rejects_negative():
    with pytest.raises(ValueError):
        parse_optional_money("-1")


def test_parse_optional_rate_blank_is_none():
    assert parse_optional_rate("") is None


def test_parse_optional_rate_valid():
    assert parse_optional_rate("0.12") == Decimal("0.12")


@pytest.mark.parametrize("raw", ["1.5", "-0.1", "abc"])
def test_parse_optional_rate_rejects_invalid(raw):
    with pytest.raises(ValueError):
        parse_optional_rate(raw)


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


def _make_demand_signals(**overrides):
    base = dict(
        query="bebedouro para gatos",
        geo="BR",
        trend_score=70.0,
        trend_direction="growing",
        average_search_interest=60.0,
        recent_search_interest=75.0,
        trend_observation_count=52,
        related_query_count=10,
        rising_query_count=2,
        regional_spread=20,
        marketplace_sample_size=None,
        price_dispersion=None,
        source_coverage=0.5,
        notes=["marketplace signals unavailable (test fixture)"],
    )
    base.update(overrides)
    return DemandSignals(**base)


def test_format_demand_report_contains_key_sections():
    signals = _make_demand_signals()
    result = analyze_demand(signals)
    report = format_demand_report(signals, result)

    assert "bebedouro para gatos" in report
    assert "Demand Score" in report
    assert "PROVISIONAL" in report
    assert "Confidence Score" in report
    assert "Trend:" in report
    assert "Breadth:" in report
    assert "Regional:" in report
    assert "Marketplace:" in report
    assert "Observed:" in report
    assert "Derived:" in report
    assert "Unavailable:" in report
    assert "marketplace listing/price data (total result count not available)" in report
    assert "exact sales volume" in report
    assert "NOT fed into the Phase 1 Opportunity Scoring Engine" in report


def test_run_demand_analysis_combines_both_sources(monkeypatch, capsys):
    trend_data = TrendData(
        query="bebedouro para gatos",
        geo="BR",
        timeframe="today 12-m",
        retrieved_at="2026-10-29T12:00:00Z",
        interest_over_time=[TrendPoint(date="2026-01-01", value=60, formatted_value="60")],
        interest_by_region=[TrendRegion(region_code="BR-SP", region_name="Sao Paulo", value=90)],
        related_top_queries=[RelatedQuery(query="q1", value=10, formatted_value="10", link=None)],
        related_rising_queries=[],
        source="apify:themineworks/google-trends-pro",
    )
    marketplace_item = MercadoLivreItem(
        item_id="MLB1",
        title="Bebedouro",
        price=50.0,
        currency_id="BRL",
        seller_id=1,
        category_id="MLB1",
        condition="new",
        permalink=None,
        free_shipping=None,
        available_quantity=None,
    )

    monkeypatch.setattr("src.main.fetch_trend_data", lambda query, geo="BR": trend_data)
    monkeypatch.setattr("src.main.search_products", lambda query: [marketplace_item])

    fake_input = make_input(["bebedouro para gatos", ""])
    run_demand_analysis(fake_input)

    captured = capsys.readouterr()
    assert "DEMAND ANALYSIS REPORT" in captured.out
    assert "Unavailable:" in captured.out


def test_run_demand_analysis_handles_both_sources_failing_without_crashing(monkeypatch, capsys):
    def fake_fetch_trend_data(query, geo="BR"):
        raise ApifyTrendsResponseError(status_code=403, message="Forbidden")

    def fake_search_products(query):
        raise MercadoLivreResponseError(status_code=403, message="Forbidden")

    monkeypatch.setattr("src.main.fetch_trend_data", fake_fetch_trend_data)
    monkeypatch.setattr("src.main.search_products", fake_search_products)

    fake_input = make_input(["bebedouro para gatos", ""])
    run_demand_analysis(fake_input)

    captured = capsys.readouterr()
    assert "trend source unavailable" in captured.out
    assert "marketplace source unavailable" in captured.out
    assert "DEMAND ANALYSIS REPORT" in captured.out


def _make_competition_signals(**overrides):
    base = dict(
        query="bebedouro para gatos",
        marketplace_sample_size=5,
        total_result_count=None,
        seller_count=3,
        unique_seller_ratio=0.6,
        price_min=10.0,
        price_max=30.0,
        price_mean=20.0,
        price_median=20.0,
        price_dispersion=0.2,
        free_shipping_ratio=0.4,
        condition_distribution={"new": 4, "used": 1},
        duplicate_title_ratio=0.2,
        source_coverage=1.0,
        notes=[],
    )
    base.update(overrides)
    return CompetitionSignals(**base)


def test_format_competition_report_contains_key_sections():
    signals = _make_competition_signals()
    result = analyze_competition(signals)
    report = format_competition_report(signals, result)

    assert "bebedouro para gatos" in report
    assert "Competition Score" in report
    assert "PROVISIONAL" in report
    assert "Confidence Score" in report
    assert "Seller concentration:" in report
    assert "Listing saturation:" in report
    assert "Price crowding:" in report
    assert "Duplicate listings:" in report
    assert "Shipping:" in report
    assert "Observed:" in report
    assert "Derived:" in report
    assert "Unavailable:" in report
    assert "one street block" in report
    assert "NOT fed into the Phase 1 Opportunity Scoring Engine" in report


def test_run_competition_analysis_succeeds_with_marketplace_data(monkeypatch, capsys):
    item = MercadoLivreItem(
        item_id="MLB1",
        title="Bebedouro",
        price=50.0,
        currency_id="BRL",
        seller_id=1,
        category_id="MLB1",
        condition="new",
        permalink=None,
        free_shipping=True,
        available_quantity=None,
    )
    monkeypatch.setattr("src.main.search_products", lambda query, limit=10: [item])

    fake_input = make_input(["bebedouro para gatos"])
    run_competition_analysis(fake_input)

    captured = capsys.readouterr()
    assert "COMPETITION ANALYSIS REPORT" in captured.out


def test_run_competition_analysis_handles_source_failure_without_crashing(monkeypatch, capsys):
    def fake_search_products(query, limit=10):
        raise MercadoLivreResponseError(status_code=403, message="Forbidden")

    monkeypatch.setattr("src.main.search_products", fake_search_products)

    fake_input = make_input(["bebedouro para gatos"])
    run_competition_analysis(fake_input)

    captured = capsys.readouterr()
    assert "marketplace source unavailable" in captured.out
    assert "COMPETITION ANALYSIS REPORT" in captured.out
    assert "not available" in captured.out


def _make_margin_inputs(**overrides):
    base = dict(
        product_name="Bebedouro",
        sale_price=Decimal("100"),
        product_cost=Decimal("50"),
        marketplace_fee_amount=Decimal("15"),
        seller_shipping_cost=Decimal("10"),
    )
    base.update(overrides)
    return MarginInputs(**base)


def test_format_margin_report_contains_key_sections():
    inputs = _make_margin_inputs()
    result = analyze_margin(inputs)
    report = format_margin_report(inputs, result)

    assert "Bebedouro" in report
    assert "MARGIN ANALYSIS REPORT" in report
    assert "PROVISIONAL" in report
    assert "Gross profit:" in report
    assert "Gross margin:" in report
    assert "Markup:" in report
    assert "Contribution profit (known costs only):" in report
    assert "Contribution margin (known costs only):" in report
    assert "Break-even price" in report
    assert "Margin Score:" in report
    assert "Cost Completeness Score:" in report
    assert "Unavailable / unknown costs:" in report
    assert "NOT net profit" in report
    assert "NOT fed into the Phase 1 Opportunity Scoring Engine" in report


def test_run_margin_analysis_happy_path(capsys):
    fake_input = make_input(
        ["Bebedouro", "100", "50", "15", "", "", "10", "", "", "", "", "", "", ""]
    )
    run_margin_analysis(fake_input)

    captured = capsys.readouterr()
    assert "MARGIN ANALYSIS REPORT" in captured.out
    assert "Gross profit: 50.00" in captured.out
    assert "Contribution profit (known costs only): 25.00" in captured.out


def test_run_margin_analysis_reports_conflicting_inputs_without_crashing(capsys):
    fake_input = make_input(
        ["Bebedouro", "100", "50", "10", "0.1", "", "", "", "", "", "", "", "", ""]
    )
    run_margin_analysis(fake_input)

    captured = capsys.readouterr()
    assert "Invalid input" in captured.out
    assert "MARGIN ANALYSIS REPORT" not in captured.out


def _make_supplier_inputs(**overrides):
    base = dict(
        product_name="Bebedouro",
        supplier_name="Fornecedor A",
        moq_units=1,
        dispatch_time_days=1,
        delivery_time_days=2,
        dropshipping_supported=True,
    )
    base.update(overrides)
    return SupplierInputs(**base)


def test_format_supplier_report_contains_key_sections():
    inputs = _make_supplier_inputs()
    result = analyze_supplier(inputs)
    report = format_supplier_report(inputs, result)

    assert "Bebedouro" in report
    assert "Fornecedor A" in report
    assert "SUPPLIER ANALYSIS REPORT" in report
    assert "PROVISIONAL" in report
    assert "Supplier Evidence Completeness" in report
    assert "Operational Status:" in report
    assert "Order flexibility:" in report
    assert "Operational speed:" in report
    assert "Stock viability:" in report
    assert "Fulfillment capability:" in report
    assert "Trust/compliance:" in report
    assert "Blockers:" in report
    assert "NOT proof of wholesale/dropshipping capability" in report
    assert "NOT fed into the Phase 1 Opportunity Scoring Engine" in report


def test_run_supplier_analysis_happy_path(capsys):
    fake_input = make_input(
        [
            "Bebedouro", "Fornecedor A",
            "", "1", "", "", "",
            "", "",
            "", "", "",
            "",
            "", "",
            "", "", "", "",
            "", "", "",
        ]
    )
    run_supplier_analysis(fake_input)

    captured = capsys.readouterr()
    assert "SUPPLIER ANALYSIS REPORT" in captured.out
    assert "Fornecedor A" in captured.out


def test_run_supplier_analysis_reports_conflicting_lead_time_without_crashing(capsys):
    fake_input = make_input(
        [
            "Bebedouro", "Fornecedor A",
            "", "", "", "", "",
            "", "",
            "5", "5", "10",
            "",
            "", "",
            "", "", "", "",
            "", "", "",
        ]
    )
    run_supplier_analysis(fake_input)

    captured = capsys.readouterr()
    assert "Invalid input" in captured.out
    assert "SUPPLIER ANALYSIS REPORT" not in captured.out


def _make_logistics_inputs(**overrides):
    base = dict(product_name="Phone case", weight_kg=Decimal("0.1"))
    base.update(overrides)
    return LogisticsInputs(**base)


def test_format_logistics_report_contains_key_sections():
    inputs = _make_logistics_inputs()
    result = analyze_logistics(inputs)
    report = format_logistics_report(inputs, result)

    assert "Phone case" in report
    assert "LOGISTICS ANALYSIS REPORT" in report
    assert "PROVISIONAL" in report
    assert "0 = operationally difficult, 100 = easy/favorable" in report
    assert "Logistics Evidence Completeness" in report
    assert "Operational Status:" in report
    assert "Physical ease:" in report
    assert "Handling ease:" in report
    assert "Delivery convenience:" in report
    assert "Fulfillment support:" in report
    assert "Shipping support:" in report
    assert "Reference billable weight (kg, NOT a real carrier charge):" in report
    assert "Blockers:" in report
    assert "CUSTOMER-facing delivery leg, not Phase 8's" in report
    assert "NOT fed into the Phase 1 Opportunity Scoring Engine" in report


def test_run_logistics_analysis_happy_path(capsys):
    fake_input = make_input(
        [
            "Phone case", "0.1", "15", "8", "1", "",
            "n", "n", "n", "n", "n", "y", "n",
            "", "",
            "y", "", "",
            "", "2", "y", "y",
            "", "",
        ]
    )
    run_logistics_analysis(fake_input)

    captured = capsys.readouterr()
    assert "LOGISTICS ANALYSIS REPORT" in captured.out
    assert "Phone case" in captured.out


def test_run_logistics_analysis_reprompts_on_invalid_input_then_succeeds(capsys):
    fake_input = make_input(
        [
            "Mirror", "-1", "0.5", "", "", "", "",
            "", "", "", "", "", "", "",
            "", "",
            "", "", "",
            "", "", "", "",
            "", "",
        ]
    )
    run_logistics_analysis(fake_input)

    captured = capsys.readouterr()
    assert "Invalid input" in captured.out
    assert "LOGISTICS ANALYSIS REPORT" in captured.out
    assert "Mirror" in captured.out


def _make_risk_inputs(**overrides):
    base = dict(product_name="Widget", supplier_count=5)
    base.update(overrides)
    return RiskInputs(**base)


def test_format_risk_report_contains_key_sections():
    inputs = _make_risk_inputs()
    result = analyze_risk(inputs)
    report = format_risk_report(inputs, result)

    assert "Widget" in report
    assert "RISK ANALYSIS REPORT" in report
    assert "PROVISIONAL" in report
    assert "0 = low apparent risk, 100 = high apparent risk" in report
    assert "Risk Evidence Completeness" in report
    assert "Risk Status:" in report
    assert "Dependency risk:" in report
    assert "Supply continuity risk:" in report
    assert "Volatility risk:" in report
    assert "Operational history risk:" in report
    assert "Compliance/IP uncertainty risk:" in report
    assert "Blockers:" in report
    assert "never legal/infringement conclusions" in report
    assert "NOT fed into the Phase 1 Opportunity Scoring Engine" in report


def test_run_risk_analysis_happy_path(capsys):
    fake_input = make_input(
        [
            "Diversified product", "5", "0.30", "0.40", "",
            "0.05", "0.02", "0.03", "",
            "",
            "n", "n", "n", "y", "y",
        ]
    )
    run_risk_analysis(fake_input)

    captured = capsys.readouterr()
    assert "RISK ANALYSIS REPORT" in captured.out
    assert "Diversified product" in captured.out


def test_run_risk_analysis_reprompts_on_invalid_input_then_succeeds(capsys):
    fake_input = make_input(
        [
            "Concentrated product", "-1", "5",
            "", "", "",
            "", "", "", "",
            "",
            "", "", "", "", "",
        ]
    )
    run_risk_analysis(fake_input)

    captured = capsys.readouterr()
    assert "Invalid input" in captured.out
    assert "RISK ANALYSIS REPORT" in captured.out
    assert "Concentrated product" in captured.out


# -- Phase 11: integrated opportunity analysis (composition layer) --------


def scenario(index):
    """Build one of the labelled illustrative demo scenarios.

    Indices follow INTEGRATED_DEMO_SCENARIOS: 0 = complete evidence
    (READY), 1 = operationally unvalidated, 2 = commercial evidence
    incomplete (Margin withheld), 3 = Supplier blocked.
    """
    return INTEGRATED_DEMO_SCENARIOS[index]()


def test_integrated_demo_exposes_one_scenario_per_readiness_state():
    """Four scenarios, one per readiness state -- no more than needed."""
    assert len(INTEGRATED_DEMO_SCENARIOS) == 4

    readinesses = [
        compose_opportunity("Demo", **scenario(index)[2]).readiness
        for index in range(4)
    ]
    assert readinesses == [
        "READY",
        "OPERATIONALLY_UNVALIDATED",
        "INCOMPLETE_EVIDENCE",
        "BLOCKED",
    ]


def test_run_integrated_opportunity_analysis_renders_all_scenarios(capsys):
    run_integrated_opportunity_analysis(make_input([]))

    captured = capsys.readouterr()
    assert captured.out.count("INTEGRATED OPPORTUNITY ANALYSIS") == 4
    assert "Scenario A -- complete evidence" in captured.out
    assert "Scenario B -- commercially attractive, operationally UNVALIDATED" in captured.out
    assert "Scenario C -- COMMERCIAL evidence incomplete" in captured.out
    assert "Scenario D -- Supplier BLOCKED" in captured.out


def test_integrated_demo_takes_no_user_input(capsys):
    """The demo must never consume input: make_input([]) would raise."""
    run_integrated_opportunity_analysis(make_input([]))
    assert "INTEGRATED OPPORTUNITY ANALYSIS" in capsys.readouterr().out


def test_integrated_demo_does_not_claim_automated_end_to_end_analysis(capsys):
    """No fake automation: Phase 11 is composition, not orchestration."""
    run_integrated_opportunity_analysis(make_input([]))

    out = capsys.readouterr().out.lower()
    assert "does not collect or fetch anything itself" in out
    assert "illustrative" in out
    assert "not fetched data" in out
    assert "future" in out and "orchestrator" in out
    for forbidden in (
        "automatically analyzing opportunity",
        "fetching all data",
        "fully automated",
    ):
        assert forbidden not in out


def test_integrated_demo_labels_its_inputs_as_not_real_product_data(capsys):
    run_integrated_opportunity_analysis(make_input([]))
    assert "(ILLUSTRATIVE)" in capsys.readouterr().out


def test_format_opportunity_report_shows_withheld_classification():
    _title, _explanation, domain_results = scenario(2)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result)

    assert "Final Classification: WITHHELD" in report
    assert "Publishable recommendation: no" in report
    assert "Missing COMMERCIAL requirements: margin" in report
    assert "UNAVAILABLE (required for commercial validation)" in report
    assert "Commercial validation: INCOMPLETE" in report


def test_format_opportunity_report_separates_the_two_validation_layers():
    """Spec 27: users must be able to answer both questions separately."""
    _title, _explanation, domain_results = scenario(1)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result)

    assert "Commercial validation: complete" in report
    assert "Operational validation: INCOMPLETE" in report
    assert "is the market/economic case validated?" in report
    assert "is execution validated?" in report
    assert "Readiness: OPERATIONALLY_UNVALIDATED" in report
    assert "Final Classification: WITHHELD" in report
    assert "Missing OPERATIONAL requirements: supplier, logistics" in report


def test_format_opportunity_report_labels_a_non_final_band_as_non_final():
    """A band outside READY must never read as an approval."""
    _title, _explanation, domain_results = scenario(1)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result)

    assert "Analytical band (NON-FINAL" in report
    assert "not a recommendation" in report
    assert "analytical, NOT final" in report


def test_format_opportunity_report_marks_a_ready_score_as_final():
    _title, _explanation, domain_results = scenario(0)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result)

    assert "analytical, NOT final" not in report
    assert "Commercial validation: complete" in report
    assert "Operational validation: complete" in report
    assert "Readiness: READY" in report
    assert "WITHHELD" not in report


def test_format_opportunity_report_shows_blockers_prominently():
    _title, _explanation, domain_results = scenario(3)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result)

    assert "Readiness: BLOCKED" in report
    assert "BLOCKERS (never averaged into the score):" in report
    assert "below moq_units" in report
    # The arithmetic is still shown, not suppressed.
    assert "Opportunity Score:" in report


def test_format_opportunity_report_marks_trend_as_not_counted():
    _title, _explanation, domain_results = scenario(0)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result)

    assert "NOT COUNTED (correlated evidence" in report
    assert "search-interest family" in report


def test_format_opportunity_report_never_calls_coverage_confidence():
    _title, _explanation, domain_results = scenario(0)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result)

    assert "coverage is NOT confidence" in report
    assert "each metric under its own name" in report


def test_format_opportunity_report_states_the_score_is_provisional():
    _title, _explanation, domain_results = scenario(0)
    result = compose_opportunity("Demo", **domain_results)
    report = format_opportunity_report(result).lower()

    assert "provisional business heuristic" in report
    assert "not a probability" in report


def test_integrated_demo_scenarios_are_deterministic():
    first = compose_opportunity("Demo", **scenario(0)[2])
    second = compose_opportunity("Demo", **scenario(0)[2])
    assert first.opportunity_score == second.opportunity_score
    assert first.readiness == second.readiness
