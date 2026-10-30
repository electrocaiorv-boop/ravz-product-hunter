"""Phase 11 backwards-compatibility pins for the Phase 1/2 legacy API.

Phase 11 adds an integrated composition layer ALONGSIDE the original
scoring engine; it does not migrate it. These tests exist so that any
future change to `src/scoring.py`, `src/models.py`, or the manual CLI
flow fails loudly here rather than silently altering results users may
already have recorded.

The legacy engine and the integrated engine deliberately differ (weights,
missing-data semantics, rounding-before-classification). Those
differences are asserted here too, so nobody "fixes" one to match the
other by accident.
"""

import pytest

from src.main import collect_scores, format_report, recommend, run_manual_analyzer
from src.models import SCORE_FIELDS, ComponentScores, OpportunityResult, Product
from src.opportunity_models import (
    INTEGRATED_WEIGHTS,
    SEARCH_INTEREST_FAMILY_WEIGHT,
    classify_exact,
)
from src.scoring import (
    NEGATIVE_DIMENSIONS,
    WEIGHTS,
    calculate_opportunity_score,
    classify,
    score_opportunity,
)


def make_scores(**overrides):
    base = dict(
        demand=50, trend=50, competition=50, margin=50,
        supplier=50, logistics=50, risk=50,
    )
    base.update(overrides)
    return ComponentScores(**base)


# -- The legacy weight contract is frozen ---------------------------------


def test_legacy_weights_are_exactly_the_phase_1_contract():
    assert WEIGHTS == {
        "demand": 0.30,
        "trend": 0.20,
        "competition": 0.15,
        "margin": 0.15,
        "supplier": 0.10,
        "logistics": 0.05,
        "risk": 0.05,
    }


def test_legacy_weights_sum_to_one():
    assert sum(WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)


def test_legacy_negative_dimensions_are_unchanged():
    assert NEGATIVE_DIMENSIONS == {"competition", "risk"}


def test_legacy_score_fields_are_unchanged():
    assert SCORE_FIELDS == (
        "demand", "trend", "competition", "margin",
        "supplier", "logistics", "risk",
    )


# -- Legacy scoring behaviour is frozen -----------------------------------


def test_legacy_score_opportunity_is_unchanged():
    product = Product(name="Fone", category="Audio")
    scores = ComponentScores(
        demand=80, trend=60, competition=40, margin=70,
        supplier=50, logistics=90, risk=20,
    )
    result = score_opportunity(product, scores)

    expected = (
        80 * 0.30 + 60 * 0.20 + (100 - 40) * 0.15 + 70 * 0.15
        + 50 * 0.10 + 90 * 0.05 + (100 - 20) * 0.05
    )
    assert isinstance(result, OpportunityResult)
    assert result.opportunity_score == pytest.approx(round(expected, 2), abs=1e-9)
    assert result.classification == "Worth deeper investigation"
    assert result.product is product
    assert result.scores is scores


def test_legacy_breakdown_still_reports_every_dimension():
    _, breakdown = calculate_opportunity_score(make_scores())
    assert set(breakdown) == set(WEIGHTS)


def test_legacy_component_scores_still_reject_missing_values():
    """The legacy API is mandatory-seven by design.

    Missing-score semantics belong to the integrated layer; forcing them
    into `ComponentScores` would destabilize the Phase 1/2 contract.
    """
    with pytest.raises(TypeError):
        ComponentScores(demand=50)


@pytest.mark.parametrize("field", SCORE_FIELDS)
def test_legacy_component_scores_still_reject_none(field):
    with pytest.raises(TypeError):
        make_scores(**{field: None})


def test_legacy_classification_bands_are_unchanged():
    assert classify(80) == "Strong opportunity"
    assert classify(79.99) == "Worth deeper investigation"
    assert classify(65) == "Worth deeper investigation"
    assert classify(64.99) == "Weak or uncertain opportunity"
    assert classify(50) == "Weak or uncertain opportunity"
    assert classify(49.99) == "Reject"


# -- Legacy vs integrated: the differences are intentional ----------------


def test_legacy_and_integrated_weight_tables_are_separate_objects():
    """Changing one must never change the other.

    Note `WEIGHTS["demand"]` and the integrated family weight both read
    0.30 -- a coincidence, not a link: legacy's is Demand alone, the
    integrated one covers the whole Demand/Trend family. Separateness
    is therefore asserted structurally, not by comparing values.
    """
    assert WEIGHTS is not INTEGRATED_WEIGHTS
    # The tables do not even describe the same slots: integrated adds a
    # trend entry carrying the shared family weight.
    assert INTEGRATED_WEIGHTS["trend"] != WEIGHTS["trend"]
    assert sum(WEIGHTS.values()) == pytest.approx(1.0, abs=1e-9)
    assert sum(INTEGRATED_WEIGHTS.values()) > 1.0, (
        "integrated lists the family weight on BOTH members; only the elected "
        "representative is ever counted"
    )


