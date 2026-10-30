"""Integrated Opportunity composition tests (Phase 11).

Two complementary styles are used deliberately:

  - STUB domain results (simple objects carrying the same public
    attribute names as the real results) give exact numeric control, so
    weighted arithmetic, inversion and the missing-data policies can be
    asserted precisely.
  - REAL domain results (produced by the actual Phase 4-10 analysis
    functions) prove the adapters read the genuine contracts, so a
    rename or direction change in any domain module fails here.
"""

from decimal import Decimal

import pytest

from src.competition_analysis import analyze_competition
from src.competition_models import build_competition_signals
from src.demand_analysis import analyze_demand
from src.demand_models import build_demand_signals
from src.logistics_analysis import analyze_logistics
from src.logistics_models import LogisticsInputs
from src.margin_analysis import analyze_margin
from src.margin_models import MarginInputs
from src.opportunity_integration import (
    FAMILY_OVERLAP_POLICY,
    compose_opportunity,
    from_competition_result,
    from_demand_result,
    from_logistics_result,
    from_margin_result,
    from_risk_result,
    from_supplier_result,
    from_trend_metrics,
)
from src.opportunity_models import (
    DIRECTION_NEGATIVE,
    DIRECTION_POSITIVE,
    FAMILY_SEARCH_INTEREST,
    INTEGRATED_MODEL_VERSION,
    INTEGRATED_WEIGHTS,
    READINESS_BLOCKED,
    READINESS_INCOMPLETE_EVIDENCE,
    READINESS_OPERATIONALLY_UNVALIDATED,
    READINESS_READY,
    SEARCH_INTEREST_FAMILY_WEIGHT,
    VALIDATION_COMMERCIAL,
    VALIDATION_OPERATIONAL,
)
from src.risk_analysis import analyze_risk
from src.risk_models import RiskInputs
from src.supplier_analysis import analyze_supplier
from src.supplier_models import SupplierInputs
from src.trend_analysis import analyze_interest_series
from src.trend_models import TrendPoint


# -- Stubs mirroring the real domain result contracts ---------------------


class DemandStub:
    def __init__(self, demand_score=80.0, confidence_score=50.0):
        self.demand_score = demand_score
        self.confidence_score = confidence_score


class TrendStub:
    def __init__(self, provisional_trend_score=70.0, observation_count=52, direction="growing"):
        self.provisional_trend_score = provisional_trend_score
        self.observation_count = observation_count
        self.direction = direction


class CompetitionStub:
    def __init__(self, competition_score=40.0, confidence_score=55.0):
        self.competition_score = competition_score
        self.confidence_score = confidence_score


class MarginStub:
    def __init__(self, margin_score=75.0, cost_completeness_score=62.5):
        self.margin_score = margin_score
        self.cost_completeness_score = cost_completeness_score


class SupplierStub:
    def __init__(
        self,
        supplier_score=82.0,
        evidence_completeness_score=70.0,
        operational_status="VIABLE",
        blockers=None,
        warnings=None,
    ):
        self.supplier_score = supplier_score
        self.evidence_completeness_score = evidence_completeness_score
        self.operational_status = operational_status
        self.blockers = blockers or []
        self.warnings = warnings or []


class LogisticsStub:
    def __init__(
        self,
        logistics_score=90.0,
        evidence_completeness_score=60.0,
        operational_status="EASY",
        blockers=None,
        warnings=None,
    ):
        self.logistics_score = logistics_score
        self.evidence_completeness_score = evidence_completeness_score
        self.operational_status = operational_status
        self.blockers = blockers or []
        self.warnings = warnings or []


class RiskStub:
    def __init__(
        self,
        risk_score=20.0,
        evidence_completeness_score=55.0,
        risk_status="LOW",
        blockers=None,
        warnings=None,
    ):
        self.risk_score = risk_score
        self.evidence_completeness_score = evidence_completeness_score
        self.risk_status = risk_status
        self.blockers = blockers or []
        self.warnings = warnings or []


def compose(**overrides):
    """Compose with every domain available by default, overridable per test."""
    kwargs = dict(
        demand_result=DemandStub(),
        trend_metrics=TrendStub(),
        competition_result=CompetitionStub(),
        margin_result=MarginStub(),
        supplier_result=SupplierStub(),
        logistics_result=LogisticsStub(),
        risk_result=RiskStub(),
    )
    kwargs.update(overrides)
    return compose_opportunity("Test Product", **kwargs)


def component(result, name):
    return next(c for c in result.components if c.name == name)


# -- 1-3. Full availability, strong and weak publishable results ----------


def test_all_intended_components_available_is_ready_and_publishable():
    result = compose()
    assert result.readiness == READINESS_READY
    assert result.publishable is True
    assert result.classification is not None
    assert result.withheld_reason is None
    assert result.missing_components == ()
    assert result.missing_commercial_requirements == ()
    assert result.missing_operational_requirements == ()


def test_strong_publishable_opportunity():
    result = compose(
        demand_result=DemandStub(demand_score=95.0),
        trend_metrics=TrendStub(provisional_trend_score=95.0),
        competition_result=CompetitionStub(competition_score=10.0),
        margin_result=MarginStub(margin_score=95.0),
        supplier_result=SupplierStub(supplier_score=95.0),
        logistics_result=LogisticsStub(logistics_score=95.0),
        risk_result=RiskStub(risk_score=5.0),
    )
    assert result.publishable is True
    assert result.classification == "Strong opportunity"
    assert result.opportunity_score >= 80


def test_weak_publishable_opportunity():
    result = compose(
        demand_result=DemandStub(demand_score=55.0),
        competition_result=CompetitionStub(competition_score=50.0),
        margin_result=MarginStub(margin_score=45.0),
        supplier_result=SupplierStub(supplier_score=50.0),
        logistics_result=LogisticsStub(logistics_score=50.0),
        risk_result=RiskStub(risk_score=50.0),
    )
    assert result.publishable is True
    assert result.classification == "Weak or uncertain opportunity"
    assert 50 <= result.opportunity_score < 65


def test_reject_classification_is_reachable():
    result = compose(
        demand_result=DemandStub(demand_score=10.0),
        competition_result=CompetitionStub(competition_score=95.0),
        margin_result=MarginStub(margin_score=5.0),
        supplier_result=SupplierStub(supplier_score=10.0),
        logistics_result=LogisticsStub(logistics_score=10.0),
        risk_result=RiskStub(risk_score=95.0),
    )
    assert result.publishable is True
    assert result.classification == "Reject"


# -- 4-11. Score direction and inversion ----------------------------------


def test_competition_is_inverted_exactly_once():
    result = compose(competition_result=CompetitionStub(competition_score=40.0))
    comp = component(result, "competition")
    assert comp.direction == DIRECTION_NEGATIVE
    assert comp.raw_score == 40.0
    assert comp.opportunity_score == 60.0


def test_risk_is_inverted_exactly_once():
    result = compose(risk_result=RiskStub(risk_score=30.0))
    risk = component(result, "risk")
    assert risk.direction == DIRECTION_NEGATIVE
    assert risk.raw_score == 30.0
    assert risk.opportunity_score == 70.0


