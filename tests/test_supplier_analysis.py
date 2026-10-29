from decimal import Decimal

import pytest

from src.supplier_analysis import analyze_supplier
from src.supplier_models import SupplierInputs


def make_inputs(**overrides):
    base = dict(product_name="Bebedouro", supplier_name="Fornecedor")
    base.update(overrides)
    return SupplierInputs(**base)


# --- Composite scenarios (verified against the real implementation) -------


def test_strong_complete_supplier():
    inputs = make_inputs(
        unit_cost=Decimal("10"),
        moq_units=1,
        shipping_cost=Decimal("5"),
        payment_terms_days=30,
        stock_quantity=1000,
        stock_available=True,
        dispatch_time_days=1,
        delivery_time_days=2,
        tracking_available=True,
        dropshipping_supported=True,
        blind_shipping_supported=True,
        invoice_available=True,
        return_policy_available=True,
        business_verified=True,
        contact_available=True,
        supplier_rating=Decimal("4.8"),
        review_count=500,
        years_active=5,
    )
    result = analyze_supplier(inputs)

    assert result.supplier_score == pytest.approx(98.84, abs=0.01)
    assert result.evidence_completeness_score == pytest.approx(95.0, abs=0.01)
    assert result.operational_status == "VIABLE"
    assert result.blockers == []


def test_weak_supplier_with_blocker():
    inputs = make_inputs(
        moq_units=500,
        minimum_order_value=Decimal("5000"),
        dispatch_time_days=20,
        delivery_time_days=40,
        stock_quantity=10,
        dropshipping_supported=False,
        blind_shipping_supported=False,
        tracking_available=False,
        invoice_available=False,
        return_policy_available=False,
        business_verified=False,
        contact_available=False,
        supplier_rating=Decimal("2.0"),
        review_count=3,
    )
    result = analyze_supplier(inputs)

    assert result.supplier_score == pytest.approx(10.4, abs=0.01)
    # A hard blocker must be visible even though a score was still computed.
    assert result.operational_status == "BLOCKED"
    assert any("below moq_units" in b for b in result.blockers)


def test_sparse_supplier_data_withholds_score():
    inputs = make_inputs(moq_units=10)
    result = analyze_supplier(inputs)

    assert result.evidence_completeness_score == pytest.approx(12.0, abs=0.01)
    assert result.supplier_score is None
    assert result.operational_status == "INSUFFICIENT_DATA"


def test_all_optional_data_missing():
    inputs = make_inputs()
    result = analyze_supplier(inputs)

    assert result.evidence_completeness_score == pytest.approx(0.0)
    assert result.supplier_score is None
    assert result.operational_status == "INSUFFICIENT_DATA"
    assert result.order_flexibility_score is None
    assert result.operational_speed_score is None
    assert result.stock_viability_score is None
    assert result.fulfillment_capability_score is None
    assert result.trust_score is None
    assert result.blockers == []


# --- MOQ / order flexibility -------------------------------------------------


def test_moq_of_one_is_most_flexible():
    result = analyze_supplier(make_inputs(moq_units=1))
    assert result.order_flexibility_score == pytest.approx(100.0)


def test_high_moq_is_least_flexible():
    result = analyze_supplier(make_inputs(moq_units=1000))
    assert result.order_flexibility_score == pytest.approx(0.0)


def test_minimum_order_value_alone_contributes_to_order_flexibility():
    result = analyze_supplier(make_inputs(minimum_order_value=Decimal("1000")))
    assert result.order_flexibility_score == pytest.approx(50.0)


def test_order_flexibility_excluded_without_moq_or_minimum_value():
    result = analyze_supplier(make_inputs(unit_cost=Decimal("10")))
    assert result.order_flexibility_score is None
    assert "order flexibility (MOQ / minimum order value)" in result.unavailable


# --- Lead time: dispatch vs. delivery vs. explicit, no double counting ----


def test_dispatch_time_alone_does_not_produce_a_lead_time():
    result = analyze_supplier(make_inputs(dispatch_time_days=5))
    assert result.lead_time_days is None
    assert result.operational_speed_score is None


def test_delivery_time_alone_does_not_produce_a_lead_time():
    result = analyze_supplier(make_inputs(delivery_time_days=5))
    assert result.lead_time_days is None
    assert result.operational_speed_score is None


def test_dispatch_plus_delivery_sum_to_lead_time():
    result = analyze_supplier(make_inputs(dispatch_time_days=1, delivery_time_days=2))
    assert result.lead_time_days == 3
    assert any("derived as dispatch_time_days + delivery_time_days" in n for n in result.notes)