def test_integrated_family_weight_deliberately_differs_from_the_legacy_sum():
    """The hardened integrated model does NOT inherit legacy's 0.50.

    Legacy split 0.50 across what it BELIEVED were two independent
    demand signals (Demand 0.30 + Trend 0.20). Once the audit proved
    they are ONE evidence family fed by ONE Google Trends call,
    preserving 0.50 would not have preserved the original business
    judgment -- it would have silently converted "half the score from
    two independent signals" into "half the score from one provider
    call", a materially more concentrated claim than Phase 1 intended.

    Integrated-v1 therefore re-derives the weight from marginal
    information value (0.30). Legacy keeps its own table untouched.
    """
    legacy_sum = WEIGHTS["demand"] + WEIGHTS["trend"]
    assert legacy_sum == pytest.approx(0.50, abs=1e-9)
    assert SEARCH_INTEREST_FAMILY_WEIGHT == pytest.approx(0.30, abs=1e-9)
    assert SEARCH_INTEREST_FAMILY_WEIGHT < legacy_sum


def test_every_integrated_weight_is_independent_of_its_legacy_counterpart():
    """No integrated weight may be derived from the legacy table.

    Each integrated weight is justified by evidence value, not copied.
    Only Competition happens to coincide at 0.15, which this test
    documents as a coincidence rather than a dependency.
    """
    assert INTEGRATED_WEIGHTS["margin"] != WEIGHTS["margin"]
    assert INTEGRATED_WEIGHTS["supplier"] != WEIGHTS["supplier"]
    assert INTEGRATED_WEIGHTS["logistics"] != WEIGHTS["logistics"]
    assert INTEGRATED_WEIGHTS["risk"] != WEIGHTS["risk"]
    assert INTEGRATED_WEIGHTS["competition"] == pytest.approx(
        WEIGHTS["competition"], abs=1e-9
    ), "coincidence, not a derivation -- both happen to be 0.15"


def test_legacy_classifies_the_rounded_total_by_documented_contract():
    """Legacy rounds to 2dp BEFORE classifying; integrated does not.

    `score_opportunity()` has always passed the already-rounded total to
    `classify()`. Phase 11 preserves that rather than "fixing" it (no
    proven bug, and changing it would move previously recorded results).
    The integrated engine deliberately classifies the exact value --
    this test pins both behaviours so the divergence stays deliberate.
    """
    rounded_up = 79.995
    assert round(rounded_up, 2) == pytest.approx(80.0, abs=1e-9)
    # Legacy: a display-rounded 80.00 classifies as Strong.
    assert classify(round(rounded_up, 2)) == "Strong opportunity"
    # Integrated: the exact value is below 80, so it does not promote.
    assert classify_exact(rounded_up) == "Worth deeper investigation"


# -- The manual CLI flow still works --------------------------------------


def test_legacy_manual_analyzer_still_runs_end_to_end(capsys):
    answers = iter([
        "Fone Bluetooth",  # product name
        "Audio",            # category
        "80", "60", "40", "70", "50", "90", "20",  # the seven scores
    ])
    run_manual_analyzer(input_func=lambda _prompt: next(answers))

    output = capsys.readouterr().out
    assert "OPPORTUNITY REPORT" in output
    assert "Fone Bluetooth" in output
    assert "Opportunity Score:" in output
    assert "Classification:" in output
    assert "Recommendation:" in output


def test_legacy_collect_scores_still_collects_all_seven():
    answers = iter(["10", "20", "30", "40", "50", "60", "70"])
    scores = collect_scores(input_func=lambda _prompt: next(answers))
    assert scores == ComponentScores(
        demand=10, trend=20, competition=30, margin=40,
        supplier=50, logistics=60, risk=70,
    )


def test_legacy_format_report_is_unchanged():
    product = Product(name="Fone", category="Audio")
    result = score_opportunity(product, make_scores())
    report = format_report(result)

    assert "OPPORTUNITY REPORT" in report
    assert "Component scores:" in report
    assert "Weighted breakdown:" in report
    for dimension in WEIGHTS:
        assert dimension.capitalize() in report


def test_legacy_recommendations_still_map_every_classification():
    for label in (
        "Strong opportunity",
        "Worth deeper investigation",
        "Weak or uncertain opportunity",
        "Reject",
    ):
        assert recommend(label) != "No recommendation available."
