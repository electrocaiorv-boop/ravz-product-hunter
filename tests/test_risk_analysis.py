"""Tests for the deterministic Risk analysis engine (Phase 10).

Every exact-value assertion here was first computed by running the real
implementation directly and only then copied into an assertion -- never
hand-derived and assumed correct.
"""

from decimal import Decimal

import pytest

from src.risk_analysis import EVIDENCE_WEIGHTS, _interpolate, analyze_risk
from src.risk_models import RiskInputs


def _diversified():
    """Worked Example A from the Phase 10 spec: diversified, stable."""
    return RiskInputs(
        product_name="Diversified product",
        supplier_count=5,
        primary_supplier_dependency_percent=Decimal("0.30"),
        platform_dependency_percent=Decimal("0.40"),
        observed_price_volatility_percent=Decimal("0.05"),
        historical_stockout_rate=Decimal("0.02"),
        observed_return_rate=Decimal("0.03"),
    )


def _concentrated():
    """Worked Example B from the Phase 10 spec: concentrated, unstable."""
    return RiskInputs(
        product_name="Concentrated product",
        supplier_count=1,
        primary_supplier_dependency_percent=Decimal("1.00"),
        platform_dependency_percent=Decimal("1.00"),
        observed_price_volatility_percent=Decimal("0.35"),
        historical_stockout_rate=Decimal("0.40"),
        observed_return_rate=Decimal("0.25"),
    )


# -- Evidence weights sanity --------------------------------------------------


def test_evidence_weights_sum_to_one():
    assert sum(EVIDENCE_WEIGHTS.values()) == pytest.approx(1.0)


# -- Worked example: diversified (low risk) vs concentrated (high risk) -------


def test_diversified_scenario_is_low_risk():
    result = analyze_risk(_diversified())
    assert result.risk_score == 14.26
    assert result.evidence_completeness_score == 50.0
    assert result.risk_status == "LOW"
    assert result.dependency_risk_score == pytest.approx(22.87878787878788)
    assert result.supply_continuity_risk_score == pytest.approx(7.999999999999998)
    assert result.volatility_risk_score == 15.0
    assert result.operational_history_risk_score == 9.0
    assert result.compliance_uncertainty_risk_score is None


def test_concentrated_scenario_is_severe_risk():
    result = analyze_risk(_concentrated())
    assert result.risk_score == 83.82
    assert result.evidence_completeness_score == 50.0
    assert result.risk_status == "SEVERE"
    assert result.dependency_risk_score == 100.0
    assert result.supply_continuity_risk_score == 90.0
    assert result.volatility_risk_score == 81.25
    assert result.operational_history_risk_score == 60.0
    assert result.compliance_uncertainty_risk_score is None


def test_concentrated_scenario_scores_higher_than_diversified():
    """Section 23: high dependency/volatility/stockout/returns must score
    higher than a diversified, stable scenario -- the core direction test."""
    diversified_result = analyze_risk(_diversified())
    concentrated_result = analyze_risk(_concentrated())
    assert concentrated_result.risk_score > diversified_result.risk_score


# -- Risk score direction: 0 = good, 100 = bad --------------------------------


def test_risk_score_direction_zero_is_low_risk_favorable():
    all_clear = RiskInputs(
        product_name="All clear",
        supplier_count=10,
        primary_supplier_dependency_percent=Decimal("0"),
        platform_dependency_percent=Decimal("0"),
        advertising_dependency_percent=Decimal("0"),
        observed_price_volatility_percent=Decimal("0"),
        historical_stockout_rate=Decimal("0"),
        observed_return_rate=Decimal("0"),
        observed_damage_rate=Decimal("0"),
        seasonality_level=0,
        regulatory_uncertainty=False,
        brand_ip_uncertainty=False,
        recall_history_present=False,
        replacement_supplier_available=True,
        alternative_fulfillment_available=True,
    )
    result = analyze_risk(all_clear)
    assert result.risk_score == 0.0
    assert result.risk_status == "LOW"


