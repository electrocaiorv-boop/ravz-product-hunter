"""RAVZ Product Hunter CLI (Phase 2: Manual Analyzer, Phase 3: ML search).

This module is the presentation layer: it collects input from the user,
delegates all scoring logic to src.models / src.scoring and all Mercado
Livre HTTP/JSON handling to src.integrations.mercadolivre, and renders the
result. It contains no scoring math and no HTTP logic of its own.

Input-collecting functions accept an injectable `input_func` so the
retry/validation logic can be unit tested without calling the real
built-in input().
"""

from src.integrations.mercadolivre import MercadoLivreError, search_products
from src.models import ComponentScores, Product
from src.scoring import score_opportunity

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
    """Validate that raw text is one of the main menu options ("1" or "2")."""
    text = raw.strip()
    if text not in {"1", "2"}:
        raise ValueError("choose 1 or 2")
    return int(text)


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


def main() -> None:
    print("RAVZ Product Hunter")
    print("1. Manual Product Analyzer")
    print("2. Search Mercado Livre")

    choice = ask("Choose an option (1-2): ", parse_menu_choice)

    if choice == 1:
        run_manual_analyzer()
    else:
        run_mercado_livre_search()


if __name__ == "__main__":
    main()