@pytest.mark.parametrize(
    "name, stub_kwargs, raw",
    [
        ("demand", {"demand_result": DemandStub(demand_score=64.0)}, 64.0),
        ("trend", {"trend_metrics": TrendStub(provisional_trend_score=64.0)}, 64.0),
        ("margin", {"margin_result": MarginStub(margin_score=64.0)}, 64.0),
        ("supplier", {"supplier_result": SupplierStub(supplier_score=64.0)}, 64.0),
        ("logistics", {"logistics_result": LogisticsStub(logistics_score=64.0)}, 64.0),
    ],
)
def test_positive_components_are_not_inverted(name, stub_kwargs, raw):
    result = compose(**stub_kwargs)
    comp = component(result, name)
    assert comp.direction == DIRECTION_POSITIVE
    assert comp.raw_score == raw
    assert comp.opportunity_score == raw, f"{name} must not be inverted"


def test_higher_competition_lowers_the_opportunity_score():
    low = compose(competition_result=CompetitionStub(competition_score=10.0))
    high = compose(competition_result=CompetitionStub(competition_score=90.0))
    assert low.opportunity_score > high.opportunity_score


def test_higher_risk_lowers_the_opportunity_score():
    low = compose(risk_result=RiskStub(risk_score=10.0))
    high = compose(risk_result=RiskStub(risk_score=90.0))
    assert low.opportunity_score > high.opportunity_score


def test_no_double_inversion_of_negative_components():
    """A risk of 0 must become 100, not fold back to 0."""
    result = compose(risk_result=RiskStub(risk_score=0.0))
    assert component(result, "risk").opportunity_score == 100.0


# -- 12-13. Weight and contribution arithmetic ----------------------------


def test_weighted_contributions_are_mathematically_correct():
    result = compose()
    expected = {
        "demand": 80.0 * 0.30,
        "competition": (100 - 40.0) * 0.15,
        "margin": 75.0 * 0.20,
        "supplier": 82.0 * 0.12,
        "logistics": 90.0 * 0.08,
        "risk": (100 - 20.0) * 0.15,
    }
    for name, value in expected.items():
        assert component(result, name).weighted_contribution == pytest.approx(
            value, abs=1e-9
        )


def test_contribution_sum_matches_the_aggregate_score():
    result = compose()
    total = sum(
        c.weighted_contribution for c in result.counted_components
    )
    assert result.opportunity_score == pytest.approx(round(total, 2), abs=1e-9)


def test_counted_effective_weights_sum_to_one_when_all_available():
    result = compose()
    assert sum(c.effective_weight for c in result.components) == pytest.approx(
        1.0, abs=1e-9
    )


def test_opportunity_score_stays_within_bounds():
    best = compose(
        demand_result=DemandStub(demand_score=100.0),
        competition_result=CompetitionStub(competition_score=0.0),
        margin_result=MarginStub(margin_score=100.0),
        supplier_result=SupplierStub(supplier_score=100.0),
        logistics_result=LogisticsStub(logistics_score=100.0),
        risk_result=RiskStub(risk_score=0.0),
    )
    worst = compose(
        demand_result=DemandStub(demand_score=0.0),
        competition_result=CompetitionStub(competition_score=100.0),
        margin_result=MarginStub(margin_score=0.0),
        supplier_result=SupplierStub(supplier_score=0.0),
        logistics_result=LogisticsStub(logistics_score=0.0),
        risk_result=RiskStub(risk_score=100.0),
    )
    assert best.opportunity_score == 100.0
    assert worst.opportunity_score == 0.0


# -- 47-48. Evidence overlap / double-counting policy ---------------------


def test_trend_does_not_contribute_weight_when_demand_is_available():
    """The central Phase 11 regression test.

    Demand Analysis already consumes the same Google Trends evidence
    (its largest component is rebuilt from the same interest level and
    direction that dominate the Trend Score). Counting the Trend Score
    as an independent component would reward that evidence twice. If a
    future refactor re-adds Trend as a weighted vote, this fails.
    """
    result = compose()
    trend = component(result, "trend")
    demand = component(result, "demand")

    assert trend.available is True, "the Trend result is still read and reported"
    assert trend.counted is False
    assert trend.effective_weight == 0.0
    assert trend.weighted_contribution is None
    assert trend.overlap_policy == FAMILY_OVERLAP_POLICY
    assert trend.family == FAMILY_SEARCH_INTEREST

    assert demand.counted is True
    assert demand.effective_weight == pytest.approx(
        SEARCH_INTEREST_FAMILY_WEIGHT, abs=1e-9
    )


def test_changing_only_the_trend_score_cannot_move_the_opportunity_score():
    """Direct proof that correlated evidence is not double counted."""
    low_trend = compose(trend_metrics=TrendStub(provisional_trend_score=1.0))
    high_trend = compose(trend_metrics=TrendStub(provisional_trend_score=99.0))
    assert low_trend.opportunity_score == high_trend.opportunity_score


def test_trend_becomes_the_family_representative_when_demand_is_absent():
    """Supplying only Trend must not leave 50% of the weight unearned."""
    result = compose(demand_result=None)
    trend = component(result, "trend")
    demand = component(result, "demand")

    assert trend.counted is True
    assert trend.effective_weight == pytest.approx(
        SEARCH_INTEREST_FAMILY_WEIGHT, abs=1e-9
    )
    assert demand.available is False
    assert demand.effective_weight == 0.0
    assert FAMILY_SEARCH_INTEREST not in result.missing_commercial_requirements


def test_search_interest_family_is_critical_as_a_family():
    """Neither member available => the family is the missing critical."""
    result = compose(demand_result=None, trend_metrics=None)
    assert FAMILY_SEARCH_INTEREST in result.missing_commercial_requirements
    assert result.publishable is False


def test_family_never_contributes_more_than_its_single_weight():
    result = compose()
    family_weight = sum(
        c.effective_weight
        for c in result.components
        if c.family == FAMILY_SEARCH_INTEREST
    )
    assert family_weight == pytest.approx(SEARCH_INTEREST_FAMILY_WEIGHT, abs=1e-9)


def test_logistics_scored_dimensions_never_consume_observed_rates():
    """Logistics/Risk correlated-evidence regression.

    `observed_damage_rate`/`observed_return_rate` exist in BOTH
    LogisticsInputs and RiskInputs. Risk scores them
    (operational_history_risk_score); Logistics must NOT, or the same
    raw observation would move two separately weighted components.
    Logistics may use them only for warnings/status/completeness.
    """
    base = dict(product_name="Widget", weight_kg=Decimal("1"), fragile=False,
                hazardous=False, estimated_delivery_days=5,
                tracking_available=True, insurance_available=True,
                supplier_fulfilled=True)
    without = analyze_logistics(LogisticsInputs(**base))
    with_rates = analyze_logistics(
        LogisticsInputs(
            **base,
            observed_damage_rate=Decimal("0.4"),
            observed_return_rate=Decimal("0.4"),
        )
    )
    # The five scored dimensions must be byte-identical.
    for attribute in (
        "physical_ease_score",
        "handling_ease_score",
        "delivery_convenience_score",
        "fulfillment_support_score",
        "shipping_support_score",
    ):
        assert getattr(without, attribute) == getattr(with_rates, attribute)


