"""Provider-neutral input model for Supplier / sourcing-viability analysis.

Like `src/margin_models.py`, this is a direct input contract, not
something assembled from a fetched API response -- there is no
supplier integration in this project yet. A future supplier directory,
B2B marketplace API, or crawler could one day populate a
`SupplierInputs`, but it would still only ever PRODUCE one, never
bypass it -- see docs/MAINTENANCE.md for that architectural rule.

== A Mercado Livre seller is NOT a supplier (critical guardrail) ==

A retail marketplace listing is never proof of wholesale availability,
dropshipping support, stable supply, a supplier relationship, resale
authorization, stock continuity, invoice issuance, or acceptable lead
time. Nothing in this module reads from `src.integrations.mercadolivre`
or any marketplace data -- every field here must come from an explicit,
separate sourcing investigation (a real conversation/contract with a
supplier), never inferred from a product listing. This rule is
architectural, not just documentation: this module imports nothing
from any integration.

== Boolean tri-state semantics (critical) ==

Every boolean field here is `bool | None`, carrying three distinct
states:

    True  -> verified/known to be the case
    False -> verified/known NOT to be the case (an observed absence)
    None  -> unknown -- we simply have not verified this

`invoice_available = False` means "we checked, and this supplier does
not issue invoices." `invoice_available = None` means "we have not
checked." Never coalesce `None` to `False` anywhere downstream --
`src/supplier_analysis.py` excludes unknown booleans from scoring
entirely, it never scores them as a negative.

== MOQ, minimum order value, and lead-time precedence ==

`moq_units` (Minimum Order Quantity) must be >= 1 if given -- a MOQ of
1 is a real, meaningful, maximally-flexible value; 0 is not a
meaningful "minimum" at all, so an unconstrained MOQ is represented as
`None`, not `0`. Same reasoning for `minimum_order_value` (> 0 if
given).

`lead_time_days` is the TOTAL time from order to receipt.
`dispatch_time_days` is the time the supplier needs before shipment
leaves. `delivery_time_days` is transport time after dispatch. If BOTH
`dispatch_time_days` and `delivery_time_days` are supplied together
with an explicit `lead_time_days`, that is a conflicting double
representation (which total should win?) and is rejected -- supply
either the explicit total, or the two components (which
`src/supplier_analysis.py` sums), not both at once. Supplying only one
of dispatch/delivery alongside an explicit `lead_time_days` is NOT a
conflict (it's additional detail about one component of a stated
total) and is allowed.

Note the deliberate asymmetry with `src/margin_models.py`'s fee
conflicts: a stock/MOQ mismatch (`stock_quantity < moq_units`) is NOT
rejected here at construction time, unlike a fee representation
conflict. That mismatch is a real, analyzable business condition (a
genuine hard blocker), not an ambiguous data representation -- it is
intentionally allowed to construct so `src/supplier_analysis.py` can
surface it as an explicit, visible blocker instead of silently
rejecting the input.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_OPTIONAL_MONEY_FIELDS = ("unit_cost", "minimum_order_value", "shipping_cost")
_OPTIONAL_INT_FIELDS = (
    "moq_units",
    "payment_terms_days",
    "stock_quantity",
    "dispatch_time_days",
    "delivery_time_days",
    "lead_time_days",
    "review_count",
    "years_active",
)
_OPTIONAL_BOOL_FIELDS = (
    "stock_available",
    "tracking_available",
    "dropshipping_supported",
    "blind_shipping_supported",
    "invoice_available",
    "return_policy_available",
    "business_verified",
    "contact_available",
)


def _to_decimal(name: str, value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} is not a valid number: {value!r}") from exc


def _to_int(name: str, value) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{name} must be a number, got a boolean: {value!r}")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} is not a valid whole number: {value!r}") from exc


def _validate_bool(name: str, value) -> None:
    if value is not None and not isinstance(value, bool):
        raise ValueError(f"{name} must be True, False, or None, got {value!r}")


@dataclass
class SupplierInputs:
    """Explicit, user-supplied sourcing-viability inputs for one supplier/product pair.

    Only `product_name` and `supplier_name` are mandatory identifiers.
    Every other field defaults to `None` ("unknown"), never to a
    fabricated False or zero.
    """

    product_name: str
    supplier_name: str

    # Commercial
    unit_cost: Decimal | None = None
    moq_units: int | None = None
    minimum_order_value: Decimal | None = None
    shipping_cost: Decimal | None = None
    payment_terms_days: int | None = None

    # Inventory
    stock_quantity: int | None = None
    stock_available: bool | None = None

    # Operations
    dispatch_time_days: int | None = None
    delivery_time_days: int | None = None
    lead_time_days: int | None = None
    tracking_available: bool | None = None

    # Dropshipping
    dropshipping_supported: bool | None = None
    blind_shipping_supported: bool | None = None

    # Trust / compliance
    invoice_available: bool | None = None
    return_policy_available: bool | None = None
    business_verified: bool | None = None
    contact_available: bool | None = None

    # Evidence
    supplier_rating: Decimal | None = None  # 0-5 scale -- see module docstring
    review_count: int | None = None
    years_active: int | None = None

    def __post_init__(self) -> None:
        if not self.product_name or not self.product_name.strip():
            raise ValueError("product_name must not be empty")
        if not self.supplier_name or not self.supplier_name.strip():
            raise ValueError("supplier_name must not be empty")

        for name in _OPTIONAL_MONEY_FIELDS:
            setattr(self, name, _to_decimal(name, getattr(self, name)))
        for name in _OPTIONAL_INT_FIELDS:
            setattr(self, name, _to_int(name, getattr(self, name)))
        self.supplier_rating = _to_decimal("supplier_rating", self.supplier_rating)

        for name in _OPTIONAL_BOOL_FIELDS:
            _validate_bool(name, getattr(self, name))

        if self.unit_cost is not None and self.unit_cost < 0:
            raise ValueError("unit_cost must not be negative")
        if self.moq_units is not None and self.moq_units < 1:
            raise ValueError("moq_units must be at least 1 (0 is not a meaningful minimum)")
        if self.minimum_order_value is not None and self.minimum_order_value <= 0:
            raise ValueError(
                "minimum_order_value must be greater than 0 (0 is not a meaningful minimum)"
            )
        if self.shipping_cost is not None and self.shipping_cost < 0:
            raise ValueError("shipping_cost must not be negative")
        for name in (
            "payment_terms_days",
            "stock_quantity",
            "dispatch_time_days",
            "delivery_time_days",
            "lead_time_days",
            "review_count",
            "years_active",
        ):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")

        if self.supplier_rating is not None and not (
            Decimal("0") <= self.supplier_rating <= Decimal("5")
        ):
            raise ValueError(
                "supplier_rating must be on a 0-5 scale (this is this project's input "
                f"contract, not a universal provider behavior), got {self.supplier_rating}"
            )

        if (
            self.lead_time_days is not None
            and self.dispatch_time_days is not None
            and self.delivery_time_days is not None
        ):
            raise ValueError(
                "provide either lead_time_days OR both dispatch_time_days and "
                "delivery_time_days, not both representations of the total -- "
                "that would be an ambiguous double representation of lead time"
            )
