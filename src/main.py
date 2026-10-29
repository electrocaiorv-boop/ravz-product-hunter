"""RAVZ Product Hunter CLI.

Phase 2: Manual Analyzer. Phase 3: Mercado Livre search. Phase 4: Trend
analysis. Phase 5: Demand analysis.

This module is the presentation layer: it collects input from the user,
delegates all scoring logic to src.models / src.scoring, all Mercado
Livre HTTP/JSON handling to src.integrations.mercadolivre, all Apify/trend
HTTP/JSON handling to src.integrations.apify_trends, all trend-metric math
to src.trend_analysis, and all demand math to src.demand_models /
src.demand_analysis, then renders the result. It contains no scoring
math and no HTTP logic of its own.

Input-collecting functions accept an injectable `input_func` so the
retry/validation logic can be unit tested without calling the real
built-in input().
"""

from src.demand_analysis import analyze_demand
from src.demand_models import build_demand_signals
from src.integrations.apify_trends import (
    DEFAULT_GEO,
    DEFAULT_TIMEFRAME,
    ApifyTrendsError,
    fetch_trend_data,
)
from src.integrations.mercadolivre import MercadoLivreError, search_products
from src.models import ComponentScores, Product
from src.scoring import score_opportunity
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
    """Validate that raw text is one of the main menu options (1-4)."""
    text = raw.strip()
    if text not in {"1", "2", "3", "4"}:
        raise ValueError("choose 1, 2, 3 or 4")
    return int(text)


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


def main() -> None:
    print("RAVZ Product Hunter")
    print("1. Manual Product Analyzer")
    print("2. Search Mercado Livre")
    print("3. Analyze Trend")
    print("4. Analyze Demand")

    choice = ask("Choose an option (1-4): ", parse_menu_choice)

    if choice == 1:
        run_manual_analyzer()
    elif choice == 2:
        run_mercado_livre_search()
    elif choice == 3:
        run_trend_analysis()
    else:
        run_demand_analysis()


if __name__ == "__main__":
    main()
