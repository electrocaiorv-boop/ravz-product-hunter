"""Deterministic Margin / unit-economics analysis.

This module knows NOTHING about HTTP, Apify, Mercado Livre, or any
integration -- it only imports `src.margin_models`. No LLM, no
randomness, no wall-clock dependency. Given the same `MarginInputs`,
`analyze_margin()` always returns an identical `MarginAnalysisResult`.

== The business question ==

    "After ALL KNOWN costs, how much money appears to remain from each sale?"

This is distinct from Demand ("does the market appear interested?")
and Competition ("how difficult does the competitive environment
appear?"). A product can have strong demand, weak competition, and
still be a bad idea if its margin is thin or negative -- these three
domains are evaluated independently and never merged.

== Core financial concepts (with the worked example from CLAUDE.md) ==

    Revenue               = sale_price
    Gross profit          = sale_price - product_cost
    Gross margin %        = gross_profit / sale_price * 100
    Markup %              = gross_profit / product_cost * 100
                             (undefined, None, when product_cost == 0)
    Total variable cost   = product_cost + marketplace fee + shipping
                             + packaging + tax + payment cost +
                             advertising cost per sale + return reserve
                             + other variable cost -- but see "known
                             costs only" below: unknown categories are
                             EXCLUDED from this sum, never treated as 0.
    Contribution profit    = sale_price - total_variable_cost (known only)
    Contribution margin %  = contribution_profit / sale_price * 100

Worked example (sale_price=100, product_cost=50, marketplace_fee=15,
shipping=10, everything else unknown):

    Gross profit        = 100 - 50 = 50
    Gross margin        = 50 / 100 * 100 = 50%
    Markup               = 50 / 50 * 100 = 100%          <- NOT the same as margin!
    Known variable cost  = 50 + 15 + 10 = 75
    Contribution profit  = 100 - 75 = 25
    Contribution margin  = 25 / 100 * 100 = 25%

MARGIN AND MARKUP ARE NOT THE SAME THING: margin is profit as a
fraction of SALE PRICE (what you charged); markup is profit as a
fraction of COST (what you paid). The same R$50 of profit is a 50%
margin and a 100% markup in this example -- never call one the other.

GROSS PROFIT vs. CONTRIBUTION PROFIT vs. NET PROFIT: gross profit only
subtracts product cost (COGS). Contribution profit subtracts every
KNOWN variable cost tied to the sale (fees, shipping, packaging, tax,
payment processing, ads, return reserve, other). Neither is "net
profit" -- net profit would also subtract FIXED company expenses
(salaries, rent, software subscriptions, accounting, etc.), which this
module never sees and never estimates. This module NEVER uses the term
"net profit" for either figure.

== Missing cost != zero cost (Phase 5/6 lesson, re-applied) ==

A cost category that is `None` on `MarginInputs` is EXCLUDED from
`total_variable_cost`'s sum -- it does not contribute 0, because 0
would claim "we know this costs nothing," which is a different and
stronger claim than "we don't know." `cost_completeness_score` (below)
is how this module communicates how much of the picture is actually
known, instead of letting missing data silently vanish into a
seemingly-complete number.

== Cost Completeness Score, not "Confidence" ==

Phase 5/6 used "Confidence" for noisy, externally-sampled, provider-
dependent evidence (search interest, a marketplace page sample) where
the central risk was correlated features from one source masquerading
as independent corroboration. Margin's missing data is a different
kind of thing entirely: it is not sampled or noisy, it is simply
"how many of the 8 optional cost categories did the user actually
supply." There is no sampling bias and no source-independence question
to bound here, so this module does NOT reuse Phase 5/6's
coverage-cap/completeness-blend formula. Instead:

    cost_completeness_score = 100 * known_optional_categories / 8

The 8 optional categories are: marketplace fee, seller shipping,
packaging, tax, payment cost, advertising cost per sale, return
reserve, other variable cost. `sale_price` and `product_cost` are
mandatory prerequisites, not part of this count.

== Margin Score: only when defensible ==

`gross_profit`/`gross_margin_percent`/`markup_percent` only need
`sale_price` + `product_cost` (always known, by construction) and are
ALWAYS computed. `contribution_profit`/`contribution_margin_percent`
are also always computed, from whatever costs ARE known -- but they
are explicitly labeled "known costs only" everywhere they appear.

The single 0-100 `margin_score`, however, is withheld (`None`) unless
`cost_completeness_score` reaches `MIN_COST_COMPLETENESS_FOR_SCORE`
(50%, i.e. at least 4 of 8 categories known). Presenting one
confident-looking number from a contribution margin based on 1 of 8
known costs would overstate how much is actually known; showing the
known-cost metrics directly, without a final verdict, is the more
honest choice below that threshold.

== Margin Score formula (PROVISIONAL business heuristic) ==

Piecewise-linear interpolation over `contribution_margin_percent`,
anchored at the qualitative bands sketched in CLAUDE.md -- NOT a bare
"margin% * constant", and NOT an empirically validated model:

    <= -10%  -> 0    (meaningfully loss-making)
       0%    -> 15   (break-even: not losing money, but very weak)
       5%    -> 35
      10%    -> 55
      20%    -> 75
      30%    -> 90
    >= 50%   -> 100

Linearly interpolated between consecutive anchors, clamped at the
ends. All anchors are module-level constants, meant to be recalibrated
once real outcome data exists.

== Break-even price ==

Naive "sum all costs and call that the break-even point" is wrong
whenever any cost is a PERCENTAGE of the sale price itself (marketplace
fee rate, tax rate): raising the price to cover a percentage fee also
raises that fee. The correct derivation, solving contribution_profit(P)
= 0 for P:

    contribution_profit(P) = P - fixed_total - P * rate_sum = 0
    => P * (1 - rate_sum) = fixed_total
    => P = fixed_total / (1 - rate_sum)          [only if 1 - rate_sum > 0]

where `fixed_total` sums every KNOWN absolute cost (product_cost,
marketplace_fee_amount OR fixed_marketplace_fee, shipping, packaging,
tax_amount, payment cost, ads, return reserve, other) and `rate_sum`
sums every KNOWN percentage rate (marketplace_fee_rate, tax_rate). If
`1 - rate_sum <= 0`, known percentage costs alone consume all or more
than all revenue -- no finite price could break even, and
`break_even_price` is `None` with a clear note, never a crash or a
negative/nonsensical number. Like contribution profit, this is always
computed from KNOWN costs only, and is not gated by
`cost_completeness_score` -- it is inherently and explicitly a
"based on what we know" figure throughout.

== Decimal rounding policy ==

Every individually meaningful monetary amount (gross_profit,
marketplace_fee_total, tax_total, known_total_variable_cost,
contribution_profit, break_even_price) is rounded to 2 decimal places
with `ROUND_HALF_UP` as soon as it is computed, then used (already
rounded) in any further sum -- the same way real invoicing rounds each
line item to the cent before totaling, rather than carrying unrounded
fractions of a cent through the whole calculation and rounding only at
the very end (which can silently shift the final cent depending on
operation order). `ROUND_HALF_UP` ("round half away from zero") is a
deliberate, documented policy choice -- the common everyday rounding
convention -- over Python's statistical default (`ROUND_HALF_EVEN`,
"banker's rounding"), chosen because this is a single-transaction
report meant to match a user's intuitive expectation, not a
high-volume ledger where rounding bias matters statistically.
Percentages are rounded the same way, to 2 decimal places.
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from src.margin_models import MarginInputs

TWO_PLACES = Decimal("0.01")
HUNDRED = Decimal("100")

TOTAL_OPTIONAL_COST_CATEGORIES = 8
MIN_COST_COMPLETENESS_FOR_SCORE = 0.5  # fraction (0-1): at least 4 of 8 categories

# Piecewise-linear anchors: (contribution_margin_percent threshold, score).
# PROVISIONAL business heuristic -- see module docstring. Configurable,
# not an empirically validated model.
MARGIN_SCORE_ANCHORS = (
    (Decimal("-10"), 0.0),
    (Decimal("0"), 15.0),
    (Decimal("5"), 35.0),
    (Decimal("10"), 55.0),
    (Decimal("20"), 75.0),
    (Decimal("30"), 90.0),
    (Decimal("50"), 100.0),
)


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _round_percent(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


@dataclass
class MarginAnalysisResult:
    """Deterministic output of analyze_margin(). margin_score is PROVISIONAL.

    `total_variable_cost` and `contribution_profit`/`contribution_margin_percent`
    are computed from KNOWN costs only -- see `cost_completeness_score`
    for how much of the full picture that represents.
    """

    product_name: str
    sale_price: Decimal
    product_cost: Decimal
    gross_profit: Decimal
    gross_margin_percent: Decimal
    markup_percent: Decimal | None
    marketplace_fee_total: Decimal | None
    tax_total: Decimal | None
    total_variable_cost: Decimal
    contribution_profit: Decimal
    contribution_margin_percent: Decimal
    break_even_price: Decimal | None
    margin_score: float | None
    cost_completeness_score: float
    observed: dict
    derived: dict
    unavailable: list[str]
    notes: list[str] = field(default_factory=list)


def _marketplace_fee_total(inputs: MarginInputs) -> Decimal | None:
    if inputs.marketplace_fee_amount is not None:
        return _round_money(inputs.marketplace_fee_amount)
    if inputs.marketplace_fee_rate is None and inputs.fixed_marketplace_fee is None:
        return None
    total = Decimal("0")
    if inputs.marketplace_fee_rate is not None:
        total += inputs.sale_price * inputs.marketplace_fee_rate
    if inputs.fixed_marketplace_fee is not None:
        total += inputs.fixed_marketplace_fee
    return _round_money(total)


def _tax_total(inputs: MarginInputs) -> Decimal | None:
    if inputs.tax_amount is not None:
        return _round_money(inputs.tax_amount)
    if inputs.tax_rate is not None:
        return _round_money(inputs.sale_price * inputs.tax_rate)
    return None


def _interpolate_margin_score(contribution_margin_percent: Decimal) -> float:
    anchors = MARGIN_SCORE_ANCHORS
    if contribution_margin_percent <= anchors[0][0]:
        return anchors[0][1]
    if contribution_margin_percent >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= contribution_margin_percent <= x1:
            ratio = float(contribution_margin_percent - x0) / float(x1 - x0)
            return round(y0 + ratio * (y1 - y0), 4)
    return anchors[-1][1]  # unreachable; anchors are exhaustive by construction


def analyze_margin(inputs: MarginInputs) -> MarginAnalysisResult:
    """Compute a deterministic, provisional unit-economics analysis."""
    notes: list[str] = []
    unavailable: list[str] = []

    gross_profit = _round_money(inputs.sale_price - inputs.product_cost)
    gross_margin_percent = _round_percent(gross_profit / inputs.sale_price * HUNDRED)

    if inputs.product_cost == 0:
        markup_percent = None
        notes.append("markup is undefined when product_cost is zero (division by zero)")
    else:
        markup_percent = _round_percent(gross_profit / inputs.product_cost * HUNDRED)

    marketplace_fee_total = _marketplace_fee_total(inputs)
    tax_total = _tax_total(inputs)

    known_variable_total = inputs.product_cost
    known_categories = 0

    if marketplace_fee_total is not None:
        known_variable_total += marketplace_fee_total
        known_categories += 1
    else:
        unavailable.append("marketplace fee")

    if inputs.seller_shipping_cost is not None:
        known_variable_total += inputs.seller_shipping_cost
        known_categories += 1
    else:
        unavailable.append("seller shipping cost")

    if inputs.packaging_cost is not None:
        known_variable_total += inputs.packaging_cost
        known_categories += 1
    else:
        unavailable.append("packaging cost")

    if tax_total is not None:
        known_variable_total += tax_total
        known_categories += 1
    else:
        unavailable.append("tax")

    if inputs.payment_cost is not None:
        known_variable_total += inputs.payment_cost
        known_categories += 1
    else:
        unavailable.append("payment cost")

    if inputs.advertising_cost_per_sale is not None:
        known_variable_total += inputs.advertising_cost_per_sale
        known_categories += 1
    else:
        unavailable.append("advertising cost per sale")

    if inputs.return_reserve is not None:
        known_variable_total += inputs.return_reserve
        known_categories += 1
    else:
        unavailable.append("return/refund reserve")

    if inputs.other_variable_cost is not None:
        known_variable_total += inputs.other_variable_cost
        known_categories += 1
    else:
        unavailable.append("other variable cost")

    total_variable_cost = _round_money(known_variable_total)
    contribution_profit = _round_money(inputs.sale_price - total_variable_cost)
    contribution_margin_percent = _round_percent(
        contribution_profit / inputs.sale_price * HUNDRED
    )

    cost_completeness_score = round(
        100.0 * known_categories / TOTAL_OPTIONAL_COST_CATEGORIES, 2
    )

    # Break-even: solve contribution_profit(P) = 0 for P.
    fixed_total = inputs.product_cost
    rate_sum = Decimal("0")

    if inputs.marketplace_fee_amount is not None:
        fixed_total += inputs.marketplace_fee_amount
    elif inputs.marketplace_fee_rate is not None:
        rate_sum += inputs.marketplace_fee_rate
    if inputs.fixed_marketplace_fee is not None:
        fixed_total += inputs.fixed_marketplace_fee

    if inputs.tax_amount is not None:
        fixed_total += inputs.tax_amount
    elif inputs.tax_rate is not None:
        rate_sum += inputs.tax_rate

    for optional_amount in (
        inputs.seller_shipping_cost,
        inputs.packaging_cost,
        inputs.payment_cost,
        inputs.advertising_cost_per_sale,
        inputs.return_reserve,
        inputs.other_variable_cost,
    ):
        if optional_amount is not None:
            fixed_total += optional_amount

    denominator = Decimal("1") - rate_sum
    if denominator <= 0:
        break_even_price = None
        notes.append(
            "break-even is impossible: known percentage-based costs consume "
            "100% or more of revenue -- no finite sale price could cover costs"
        )
    else:
        break_even_price = _round_money(fixed_total / denominator)

    if cost_completeness_score / 100.0 >= MIN_COST_COMPLETENESS_FOR_SCORE:
        margin_score = round(_interpolate_margin_score(contribution_margin_percent), 2)
    else:
        margin_score = None
        notes.append(
            f"Margin Score withheld: only {known_categories} of "
            f"{TOTAL_OPTIONAL_COST_CATEGORIES} optional cost categories are known "
            f"(below the {int(MIN_COST_COMPLETENESS_FOR_SCORE * 100)}% minimum) -- "
            "a single 0-100 score from this little evidence would be misleading"
        )

    unavailable.append(
        "net profit (fixed company expenses -- salaries, rent, software, "
        "accounting, etc. -- are never included)"
    )

    observed = {
        "sale_price": inputs.sale_price,
        "product_cost": inputs.product_cost,
        "seller_shipping_cost": inputs.seller_shipping_cost,
        "packaging_cost": inputs.packaging_cost,
        "payment_cost": inputs.payment_cost,
        "advertising_cost_per_sale": inputs.advertising_cost_per_sale,
        "return_reserve": inputs.return_reserve,
        "other_variable_cost": inputs.other_variable_cost,
    }
    derived = {
        "marketplace_fee_total": marketplace_fee_total,
        "tax_total": tax_total,
        "gross_profit": gross_profit,
        "gross_margin_percent": gross_margin_percent,
        "markup_percent": markup_percent,
        "total_variable_cost": total_variable_cost,
        "contribution_profit": contribution_profit,
        "contribution_margin_percent": contribution_margin_percent,
        "break_even_price": break_even_price,
    }

    return MarginAnalysisResult(
        product_name=inputs.product_name,
        sale_price=inputs.sale_price,
        product_cost=inputs.product_cost,
        gross_profit=gross_profit,
        gross_margin_percent=gross_margin_percent,
        markup_percent=markup_percent,
        marketplace_fee_total=marketplace_fee_total,
        tax_total=tax_total,
        total_variable_cost=total_variable_cost,
        contribution_profit=contribution_profit,
        contribution_margin_percent=contribution_margin_percent,
        break_even_price=break_even_price,
        margin_score=margin_score,
        cost_completeness_score=cost_completeness_score,
        observed=observed,
        derived=derived,
        unavailable=unavailable,
        notes=notes,
    )
