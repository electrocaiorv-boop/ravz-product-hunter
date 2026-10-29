"""Provider-neutral input model for Logistics analysis.

Like `src/margin_models.py` and `src/supplier_models.py`, this is a
direct input contract -- there is no carrier/supplier/marketplace
integration in this project yet. A future carrier API or marketplace
logistics adapter could one day populate a `LogisticsInputs`, but it
would still only ever PRODUCE one, never bypass it -- see
docs/MAINTENANCE.md.

== Logistics Analysis does not duplicate Supplier or Margin Analysis ==

`estimated_delivery_days` here is the CUSTOMER-facing delivery time
(movement from seller/warehouse to the end customer, i.e. the
"last-mile" leg) -- it is a completely different leg of the journey
from Phase 8's `lead_time_days`/`dispatch_time_days`/`delivery_time_days`,
which are about SOURCING (supplier to seller). Confusing these two is
exactly the kind of semantic bug this project checks for explicitly;
never read one as the other.

`known_shipping_cost` and `packaging_cost` are recorded here purely as
OBSERVED LOGISTICS EVIDENCE. This module never computes profitability,
margin, or contribution profit from them -- there is no `sale_price`
field here at all, so it is architecturally impossible to compute a
margin from this model even by accident. That calculation belongs
exclusively to `src/margin_analysis.py`.

== Boolean tri-state, same discipline as Phase 8 ==

Every yes/no field is `bool | None`: `True` (verified yes), `False`
(verified no -- a real, informative absence), `None` (unknown). Never
coalesce `None` to `False` downstream.

== Physical dimensions: units and validation ==

`weight_kg`, `length_cm`/`width_cm`/`height_cm` -- the unit is always
in the field name, and never mixed. If supplied, physical values must
be strictly positive: a `0` would not represent "no weight/no size", it
would represent physically meaningless data for a real, tangible
product, so `0` and negative values are both rejected. `None` ("we
don't know yet") is the correct way to represent "not measured", not
`0`.

`dimensional_weight_divisor` is an OPTIONAL, EXPLICIT, user-supplied
configurable input -- never a hardcoded universal constant. Different
carriers use different divisors (common real-world values include
5000 and 6000, among others, depending on carrier and unit
convention), so this module makes no assumption: if the divisor isn't
supplied, dimensional weight simply isn't computed, rather than being
computed with a guessed value presented as fact.

`observed_damage_rate` and `observed_return_rate` are fractions in
`[0, 1]`, meant to carry ACTUAL historical observations (e.g. "3 of 40
past shipments arrived damaged" -> 0.075) -- never a probability
inferred from `fragile` or any other property flag. See
`src/logistics_analysis.py` for why these are kept architecturally
separate from the handling-risk dimension.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_OPTIONAL_POSITIVE_MONEY_OR_MEASURE_FIELDS = (
    "weight_kg",
    "length_cm",
    "width_cm",
    "height_cm",
    "dimensional_weight_divisor",
)
_OPTIONAL_NON_NEGATIVE_MONEY_FIELDS = ("packaging_cost", "known_shipping_cost")
_OPTIONAL_RATE_FIELDS = ("observed_damage_rate", "observed_return_rate")
_OPTIONAL_BOOL_FIELDS = (
    "fragile",
    "liquid",
    "hazardous",
    "perishable",
    "temperature_sensitive",
    "stackable",
    "requires_special_handling",
    "extra_packaging_required",
    "supplier_fulfilled",
    "seller_fulfilled",
    "warehouse_required",
    "tracking_available",
    "insurance_available",
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


def _validate_rate(name: str, value: Decimal | None) -> None:
    if value is not None and not (Decimal("0") <= value <= Decimal("1")):
        raise ValueError(f"{name} must be a fraction between 0 and 1, got {value}")


@dataclass
class LogisticsInputs:
    """Explicit, user-supplied logistics/handling inputs for one product.

    Only `product_name` is mandatory. Every other field defaults to
    `None` ("unknown"), never to a fabricated False or zero.
    """

    product_name: str

    # Physical
    weight_kg: Decimal | None = None
    length_cm: Decimal | None = None
    width_cm: Decimal | None = None
    height_cm: Decimal | None = None
    dimensional_weight_divisor: Decimal | None = None

    # Handling
    fragile: bool | None = None
    liquid: bool | None = None
    hazardous: bool | None = None
    perishable: bool | None = None
    temperature_sensitive: bool | None = None
    stackable: bool | None = None
    requires_special_handling: bool | None = None

    # Packaging
    extra_packaging_required: bool | None = None
    packaging_cost: Decimal | None = None

    # Fulfillment
    supplier_fulfilled: bool | None = None
    seller_fulfilled: bool | None = None
    warehouse_required: bool | None = None

    # Shipping
    known_shipping_cost: Decimal | None = None
    estimated_delivery_days: int | None = None
    tracking_available: bool | None = None
    insurance_available: bool | None = None

    # Observed operational history
    observed_damage_rate: Decimal | None = None
    observed_return_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if not self.product_name or not self.product_name.strip():
            raise ValueError("product_name must not be empty")

        for name in _OPTIONAL_POSITIVE_MONEY_OR_MEASURE_FIELDS:
            setattr(self, name, _to_decimal(name, getattr(self, name)))
        for name in _OPTIONAL_NON_NEGATIVE_MONEY_FIELDS:
            setattr(self, name, _to_decimal(name, getattr(self, name)))
        for name in _OPTIONAL_RATE_FIELDS:
            setattr(self, name, _to_decimal(name, getattr(self, name)))
        self.estimated_delivery_days = _to_int(
            "estimated_delivery_days", self.estimated_delivery_days
        )

        for name in _OPTIONAL_BOOL_FIELDS:
            _validate_bool(name, getattr(self, name))

        for name in _OPTIONAL_POSITIVE_MONEY_OR_MEASURE_FIELDS:
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError(f"{name} must be greater than 0 if supplied (0 is not meaningful)")

        for name in _OPTIONAL_NON_NEGATIVE_MONEY_FIELDS:
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must not be negative")

        if self.estimated_delivery_days is not None and self.estimated_delivery_days < 0:
            raise ValueError("estimated_delivery_days must not be negative")

        for name in _OPTIONAL_RATE_FIELDS:
            _validate_rate(name, getattr(self, name))
