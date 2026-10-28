"""Manual Product Analyzer CLI (Phase 2).

This module is the presentation layer: it collects product data and scores
from the user, delegates all scoring logic to src.models / src.scoring, and
renders the result. It contains no scoring math of its own.

Input-collecting functions accept an injectable `input_func` so the
retry/validation logic can be unit tested without calling the real
built-in input().
"""

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


def main() -> None:
    print("RAVZ Product Hunter -- Manual Product Analyzer")
    print("Enter the product details and scores below.\n")

    product = collect_product()
    scores = collect_scores()
    result = score_opportunity(product, scores)

    print()
    print(format_report(result))


if __name__ == "__main__":
    main()
