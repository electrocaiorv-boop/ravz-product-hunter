"""Provider-neutral input model for Margin / unit-economics analysis.

This module defines ONLY the input contract (`MarginInputs`) and its
validation. It imports nothing external -- no HTTP, no Mercado Livre,
no Apify, no LLM. Unlike earlier phases, there is no "build from a
provider response" step here: `MarginInputs` IS the direct, explicit
input (typically typed by a user in the CLI), not something assembled
from a fetched API response. A future marketplace-fee or tax adapter
could one day populate some of these fields automatically, but that
adapter would still produce a `MarginInputs`, never bypass it -- see
docs/MAINTENANCE.md for that architectural rule.

== Why Decimal, not float ==

Python's `float` is binary floating point: it cannot exactly represent
most decimal fractions (0.1 + 0.2 != 0.3 in float arithmetic). For
money, those tiny representation errors are unacceptable -- they
compound across additions and can silently shift a result by cents in
ways that are hard to reproduce and impossible to justify to a user who
is reconciling real currency. `decimal.Decimal` uses base-10
arbitrary-precision arithmetic: constructed from a string or an int, it
represents decimal fractions exactly. Every monetary and rate field
here is `Decimal | None` (never `float`), and `_to_decimal()` always
converts via `str(value)` rather than `Decimal(value)` directly for
floats, specifically to avoid importing a float's binary representation
error into the Decimal (e.g. `Decimal(0.1)` is "0.1000000000000000055511151231257827021181583404541015625";
`Decimal(str(0.1))` is exactly "0.1").

== Rates are fractions, not percentages ==

`marketplace_fee_rate` and `tax_rate` are fractions in `[0, 1]`
(`0.12` for 12%), NOT the number `12`. This is deliberately validated
(values outside `[0, 1]` are rejected) because mixing up "12" and
"0.12" is exactly the kind of silent percentage bug this project's
engineering review explicitly warns against. Percentages that this
module and `src/margin_analysis.py` COMPUTE (gross_margin_percent,
markup_percent, etc.) are, by contrast, human-readable numbers scaled
to 100 (e.g. `25.00` meaning "25%") -- never confuse the two
conventions within this codebase.

== Missing cost != zero cost ==

Every optional field below is `None` when the value is genuinely
unknown, and a real `Decimal` (including `Decimal("0")`) when the value
is known and happens to be zero. `seller_shipping_cost = Decimal("0")`
means "we know the seller pays no shipping"; `seller_shipping_cost =
None` means "we do not know." `src/margin_analysis.py` preserves this
distinction throughout -- an unknown cost is EXCLUDED from sums, never
silently treated as zero.

== Precedence rules for conflicting representations ==

`marketplace_fee_amount` is a complete override: if supplied, it IS the
total marketplace fee, and `marketplace_fee_rate` /
`fixed_marketplace_fee` (which would otherwise be used to COMPUTE that
same total) must both be `None`. Supplying `marketplace_fee_amount`
together with either raises `ValueError` -- there is no silent
precedence order, because guessing which one "wins" risks double- or
under-counting the fee. The same rule applies to `tax_amount` vs.
`tax_rate`.

`marketplace_fee_rate` and `fixed_marketplace_fee` MAY be supplied
together: that is not a conflict, it models a real-world fee structure
(a percentage plus an additional flat component), and the two are
additive -- see `src/margin_analysis.py`.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_OPTIONAL_MONEY_FIELDS = (
    "marketplace_fee_amount",
    "fixed_marketplace_fee",
    "seller_shipping_cost",
    "packaging_cost",
    "tax_amount",
    "payment_cost",
    "advertising_cost_per_sale",
    "return_reserve",
    "other_variable_cost",
)
_RATE_FIELDS = ("marketplace_fee_rate", "tax_rate")


def _to_decimal(name: str, value) -> Decimal | None:
    """Coerce int/float/str/Decimal to Decimal; None stays None.

    Floats are converted via str() to avoid importing binary
    floating-point representation error into the Decimal.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{name} is not a valid number: {value!r}") from exc


def _validate_non_negative(name: str, value: Decimal | None) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")


def _validate_rate(name: str, value: Decimal | None) -> None:
    if value is not None and not (Decimal("0") <= value <= Decimal("1")):
        raise ValueError(
            f"{name} must be a fraction between 0 and 1 (e.g. 0.12 for 12%), got {value}"
        )


@dataclass
class MarginInputs:
    """Explicit, user-supplied unit-economics inputs for one product/query.

    `product_name`, `sale_price`, and `product_cost` are mandatory --
    without both prices, not even a basic gross-margin figure can be
    computed. Every other field is optional and defaults to `None`
    ("unknown"), never to a fabricated zero.
    """

    product_name: str
    sale_price: Decimal
    product_cost: Decimal

    marketplace_fee_amount: Decimal | None = None
    marketplace_fee_rate: Decimal | None = None
    fixed_marketplace_fee: Decimal | None = None

    seller_shipping_cost: Decimal | None = None
    packaging_cost: Decimal | None = None

    tax_amount: Decimal | None = None
    tax_rate: Decimal | None = None

    payment_cost: Decimal | None = None
    advertising_cost_per_sale: Decimal | None = None
    return_reserve: Decimal | None = None
    other_variable_cost: Decimal | None = None

    def __post_init__(self) -> None:
        self.sale_price = _to_decimal("sale_price", self.sale_price)
        self.product_cost = _to_decimal("product_cost", self.product_cost)
        for name in _OPTIONAL_MONEY_FIELDS + _RATE_FIELDS:
            setattr(self, name, _to_decimal(name, getattr(self, name)))

        if not self.product_name or not self.product_name.strip():
            raise ValueError("product_name must not be empty")
        if self.sale_price is None or self.sale_price <= 0:
            raise ValueError("sale_price must be greater than 0")
        if self.product_cost is None or self.product_cost < 0:
            raise ValueError("product_cost must not be negative")

        for name in _OPTIONAL_MONEY_FIELDS:
            _validate_non_negative(name, getattr(self, name))
        for name in _RATE_FIELDS:
            _validate_rate(name, getattr(self, name))

        if self.marketplace_fee_amount is not None and (
            self.marketplace_fee_rate is not None or self.fixed_marketplace_fee is not None
        ):
            raise ValueError(
                "provide either marketplace_fee_amount OR "
                "marketplace_fee_rate/fixed_marketplace_fee, not both -- "
                "mixing them would double-count the marketplace fee"
            )
        if self.tax_amount is not None and self.tax_rate is not None:
            raise ValueError(
                "provide either tax_amount OR tax_rate, not both -- "
                "mixing them would double-count tax"
            )