def test_risk_score_direction_100_is_high_risk_unfavorable():
    worst_case = RiskInputs(
        product_name="Worst case",
        supplier_count=0,
        primary_supplier_dependency_percent=Decimal("1"),
        platform_dependency_percent=Decimal("1"),
        advertising_dependency_percent=Decimal("1"),
        observed_price_volatility_percent=Decimal("1"),
        historical_stockout_rate=Decimal("1"),
        observed_return_rate=Decimal("1"),
        observed_damage_rate=Decimal("1"),
        seasonality_level=100,
        regulatory_uncertainty=True,
        brand_ip_uncertainty=True,
        recall_history_present=True,
        replacement_supplier_available=False,
        alternative_fulfillment_available=False,
    )
    result = analyze_risk(worst_case)
    assert result.risk_score == 91.5
    assert result.risk_status == "SEVERE"
    assert result.blockers == []


# -- Dependency risk: supplier_count vs primary dependency percent ------------


def test_supplier_count_zero_behaves_like_supplier_count_one():
    """supplier_count=0 is NOT a blocker (it doesn't prove zero suppliers
    exist anywhere, only that none are known to this assessment) -- it
    clamps to the same maximal risk as count=1 via anchor clamping."""
    zero = analyze_risk(RiskInputs(product_name="Zero suppliers", supplier_count=0))
    one = analyze_risk(RiskInputs(product_name="One supplier", supplier_count=1))
    assert zero.dependency_risk_score == one.dependency_risk_score == 100.0
    assert zero.blockers == []


def test_supplier_count_high_is_lower_risk_than_low():
    high_count = analyze_risk(RiskInputs(product_name="Many suppliers", supplier_count=10))
    low_count = analyze_risk(RiskInputs(product_name="One supplier", supplier_count=1))
    assert high_count.dependency_risk_score < low_count.dependency_risk_score
    assert high_count.dependency_risk_score == 0.0


def test_primary_supplier_dependency_100_percent_is_high_risk():
    result = analyze_risk(
        RiskInputs(product_name="Fully dependent", primary_supplier_dependency_percent=Decimal("1"))
    )
    assert result.dependency_risk_score == 100.0


def test_primary_supplier_dependency_low_is_low_risk():
    result = analyze_risk(
        RiskInputs(product_name="Low dependency", primary_supplier_dependency_percent=Decimal("0.1"))
    )
    assert result.dependency_risk_score < 20.0


def test_supplier_count_five_but_high_dependency_percent_is_still_high_risk():
    """Section 8's exact scenario: 5 suppliers looks diversified by count
    alone, but if one still accounts for 95% of volume, dependency risk
    must stay high -- the percent is weighted higher than the count so it
    is not washed out."""
    result = analyze_risk(
        RiskInputs(
            product_name="Nominally diversified",
            supplier_count=5,
            primary_supplier_dependency_percent=Decimal("0.95"),
        )
    )
    assert result.dependency_risk_score > 50.0


def test_platform_dependency_high_vs_low():
    high = analyze_risk(RiskInputs(product_name="Single channel", platform_dependency_percent=Decimal("1.0")))
    low = analyze_risk(RiskInputs(product_name="Diversified channels", platform_dependency_percent=Decimal("0.2")))
    assert high.dependency_risk_score > low.dependency_risk_score


def test_advertising_dependency_high_vs_low():
    high = analyze_risk(RiskInputs(product_name="Ad-dependent", advertising_dependency_percent=Decimal("0.9")))
    low = analyze_risk(RiskInputs(product_name="Organic-driven", advertising_dependency_percent=Decimal("0.1")))
    assert high.dependency_risk_score > low.dependency_risk_score


def test_advertising_dependency_never_infers_profitability():
    result = analyze_risk(RiskInputs(product_name="Ad item", advertising_dependency_percent=Decimal("0.9")))
    for attr in ("cac", "profit", "margin", "contribution_margin"):
        assert not hasattr(result, attr)


