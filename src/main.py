"""RAVZ Product Hunter CLI.

Phase 2: Manual Analyzer. Phase 3: Mercado Livre search. Phase 4: Trend
analysis. Phase 5: Demand analysis. Phase 6: Competition analysis.
Phase 7: Margin analysis. Phase 8: Supplier analysis. Phase 9:
Logistics analysis.

This module is the presentation layer: it collects input from the user,
delegates all scoring logic to src.models / src.scoring, all Mercado
Livre HTTP/JSON handling to src.integrations.mercadolivre, all Apify/trend
HTTP/JSON handling to src.integrations.apify_trends, all trend-metric math
to src.trend_analysis, all demand math to src.demand_models /
src.demand_analysis, all competition math to src.competition_models /
src.competition_analysis, all margin/unit-economics math to
src.margin_models / src.margin_analysis, all supplier-viability math to
src.supplier_models / src.supplier_analysis, and all logistics math to
src.logistics_models / src.logistics_analysis, then renders the result.
It contains no scoring math and no HTTP logic of its own.

Input-collecting functions accept an injectable `input_func` so the
retry/validation logic can be unit tested without calling the real
built-in input().
"""

from decimal import Decimal, InvalidOperation

from src.competition_analysis import analyze_competition
from src.competition_models import build_competition_signals
from src.demand_analysis import analyze_demand
from src.demand_models import build_demand_signals
from src.integrations.apify_trends import (
    DEFAULT_GEO,
    DEFAULT_TIMEFRAME,
    ApifyTrendsError,
    fetch_trend_data,
)
from src.integrations.mercadolivre import MercadoLivreError, search_products
from src.logistics_analysis import analyze_logistics
from src.logistics_models import LogisticsInputs
from src.margin_analysis import analyze_margin
from src.margin_models import MarginInputs
from src.models import ComponentScores, Product
from src.scoring import score_opportunity
from src.supplier_analysis import analyze_supplier
from src.supplier_models import SupplierInputs
from src.trend_analysis import analyze_trend

SCORE_FIELDS = (
    ("demand", "Demand score"),
    ("trend", "Trend score"),
    ("competition", "Competition score"),
    ("margin", "Margin score"),
    ("supplier", "Supplier score"),
    ("logistics", "Logistics score"),
    ("risk", "Risk score"),
)

RECOMMENDATIONS = {
    "Strong opportunity": "Pursue this product -- the data supports it.",
    "Worth deeper investigation": "Investigate further before committing.",
    "Weak or uncertain opportunity": "Proceed with caution, or look for a better fit.",
    "Reject": "Do not pursue this product based on current data.",
}


def parse_score(raw: str) -> float:
    """Parse and validate a raw string as a 0-100 score.

    Raises ValueError with a user-facing message if invalid.
    """
    try:
        value = float(raw)
    except ValueError:
        raise ValueError(f"'{raw}' is not a number")
    if not 0 <= value <= 100:
        raise ValueError(f"{value} is not between 0 and 100")
    return value


def parse_non_empty_text(raw: str) -> str:
    """Validate that raw text is not empty after stripping whitespace."""
    text = raw.strip()
    if not text:
        raise ValueError("value cannot be empty")
    return text


def parse_menu_choice(raw: str) -> int:
    """Validate that raw text is one of the main menu options (1-8)."""
    text = raw.strip()
    if text not in {"1", "2", "3", "4", "5", "6", "7", "8"}:
        raise ValueError("choose 1, 2, 3, 4, 5, 6, 7 or 8")
    return int(text)


def parse_required_positive_money(raw: str) -> Decimal:
    """Parse a mandatory monetary value that must be greater than 0 (e.g. sale price)."""
    text = raw.strip()
    if not text:
        raise ValueError("value cannot be empty")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{raw}' is not a valid number")
    if value <= 0:
        raise ValueError(f"{value} must be greater than 0")
    return value


def parse_required_non_negative_money(raw: str) -> Decimal:
    """Parse a mandatory monetary value that may be zero but not negative (e.g. product cost)."""
    text = raw.strip()
    if not text:
        raise ValueError("value cannot be empty")
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{raw}' is not a valid number")
    if value < 0:
        raise ValueError(f"{value} must not be negative")
    return value


def parse_optional_money(raw: str) -> Decimal | None:
    """Parse an optional monetary value. Blank means unknown (None), never zero."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{raw}' is not a valid number")
    if value < 0:
        raise ValueError(f"{value} must not be negative")
    return value


def parse_optional_rate(raw: str) -> Decimal | None:
    """Parse an optional rate as a fraction 0-1 (e.g. 0.12 for 12%). Blank means unknown."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{raw}' is not a valid number")
    if not (0 <= value <= 1):
        raise ValueError(f"{value} must be between 0 and 1 (e.g. 0.12 for 12%)")
    return value