def test_risk_does_score_observed_rates_so_the_evidence_is_counted_once():
    """The other half of the Logistics/Risk policy: Risk is the one
    domain that turns those observed rates into a score."""
    base = dict(
        product_name="Widget",
        supplier_count=3,
        primary_supplier_dependency_percent=Decimal("0.4"),
        regulatory_uncertainty=False,
        brand_ip_uncertainty=False,
    )
    low = analyze_risk(RiskInputs(**base, observed_return_rate=Decimal("0.01")))
    high = analyze_risk(RiskInputs(**base, observed_return_rate=Decimal("0.6")))
    assert high.risk_score > low.risk_score


def test_supplier_and_risk_components_are_independently_weighted():
    """Supplier/Risk overlap is category 2 (distinct), so both vote."""
    result = compose()
    assert component(result, "supplier").effective_weight > 0
    assert component(result, "risk").effective_weight > 0


# -- 8, 14-23. Missing components and the false-safety guard --------------


def test_missing_margin_cannot_produce_a_strong_opportunity():
    """The worked example from the Phase 11 brief."""
    result = compose(
        demand_result=DemandStub(demand_score=90.0),
        trend_metrics=TrendStub(provisional_trend_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        margin_result=None,
    )
    assert "margin" in result.missing_commercial_requirements
    assert result.publishable is False
    assert result.classification is None
    assert result.readiness == READINESS_INCOMPLETE_EVIDENCE
    assert result.opportunity_score is not None, "partial score still shown"
    assert result.score_is_partial is True


def test_margin_withheld_by_its_own_threshold_is_treated_as_missing():
    """A domain that withheld its score must not be silently defaulted."""
    result = compose(margin_result=MarginStub(margin_score=None, cost_completeness_score=25.0))
    margin = component(result, "margin")
    assert margin.available is False
    assert margin.raw_score is None
    assert margin.opportunity_score is None
    assert margin.weighted_contribution is None
    assert margin.withheld_reason is not None
    assert result.publishable is False
    # The domain's own evidence metric is still preserved.
    assert result.evidence_profile.margin_cost_completeness == 25.0


def test_missing_risk_does_not_create_false_safety():
    """Removing Risk must never make the result look MORE validated."""
    with_risk = compose(
        demand_result=DemandStub(demand_score=90.0),
        competition_result=CompetitionStub(competition_score=10.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        risk_result=RiskStub(risk_score=60.0),
    )
    without_risk = compose(
        demand_result=DemandStub(demand_score=90.0),
        competition_result=CompetitionStub(competition_score=10.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        risk_result=None,
    )
    # Gate: unknown risk is never publishable, however good the rest is.
    assert with_risk.publishable is True
    assert without_risk.publishable is False
    assert without_risk.classification is None
    assert "risk" in without_risk.missing_commercial_requirements
    # Ceiling: the score must not be inflated by the missing negative.
    assert without_risk.false_safety_ceiling_applied is True


def test_false_safety_ceiling_beats_naive_renormalization():
    """Naive renormalization would return the all-positive average."""
    result = compose(
        demand_result=DemandStub(demand_score=90.0),
        competition_result=CompetitionStub(competition_score=10.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        risk_result=None,
    )
    naive = 90.0  # every available component is 90 opportunity-oriented
    assert result.opportunity_score < naive
    assert result.false_safety_ceiling_applied is True


def test_missing_competition_does_not_create_false_safety():
    result = compose(
        demand_result=DemandStub(demand_score=90.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        risk_result=RiskStub(risk_score=10.0),
        competition_result=None,
    )
    assert result.publishable is False
    assert "competition" in result.missing_commercial_requirements
    assert result.false_safety_ceiling_applied is True
    assert result.opportunity_score < 90.0


def test_false_safety_ceiling_does_not_invent_bad_news_for_weak_evidence():
    """`min()` means the guard can only lower an inflated score.

    When the known evidence is already weak, a missing negative
    dimension must not be turned into fabricated bad news either.
    """
    result = compose(
        demand_result=DemandStub(demand_score=20.0),
        competition_result=CompetitionStub(competition_score=80.0),
        margin_result=MarginStub(margin_score=20.0),
        supplier_result=SupplierStub(supplier_score=20.0),
        logistics_result=LogisticsStub(logistics_score=20.0),
        risk_result=None,
    )
    assert result.false_safety_ceiling_applied is False
    assert result.opportunity_score == pytest.approx(20.0, abs=1e-9)


def test_missing_negative_score_never_exceeds_the_neutral_case():
    """Formal statement of the ceiling guarantee."""
    unknown_risk = compose(
        demand_result=DemandStub(demand_score=100.0),
        competition_result=CompetitionStub(competition_score=0.0),
        margin_result=MarginStub(margin_score=100.0),
        supplier_result=SupplierStub(supplier_score=100.0),
        logistics_result=LogisticsStub(logistics_score=100.0),
        risk_result=None,
    )
    neutral_risk = compose(
        demand_result=DemandStub(demand_score=100.0),
        competition_result=CompetitionStub(competition_score=0.0),
        margin_result=MarginStub(margin_score=100.0),
        supplier_result=SupplierStub(supplier_score=100.0),
        logistics_result=LogisticsStub(logistics_score=100.0),
        risk_result=RiskStub(risk_score=50.0),
    )
    assert unknown_risk.opportunity_score <= neutral_risk.opportunity_score


def test_missing_demand_family_withholds_the_recommendation():
    result = compose(demand_result=None, trend_metrics=None)
    assert result.publishable is False
    assert result.readiness == READINESS_INCOMPLETE_EVIDENCE
    assert FAMILY_SEARCH_INTEREST in result.missing_commercial_requirements


def test_missing_operational_components_are_no_longer_simply_optional():
    """HARDENED: Supplier/Logistics missing is its own readiness state.

    An earlier draft treated them as plain non-critical components, so
    a result with no sourcing or shipping evidence at all could still
    be stamped READY with a final classification. That let a
    commercially attractive but operationally unverified product
    masquerade as fully validated.
    """
    result = compose(supplier_result=None, logistics_result=None)
    assert result.readiness == READINESS_OPERATIONALLY_UNVALIDATED
    assert result.publishable is False
    assert result.classification is None
    assert result.commercial_validation_complete is True
    assert result.operational_validation_complete is False
    assert result.missing_commercial_requirements == ()
    assert result.missing_operational_requirements == ("supplier", "logistics")
    assert "supplier" in result.missing_components
    assert "logistics" in result.missing_components
    assert result.score_is_partial is True


def test_no_component_available_at_all_yields_no_score():
    result = compose_opportunity("Nothing Known")
    assert result.opportunity_score is None
    assert result.classification is None
    assert result.publishable is False
    assert result.component_coverage == 0.0


@pytest.mark.parametrize(
    "name, kwargs",
    [
        ("demand", {"demand_result": DemandStub(demand_score=None)}),
        ("competition", {"competition_result": CompetitionStub(competition_score=None)}),
        ("margin", {"margin_result": MarginStub(margin_score=None)}),
        ("supplier", {"supplier_result": SupplierStub(supplier_score=None)}),
        ("logistics", {"logistics_result": LogisticsStub(logistics_score=None)}),
        ("risk", {"risk_result": RiskStub(risk_score=None)}),
    ],
)
def test_none_never_becomes_zero_or_fifty(name, kwargs):
    result = compose(**kwargs)
    comp = component(result, name)
    assert comp.raw_score is None
    assert comp.opportunity_score is None
    assert comp.weighted_contribution is None
    assert comp.available is False
    assert comp.effective_weight == 0.0


def test_unknown_risk_is_not_reported_as_a_safe_status():
    result = compose(risk_result=None)
    risk = component(result, "risk")
    assert risk.source_status is None
    assert risk.raw_score is None
    assert result.evidence_profile.risk_evidence_completeness is None


# -- 11, 17-19. Coverage -------------------------------------------------


def test_component_coverage_is_the_known_share_of_configured_weight():
    result = compose(supplier_result=None, logistics_result=None)
    # 1.00 - 0.12 (supplier) - 0.08 (logistics) = 0.80
    assert result.component_coverage == pytest.approx(80.0, abs=1e-9)


def test_component_coverage_worked_example():
    """Demand + Margin known, everything else missing."""
    result = compose(
        competition_result=None,
        supplier_result=None,
        logistics_result=None,
        risk_result=None,
    )
    # 0.30 (search-interest family) + 0.20 (margin) = 0.50
    assert result.component_coverage == pytest.approx(50.0, abs=1e-9)


def test_full_coverage_is_one_hundred_percent():
    assert compose().component_coverage == pytest.approx(100.0, abs=1e-9)


def test_coverage_is_unaffected_by_which_family_member_represents_it():
    """Coverage must be comparable across runs."""
    with_demand = compose()
    with_trend_only = compose(demand_result=None)
    assert with_demand.component_coverage == with_trend_only.component_coverage


def test_coverage_is_never_called_confidence():
    """Coverage is not confidence, completeness or accuracy.

    The result must not carry a top-level confidence field at all --
    confidence belongs to individual domains, under their own names, in
    `evidence_profile`.
    """
    result = compose()
    fields = set(result.__dict__)
    assert "component_coverage" in fields
    for forbidden in (
        "confidence",
        "confidence_score",
        "overall_confidence",
        "completeness",
        "accuracy",
    ):
        assert forbidden not in fields


def test_partial_score_note_spells_out_what_coverage_is_not():
    """When a partial score is reported, the caveat must travel with it."""
    result = compose(supplier_result=None)
    assert result.score_is_partial is True
    partial_notes = [
        n for n in result.notes if "partial analytical score" in n.lower()
    ]
    assert partial_notes, "a partial score must carry an explanatory note"
    note = partial_notes[0].lower()
    assert "not confidence" in note
    assert "not evidence completeness" in note
    assert "not accuracy" in note


# -- 24-26. Partial-score semantics --------------------------------------


def test_partial_score_is_labelled_partial():
    result = compose(supplier_result=None)
    assert result.score_is_partial is True
    assert result.opportunity_score is not None


def test_full_score_is_not_labelled_partial():
    assert compose().score_is_partial is False


def test_partial_score_with_missing_critical_cannot_get_a_strong_label():
    result = compose(
        demand_result=DemandStub(demand_score=100.0),
        trend_metrics=TrendStub(provisional_trend_score=100.0),
        competition_result=CompetitionStub(competition_score=0.0),
        supplier_result=SupplierStub(supplier_score=100.0),
        logistics_result=LogisticsStub(logistics_score=100.0),
        risk_result=RiskStub(risk_score=0.0),
        margin_result=None,
    )
    assert result.opportunity_score >= 80
    assert result.classification is None, "a high partial score must not be labelled"
    assert result.publishable is False
    assert result.withheld_reason is not None


def test_classification_is_withheld_with_an_explicit_reason():
    result = compose(margin_result=None)
    assert result.classification is None
    assert "margin" in result.withheld_reason


# -- 27-30, 49. Blocker and warning propagation --------------------------


def test_supplier_blocker_propagates_and_overrides_publishability():
    result = compose(
        demand_result=DemandStub(demand_score=95.0),
        trend_metrics=TrendStub(provisional_trend_score=90.0),
        competition_result=CompetitionStub(competition_score=5.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(
            supplier_score=82.0,
            operational_status="BLOCKED",
            blockers=["no stock available (stock_quantity = 0)"],
        ),
        logistics_result=LogisticsStub(logistics_score=95.0),
        risk_result=RiskStub(risk_score=5.0),
    )
    assert result.readiness == READINESS_BLOCKED
    assert result.publishable is False
    assert result.classification is None


def test_blocker_is_not_hidden_inside_the_weighted_average():
    """The score is still computed and shown; the RECOMMENDATION is withheld."""
    result = compose(
        demand_result=DemandStub(demand_score=95.0),
        margin_result=MarginStub(margin_score=90.0),
        competition_result=CompetitionStub(competition_score=5.0),
        risk_result=RiskStub(risk_score=5.0),
        supplier_result=SupplierStub(
            supplier_score=82.0, blockers=["stock_quantity (2) is below moq_units (10)"]
        ),
    )
    assert result.opportunity_score is not None
    assert result.opportunity_score >= 80, "the arithmetic is not suppressed"
    assert result.classification is None, "but no recommendation is issued"
    assert "Supplier Analysis (Phase 8)" in result.domain_blockers
    assert "below moq_units" in result.withheld_reason


def test_blocker_takes_precedence_over_missing_critical_evidence():
    result = compose(
        margin_result=None,
        supplier_result=SupplierStub(blockers=["no stock available"]),
    )
    assert result.readiness == READINESS_BLOCKED


def test_blockers_are_namespaced_by_originating_domain():
    result = compose(
        supplier_result=SupplierStub(blockers=["supplier blocker"]),
        logistics_result=LogisticsStub(blockers=["logistics blocker"]),
    )
    assert result.domain_blockers["Supplier Analysis (Phase 8)"] == ["supplier blocker"]
    assert result.domain_blockers["Logistics Analysis (Phase 9)"] == [
        "logistics blocker"
    ]


def test_warnings_are_preserved_and_namespaced():
    result = compose(
        supplier_result=SupplierStub(warnings=["MOQ is high"]),
        logistics_result=LogisticsStub(warnings=["dimensional weight exceeds actual"]),
        risk_result=RiskStub(warnings=["a prior recall is on record"]),
    )
    assert result.domain_warnings["Supplier Analysis (Phase 8)"] == ["MOQ is high"]
    assert result.domain_warnings["Logistics Analysis (Phase 9)"] == [
        "dimensional weight exceeds actual"
    ]
    assert result.domain_warnings["Risk Analysis (Phase 10)"] == [
        "a prior recall is on record"
    ]


def test_warnings_do_not_block_publishability():
    """A warning is severity, not impossibility."""
    result = compose(risk_result=RiskStub(warnings=["observed return rate is 0.6"]))
    assert result.publishable is True
    assert result.domain_warnings


def test_domains_without_blockers_are_absent_from_the_namespace():
    result = compose()
    assert result.domain_blockers == {}


# -- 31-34. Evidence profile ---------------------------------------------


def test_evidence_profile_preserves_every_domain_metric():
    result = compose()
    profile = result.evidence_profile
    assert profile.demand_confidence == 50.0
    assert profile.competition_confidence == 55.0
    assert profile.margin_cost_completeness == 62.5
    assert profile.supplier_evidence_completeness == 70.0
    assert profile.logistics_evidence_completeness == 60.0
    assert profile.risk_evidence_completeness == 55.0
    assert profile.trend_observation_count == 52
    assert profile.trend_direction == "growing"


def test_demand_confidence_stays_demand_confidence():
    result = compose(demand_result=DemandStub(confidence_score=37.5))
    assert result.evidence_profile.demand_confidence == 37.5
    assert component(result, "demand").evidence_label == "demand confidence"


def test_margin_cost_completeness_stays_cost_completeness():
    result = compose(margin_result=MarginStub(cost_completeness_score=87.5))
    assert result.evidence_profile.margin_cost_completeness == 87.5
    assert component(result, "margin").evidence_label == "margin cost completeness"


def test_evidence_metrics_are_not_averaged_into_the_score():
    """Evidence quality must not leak into the score itself."""
    low_evidence = compose(demand_result=DemandStub(demand_score=80.0, confidence_score=1.0))
    high_evidence = compose(demand_result=DemandStub(demand_score=80.0, confidence_score=99.0))
    assert low_evidence.opportunity_score == high_evidence.opportunity_score


def test_component_availability_differs_from_domain_evidence_completeness():
    """A domain can be rich in metadata yet still withhold its score.

    This is the Supplier/Logistics lesson: generic field completeness
    must not create an illusion of scoring coverage.
    """
    result = compose(
        logistics_result=LogisticsStub(
            logistics_score=None, evidence_completeness_score=38.0
        )
    )
    assert result.evidence_profile.logistics_evidence_completeness == 38.0
    assert component(result, "logistics").available is False
    assert component(result, "logistics").effective_weight == 0.0


# -- 25, 50. Provisional-heuristic language -------------------------------


def test_result_states_the_score_is_a_provisional_heuristic():
    result = compose()
    joined = " ".join(result.notes).lower()
    assert "provisional" in joined
    assert "heuristic" in joined


def test_result_never_describes_the_score_as_a_probability():
    """Probability language may appear ONLY inside an explicit denial.

    Checking for bare substrings would flag the disclaimer itself
    ("is NOT a probability of selling"), so the rule asserted here is
    the meaningful one: any note mentioning probability/chance/
    likelihood must also negate it.
    """
    result = compose()
    joined = " ".join(result.notes).lower()
    assert "not a probability" in joined

    probability_words = ("probability", "chance", "likelihood", "odds")
    for note in result.notes:
        lowered = note.lower()
        if any(word in lowered for word in probability_words):
            assert "not" in lowered or "never" in lowered, (
                f"note mentions probability without denying it: {note!r}"
            )


def test_no_probability_field_exists_on_the_result():
    result = compose()
    fields = set(result.__dict__)
    for forbidden in (
        "probability",
        "success_probability",
        "chance_of_success",
        "sales_probability",
    ):
        assert forbidden not in fields


# -- 25, 26. Provenance and model version ---------------------------------


def test_every_component_carries_its_originating_domain():
    result = compose()
    for comp in result.components:
        assert comp.source_domain
        assert "Phase" in comp.source_domain


def test_provenance_answers_where_a_component_came_from():
    result = compose()
    demand = component(result, "demand")
    assert demand.source_domain == "Demand Analysis (Phase 5)"
    assert demand.evidence_label == "demand confidence"
    assert demand.evidence_value == 50.0


def test_domain_statuses_are_carried_across_without_renaming():
    result = compose(
        supplier_result=SupplierStub(operational_status="CAUTION"),
        logistics_result=LogisticsStub(operational_status="MANAGEABLE"),
        risk_result=RiskStub(risk_status="MODERATE"),
    )
    assert component(result, "supplier").source_status == "CAUTION"
    assert component(result, "logistics").source_status == "MANAGEABLE"
    assert component(result, "risk").source_status == "MODERATE"


def test_readiness_is_not_the_same_vocabulary_as_a_domain_status():
    result = compose(
        supplier_result=SupplierStub(operational_status="VIABLE"),
        risk_result=RiskStub(risk_status="LOW"),
    )
    assert result.readiness == READINESS_READY
    assert result.readiness not in {"VIABLE", "LOW", "EASY", "MANAGEABLE", "CAUTION"}


def test_model_version_is_recorded():
    assert compose().model_version == INTEGRATED_MODEL_VERSION


# -- 37-38. Determinism ---------------------------------------------------


def test_composition_is_deterministic():
    first = compose()
    second = compose()
    assert first == second


def test_identical_input_produces_identical_output_repeatedly():
    demand = DemandStub()
    margin = MarginStub()
    runs = {
        compose_opportunity(
            "Stable", demand_result=demand, margin_result=margin
        ).opportunity_score
        for _ in range(5)
    }
    assert len(runs) == 1


def test_product_name_must_not_be_empty():
    with pytest.raises(ValueError):
        compose_opportunity("   ")


# -- 44-46. Architectural boundaries --------------------------------------


def _imported_modules(module):
    """Every module name imported by `module`, parsed from its AST.

    AST parsing rather than substring matching, so a forbidden import
    cannot hide behind formatting and a mention inside a docstring
    cannot produce a false positive.
    """
    import ast

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
    return names


def test_canonical_contract_depends_only_on_the_standard_library():
    import src.opportunity_models as models

    assert _imported_modules(models) == {"dataclasses"}


def test_composition_engine_depends_only_on_the_canonical_contract():
    """No providers, no HTTP, no LLM, no database -- and no domain modules.

    The engine is coupled to the canonical component contract alone, so
    a domain's internal formulas can change without touching it.
    """
    import src.opportunity_integration as engine

    assert _imported_modules(engine) == {"src.opportunity_models"}


def test_no_domain_module_imports_the_opportunity_layer():
    """Layering must stay one-directional (no cycles, no coupling).

    Domains must remain independently testable and must never gain a
    dependency on how their output is later composed.
    """
    import pathlib

    for path in sorted(pathlib.Path("src").rglob("*.py")):
        if path.name.startswith("opportunity_") or path.name == "main.py":
            continue
        source = path.read_text(encoding="utf-8")
        assert "opportunity_models" not in source, path
        assert "opportunity_integration" not in source, path


def test_adapters_do_not_mutate_the_domain_result():
    supplier = SupplierStub(supplier_score=70.0, warnings=["w"])
    before = dict(supplier.__dict__)
    from_supplier_result(supplier)
    assert supplier.__dict__ == before


# -- Adapters against REAL domain results ---------------------------------


def test_adapter_reads_a_real_demand_result():
    points = [TrendPoint(date=f"d{i}", value=v, formatted_value=None)
              for i, v in enumerate([10, 20, 30, 40, 50, 60])]
    metrics = analyze_interest_series(points)
    signals = build_demand_signals("fone bluetooth", "BR", trend_metrics=metrics)
    result = analyze_demand(signals)

    comp = from_demand_result(result)
    assert comp.name == "demand"
    assert comp.direction == DIRECTION_POSITIVE
    assert comp.raw_score == result.demand_score
    assert comp.evidence_value == result.confidence_score


def test_adapter_reads_a_real_trend_result():
    points = [TrendPoint(date=f"d{i}", value=v, formatted_value=None)
              for i, v in enumerate([10, 20, 30, 40])]
    metrics = analyze_interest_series(points)

    comp = from_trend_metrics(metrics)
    assert comp.raw_score == metrics.provisional_trend_score
    assert comp.evidence_value == float(metrics.observation_count)
    assert comp.source_status == metrics.direction


def test_adapter_reads_a_real_trend_result_that_withheld_its_score():
    metrics = analyze_interest_series([])
    comp = from_trend_metrics(metrics)
    assert comp.available is False
    assert comp.raw_score is None
    assert comp.withheld_reason is not None


class _Item:
    def __init__(self, item_id, title, price, seller_id, free_shipping, condition):
        self.item_id = item_id
        self.title = title
        self.price = price
        self.seller_id = seller_id
        self.free_shipping = free_shipping
        self.condition = condition


def test_adapter_reads_a_real_competition_result_and_inverts_it():
    items = [
        _Item("1", "Fone A", 100.0, 1, True, "new"),
        _Item("2", "Fone B", 105.0, 1, True, "new"),
        _Item("3", "Fone C", 98.0, 2, False, "new"),
    ]
    signals = build_competition_signals("fone", marketplace_items=items)
    result = analyze_competition(signals, requested_limit=3)

    comp = from_competition_result(result)
    assert comp.direction == DIRECTION_NEGATIVE
    assert comp.raw_score == result.competition_score
    assert comp.opportunity_score == pytest.approx(
        100 - result.competition_score, abs=1e-9
    )


def test_adapter_reads_a_real_margin_result():
    inputs = MarginInputs(
        product_name="Fone",
        sale_price=Decimal("100"),
        product_cost=Decimal("40"),
        marketplace_fee_rate=Decimal("0.12"),
        seller_shipping_cost=Decimal("10"),
        packaging_cost=Decimal("2"),
        tax_rate=Decimal("0.08"),
    )
    result = analyze_margin(inputs)

    comp = from_margin_result(result)
    assert comp.raw_score == result.margin_score
    assert comp.evidence_value == result.cost_completeness_score
    assert comp.direction == DIRECTION_POSITIVE


def test_adapter_reads_a_real_supplier_result_with_a_real_blocker():
    inputs = SupplierInputs(
        product_name="Fone",
        supplier_name="Distribuidora X",
        moq_units=10,
        stock_quantity=2,
        dropshipping_supported=True,
        invoice_available=True,
        lead_time_days=7,
    )
    result = analyze_supplier(inputs)
    assert result.blockers, "fixture must actually trigger a real blocker"

    composed = compose_opportunity("Fone", supplier_result=result)
    assert composed.readiness == READINESS_BLOCKED
    assert composed.domain_blockers["Supplier Analysis (Phase 8)"] == result.blockers


def test_adapter_reads_a_real_logistics_result_without_inverting_it():
    inputs = LogisticsInputs(
        product_name="Fone",
        weight_kg=Decimal("0.3"),
        length_cm=Decimal("10"),
        width_cm=Decimal("8"),
        height_cm=Decimal("5"),
        fragile=False,
        hazardous=False,
        estimated_delivery_days=4,
        tracking_available=True,
        insurance_available=True,
        supplier_fulfilled=True,
    )
    result = analyze_logistics(inputs)

    comp = from_logistics_result(result)
    assert comp.direction == DIRECTION_POSITIVE
    assert comp.raw_score == result.logistics_score
    assert comp.opportunity_score == result.logistics_score, "ease is already high-is-good"


def test_adapter_reads_a_real_risk_result_and_inverts_it_once():
    inputs = RiskInputs(
        product_name="Fone",
        supplier_count=1,
        primary_supplier_dependency_percent=Decimal("1"),
        platform_dependency_percent=Decimal("0.9"),
        regulatory_uncertainty=False,
        brand_ip_uncertainty=False,
        recall_history_present=False,
    )
    result = analyze_risk(inputs)

    comp = from_risk_result(result)
    assert comp.direction == DIRECTION_NEGATIVE
    assert comp.raw_score == result.risk_score
    assert comp.opportunity_score == pytest.approx(100 - result.risk_score, abs=1e-9)
    assert comp.source_status == result.risk_status


def test_end_to_end_composition_over_real_domain_results():
    """All seven real engines composed once, proving the whole contract."""
    points = [TrendPoint(date=f"d{i}", value=v, formatted_value=None)
              for i, v in enumerate([20, 25, 30, 45, 55, 70])]
    metrics = analyze_interest_series(points)
    demand = analyze_demand(
        build_demand_signals("fone bluetooth", "BR", trend_metrics=metrics)
    )
    items = [
        _Item("1", "Fone A", 100.0, 1, True, "new"),
        _Item("2", "Fone B", 150.0, 2, False, "new"),
        _Item("3", "Fone C", 90.0, 3, True, "new"),
    ]
    competition = analyze_competition(
        build_competition_signals("fone", marketplace_items=items), requested_limit=3
    )
    margin = analyze_margin(
        MarginInputs(
            product_name="Fone",
            sale_price=Decimal("120"),
            product_cost=Decimal("45"),
            marketplace_fee_rate=Decimal("0.12"),
            seller_shipping_cost=Decimal("12"),
            packaging_cost=Decimal("2"),
            tax_rate=Decimal("0.08"),
        )
    )
    supplier = analyze_supplier(
        SupplierInputs(
            product_name="Fone",
            supplier_name="Distribuidora X",
            moq_units=5,
            stock_quantity=400,
            lead_time_days=8,
            dropshipping_supported=True,
            invoice_available=True,
            business_verified=True,
            tracking_available=True,
        )
    )
    logistics = analyze_logistics(
        LogisticsInputs(
            product_name="Fone",
            weight_kg=Decimal("0.3"),
            length_cm=Decimal("12"),
            width_cm=Decimal("9"),
            height_cm=Decimal("5"),
            fragile=False,
            hazardous=False,
            estimated_delivery_days=5,
            tracking_available=True,
            insurance_available=True,
            supplier_fulfilled=True,
        )
    )
    risk = analyze_risk(
        RiskInputs(
            product_name="Fone",
            supplier_count=3,
            primary_supplier_dependency_percent=Decimal("0.5"),
            platform_dependency_percent=Decimal("0.8"),
            historical_stockout_rate=Decimal("0.05"),
            observed_return_rate=Decimal("0.04"),
            regulatory_uncertainty=False,
            brand_ip_uncertainty=False,
            recall_history_present=False,
        )
    )

    result = compose_opportunity(
        "Fone Bluetooth",
        demand_result=demand,
        trend_metrics=metrics,
        competition_result=competition,
        margin_result=margin,
        supplier_result=supplier,
        logistics_result=logistics,
        risk_result=risk,
    )

    assert result.model_version == INTEGRATED_MODEL_VERSION
    assert result.component_coverage == pytest.approx(100.0, abs=1e-9)
    assert result.readiness == READINESS_READY
    assert result.publishable is True
    assert result.classification is not None
    assert 0 <= result.opportunity_score <= 100
    # Trend still reported, still not double counted.
    assert component(result, "trend").available is True
    assert component(result, "trend").effective_weight == 0.0
    # Every evidence metric preserved under its own name.
    profile = result.evidence_profile
    assert profile.demand_confidence == demand.confidence_score
    assert profile.margin_cost_completeness == margin.cost_completeness_score
    assert profile.risk_evidence_completeness == risk.evidence_completeness_score


# ==========================================================================
# HARDENING PASS: commercial vs operational validation, readiness states
# ==========================================================================


def test_supplier_missing_is_operationally_unvalidated():
    """Matrix 28 / spec 11: no invented Supplier score, no READY stamp."""
    result = compose(supplier_result=None)

    assert result.readiness == READINESS_OPERATIONALLY_UNVALIDATED
    assert result.commercial_validation_complete is True
    assert result.operational_validation_complete is False
    assert result.missing_operational_requirements == ("supplier",)
    assert result.publishable is False
    assert result.classification is None

    supplier = component(result, "supplier")
    assert supplier.available is False
    assert supplier.raw_score is None
    assert supplier.opportunity_score is None
    assert supplier.weighted_contribution is None
    assert supplier.effective_weight == 0.0
    # Analytical score survives for transparency.
    assert result.opportunity_score is not None
    # Coverage reflects exactly the missing supplier weight.
    assert result.component_coverage == pytest.approx(88.0, abs=1e-9)


def test_logistics_missing_is_operationally_unvalidated():
    """Matrix 29 / spec 12."""
    result = compose(logistics_result=None)

    assert result.readiness == READINESS_OPERATIONALLY_UNVALIDATED
    assert result.commercial_validation_complete is True
    assert result.operational_validation_complete is False
    assert result.missing_operational_requirements == ("logistics",)
    assert result.classification is None

    logistics = component(result, "logistics")
    assert logistics.available is False
    assert logistics.raw_score is None
    assert logistics.effective_weight == 0.0
    assert result.opportunity_score is not None
    assert result.component_coverage == pytest.approx(92.0, abs=1e-9)


def test_both_operational_components_missing_is_not_ready():
    """Matrix 30 / spec 13: the explicit regression scenario."""
    result = compose(supplier_result=None, logistics_result=None)

    assert result.readiness == READINESS_OPERATIONALLY_UNVALIDATED
    assert result.readiness != READINESS_READY
    assert result.readiness != READINESS_INCOMPLETE_EVIDENCE
    assert result.commercial_validation_complete is True
    assert result.operational_validation_complete is False
    assert result.operational_coverage == pytest.approx(0.0, abs=1e-9)
    assert result.commercial_coverage == pytest.approx(100.0, abs=1e-9)
    assert result.component_coverage == pytest.approx(80.0, abs=1e-9)


def test_commercially_attractive_but_operationally_unvalidated_is_not_strong():
    """Matrix 37 / spec 5: the worked example from the brief.

    Demand strong, Competition acceptable, Margin strong, Risk low --
    but nobody checked sourcing or shipping. This must NOT read as a
    fully validated "Strong Opportunity".
    """
    result = compose(
        demand_result=DemandStub(demand_score=95.0),
        competition_result=CompetitionStub(competition_score=10.0),
        margin_result=MarginStub(margin_score=95.0),
        risk_result=RiskStub(risk_score=5.0),
        supplier_result=None,
        logistics_result=None,
    )

    assert result.opportunity_score >= 80, "the commercial arithmetic is strong"
    assert result.readiness == READINESS_OPERATIONALLY_UNVALIDATED
    assert result.publishable is False
    assert result.classification is None, "no final Strong opportunity stamp"
    # The non-final band explains the commercial case without approving it.
    assert result.analytical_band_non_final == "Strong opportunity"
    assert "operational" in result.withheld_reason.lower()


@pytest.mark.parametrize(
    "missing, expected_key",
    [
        ({"margin_result": None}, "margin"),
        ({"risk_result": None}, "risk"),
        ({"competition_result": None}, "competition"),
        ({"demand_result": None, "trend_metrics": None}, FAMILY_SEARCH_INTEREST),
    ],
)
def test_missing_commercial_requirement_is_incomplete_evidence(missing, expected_key):
    """Matrix 31-34 / spec 14: NOT OPERATIONALLY_UNVALIDATED.

    The business case itself cannot be evaluated, which is a different
    and more fundamental gap than unverified execution.
    """
    result = compose(**missing)

    assert result.readiness == READINESS_INCOMPLETE_EVIDENCE
    assert result.readiness != READINESS_OPERATIONALLY_UNVALIDATED
    assert result.commercial_validation_complete is False
    assert expected_key in result.missing_commercial_requirements
    assert result.classification is None
    assert result.publishable is False
    # No band offered: the commercial case is not evaluable.
    assert result.analytical_band_non_final is None


def test_commercial_gap_outranks_operational_gap():
    """Precedence: an unevaluable business case makes execution moot."""
    result = compose(margin_result=None, supplier_result=None, logistics_result=None)
    assert result.readiness == READINESS_INCOMPLETE_EVIDENCE
    assert result.commercial_validation_complete is False
    assert result.operational_validation_complete is False


def test_blocker_outranks_every_evidence_gap():
    """Matrix 35 / spec 7: blockers have highest readiness precedence."""
    result = compose(
        margin_result=None,
        logistics_result=None,
        supplier_result=SupplierStub(blockers=["no stock available"]),
    )
    assert result.readiness == READINESS_BLOCKED
    assert result.publishable is False
    assert result.classification is None
    assert result.analytical_band_non_final is None


def test_incomplete_commercial_evidence_keeps_an_explicit_partial_score():
    """Matrix 42: useful information is shown, never disguised as final."""
    result = compose(margin_result=None)
    assert result.opportunity_score is not None
    assert result.score_is_partial is True
    assert result.classification is None
    assert "must NOT be read as a validated recommendation" in result.withheld_reason


def test_analytical_band_is_only_offered_for_operationally_unvalidated():
    """The band is meaningful only where the commercial case is complete."""
    assert compose().analytical_band_non_final is None, "READY uses classification"
    assert compose(supplier_result=None).analytical_band_non_final is not None
    assert compose(margin_result=None).analytical_band_non_final is None
    assert (
        compose(
            supplier_result=SupplierStub(blockers=["no stock"])
        ).analytical_band_non_final
        is None
    )


def test_analytical_band_is_labelled_non_final_in_the_notes():
    result = compose(supplier_result=None)
    joined = " ".join(result.notes)
    assert "NON-FINAL" in joined
    assert "not a recommendation" in joined


def test_validation_layers_are_reported_on_every_component():
    """Matrix 46: users can tell which question each component answers."""
    result = compose()
    layers = {c.name: c.validation_layer for c in result.components}
    assert layers["demand"] == VALIDATION_COMMERCIAL
    assert layers["trend"] == VALIDATION_COMMERCIAL
    assert layers["competition"] == VALIDATION_COMMERCIAL
    assert layers["margin"] == VALIDATION_COMMERCIAL
    assert layers["risk"] == VALIDATION_COMMERCIAL
    assert layers["supplier"] == VALIDATION_OPERATIONAL
    assert layers["logistics"] == VALIDATION_OPERATIONAL


def test_layer_coverages_are_reported_separately():
    """Spec 8: the economic-case question vs the execution question."""
    result = compose(supplier_result=None)
    assert result.commercial_coverage == pytest.approx(100.0, abs=1e-9)
    # Logistics 0.08 of the 0.20 operational layer = 40%.
    assert result.operational_coverage == pytest.approx(40.0, abs=1e-9)


def test_commercial_coverage_reflects_a_missing_commercial_component():
    result = compose(margin_result=None)
    # 0.80 - 0.20 margin = 0.60 of the 0.80 commercial layer = 75%.
    assert result.commercial_coverage == pytest.approx(75.0, abs=1e-9)
    assert result.operational_coverage == pytest.approx(100.0, abs=1e-9)


def test_operational_validation_is_not_mislabelled_commercial():
    """The two booleans must move independently."""
    operational_gap = compose(supplier_result=None)
    commercial_gap = compose(risk_result=None)

    assert operational_gap.commercial_validation_complete is True
    assert operational_gap.operational_validation_complete is False

    assert commercial_gap.commercial_validation_complete is False
    assert commercial_gap.operational_validation_complete is True


def test_false_safety_guard_still_correct_under_hardened_weights():
    """Spec 15: re-verified after Risk rose from 0.05 to 0.15.

    The larger negative weight makes the ceiling bind HARDER, so the
    mechanism is strictly more protective than before, with no formula
    change. Verified against the arithmetic by hand.
    """
    result = compose(
        demand_result=DemandStub(demand_score=90.0),
        competition_result=CompetitionStub(competition_score=10.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        risk_result=None,
    )
    # Every available component is 90 opportunity-oriented, earning 0.85.
    numerator = 90.0 * 0.85
    naive = 90.0
    expected_ceiling = (numerator + 0.15 * 50.0) / 1.0

    assert result.false_safety_ceiling_applied is True
    assert result.opportunity_score == pytest.approx(expected_ceiling, abs=0.01)
    assert result.opportunity_score < naive
    assert expected_ceiling == pytest.approx(84.0, abs=1e-9)


def test_hardened_weights_make_the_ceiling_stricter_than_the_old_draft():
    """The 0.05-risk draft capped at 88.0; 0.15 caps at 84.0."""
    result = compose(
        demand_result=DemandStub(demand_score=90.0),
        competition_result=CompetitionStub(competition_score=10.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        risk_result=None,
    )
    assert result.opportunity_score < 88.0


def test_both_negative_dimensions_missing_caps_hardest():
    result = compose(
        demand_result=DemandStub(demand_score=90.0),
        margin_result=MarginStub(margin_score=90.0),
        supplier_result=SupplierStub(supplier_score=90.0),
        logistics_result=LogisticsStub(logistics_score=90.0),
        competition_result=None,
        risk_result=None,
    )
    # 0.70 earned at 90, 0.30 of missing negatives held at neutral.
    expected = (90.0 * 0.70 + 0.30 * 50.0) / 1.0
    assert result.false_safety_ceiling_applied is True
    assert result.opportunity_score == pytest.approx(expected, abs=0.01)
    assert result.opportunity_score == pytest.approx(78.0, abs=1e-9)


def test_supplier_adapter_ignores_unit_cost_so_margin_owns_economics():
    """Spec 25 / matrix 60: Supplier cost must not re-enter the score.

    Supplier records `unit_cost` as sourcing evidence but never scores
    it; Margin owns every profitability calculation. If the adapter
    ever started reading it, the same economics would be counted in two
    separately weighted components.
    """
    base = dict(
        product_name="Widget",
        supplier_name="Fornecedor X",
        moq_units=5,
        stock_quantity=400,
        lead_time_days=8,
        dropshipping_supported=True,
        invoice_available=True,
        business_verified=True,
        tracking_available=True,
    )
    cheap = analyze_supplier(SupplierInputs(**base, unit_cost=Decimal("1")))
    pricey = analyze_supplier(SupplierInputs(**base, unit_cost=Decimal("9999")))

    assert cheap.supplier_score == pricey.supplier_score, (
        "unit_cost must not move the Supplier Score -- that is Margin's job"
    )
    assert (
        from_supplier_result(cheap).raw_score == from_supplier_result(pricey).raw_score
    )


def test_supplier_and_risk_measure_different_things():
    """Spec 24 / matrix 59: current viability vs structural dependency.

    Risk's continuity evidence is an OBSERVED historical frequency and
    must never be derived from Supplier's current stock level.
    """
    stocked = analyze_supplier(
        SupplierInputs(
            product_name="Widget",
            supplier_name="Fornecedor X",
            moq_units=5,
            stock_quantity=900,
            lead_time_days=5,
            dropshipping_supported=True,
            invoice_available=True,
        )
    )
    assert stocked.supplier_score is not None

    # A healthy current stock says NOTHING about historical stockouts:
    # Risk only moves when a real observed rate is supplied.
    risk_base = dict(
        product_name="Widget",
        supplier_count=3,
        primary_supplier_dependency_percent=Decimal("0.4"),
        regulatory_uncertainty=False,
        brand_ip_uncertainty=False,
    )
    unreliable_history = analyze_risk(
        RiskInputs(**risk_base, historical_stockout_rate=Decimal("0.4"))
    )
    reliable_history = analyze_risk(
        RiskInputs(**risk_base, historical_stockout_rate=Decimal("0.0"))
    )
    assert unreliable_history.risk_score > reliable_history.risk_score


def test_readiness_states_are_all_reachable():
    """All four states must be distinguishable from real compositions."""
    reached = {
        compose().readiness,
        compose(supplier_result=None).readiness,
        compose(margin_result=None).readiness,
        compose(supplier_result=SupplierStub(blockers=["no stock"])).readiness,
    }
    assert reached == {
        READINESS_READY,
        READINESS_OPERATIONALLY_UNVALIDATED,
        READINESS_INCOMPLETE_EVIDENCE,
        READINESS_BLOCKED,
    }


def test_only_ready_is_publishable():
    for kwargs in (
        {"supplier_result": None},
        {"logistics_result": None},
        {"margin_result": None},
        {"risk_result": None},
        {"competition_result": None},
        {"supplier_result": SupplierStub(blockers=["no stock"])},
    ):
        result = compose(**kwargs)
        assert result.publishable is False
        assert result.classification is None
    assert compose().publishable is True
    assert compose().classification is not None