# -- Price volatility -----------------------------------------------------------


def test_price_volatility_zero_is_distinct_from_none():
    zero = analyze_risk(RiskInputs(product_name="Stable price", observed_price_volatility_percent=Decimal("0")))
    unknown = analyze_risk(RiskInputs(product_name="Unknown price", observed_price_volatility_percent=None))
    assert zero.observed["observed_price_volatility_percent"] == Decimal("0")
    assert zero.volatility_risk_score == 0.0
    assert unknown.observed["observed_price_volatility_percent"] is None
    assert unknown.volatility_risk_score is None


def test_high_price_volatility_increases_volatility_risk_and_warns():
    result = analyze_risk(RiskInputs(product_name="Volatile price", observed_price_volatility_percent=Decimal("0.4")))
    assert result.volatility_risk_score > 50.0
    assert any("observed price volatility" in w for w in result.warnings)


# -- Stockout rate ----------------------------------------------------------------


def test_stockout_rate_zero_is_distinct_from_none():
    zero = analyze_risk(RiskInputs(product_name="Reliable stock", historical_stockout_rate=Decimal("0")))
    unknown = analyze_risk(RiskInputs(product_name="Unknown stock history", historical_stockout_rate=None))
    assert zero.observed["historical_stockout_rate"] == Decimal("0")
    assert zero.supply_continuity_risk_score == 0.0
    assert unknown.observed["historical_stockout_rate"] is None
    assert unknown.supply_continuity_risk_score is None


def test_high_stockout_rate_increases_continuity_risk_and_warns():
    result = analyze_risk(RiskInputs(product_name="Frequent stockouts", historical_stockout_rate=Decimal("0.4")))
    assert result.supply_continuity_risk_score > 80.0
    assert any("historical stockout rate" in w for w in result.warnings)


def test_stockout_rate_never_derived_from_current_stock_field():
    """RiskInputs has no current-stock field at all -- that belongs to
    Supplier Analysis; historical_stockout_rate can only ever be an
    explicitly-supplied historical observation."""
    inputs = RiskInputs(product_name="Item")
    assert not hasattr(inputs, "stock_quantity")
    assert not hasattr(inputs, "stock_available")


# -- Observed return / damage rate -------------------------------------------------


def test_observed_return_rate_zero_vs_none():
    zero = analyze_risk(RiskInputs(product_name="No returns", observed_return_rate=Decimal("0")))
    unknown = analyze_risk(RiskInputs(product_name="Unknown returns", observed_return_rate=None))
    assert zero.observed["observed_return_rate"] == Decimal("0")
    assert unknown.observed["observed_return_rate"] is None


def test_observed_damage_rate_zero_vs_none():
    zero = analyze_risk(RiskInputs(product_name="No damage", observed_damage_rate=Decimal("0")))
    unknown = analyze_risk(RiskInputs(product_name="Unknown damage", observed_damage_rate=None))
    assert zero.observed["observed_damage_rate"] == Decimal("0")
    assert unknown.observed["observed_damage_rate"] is None


def test_severe_observed_rates_increase_risk_but_never_block():
    inputs = RiskInputs(
        product_name="Severe history",
        supplier_count=5,
        observed_return_rate=Decimal("0.9"),
        observed_damage_rate=Decimal("0.9"),
    )
    result = analyze_risk(inputs)
    assert result.operational_history_risk_score > 80.0
    assert result.blockers == []
    assert any("observed return rate" in w for w in result.warnings)
    assert any("observed damage rate" in w for w in result.warnings)


# -- Regulatory / brand-IP / recall flags: True/False/None ---------------------


@pytest.mark.parametrize("value", [True, False, None])
def test_regulatory_uncertainty_true_false_none(value):
    result = analyze_risk(RiskInputs(product_name="Item", regulatory_uncertainty=value))
    assert result.observed["regulatory_uncertainty"] is value