def test_explicit_lead_time_is_used_directly_without_doubling():
    result = analyze_supplier(make_inputs(lead_time_days=10))
    assert result.lead_time_days == 10
    assert result.operational_speed_score == pytest.approx(77.5, abs=0.01)
    assert not any("derived as" in n for n in result.notes)


def test_explicit_lead_time_with_both_dispatch_and_delivery_rejected_at_input():
    """No double-counting: this conflict must be caught by SupplierInputs itself."""
    with pytest.raises(ValueError):
        make_inputs(lead_time_days=10, dispatch_time_days=2, delivery_time_days=8)


# --- Stock / MOQ interaction, hard blockers ---------------------------------


def test_stock_quantity_zero_is_a_blocker():
    result = analyze_supplier(make_inputs(stock_quantity=0))
    assert result.operational_status == "BLOCKED"
    assert any("stock_quantity = 0" in b for b in result.blockers)
    assert result.stock_viability_score == pytest.approx(0.0)


def test_stock_available_false_is_a_blocker():
    result = analyze_supplier(make_inputs(stock_available=False))
    assert result.operational_status == "BLOCKED"
    assert any("stock_available = False" in b for b in result.blockers)
    assert result.stock_viability_score == pytest.approx(0.0)


def test_stock_available_true_without_quantity_gives_moderate_score():
    result = analyze_supplier(make_inputs(stock_available=True))
    assert result.stock_viability_score == pytest.approx(55.0)
    assert any("quantity is unknown" in w for w in result.warnings)


def test_stock_quantity_below_moq_is_a_blocker_even_with_a_score():
    result = analyze_supplier(make_inputs(moq_units=100, stock_quantity=5))
    assert result.operational_status == "BLOCKED"
    assert any("below moq_units" in b for b in result.blockers)
    assert result.stock_viability_score == pytest.approx(10.0)


def test_stock_known_zero_differs_from_stock_unknown():
    zero_stock = analyze_supplier(make_inputs(stock_quantity=0))
    unknown_stock = analyze_supplier(make_inputs())

    assert zero_stock.stock_viability_score == pytest.approx(0.0)
    assert unknown_stock.stock_viability_score is None
    assert zero_stock.blockers != unknown_stock.blockers


# --- Boolean tri-state: dropshipping / blind shipping / invoice / tracking -


@pytest.mark.parametrize("field", ["dropshipping_supported", "blind_shipping_supported", "tracking_available"])
def test_fulfillment_boolean_tristate_excludes_unknown(field):
    true_result = analyze_supplier(make_inputs(**{field: True}))
    false_result = analyze_supplier(make_inputs(**{field: False}))
    none_result = analyze_supplier(make_inputs())

    assert true_result.fulfillment_capability_score is not None
    assert false_result.fulfillment_capability_score is not None
    assert true_result.fulfillment_capability_score > false_result.fulfillment_capability_score
    assert none_result.fulfillment_capability_score is None


def test_dropshipping_false_is_not_a_hard_blocker():
    """Bulk purchase + self-fulfillment remains viable -- this reduces a score, never blocks."""
    result = analyze_supplier(make_inputs(dropshipping_supported=False))
    assert result.blockers == []
    assert any("dropshipping is not supported" in w for w in result.warnings)


@pytest.mark.parametrize(
    "field", ["invoice_available", "return_policy_available", "business_verified", "contact_available"]
)
def test_trust_boolean_tristate_excludes_unknown(field):
    true_result = analyze_supplier(make_inputs(**{field: True}))
    false_result = analyze_supplier(make_inputs(**{field: False}))
    none_result = analyze_supplier(make_inputs())

    assert true_result.trust_score == pytest.approx(100.0)
    assert false_result.trust_score == pytest.approx(0.0)
    assert none_result.trust_score is None


# --- Rating / review count credibility --------------------------------------


def test_high_rating_with_low_review_count_is_shrunk_toward_neutral():
    result = analyze_supplier(make_inputs(supplier_rating=Decimal("5.0"), review_count=2))
    assert result.trust_score == pytest.approx(60.0, abs=0.01)
    assert any("very few" in w for w in result.warnings)


def test_high_rating_with_high_review_count_is_trusted_near_face_value():
    result = analyze_supplier(make_inputs(supplier_rating=Decimal("4.8"), review_count=10000))
    assert result.trust_score == pytest.approx(96.0, abs=0.01)


def test_same_rating_different_review_counts_produce_different_trust():
    """The exact '5.0 with 2 reviews != 4.8 with 10,000 reviews' example from the task."""
    low_evidence = analyze_supplier(make_inputs(supplier_rating=Decimal("5.0"), review_count=2))
    high_evidence = analyze_supplier(make_inputs(supplier_rating=Decimal("4.8"), review_count=10000))
    assert low_evidence.trust_score < high_evidence.trust_score