def parse_optional_positive_money(raw: str) -> Decimal | None:
    """Parse an optional monetary value that must be > 0 if given (e.g. minimum order value)."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{raw}' is not a valid number")
    if value <= 0:
        raise ValueError(f"{value} must be greater than 0 (0 is not a meaningful minimum)")
    return value


def parse_optional_int(raw: str) -> int | None:
    """Parse an optional non-negative whole number. Blank means unknown."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"'{raw}' is not a whole number")
    if value < 0:
        raise ValueError(f"{value} must not be negative")
    return value


def parse_optional_moq(raw: str) -> int | None:
    """Parse an optional MOQ (Minimum Order Quantity). Must be >= 1 if given."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = int(text)
    except ValueError:
        raise ValueError(f"'{raw}' is not a whole number")
    if value < 1:
        raise ValueError(f"{value} must be at least 1 (0 is not a meaningful minimum)")
    return value


def parse_optional_rating(raw: str) -> Decimal | None:
    """Parse an optional supplier rating on a 0-5 scale. Blank means unknown."""
    text = raw.strip()
    if not text:
        return None
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ValueError(f"'{raw}' is not a valid number")
    if not (0 <= value <= 5):
        raise ValueError(f"{value} must be on a 0-5 scale")
    return value


def parse_optional_bool(raw: str) -> bool | None:
    """Parse a tri-state boolean: 'y' -> True, 'n' -> False, blank -> None (unknown)."""
    text = raw.strip().lower()
    if not text:
        return None
    if text == "y":
        return True
    if text == "n":
        return False
    raise ValueError("enter 'y', 'n', or leave blank if unknown")


def ask_with_default(prompt_text: str, default: str, input_func=input) -> str:
    """Prompt once; return `default` if the user enters nothing."""
    raw = input_func(prompt_text).strip()
    return raw if raw else default


def ask(prompt_text: str, parser, input_func=input):
    """Prompt with `prompt_text` until `parser(raw)` succeeds, then return it."""
    while True:
        raw = input_func(prompt_text)
        try:
            return parser(raw)
        except ValueError as exc:
            print(f"Invalid input: {exc}. Please try again.")


def collect_product(input_func=input) -> Product:
    """Ask the user for product name and category."""
    name = ask("Product name: ", parse_non_empty_text, input_func)
    category = ask("Category: ", parse_non_empty_text, input_func)
    return Product(name=name, category=category)


def collect_scores(input_func=input) -> ComponentScores:
    """Ask the user for every component score, one at a time."""
    values = {}
    for field, label in SCORE_FIELDS:
        values[field] = ask(f"{label} (0-100): ", parse_score, input_func)
    return ComponentScores(**values)


def recommend(classification: str) -> str:
    """Map a classification label to a short, clear recommendation."""
    return RECOMMENDATIONS.get(classification, "No recommendation available.")


def format_report(result) -> str:
    """Render an OpportunityResult as a human-readable terminal report."""
    scores = result.scores
    lines = [
        "=" * 50,
        "OPPORTUNITY REPORT",
        "=" * 50,
        f"Product: {result.product.name}",
        f"Category: {result.product.category}",
        "",
        "Component scores:",
        f"  Demand:      {scores.demand}",
        f"  Trend:       {scores.trend}",
        f"  Competition: {scores.competition}",
        f"  Margin:      {scores.margin}",
        f"  Supplier:    {scores.supplier}",
        f"  Logistics:   {scores.logistics}",
        f"  Risk:        {scores.risk}",
        "",
        "Weighted breakdown:",
    ]
    for dimension, contribution in result.breakdown.items():
        lines.append(f"  {dimension.capitalize():<12} contributes {contribution}")
    lines += [
        "",
        f"Opportunity Score: {result.opportunity_score}",
        f"Classification: {result.classification}",
        "",
        f"Recommendation: {recommend(result.classification)}",
        "=" * 50,
    ]
    return "\n".join(lines)


def format_search_results(items) -> str:
    """Render a list of MercadoLivreItem as a concise, human-readable list.

    Only fields the item actually has are shown -- missing fields are
    omitted rather than printed as a fabricated placeholder.
    """
    if not items:
        return "No results found."

    blocks = []
    for item in items:
        lines = [f"- {item.title}", f"    item id: {item.item_id}"]
        if item.price is not None:
            price_line = f"    price: {item.price}"
            if item.currency_id:
                price_line += f" {item.currency_id}"
            lines.append(price_line)
        if item.category_id:
            lines.append(f"    category: {item.category_id}")
        if item.condition:
            lines.append(f"    condition: {item.condition}")
        if item.available_quantity is not None:
            lines.append(
                f"    available quantity (reference, not exact stock): "
                f"{item.available_quantity}"
            )
        if item.free_shipping is not None:
            lines.append(f"    free shipping: {item.free_shipping}")
        if item.permalink:
            lines.append(f"    link: {item.permalink}")
        blocks.append("\n".join(lines))
    return "\n".join(blocks)


TREND_DATA_WARNING = (
    "Google Trends values represent relative search interest (0-100), "
    "not absolute search volume."
)


def _format_optional(value, suffix: str = "") -> str:
    if value is None:
        return "not available"
    if isinstance(value, float):
        return f"{value:.2f}{suffix}"
    return f"{value}{suffix}"


def format_trend_report(data, metrics) -> str:
    """Render a TrendData + TrendMetrics pair as a human-readable report.

    The Provisional Trend Score is always labeled as provisional -- it
    has not been validated against real sales outcomes.
    """
    lines = [
        "=" * 50,
        "TREND ANALYSIS REPORT (PROVISIONAL)",
        "=" * 50,
        f"Query: {data.query}",
        f"Source: {data.source}",
        f"Geo: {data.geo}",
        f"Timeframe: {data.timeframe}",
        f"Retrieved at: {data.retrieved_at}",
        "",
        f"Number of observations: {metrics.observation_count}",
        f"Average interest: {_format_optional(metrics.average_interest)}",
        f"Recent average: {_format_optional(metrics.recent_average)}",
        f"Previous average: {_format_optional(metrics.previous_average)}",
        f"Percentage change: {_format_optional(metrics.percentage_change, '%')}",
        f"Direction: {metrics.direction}",
        f"Volatility: {_format_optional(metrics.volatility)}",
        "Provisional Trend Score: "
        f"{_format_optional(metrics.provisional_trend_score)} "
        "(PROVISIONAL -- not validated against real sales outcomes)",
    ]

    if metrics.notes:
        lines.append("")
        lines.append("Notes:")
        for note in metrics.notes:
            lines.append(f"  - {note}")

    lines.append("")
    lines.append("Top related searches:")
    if data.related_top_queries:
        for related in data.related_top_queries:
            lines.append(f"  - {related.query} ({related.formatted_value or related.value})")
    else:
        lines.append("  (none returned)")

    lines.append("")
    lines.append("Rising related searches:")
    if data.related_rising_queries:
        for related in data.related_rising_queries:
            lines.append(f"  - {related.query} ({related.formatted_value or related.value})")
    else:
        lines.append("  (none returned)")

    scored_regions = [r for r in data.interest_by_region if r.value is not None]
    if scored_regions:
        top_regions = sorted(scored_regions, key=lambda r: r.value, reverse=True)[:5]
        lines.append("")
        lines.append("Highest-interest regions:")
        for region in top_regions:
            lines.append(f"  - {region.region_name or region.region_code}: {region.value}")

    lines.append("")
    lines.append(TREND_DATA_WARNING)
    lines.append("=" * 50)
    return "\n".join(lines)


def format_demand_report(signals, result) -> str:
    """Render DemandSignals + DemandAnalysisResult as a human-readable report.

    Both scores are always labeled PROVISIONAL, and evidence is always
    split into observed / derived / unavailable so nothing is implied
    to be more certain than it is.
    """
    lines = [
        "=" * 50,
        "DEMAND ANALYSIS REPORT (PROVISIONAL)",
        "=" * 50,
        f"Query: {result.query}",
        f"Geo: {signals.geo}",
        "",
        f"Demand Score: {_format_optional(result.demand_score)} "
        "(PROVISIONAL -- not validated against real sales outcomes)",
        f"Confidence Score: {result.confidence_score:.2f} "
        "(how much evidence supports the Demand Score above)",
        "",
        "Contributions (None = excluded from Demand Score, not penalized):",
        f"  Trend:       {_format_optional(result.trend_contribution)}",
        f"  Breadth:     {_format_optional(result.breadth_contribution)}",
        f"  Regional:    {_format_optional(result.regional_contribution)}",
        f"  Marketplace: {_format_optional(result.marketplace_contribution)}",
    ]

    lines.append("")
    lines.append("Observed:")
    for key, value in result.observed.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Derived:")
    for key, value in result.derived.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Unavailable:")
    if result.unavailable:
        for item in result.unavailable:
            lines.append(f"  - {item}")
    else:
        lines.append("  (none -- all signal groups had data)")
    lines.append("  - exact sales volume, number of buyers, revenue, conversion")
    lines.append("    rate, and absolute search volume are never available from")
    lines.append("    any current source and are never estimated")

    if result.notes:
        lines.append("")
        lines.append("Notes:")
        for note in result.notes:
            lines.append(f"  - {note}")

    lines.append("")
    lines.append(TREND_DATA_WARNING)
    lines.append(
        "This Demand Score is NOT fed into the Phase 1 Opportunity Scoring "
        "Engine yet."
    )
    lines.append("=" * 50)
    return "\n".join(lines)


def run_manual_analyzer(input_func=input) -> None:
    """Run the Phase 2 Manual Product Analyzer flow end to end."""
    print("\nManual Product Analyzer")
    print("Enter the product details and scores below.\n")

    product = collect_product(input_func)
    scores = collect_scores(input_func)
    result = score_opportunity(product, scores)

    print()
    print(format_report(result))


def run_mercado_livre_search(input_func=input) -> None:
    """Run the Phase 3 Mercado Livre search flow end to end.

    This only retrieves, validates, maps, and displays real external
    data -- it does not compute an Opportunity Score from it.
    """
    print("\nSearch Mercado Livre")
    query = ask("Search term: ", parse_non_empty_text, input_func)

    try:
        items = search_products(query)
    except MercadoLivreError as exc:
        print(f"\nMercado Livre search failed: {exc}")
        return

    print()
    print(format_search_results(items))


def run_trend_analysis(input_func=input) -> None:
    """Run the Phase 4 trend-analysis flow end to end.

    Fetches trend data via the Apify integration layer, then computes
    deterministic metrics and a provisional Trend Score via
    src.trend_analysis. This Trend Score is not wired into the Phase 1
    Opportunity Scoring Engine.
    """
    print("\nAnalyze Trend")
    query = ask("Search term: ", parse_non_empty_text, input_func)
    geo = ask_with_default(f"Geo [default {DEFAULT_GEO}]: ", DEFAULT_GEO, input_func)
    timeframe = ask_with_default(
        f"Timeframe [default {DEFAULT_TIMEFRAME}]: ", DEFAULT_TIMEFRAME, input_func
    )

    try:
        data = fetch_trend_data(query, geo=geo, timeframe=timeframe)
    except ApifyTrendsError as exc:
        print(f"\nTrend analysis failed: {exc}")
        return

    metrics = analyze_trend(data)

    print()
    print(format_trend_report(data, metrics))


def run_demand_analysis(input_func=input) -> None:
    """Run the Phase 5 demand-analysis flow end to end.

    Attempts both currently-integrated sources (trend/search-interest
    via Apify, marketplace via Mercado Livre) independently -- a
    failure in one does not block the other, and whichever source
    fails is honestly reported as unavailable, never guessed.

    Does NOT feed the resulting Demand Score into the Phase 1
    Opportunity Scoring Engine.
    """
    print("\nAnalyze Demand")
    query = ask("Search term: ", parse_non_empty_text, input_func)
    geo = ask_with_default(f"Geo [default {DEFAULT_GEO}]: ", DEFAULT_GEO, input_func)

    trend_data = None
    trend_metrics = None
    try:
        trend_data = fetch_trend_data(query, geo=geo)
        trend_metrics = analyze_trend(trend_data)
    except ApifyTrendsError as exc:
        print(f"\n(trend source unavailable: {exc})")

    marketplace_items = None
    try:
        marketplace_items = search_products(query)
    except MercadoLivreError as exc:
        print(f"(marketplace source unavailable: {exc})")

    signals = build_demand_signals(
        query,
        geo,
        trend_data=trend_data,
        trend_metrics=trend_metrics,
        marketplace_items=marketplace_items,
    )
    result = analyze_demand(signals)

    print()
    print(format_demand_report(signals, result))


COMPETITION_SAMPLE_LIMIT = 10


def format_competition_report(signals, result) -> str:
    """Render CompetitionSignals + CompetitionAnalysisResult as a human-readable report.

    Both scores are always labeled PROVISIONAL. A sample from one
    marketplace call is "one street block," never "the whole city" --
    the report never implies otherwise.
    """
    lines = [
        "=" * 50,
        "COMPETITION ANALYSIS REPORT (PROVISIONAL)",
        "=" * 50,
        f"Query: {result.query}",
        "",
        f"Competition Score: {_format_optional(result.competition_score)} "
        "(PROVISIONAL -- 0 = low apparent competition, 100 = very high; "
        "not validated against real outcomes)",
        f"Confidence Score: {result.confidence_score:.2f} "
        "(how much evidence supports the Competition Score above)",
        "",
        "Contributions (None = excluded from Competition Score, not penalized):",
        f"  Seller concentration: {_format_optional(result.seller_concentration_contribution)}",
        f"  Listing saturation:   {_format_optional(result.listing_saturation_contribution)}",
        f"  Price crowding:       {_format_optional(result.price_crowding_contribution)}",
        f"  Duplicate listings:   {_format_optional(result.duplicate_listing_contribution)}",
        f"  Shipping:             {_format_optional(result.shipping_contribution)}",
    ]

    lines.append("")
    lines.append("Observed:")
    for key, value in result.observed.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Derived:")
    for key, value in result.derived.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Unavailable:")
    for item in result.unavailable:
        lines.append(f"  - {item}")

    if result.notes:
        lines.append("")
        lines.append("Notes:")
        for note in result.notes:
            lines.append(f"  - {note}")

    lines.append("")
    lines.append(
        "A marketplace sample is one street block, not the whole city -- "
        "it is never treated as a total market count."
    )
    lines.append(
        "This Competition Score is NOT fed into the Phase 1 Opportunity "
        "Scoring Engine yet."
    )
    lines.append("=" * 50)
    return "\n".join(lines)


def run_competition_analysis(input_func=input) -> None:
    """Run the Phase 6 competition-analysis flow end to end.

    Attempts the marketplace source; if it fails, no Competition Score
    is fabricated -- the failure is reported honestly and the report
    still renders with everything marked unavailable.

    Does NOT feed the resulting Competition Score into the Phase 1
    Opportunity Scoring Engine.
    """
    print("\nAnalyze Competition")
    query = ask("Search term: ", parse_non_empty_text, input_func)

    marketplace_items = None
    try:
        marketplace_items = search_products(query, limit=COMPETITION_SAMPLE_LIMIT)
    except MercadoLivreError as exc:
        print(f"\n(marketplace source unavailable: {exc})")

    signals = build_competition_signals(query, marketplace_items=marketplace_items)
    result = analyze_competition(signals, requested_limit=COMPETITION_SAMPLE_LIMIT)

    print()
    print(format_competition_report(signals, result))


def format_margin_report(inputs, result) -> str:
    """Render MarginInputs + MarginAnalysisResult as a human-readable report.

    Never calls contribution profit "net profit" -- fixed company
    expenses are not included anywhere in this calculation.
    """
    lines = [
        "=" * 50,
        "MARGIN ANALYSIS REPORT (PROVISIONAL)",
        "=" * 50,
        f"Product: {result.product_name}",
        f"Sale price: {result.sale_price}",
        f"Product cost: {result.product_cost}",
        "",
        "Known costs:",
        f"  Marketplace fee: {_format_optional(result.marketplace_fee_total)}",
        f"  Shipping: {_format_optional(inputs.seller_shipping_cost)}",
        f"  Packaging: {_format_optional(inputs.packaging_cost)}",
        f"  Tax: {_format_optional(result.tax_total)}",
        f"  Payment: {_format_optional(inputs.payment_cost)}",
        f"  Advertising: {_format_optional(inputs.advertising_cost_per_sale)}",
        f"  Return reserve: {_format_optional(inputs.return_reserve)}",
        f"  Other: {_format_optional(inputs.other_variable_cost)}",
        "",
        "Derived (known-cost basis):",
        f"  Gross profit: {result.gross_profit}",
        f"  Gross margin: {result.gross_margin_percent}%",
        f"  Markup: {_format_optional(result.markup_percent, '%')}",
        f"  Known total variable cost: {result.total_variable_cost}",
        f"  Contribution profit (known costs only): {result.contribution_profit}",
        f"  Contribution margin (known costs only): {result.contribution_margin_percent}%",
        f"  Break-even price (known costs only): {_format_optional(result.break_even_price)}",
        "",
        f"Margin Score: {_format_optional(result.margin_score)} "
        "(PROVISIONAL -- business heuristic, not empirically validated)",
        f"Cost Completeness Score: {result.cost_completeness_score:.2f}",
    ]

    lines.append("")
    lines.append("Unavailable / unknown costs:")
    for item in result.unavailable:
        lines.append(f"  - {item}")

    if result.notes:
        lines.append("")
        lines.append("Warnings:")
        for note in result.notes:
            lines.append(f"  - {note}")

    lines.append("")
    lines.append(
        "Contribution profit is based on KNOWN variable costs only -- it is "
        "NOT net profit. Fixed company expenses (salaries, rent, software, "
        "accounting, etc.) are never included."
    )
    lines.append(
        "This Margin Score is NOT fed into the Phase 1 Opportunity Scoring Engine yet."
    )
    lines.append("=" * 50)
    return "\n".join(lines)


def run_margin_analysis(input_func=input) -> None:
    """Run the Phase 7 margin-analysis flow end to end.

    Only `product_name`, `sale_price`, and `product_cost` are
    mandatory. Every other cost is optional -- a blank answer means
    "unknown" (excluded from sums), never a fabricated zero.
    """
    print("\nAnalyze Margin")
    product_name = ask("Product name: ", parse_non_empty_text, input_func)
    sale_price = ask("Sale price: ", parse_required_positive_money, input_func)
    product_cost = ask("Product cost: ", parse_required_non_negative_money, input_func)

    print(
        "\nOptional costs -- leave blank if unknown "
        "(blank = unknown, 0 = explicitly zero; they are not the same):"
    )
    marketplace_fee_amount = ask(
        "Marketplace fee amount (blank if unknown): ", parse_optional_money, input_func
    )
    marketplace_fee_rate = ask(
        "Marketplace fee rate, 0-1 e.g. 0.12 for 12% (blank if unknown): ",
        parse_optional_rate,
        input_func,
    )
    fixed_marketplace_fee = ask(
        "Fixed marketplace fee (blank if unknown): ", parse_optional_money, input_func
    )
    seller_shipping_cost = ask(
        "Seller shipping cost (blank if unknown): ", parse_optional_money, input_func
    )
    packaging_cost = ask("Packaging cost (blank if unknown): ", parse_optional_money, input_func)
    tax_amount = ask("Tax amount (blank if unknown): ", parse_optional_money, input_func)
    tax_rate = ask(
        "Tax rate, 0-1 e.g. 0.06 for 6% (blank if unknown): ", parse_optional_rate, input_func
    )
    payment_cost = ask(
        "Payment processing cost (blank if unknown): ", parse_optional_money, input_func
    )
    advertising_cost_per_sale = ask(
        "Advertising cost per sale (blank if unknown): ", parse_optional_money, input_func
    )
    return_reserve = ask(
        "Return/refund reserve per sale (blank if unknown): ", parse_optional_money, input_func
    )
    other_variable_cost = ask(
        "Other variable cost (blank if unknown): ", parse_optional_money, input_func
    )

    try:
        inputs = MarginInputs(
            product_name=product_name,
            sale_price=sale_price,
            product_cost=product_cost,
            marketplace_fee_amount=marketplace_fee_amount,
            marketplace_fee_rate=marketplace_fee_rate,
            fixed_marketplace_fee=fixed_marketplace_fee,
            seller_shipping_cost=seller_shipping_cost,
            packaging_cost=packaging_cost,
            tax_amount=tax_amount,
            tax_rate=tax_rate,
            payment_cost=payment_cost,
            advertising_cost_per_sale=advertising_cost_per_sale,
            return_reserve=return_reserve,
            other_variable_cost=other_variable_cost,
        )
    except ValueError as exc:
        print(f"\nInvalid input: {exc}")
        return

    result = analyze_margin(inputs)

    print()
    print(format_margin_report(inputs, result))


def format_supplier_report(inputs, result) -> str:
    """Render SupplierInputs + SupplierAnalysisResult as a human-readable report.

    Makes it obvious that unknown != bad (missing fields are shown as
    "not available", never as a negative score) and that a high score
    != high certainty (Supplier Score and Evidence Completeness are
    always shown side by side, and a BLOCKED status is never hidden
    inside an average).
    """
    lines = [
        "=" * 50,
        "SUPPLIER ANALYSIS REPORT (PROVISIONAL)",
        "=" * 50,
        f"Product: {result.product_name}",
        f"Supplier: {result.supplier_name}",
        "",
        f"Supplier Score: {_format_optional(result.supplier_score)} "
        "(PROVISIONAL -- business heuristic, not empirically validated)",
        f"Supplier Evidence Completeness: {result.evidence_completeness_score:.2f}%",
        f"Operational Status: {result.operational_status}",
        "",
        "Dimensions (None = excluded, not penalized):",
        f"  Order flexibility:      {_format_optional(result.order_flexibility_score)}",
        f"  Operational speed:      {_format_optional(result.operational_speed_score)}",
        f"  Stock viability:        {_format_optional(result.stock_viability_score)}",
        f"  Fulfillment capability: {_format_optional(result.fulfillment_capability_score)}",
        f"  Trust/compliance:       {_format_optional(result.trust_score)}",
        f"  Lead time (days):       {_format_optional(result.lead_time_days)}",
    ]

    lines.append("")
    lines.append("Observed:")
    for key, value in result.observed.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Derived:")
    for key, value in result.derived.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Unavailable / unknown:")
    for item in result.unavailable:
        lines.append(f"  - {item}")

    lines.append("")
    lines.append("Blockers:")
    if result.blockers:
        for blocker in result.blockers:
            lines.append(f"  - {blocker}")
    else:
        lines.append("  (none detected)")

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    if result.notes:
        lines.append("")
        lines.append("Notes:")
        for note in result.notes:
            lines.append(f"  - {note}")

    lines.append("")
    lines.append(
        "A Mercado Livre listing is NOT proof of wholesale/dropshipping capability -- "
        "every field above must come from an explicit sourcing investigation."
    )
    lines.append(
        "This Supplier Score is NOT fed into the Phase 1 Opportunity Scoring Engine yet."
    )
    lines.append("=" * 50)
    return "\n".join(lines)


def run_supplier_analysis(input_func=input) -> None:
    """Run the Phase 8 supplier-analysis flow end to end.

    Only product_name and supplier_name are mandatory. Every other
    field accepts a blank answer for "unknown" -- blank is never
    silently treated as False or zero.
    """
    print("\nAnalyze Supplier")
    product_name = ask("Product name: ", parse_non_empty_text, input_func)
    supplier_name = ask("Supplier name: ", parse_non_empty_text, input_func)

    print(
        "\nOptional fields -- leave blank if unknown. For yes/no fields: "
        "'y' = yes, 'n' = no, blank = unknown (never forced to 'n'):"
    )
    unit_cost = ask("Unit cost (blank if unknown): ", parse_optional_money, input_func)
    moq_units = ask("MOQ in units (blank if unknown): ", parse_optional_moq, input_func)
    minimum_order_value = ask(
        "Minimum order value (blank if unknown): ", parse_optional_positive_money, input_func
    )
    shipping_cost = ask(
        "Shipping cost to seller (blank if unknown): ", parse_optional_money, input_func
    )
    payment_terms_days = ask(
        "Payment terms, days (blank if unknown): ", parse_optional_int, input_func
    )
    stock_quantity = ask("Stock quantity (blank if unknown): ", parse_optional_int, input_func)
    stock_available = ask(
        "Stock currently available? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    dispatch_time_days = ask(
        "Dispatch time, days (blank if unknown): ", parse_optional_int, input_func
    )
    delivery_time_days = ask(
        "Delivery time, days (blank if unknown): ", parse_optional_int, input_func
    )
    lead_time_days = ask(
        "Explicit total lead time, days -- only if you did NOT give dispatch+delivery "
        "above (blank if unknown): ",
        parse_optional_int,
        input_func,
    )
    tracking_available = ask(
        "Tracking available? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    dropshipping_supported = ask(
        "Dropshipping supported? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    blind_shipping_supported = ask(
        "Blind shipping supported? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    invoice_available = ask(
        "Invoice available? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    return_policy_available = ask(
        "Return policy available? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    business_verified = ask(
        "Business registration verified? y/n (blank if unknown): ",
        parse_optional_bool,
        input_func,
    )
    contact_available = ask(
        "Contact available? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    supplier_rating = ask(
        "Supplier rating, 0-5 scale (blank if unknown): ", parse_optional_rating, input_func
    )
    review_count = ask("Review count (blank if unknown): ", parse_optional_int, input_func)
    years_active = ask("Years active (blank if unknown): ", parse_optional_int, input_func)

    try:
        inputs = SupplierInputs(
            product_name=product_name,
            supplier_name=supplier_name,
            unit_cost=unit_cost,
            moq_units=moq_units,
            minimum_order_value=minimum_order_value,
            shipping_cost=shipping_cost,
            payment_terms_days=payment_terms_days,
            stock_quantity=stock_quantity,
            stock_available=stock_available,
            dispatch_time_days=dispatch_time_days,
            delivery_time_days=delivery_time_days,
            lead_time_days=lead_time_days,
            tracking_available=tracking_available,
            dropshipping_supported=dropshipping_supported,
            blind_shipping_supported=blind_shipping_supported,
            invoice_available=invoice_available,
            return_policy_available=return_policy_available,
            business_verified=business_verified,
            contact_available=contact_available,
            supplier_rating=supplier_rating,
            review_count=review_count,
            years_active=years_active,
        )
    except ValueError as exc:
        print(f"\nInvalid input: {exc}")
        return

    result = analyze_supplier(inputs)

    print()
    print(format_supplier_report(inputs, result))


def format_logistics_report(inputs, result) -> str:
    """Render LogisticsInputs + LogisticsAnalysisResult as a human-readable report.

    Makes it obvious that unknown != bad (missing fields are shown as
    "not available", never scored as a negative) and that a high
    Logistics Score != high evidence completeness -- the two are
    always shown side by side.
    """
    lines = [
        "=" * 50,
        "LOGISTICS ANALYSIS REPORT (PROVISIONAL)",
        "=" * 50,
        f"Product: {result.product_name}",
        "",
        f"Logistics Score: {_format_optional(result.logistics_score)} "
        "(PROVISIONAL -- 0 = operationally difficult, 100 = easy/favorable; "
        "business heuristic, not empirically validated)",
        f"Logistics Evidence Completeness: {result.evidence_completeness_score:.2f}%",
        f"Operational Status: {result.operational_status}",
        "",
        "Dimensions (None = excluded, not penalized):",
        f"  Physical ease:          {_format_optional(result.physical_ease_score)}",
        f"  Handling ease:          {_format_optional(result.handling_ease_score)}",
        f"  Delivery convenience:   {_format_optional(result.delivery_convenience_score)}",
        f"  Fulfillment support:    {_format_optional(result.fulfillment_support_score)}",
        f"  Shipping support:       {_format_optional(result.shipping_support_score)}",
        "",
        f"Package volume (cm3):   {_format_optional(result.package_volume_cm3)}",
        f"Volume (liters):        {_format_optional(result.volume_liters)}",
        f"Dimensional weight (kg): {_format_optional(result.dimensional_weight_kg)}",
        f"Reference billable weight (kg, NOT a real carrier charge): "
        f"{_format_optional(result.reference_billable_weight_kg)}",
    ]

    lines.append("")
    lines.append("Observed:")
    for key, value in result.observed.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Derived:")
    for key, value in result.derived.items():
        lines.append(f"  - {key}: {_format_optional(value)}")

    lines.append("")
    lines.append("Unavailable / unknown:")
    for item in result.unavailable:
        lines.append(f"  - {item}")

    lines.append("")
    lines.append("Blockers:")
    if result.blockers:
        for blocker in result.blockers:
            lines.append(f"  - {blocker}")
    else:
        lines.append("  (none detected)")

    if result.warnings:
        lines.append("")
        lines.append("Warnings:")
        for warning in result.warnings:
            lines.append(f"  - {warning}")

    if result.notes:
        lines.append("")
        lines.append("Notes:")
        for note in result.notes:
            lines.append(f"  - {note}")

    lines.append("")
    lines.append(
        "estimated_delivery_days is the CUSTOMER-facing delivery leg, not Phase 8's "
        "supplier lead time -- the two are never interchangeable."
    )
    lines.append(
        "This Logistics Score is NOT fed into the Phase 1 Opportunity Scoring Engine yet."
    )
    lines.append("=" * 50)
    return "\n".join(lines)


def run_logistics_analysis(input_func=input) -> None:
    """Run the Phase 9 logistics-analysis flow end to end.

    Only product_name is mandatory. Every other field accepts a blank
    answer for "unknown" -- blank is never silently treated as False
    or zero.
    """
    print("\nAnalyze Logistics")
    product_name = ask("Product name: ", parse_non_empty_text, input_func)

    print("\nPhysical -- leave blank if unknown:")
    weight_kg = ask("Weight, kg (blank if unknown): ", parse_optional_positive_money, input_func)
    length_cm = ask("Length, cm (blank if unknown): ", parse_optional_positive_money, input_func)
    width_cm = ask("Width, cm (blank if unknown): ", parse_optional_positive_money, input_func)
    height_cm = ask("Height, cm (blank if unknown): ", parse_optional_positive_money, input_func)
    dimensional_weight_divisor = ask(
        "Dimensional weight divisor, carrier-specific (blank if unknown): ",
        parse_optional_positive_money,
        input_func,
    )

    print("\nHandling -- y/n/blank:")
    fragile = ask("Fragile? y/n (blank if unknown): ", parse_optional_bool, input_func)
    liquid = ask("Liquid? y/n (blank if unknown): ", parse_optional_bool, input_func)
    hazardous = ask("Hazardous? y/n (blank if unknown): ", parse_optional_bool, input_func)
    perishable = ask("Perishable? y/n (blank if unknown): ", parse_optional_bool, input_func)
    temperature_sensitive = ask(
        "Temperature sensitive? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    stackable = ask("Stackable? y/n (blank if unknown): ", parse_optional_bool, input_func)
    requires_special_handling = ask(
        "Requires special handling? y/n (blank if unknown): ", parse_optional_bool, input_func
    )

    print("\nPackaging:")
    extra_packaging_required = ask(
        "Extra packaging required? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    packaging_cost = ask("Packaging cost (blank if unknown): ", parse_optional_money, input_func)

    print("\nFulfillment:")
    supplier_fulfilled = ask(
        "Supplier fulfilled? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    seller_fulfilled = ask(
        "Seller fulfilled? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    warehouse_required = ask(
        "Warehouse required? y/n (blank if unknown): ", parse_optional_bool, input_func
    )

    print("\nShipping (customer-facing delivery, not supplier lead time):")
    known_shipping_cost = ask(
        "Known shipping cost (blank if unknown): ", parse_optional_money, input_func
    )
    estimated_delivery_days = ask(
        "Estimated delivery days (blank if unknown): ", parse_optional_int, input_func
    )
    tracking_available = ask(
        "Tracking available? y/n (blank if unknown): ", parse_optional_bool, input_func
    )
    insurance_available = ask(
        "Insurance available? y/n (blank if unknown): ", parse_optional_bool, input_func
    )

    print("\nObserved history -- real historical rates only, never estimated:")
    observed_damage_rate = ask(
        "Observed damage rate, 0-1 (blank if unknown): ", parse_optional_rate, input_func
    )
    observed_return_rate = ask(
        "Observed return rate, 0-1 (blank if unknown): ", parse_optional_rate, input_func
    )

    try:
        inputs = LogisticsInputs(
            product_name=product_name,
            weight_kg=weight_kg,
            length_cm=length_cm,
            width_cm=width_cm,
            height_cm=height_cm,
            dimensional_weight_divisor=dimensional_weight_divisor,
            fragile=fragile,
            liquid=liquid,
            hazardous=hazardous,
            perishable=perishable,
            temperature_sensitive=temperature_sensitive,
            stackable=stackable,
            requires_special_handling=requires_special_handling,
            extra_packaging_required=extra_packaging_required,
            packaging_cost=packaging_cost,
            supplier_fulfilled=supplier_fulfilled,
            seller_fulfilled=seller_fulfilled,
            warehouse_required=warehouse_required,
            known_shipping_cost=known_shipping_cost,
            estimated_delivery_days=estimated_delivery_days,
            tracking_available=tracking_available,
            insurance_available=insurance_available,
            observed_damage_rate=observed_damage_rate,
            observed_return_rate=observed_return_rate,
        )
    except ValueError as exc:
        print(f"\nInvalid input: {exc}")
        return

    result = analyze_logistics(inputs)

    print()
    print(format_logistics_report(inputs, result))


def main() -> None:
    print("RAVZ Product Hunter")
    print("1. Manual Product Analyzer")
    print("2. Search Mercado Livre")
    print("3. Analyze Trend")
    print("4. Analyze Demand")
    print("5. Analyze Competition")
    print("6. Analyze Margin")
    print("7. Analyze Supplier")
    print("8. Analyze Logistics")

    choice = ask("Choose an option (1-8): ", parse_menu_choice)

    if choice == 1:
        run_manual_analyzer()
    elif choice == 2:
        run_mercado_livre_search()
    elif choice == 3:
        run_trend_analysis()
    elif choice == 4:
        run_demand_analysis()
    elif choice == 5:
        run_competition_analysis()
    elif choice == 6:
        run_margin_analysis()
    elif choice == 7:
        run_supplier_analysis()
    else:
        run_logistics_analysis()


if __name__ == "__main__":
    main()