@pytest.mark.parametrize("value", [True, False, None])
def test_brand_ip_uncertainty_true_false_none(value):
    result = analyze_risk(RiskInputs(product_name="Item", brand_ip_uncertainty=value))
    assert result.observed["brand_ip_uncertainty"] is value


@pytest.mark.parametrize("value", [True, False, None])
def test_recall_history_true_false_none(value):
    result = analyze_risk(RiskInputs(product_name="Item", recall_history_present=value))
    assert result.observed["recall_history_present"] is value


@pytest.mark.parametrize("value", [True, False, None])
def test_replacement_supplier_available_true_false_none(value):
    result = analyze_risk(RiskInputs(product_name="Item", replacement_supplier_available=value))
    assert result.observed["replacement_supplier_available"] is value


@pytest.mark.parametrize("value", [True, False, None])
def test_alternative_fulfillment_available_true_false_none(value):
    result = analyze_risk(RiskInputs(product_name="Item", alternative_fulfillment_available=value))
    assert result.observed["alternative_fulfillment_available"] is value


def test_regulatory_uncertainty_true_never_claims_illegality():
    result = analyze_risk(RiskInputs(product_name="Item", regulatory_uncertainty=True))
    assert any("legal" in item.lower() for item in result.unavailable)
    assert result.compliance_uncertainty_risk_score == 70.0  # flagged, not treated as proven (100)


def test_brand_ip_uncertainty_true_never_claims_infringement():
    result = analyze_risk(RiskInputs(product_name="Item", brand_ip_uncertainty=True))
    assert any("infringement" in item.lower() for item in result.unavailable)
    assert result.compliance_uncertainty_risk_score == 70.0


def test_regulatory_and_brand_ip_both_true_produces_compound_warning():
    result = analyze_risk(RiskInputs(product_name="Item", regulatory_uncertainty=True, brand_ip_uncertainty=True))
    assert any("both regulatory and brand/IP" in w for w in result.warnings)
    assert not any("both regulatory and brand/IP" in w for w in analyze_risk(
        RiskInputs(product_name="Item", regulatory_uncertainty=True, brand_ip_uncertainty=False)
    ).warnings)


def test_recall_history_present_true_produces_warning_not_blocker():
    result = analyze_risk(RiskInputs(product_name="Item", recall_history_present=True))
    assert result.blockers == []
    assert any("prior recall" in w for w in result.warnings)
    assert result.operational_history_risk_score == 100.0


def test_full_dependency_with_no_replacement_warns():
    result = analyze_risk(
        RiskInputs(
            product_name="Item",
            primary_supplier_dependency_percent=Decimal("1"),
            replacement_supplier_available=False,
        )
    )
    assert any("no known replacement" in w for w in result.warnings)


# -- No hard blockers reachable ------------------------------------------------


def test_no_hard_blocker_from_uncertainty_flags():
    result = analyze_risk(
        RiskInputs(product_name="Item", regulatory_uncertainty=True, brand_ip_uncertainty=True, recall_history_present=True)
    )
    assert result.blockers == []
    assert result.risk_status != "BLOCKED"


def test_no_hard_blocker_from_worst_case_input_combination():
    worst_case = RiskInputs(
        product_name="Worst plausible case",
        supplier_count=0,
        primary_supplier_dependency_percent=Decimal("1"),
        platform_dependency_percent=Decimal("1"),
        advertising_dependency_percent=Decimal("1"),
        observed_price_volatility_percent=Decimal("1"),
        historical_stockout_rate=Decimal("1"),
        observed_return_rate=Decimal("1"),
        observed_damage_rate=Decimal("1"),
        seasonality_level=100,
        regulatory_uncertainty=True,
        brand_ip_uncertainty=True,
        recall_history_present=True,
        replacement_supplier_available=False,
        alternative_fulfillment_available=False,
    )
    result = analyze_risk(worst_case)
    assert result.blockers == []
    assert result.risk_status != "BLOCKED"


