"""Opportunity scoring engine.

Combines ComponentScores into a single 0-100 Opportunity Score using the
weights defined in CLAUDE.md:

    Demand 30% | Trend 20% | Competition 15% | Margin 15%
    Supplier 10% | Logistics 5% | Risk 5%

Demand, Trend, Margin, Supplier, and Logistics are positive dimensions: a
higher score raises the opportunity score.

Competition and Risk are negative dimensions: a higher score means more
competition or more risk, which must LOWER the opportunity score. They are
inverted (100 - score) before weighting.
"""

from src.models import ComponentScores, OpportunityResult, Product

WEIGHTS = {
    "demand": 0.30,
    "trend": 0.20,
    "competition": 0.15,
    "margin": 0.15,
    "supplier": 0.10,
    "logistics": 0.05,
    "risk": 0.05,
}

NEGATIVE_DIMENSIONS = {"competition", "risk"}


def calculate_opportunity_score(scores: ComponentScores) -> tuple[float, dict]:
    """Return (opportunity_score, breakdown) for the given component scores."""
    breakdown = {}
    total = 0.0
    for dimension, weight in WEIGHTS.items():
        raw = getattr(scores, dimension)
        effective = (100 - raw) if dimension in NEGATIVE_DIMENSIONS else raw
        contribution = effective * weight
        breakdown[dimension] = round(contribution, 2)
        total += contribution
    return round(total, 2), breakdown


def classify(opportunity_score: float) -> str:
    """Map a 0-100 opportunity score to its classification label."""
    if opportunity_score >= 80:
        return "Strong opportunity"
    if opportunity_score >= 65:
        return "Worth deeper investigation"
    if opportunity_score >= 50:
        return "Weak or uncertain opportunity"
    return "Reject"


def score_opportunity(product: Product, scores: ComponentScores) -> OpportunityResult:
    """Score a product end-to-end and return the full OpportunityResult."""
    opportunity_score, breakdown = calculate_opportunity_score(scores)
    return OpportunityResult(
        product=product,
        scores=scores,
        opportunity_score=opportunity_score,
        classification=classify(opportunity_score),
        breakdown=breakdown,
    )
