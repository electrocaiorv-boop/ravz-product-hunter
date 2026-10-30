"""Canonical Opportunity contract tests (Phase 11).

Covers the integrated weight contract, the evidence-family policy, the
two validation layers, score direction / single inversion, the
classification bands, and the rounding policy -- the invariants a future
refactor is most likely to break silently.
"""

import pytest

from src.opportunity_models import (
    CLASSIFICATION_REJECT,
    COMMERCIAL_REQUIREMENTS,
    COMPONENT_FAMILIES,
    COMPONENT_ORDER,
    COMPONENT_VALIDATION_LAYER,
    DIRECTION_NEGATIVE,
    DIRECTION_POSITIVE,
    DISTINCT_WEIGHTED_SLOTS,
    EVIDENCE_FAMILIES,
    FAMILY_REPRESENTATIVE_PRECEDENCE,
    FAMILY_SEARCH_INTEREST,
    INTEGRATED_MODEL_VERSION,
    INTEGRATED_WEIGHTS,
    LEGACY_MODEL_VERSION,
    NEGATIVE_COMPONENTS,
    OPERATIONAL_REQUIREMENTS,
    READINESS_BLOCKED,
    READINESS_INCOMPLETE_EVIDENCE,
    READINESS_OPERATIONALLY_UNVALIDATED,
    READINESS_PRECEDENCE,
    READINESS_READY,
    SEARCH_INTEREST_FAMILY,
    SEARCH_INTEREST_FAMILY_WEIGHT,
    TOTAL_COMMERCIAL_WEIGHT,
    TOTAL_INTEGRATED_WEIGHT,
    TOTAL_OPERATIONAL_WEIGHT,
    VALIDATION_COMMERCIAL,
    VALIDATION_OPERATIONAL,
    EvidenceFamilyPolicy,
    EvidenceProfile,
    OpportunityComponent,
    classify_exact,
    to_opportunity_oriented,
)

POSITIVE_COMPONENTS = ("demand", "trend", "margin", "supplier", "logistics")


# -- Integrated weight contract (hardened) --------------------------------


def test_integrated_distinct_weights_sum_to_exactly_one():
    """Counting each evidence family ONCE, weights must sum to 1.0."""
    assert TOTAL_INTEGRATED_WEIGHT == pytest.approx(1.0, abs=1e-9)


def test_search_interest_family_weight_is_thirty_percent():
    """Hardened: the family no longer inherits legacy's combined 0.50.

    Legacy's 0.50 was split across what it BELIEVED were two
    independent demand signals. Once the audit proved they are one
    evidence family fed by one provider call, preserving 0.50 would
    silently convert "half the score from two independent signals" into
    "half the score from one Google Trends call" -- a materially
    different and far more concentrated claim.
    """
    assert SEARCH_INTEREST_FAMILY_WEIGHT == pytest.approx(0.30, abs=1e-9)
    assert SEARCH_INTEREST_FAMILY.weight == pytest.approx(0.30, abs=1e-9)


def test_search_interest_family_weight_is_not_the_legacy_sum():
    """Explicit regression against reverting to the 0.50 draft."""
    assert SEARCH_INTEREST_FAMILY_WEIGHT != pytest.approx(0.50, abs=1e-9)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("competition", 0.15),
        ("margin", 0.20),
        ("supplier", 0.12),
        ("logistics", 0.08),
        ("risk", 0.15),
    ],
)
def test_integrated_component_weights_are_the_documented_contract(name, expected):
    assert INTEGRATED_WEIGHTS[name] == pytest.approx(expected, abs=1e-9)


def test_margin_outweighs_the_search_interest_family():
    """A product that loses money per unit is not an opportunity at all.

    Unit economics are material to viability in a way search interest
    is not, so Margin is deliberately weighted above the family.
    """
    assert INTEGRATED_WEIGHTS["margin"] > SEARCH_INTEREST_FAMILY_WEIGHT / 2
    assert INTEGRATED_WEIGHTS["margin"] == pytest.approx(0.20, abs=1e-9)