def test_rating_with_unknown_review_count_treated_as_cautiously_as_zero():
    unknown_rc = analyze_supplier(make_inputs(supplier_rating=Decimal("5.0")))
    zero_rc = analyze_supplier(make_inputs(supplier_rating=Decimal("5.0"), review_count=0))
    assert unknown_rc.trust_score == pytest.approx(zero_rc.trust_score, abs=0.01)


def test_invalid_rating_rejected_at_input():
    with pytest.raises(ValueError):
        make_inputs(supplier_rating=Decimal("9"))


# --- Determinism, renormalization, score boundaries -------------------------


def test_identical_inputs_produce_identical_results():
    inputs = make_inputs(moq_units=10, dropshipping_supported=True, stock_quantity=100)
    assert analyze_supplier(inputs) == analyze_supplier(inputs)


def test_missing_dimensions_are_excluded_and_weights_renormalize():
    """Operational speed / fulfillment / trust stay unknown here -- the score
    must come ONLY from order_flexibility + stock_viability, renormalized
    over their combined weight (0.25 + 0.20 = 0.45), never diluted by the
    3 missing dimensions as if they were zero."""
    inputs = make_inputs(
        moq_units=1,
        unit_cost=Decimal("5"),
        shipping_cost=Decimal("2"),
        payment_terms_days=10,
        stock_quantity=1,
        review_count=1,
        years_active=1,
    )
    result = analyze_supplier(inputs)

    assert result.operational_speed_score is None
    assert result.fulfillment_capability_score is None
    assert result.trust_score is None
    assert result.order_flexibility_score == pytest.approx(100.0)  # moq=1
    assert result.stock_viability_score == pytest.approx(60.0)  # qty=1, moq=1 -> ratio 1
    # (100*0.25 + 60*0.20) / (0.25+0.20) = 37 / 0.45
    assert result.supplier_score == pytest.approx(82.22, abs=0.01)


def test_blockers_are_not_hidden_by_a_high_average():
    """A supplier can score reasonably well on paper while still being BLOCKED."""
    inputs = make_inputs(
        moq_units=1,  # maximally flexible -> pulls the average up
        dispatch_time_days=1,
        delivery_time_days=1,  # very fast -> pulls the average up
        dropshipping_supported=True,
        invoice_available=True,
        stock_quantity=0,  # but there is literally no stock
    )
    result = analyze_supplier(inputs)
    assert result.operational_status == "BLOCKED"
    # The numeric score can still exist (shown ALONGSIDE the blocker, not hidden by it).
    assert result.supplier_score is not None


@pytest.mark.parametrize(
    "overrides",
    [
        dict(moq_units=1, dispatch_time_days=1, delivery_time_days=1, stock_quantity=1000,
             dropshipping_supported=True, blind_shipping_supported=True, tracking_available=True,
             invoice_available=True, return_policy_available=True, business_verified=True,
             contact_available=True, supplier_rating=Decimal("5"), review_count=1000),
        dict(moq_units=1000, minimum_order_value=Decimal("20000"), dispatch_time_days=60,
             delivery_time_days=60, stock_quantity=0, dropshipping_supported=False,
             blind_shipping_supported=False, tracking_available=False, invoice_available=False,
             return_policy_available=False, business_verified=False, contact_available=False,
             supplier_rating=Decimal("0"), review_count=1000),
    ],
)
def test_supplier_score_always_within_0_to_100(overrides):
    result = analyze_supplier(make_inputs(**overrides))
    assert result.supplier_score is not None
    assert 0.0 <= result.supplier_score <= 100.0


def test_evidence_completeness_independent_of_supplier_quality():
    """A terrible-but-fully-documented supplier and a great-but-sparse supplier
    must have completeness driven only by HOW MUCH is known, not by quality."""
    terrible_but_documented = analyze_supplier(
        make_inputs(
            moq_units=1000,
            minimum_order_value=Decimal("20000"),
            unit_cost=Decimal("1"),
            shipping_cost=Decimal("1"),
            payment_terms_days=0,
            stock_quantity=0,
            stock_available=False,
            dispatch_time_days=60,
            delivery_time_days=60,
            tracking_available=False,
            dropshipping_supported=False,
            blind_shipping_supported=False,
            invoice_available=False,
            return_policy_available=False,
            business_verified=False,
            contact_available=False,
            supplier_rating=Decimal("0"),
            review_count=1000,
            years_active=0,
        )
    )
    great_but_sparse = analyze_supplier(make_inputs(moq_units=1))

    assert terrible_but_documented.supplier_score < great_but_sparse.order_flexibility_score
    assert terrible_but_documented.evidence_completeness_score > great_but_sparse.evidence_completeness_score
