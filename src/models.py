"""Data models for RAVZ Product Hunter.

Three distinct concerns, kept as separate models:

- Product: raw product identification data. No scores.
- ComponentScores: the 0-100 scoring inputs for each opportunity dimension.
- OpportunityResult: the final computed output of the scoring engine.
"""

from dataclasses import dataclass

SCORE_FIELDS = (
    "demand",
    "trend",
    "competition",
    "margin",
    "supplier",
    "logistics",
    "risk",
)


def _validate_score(name: str, value: float) -> None:
    if not 0 <= value <= 100:
        raise ValueError(f"{name} must be between 0 and 100, got {value}")


@dataclass
class Product:
    """Identifies the product being evaluated."""

    name: str
    category: str
    source: str = "manual"


@dataclass
class ComponentScores:
    """Scoring inputs (0-100) for each opportunity dimension.

    All fields use the same direction: higher means "more of this thing."
    For competition and risk, "more" is bad for the opportunity -- inverting
    them is the scoring engine's job, not this model's.
    """

    demand: float
    trend: float
    competition: float
    margin: float
    supplier: float
    logistics: float
    risk: float

    def __post_init__(self) -> None:
        for name in SCORE_FIELDS:
            _validate_score(name, getattr(self, name))


@dataclass
class OpportunityResult:
    """Final output of the scoring engine for a given product."""

    product: Product
    scores: ComponentScores
    opportunity_score: float
    classification: str
    breakdown: dict