def test_risk_is_materially_weighted_not_marginal():
    """Risk tripled from legacy's 0.05, which was too small for a
    dimension the project treats as mandatory evidence."""
    assert INTEGRATED_WEIGHTS["risk"] == pytest.approx(0.15, abs=1e-9)
    assert INTEGRATED_WEIGHTS["risk"] > INTEGRATED_WEIGHTS["logistics"]


def test_supplier_outweighs_logistics():
    assert INTEGRATED_WEIGHTS["supplier"] > INTEGRATED_WEIGHTS["logistics"]


def test_logistics_stays_below_margin_and_supplier():
    assert INTEGRATED_WEIGHTS["logistics"] < INTEGRATED_WEIGHTS["margin"]
    assert INTEGRATED_WEIGHTS["logistics"] < INTEGRATED_WEIGHTS["supplier"]


def test_demand_and_trend_share_one_family_weight():
    assert INTEGRATED_WEIGHTS["demand"] == INTEGRATED_WEIGHTS["trend"]
    assert COMPONENT_FAMILIES["demand"] == FAMILY_SEARCH_INTEREST
    assert COMPONENT_FAMILIES["trend"] == FAMILY_SEARCH_INTEREST


def test_naively_summing_every_component_weight_would_exceed_one():
    """Regression guard for the double-counting trap itself.

    If a future refactor treats Demand and Trend as independent
    components again, the naive sum over all seven exceeds 1.0 -- this
    documents that the family mechanism is what keeps the contract
    coherent, so deleting it cannot pass unnoticed.
    """
    assert sum(INTEGRATED_WEIGHTS.values()) > 1.0


def test_integrated_weights_cover_exactly_the_seven_domains():
    assert set(INTEGRATED_WEIGHTS) == set(COMPONENT_ORDER)
    assert len(COMPONENT_ORDER) == 7


def test_distinct_weighted_slots_have_one_entry_per_family():
    keys = [key for key, _weight, _layer in DISTINCT_WEIGHTED_SLOTS]
    assert len(keys) == len(set(keys))
    assert FAMILY_SEARCH_INTEREST in keys
    assert "demand" not in keys and "trend" not in keys


def test_model_versions_are_distinct_and_integrated_not_renamed():
    """integrated-v1 is hardened pre-release, so the name does not bump."""
    assert INTEGRATED_MODEL_VERSION == "integrated-v1"
    assert LEGACY_MODEL_VERSION == "legacy-v1"
    assert INTEGRATED_MODEL_VERSION != LEGACY_MODEL_VERSION


# -- Evidence-family policy (durable, declarative) ------------------------


def test_search_interest_family_is_a_declared_policy_object():
    """The no-double-counting rule must be data, not ad-hoc conditionals."""
    assert isinstance(SEARCH_INTEREST_FAMILY, EvidenceFamilyPolicy)
    assert SEARCH_INTEREST_FAMILY in EVIDENCE_FAMILIES


def test_family_members_are_demand_then_trend_in_precedence_order():
    assert SEARCH_INTEREST_FAMILY.members == ("demand", "trend")
    assert SEARCH_INTEREST_FAMILY.representative_precedence == ("demand", "trend")
    assert FAMILY_REPRESENTATIVE_PRECEDENCE[FAMILY_SEARCH_INTEREST] == (
        "demand",
        "trend",
    )


def test_family_policy_documents_why_the_evidence_is_shared():
    rationale = SEARCH_INTEREST_FAMILY.rationale.lower()
    assert "same" in rationale
    assert "google" in rationale or "trends" in rationale
    assert "representative" in rationale


def test_family_policy_is_immutable():
    with pytest.raises(Exception):
        SEARCH_INTEREST_FAMILY.weight = 0.50


def test_component_families_are_derived_from_the_declared_policies():
    """No hand-maintained parallel table that could drift."""
    expected = {
        member: family.name
        for family in EVIDENCE_FAMILIES
        for member in family.members
    }
    assert COMPONENT_FAMILIES == expected


def test_only_demand_and_trend_are_in_a_family_today():
    assert set(COMPONENT_FAMILIES) == {"demand", "trend"}


# -- Validation layers ----------------------------------------------------