# -- Evidence completeness: independent from score -----------------------------


def test_evidence_completeness_independent_from_risk_score():
    diversified_result = analyze_risk(_diversified())
    concentrated_result = analyze_risk(_concentrated())
    assert diversified_result.evidence_completeness_score == concentrated_result.evidence_completeness_score == 50.0
    assert diversified_result.risk_score != concentrated_result.risk_score


def test_low_evidence_with_apparently_low_risk_withholds_score():
    """A single favorable-looking field must not be enough to produce a
    confident-sounding low score."""
    sparse = RiskInputs(product_name="Sparse but looks fine", observed_return_rate=Decimal("0"))
    result = analyze_risk(sparse)
    assert result.risk_score is None
    assert result.risk_status == "INSUFFICIENT_DATA"
    assert result.evidence_completeness_score < 35.0


def test_minimal_inputs_score_withheld():
    result = analyze_risk(RiskInputs(product_name="Mystery product"))
    assert result.risk_score is None
    assert result.evidence_completeness_score == 0.0
    assert result.risk_status == "INSUFFICIENT_DATA"


# -- Missing dimensions excluded, weights renormalize --------------------------


def test_missing_dimensions_excluded_and_weights_renormalize():
    result = analyze_risk(_diversified())
    assert result.compliance_uncertainty_risk_score is None
    assert any("compliance" in item.lower() for item in result.unavailable)
    # risk_score is computed from the 4 known dimensions' renormalized
    # weights (0.25+0.20+0.20+0.20=0.85), never defaulting the missing
    # 5th dimension to 0 (which would silently reward missing evidence).
    assert result.risk_score is not None


# -- Determinism and score bounds ----------------------------------------------


def test_identical_inputs_produce_identical_results():
    first = analyze_risk(_concentrated())
    second = analyze_risk(_concentrated())
    assert first.risk_score == second.risk_score
    assert first.evidence_completeness_score == second.evidence_completeness_score
    assert first.risk_status == second.risk_status


@pytest.mark.parametrize("builder", [_diversified, _concentrated])
def test_score_within_bounds(builder):
    result = analyze_risk(builder())
    assert 0.0 <= result.risk_score <= 100.0
    assert 0.0 <= result.evidence_completeness_score <= 100.0


# -- No duplication of other analysis modules ----------------------------------


def test_no_sale_price_field_so_no_margin_logic_possible():
    inputs = RiskInputs(product_name="Item")
    assert not hasattr(inputs, "sale_price")


def test_risk_analysis_module_imports_nothing_from_prior_analysis_modules():
    """Checks actual `import`/`from` statement lines only -- the module
    docstring legitimately NAMES these modules in prose (to document that
    they are deliberately not imported), so a blanket substring search
    over the whole file would false-positive on its own documentation."""
    import src.risk_analysis as risk_analysis_module

    source = risk_analysis_module.__file__
    with open(source, encoding="utf-8") as f:
        import_lines = [
            line for line in f if line.strip().startswith(("import ", "from "))
        ]
    forbidden = (
        "src.demand_analysis",
        "src.trend_analysis",
        "src.competition_analysis",
        "src.margin_analysis",
        "src.supplier_analysis",
        "src.logistics_analysis",
        "src.integrations",
    )
    for line in import_lines:
        for name in forbidden:
            assert name not in line


# -- Interpolation helper sanity ------------------------------------------------


def test_interpolate_exact_anchor_matches():
    anchors = ((1, 100.0), (2, 70.0), (5, 20.0))
    assert _interpolate(1, anchors) == 100.0
    assert _interpolate(5, anchors) == 20.0


def test_interpolate_below_first_anchor_clamps():
    anchors = ((1, 100.0), (2, 70.0), (5, 20.0))
    assert _interpolate(0, anchors) == 100.0


def test_interpolate_above_last_anchor_clamps():
    anchors = ((1, 100.0), (2, 70.0), (5, 20.0))
    assert _interpolate(100, anchors) == 20.0