def test_every_component_belongs_to_exactly_one_validation_layer():
    assert set(COMPONENT_VALIDATION_LAYER) == set(COMPONENT_ORDER)
    assert set(COMPONENT_VALIDATION_LAYER.values()) == {
        VALIDATION_COMMERCIAL,
        VALIDATION_OPERATIONAL,
    }


def test_commercial_layer_is_the_business_case():
    assert COMMERCIAL_REQUIREMENTS == (
        FAMILY_SEARCH_INTEREST,
        "competition",
        "margin",
        "risk",
    )


def test_operational_layer_is_execution():
    assert OPERATIONAL_REQUIREMENTS == ("supplier", "logistics")


def test_layer_weights_partition_the_total_exactly():
    assert TOTAL_COMMERCIAL_WEIGHT == pytest.approx(0.80, abs=1e-9)
    assert TOTAL_OPERATIONAL_WEIGHT == pytest.approx(0.20, abs=1e-9)
    assert TOTAL_COMMERCIAL_WEIGHT + TOTAL_OPERATIONAL_WEIGHT == pytest.approx(
        TOTAL_INTEGRATED_WEIGHT, abs=1e-9
    )


def test_supplier_and_logistics_are_operational_not_optional():
    """Hardened: they are no longer simply "non-critical".

    A product can be commercially attractive and operationally
    unvalidated; that must be sayable, so they are required for their
    own layer rather than ignorable.
    """
    assert COMPONENT_VALIDATION_LAYER["supplier"] == VALIDATION_OPERATIONAL
    assert COMPONENT_VALIDATION_LAYER["logistics"] == VALIDATION_OPERATIONAL
    assert "supplier" in OPERATIONAL_REQUIREMENTS
    assert "logistics" in OPERATIONAL_REQUIREMENTS


def test_readiness_precedence_is_worst_first_and_distinguishes_all_four():
    assert READINESS_PRECEDENCE == (
        READINESS_BLOCKED,
        READINESS_INCOMPLETE_EVIDENCE,
        READINESS_OPERATIONALLY_UNVALIDATED,
        READINESS_READY,
    )
    assert len(set(READINESS_PRECEDENCE)) == 4


def test_operationally_unvalidated_is_not_collapsed_into_incomplete():
    assert READINESS_OPERATIONALLY_UNVALIDATED != READINESS_INCOMPLETE_EVIDENCE


# -- Direction / inversion ------------------------------------------------


def test_negative_components_are_exactly_competition_and_risk():
    assert NEGATIVE_COMPONENTS == frozenset({"competition", "risk"})


@pytest.mark.parametrize("name", POSITIVE_COMPONENTS)
def test_positive_components_are_never_inverted(name):
    assert name not in NEGATIVE_COMPONENTS
    assert to_opportunity_oriented(70.0, DIRECTION_POSITIVE) == 70.0


@pytest.mark.parametrize("raw, expected", [(0.0, 100.0), (40.0, 60.0), (100.0, 0.0)])
def test_negative_direction_inverts_once(raw, expected):
    assert to_opportunity_oriented(raw, DIRECTION_NEGATIVE) == expected


def test_no_double_inversion():
    """Re-orienting an already-oriented value must not restore the original."""
    once = to_opportunity_oriented(30.0, DIRECTION_NEGATIVE)
    twice = to_opportunity_oriented(once, DIRECTION_NEGATIVE)
    assert once == 70.0
    assert twice == 30.0
    assert twice != once, "inverting twice silently cancels out -- invert exactly once"


@pytest.mark.parametrize("direction", [DIRECTION_POSITIVE, DIRECTION_NEGATIVE])
def test_none_score_stays_none_in_both_directions(direction):
    """None must never become 0, 50, 'safe', or 'average'."""
    assert to_opportunity_oriented(None, direction) is None


# -- Classification / rounding policy -------------------------------------


@pytest.mark.parametrize(
    "score, expected",
    [
        (100.0, "Strong opportunity"),
        (80.0, "Strong opportunity"),
        (79.99, "Worth deeper investigation"),
        (65.0, "Worth deeper investigation"),
        (64.99, "Weak or uncertain opportunity"),
        (50.0, "Weak or uncertain opportunity"),
        (49.99, CLASSIFICATION_REJECT),
        (0.0, CLASSIFICATION_REJECT),
    ],
)
def test_classification_bands_match_the_documented_contract(score, expected):
    assert classify_exact(score) == expected


@pytest.mark.parametrize("boundary", [50.0, 65.0, 80.0])
def test_classification_uses_the_exact_value_not_the_displayed_one(boundary):
    """A value that DISPLAYS as the boundary but is below it must not promote.

    `boundary - 0.004` both rounds AND formats to the boundary at 2
    decimal places while being strictly below it -- exactly the trap
    described in the Phase 11 rounding review. (0.005 is deliberately
    avoided here: it is not exactly representable in binary and
    Python's `round` is half-to-even, so it is a poor probe.)
    """
    just_below = boundary - 0.004
    assert just_below < boundary
    assert round(just_below, 2) == pytest.approx(boundary, abs=1e-9)
    assert f"{just_below:.2f}" == f"{boundary:.2f}"
    assert classify_exact(just_below) != classify_exact(boundary)


def test_classification_is_monotonic_across_the_bands():
    labels = [classify_exact(s) for s in (10.0, 55.0, 70.0, 95.0)]
    assert labels == [
        CLASSIFICATION_REJECT,
        "Weak or uncertain opportunity",
        "Worth deeper investigation",
        "Strong opportunity",
    ]


# -- Component behaviour ---------------------------------------------------


def _component(**overrides):
    base = dict(
        name="demand",
        source_domain="Demand Analysis (Phase 5)",
        direction=DIRECTION_POSITIVE,
        configured_weight=0.30,
        validation_layer=VALIDATION_COMMERCIAL,
        available=True,
        raw_score=80.0,
        opportunity_score=80.0,
        weighted_contribution=24.0,
        evidence_label="demand confidence",
        evidence_value=50.0,
    )
    base.update(overrides)
    return OpportunityComponent(**base)


def test_effective_weight_is_the_configured_weight_when_counted_and_available():
    assert _component().effective_weight == 0.30


def test_effective_weight_is_zero_when_unavailable():
    component = _component(available=False, raw_score=None, opportunity_score=None)
    assert component.effective_weight == 0.0


def test_effective_weight_is_zero_when_not_the_family_representative():
    """A non-elected family member must contribute no weight at all."""
    component = _component(name="trend", counted=False)
    assert component.effective_weight == 0.0


def test_component_is_immutable():
    """Adapters must never be able to mutate a composed component."""
    component = _component()
    with pytest.raises(Exception):
        component.raw_score = 1.0


def test_component_carries_its_validation_layer():
    assert _component().validation_layer == VALIDATION_COMMERCIAL
    assert (
        _component(name="supplier", validation_layer=VALIDATION_OPERATIONAL).validation_layer
        == VALIDATION_OPERATIONAL
    )


# -- Evidence profile ------------------------------------------------------


def test_evidence_profile_keeps_each_metric_under_its_own_name():
    """Unlike evidence concepts must not be renamed into one another."""
    fields = set(EvidenceProfile().__dict__)
    assert "demand_confidence" in fields
    assert "competition_confidence" in fields
    assert "margin_cost_completeness" in fields
    assert "supplier_evidence_completeness" in fields
    assert "logistics_evidence_completeness" in fields
    assert "risk_evidence_completeness" in fields


def test_evidence_profile_offers_no_aggregate_metric():
    """Averaging a bounded-confidence figure with a field-count
    completeness figure would produce a meaningless number, so no
    aggregate field may exist."""
    fields = set(EvidenceProfile().__dict__)
    for forbidden in (
        "overall_confidence",
        "average_confidence",
        "aggregate_evidence",
        "evidence_score",
        "combined_confidence",
    ):
        assert forbidden not in fields


def test_evidence_profile_does_not_call_trend_metadata_a_confidence():
    """Trend has no confidence metric; inventing one would be fabrication."""
    fields = set(EvidenceProfile().__dict__)
    assert "trend_confidence" not in fields
    assert "trend_observation_count" in fields


def test_evidence_profile_defaults_to_all_unknown():
    profile = EvidenceProfile()
    assert all(value is None for value in profile.__dict__.values())
