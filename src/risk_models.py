"""Provider-neutral input model for Risk analysis (Phase 10).

== Source / input evaluation (written BEFORE any scoring code) ==

A. Risk-related fields already available in this project: scattered
   across other phases' own models (`SupplierInputs.stock_quantity`,
   `LogisticsInputs.observed_damage_rate`/`observed_return_rate`,
   Margin's cost buffers, Competition's seller concentration). None of
   these are accessible to Risk Analysis directly -- Phase 10 does not
   import any prior analysis module (see "Future orchestration
   boundary" below). They exist in the project, just not here yet.
B. Risk data currently manual: ALL of it, specifically for `RiskInputs`.
   This is NOT a claim that the project has no external integrations
   at all -- Phase 3 already integrates Mercado Livre
   (`src.integrations.mercadolivre`) and Phase 4 already integrates
   Apify/Google Trends (`src.integrations.apify_trends`). The precise
   claim is narrower: no external integration currently populates
   `RiskInputs`, and Risk Analysis itself (`src/risk_analysis.py`) has
   no integration of its own and never will directly -- every field
   here is explicit, manually-supplied input today, the same strategy
   `src/margin_models.py`/`src/supplier_models.py`/`src/logistics_models.py`
   used before any integration existed for THEM. A future orchestrator
   may populate `RiskInputs` from those already-integrated phases'
   validated outputs (or from new integrations) without
   `src/risk_analysis.py` ever importing or coupling to them directly
   -- see "Future orchestration boundary" below.
C. Fields that could later come from integrations: `observed_damage_rate`/
   `observed_return_rate` (from marketplace order data), price history
   underlying `observed_price_volatility_percent` (from marketplace
   price tracking), `historical_stockout_rate` (from inventory
   history), `platform_dependency_percent` (from sales-channel
   analytics), `advertising_dependency_percent` (from ad-platform
   spend data), `supplier_count` (from supplier records).
D. Unavailable fields today: regulatory status, brand/IP legal status,
   recall databases, real historical price series, channel-level sales
   breakdowns, ad-spend data -- no integration exists for any of these.
E. Strong risk signals: `primary_supplier_dependency_percent` (direct,
   precise concentration evidence), `observed_return_rate`/
   `observed_damage_rate` at a high value (direct observed evidence),
   `recall_history_present=True` (a concrete historical fact),
   `regulatory_uncertainty=True`/`brand_ip_uncertainty=True` (an
   explicit acknowledgment that investigation is needed).
F. Weak signals: `supplier_count` ALONE (does not prove independence --
   5 suppliers where one does 95% of volume is still highly
   concentrated; see "Dependency risk" below), `seasonality_level`
   (currently a manual judgment call, not derived from real historical
   trend data -- documented as provisional until a future Trend
   Analysis integration can populate it).
G. Risk claims that must NEVER be inferred by this module: the legality
   of a product (`regulatory_uncertainty` is an investigation flag,
   never a legal conclusion), IP/trademark infringement from a brand
   name (`brand_ip_uncertainty` is an investigation flag, never an
   infringement finding), future stockouts from a CURRENT stock level
   (that belongs to Supplier Analysis; `historical_stockout_rate` here
   must be a real OBSERVED historical frequency, never derived from
   today's stock count), future price volatility from a SINGLE price
   point (`observed_price_volatility_percent` must be an already-
   computed historical metric, never invented from one observation),
   and "high risk" from any merely MISSING field (see "Risk vs.
   uncertainty" below).

== Risk vs. uncertainty ==

`supplier_count = 1` is an OBSERVED concentration risk (we know there
is exactly one known supplier). `supplier_count = None` is UNCERTAINTY
(we simply don't know) -- it is NOT evidence of single-source
dependency and must never be scored as if it were. This is why
`analyze_risk()` produces a `risk_score` AND a separate
`evidence_completeness_score`: a low score with low completeness means
"what little we know looks fine, but we barely know anything," not
"this is safe."

== Dependency risk: complementary, not double-counted ==

`supplier_count` and `primary_supplier_dependency_percent` measure
related but DIFFERENT things: `supplier_count` is a structural count of
known alternatives; `primary_supplier_dependency_percent` is the actual
share of volume/spend concentrated in the largest one. Five known
suppliers where one still accounts for 95% of volume is still highly
concentrated, despite looking diversified by count alone -- so both
are kept as separate, differently-weighted sub-signals in
`src/risk_analysis.py` (dependency percent weighted higher, since it is
the more precise, direct signal), rather than collapsing them into one
field or rejecting one as redundant.

== Platform / advertising dependency: concentration, not blame ==

`platform_dependency_percent` and `advertising_dependency_percent`
measure CONCENTRATION on a single channel or acquisition method, never
an opinion about that channel or method. 100% of sales via a single
marketplace is a concentration risk regardless of which marketplace it
is; this module never names or blames a specific platform.
`advertising_dependency_percent` measures ACQUISITION dependency only
-- it never infers profitability or CAC, which remains exclusively
Margin Analysis's responsibility.

== Rejected / deferred fields (and why) ==

- `demand_variability_level`: deferred. Unlike `seasonality_level`
  (which has an explicit, documented 0-100 scale definition), a
  general "demand variability" manual input has no clear, defensible
  semantics without real historical trend data behind it -- entering
  it by hand today would just be a disguised, duplicated guess at what
  Trend Analysis already measures. Revisit once a future orchestrator
  can feed in a real derived instability metric from
  `src/trend_analysis.py`'s output.
- `single_channel_dependency` (boolean): rejected. It would be
  strictly less informative than the already-included
  `platform_dependency_percent` (100% dependency IS single-channel
  dependency, with more precision) -- keeping both would be
  redundant, not complementary, unlike the supplier_count /
  primary_supplier_dependency_percent pair above.

== Tri-state booleans (same discipline as Phases 8-9) ==

`regulatory_uncertainty`, `brand_ip_uncertainty`, `recall_history_present`,
`replacement_supplier_available`, `alternative_fulfillment_available`
are all `bool | None`: `True` (verified/flagged yes), `False`
(verified/checked no -- a real, informative absence), `None` (not
evaluated). `None` is never coalesced to `False` downstream.

`regulatory_uncertainty=True` means "there is known unresolved
regulatory/compliance uncertainty requiring investigation" -- NOT "this
product is illegal." `brand_ip_uncertainty=True` means "there is an
unresolved concern about trademark/brand/resale authorization/IP
requiring investigation" -- NOT "this infringes." Both are
investigation flags, never legal determinations, documented identically
here and in `src/risk_analysis.py`.

== Rate semantics: 0-1 fractions, except one explicit exception ==

Every percentage/rate field below is a fraction in `[0, 1]` (e.g. `0.8`
means 80%), consistent with every prior phase's CLI convention
(`parse_optional_rate`). The ONE deliberate exception is
`seasonality_level`, which is an integer on a `[0, 100]` scale by this
phase's own definition (0 = little observed seasonality, 100 = extreme
dependence on a narrow seasonal window) -- this is called out
explicitly in its docstring, its CLI prompt, and its validation range
specifically so the two conventions are never confused.

== Future orchestration boundary ==

This module and `src/risk_analysis.py` import NOTHING from
`src.demand_analysis`, `src.trend_analysis`, `src.competition_analysis`,
`src.margin_analysis`, `src.supplier_analysis`, `src.logistics_analysis`,
or `src.integrations` -- NOT because `src.integrations` is empty (it
already contains real, working integrations: `src.integrations.mercadolivre`
since Phase 3, `src.integrations.apify_trends` since Phase 4), but
because Risk Analysis must stay decoupled from HOW any upstream data
was obtained or computed. A future orchestrator may one day compose
normalized outputs from those already-integrated phases (or from new
integrations) into a `RiskInputs` instance (see `src/risk_analysis.py`'s
module docstring for the target architecture diagram), but Risk
Analysis itself stays deterministic, provider-neutral, and decoupled
from how any of those other scores are computed internally.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_OPTIONAL_RATE_FIELDS = (
    "primary_supplier_dependency_percent",
    "platform_dependency_percent",
    "advertising_dependency_percent",
    "observed_price_volatility_percent",
    "historical_stockout_rate",
    "observed_return_rate",
    "observed_damage_rate",
)
_OPTIONAL_BOOL_FIELDS = (
    "regulatory_uncertainty",
    "brand_ip_uncertainty",
    "recall_history_present",
    "replacement_supplier_available",
    "alternative_fulfillment_available",
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
class RiskInputs:
    """Explicit, user-supplied risk/uncertainty inputs for one product.

    Only `product_name` is mandatory. Every other field defaults to
    `None` ("not evaluated / unknown"), never to a fabricated low-risk
    value. No cross-field conflict validation exists here -- unlike
    Phase 7/8, there is no ambiguous dual representation of the same
    fact in this schema; `supplier_count` and
    `primary_supplier_dependency_percent` are deliberately allowed to
    coexist (see module docstring, "Dependency risk").
    """

    product_name: str

    # Dependency
    supplier_count: int | None = None
    primary_supplier_dependency_percent: Decimal | None = None
    platform_dependency_percent: Decimal | None = None
    advertising_dependency_percent: Decimal | None = None

    # Observed instability / continuity
    observed_price_volatility_percent: Decimal | None = None
    historical_stockout_rate: Decimal | None = None
    observed_return_rate: Decimal | None = None
    observed_damage_rate: Decimal | None = None

    # Market structure
    seasonality_level: int | None = None  # 0-100 scale, NOT a 0-1 rate

    # Exposure (investigation flags, never legal/IP conclusions)
    regulatory_uncertainty: bool | None = None
    brand_ip_uncertainty: bool | None = None
    recall_history_present: bool | None = None

    # Operational mitigants
    replacement_supplier_available: bool | None = None
    alternative_fulfillment_available: bool | None = None

    def __post_init__(self) -> None:
        if not self.product_name or not self.product_name.strip():
            raise ValueError("product_name must not be empty")

        self.supplier_count = _to_int("supplier_count", self.supplier_count)
        if self.supplier_count is not None and self.supplier_count < 0:
            raise ValueError("supplier_count must not be negative")

        for name in _OPTIONAL_RATE_FIELDS:
            setattr(self, name, _to_decimal(name, getattr(self, name)))
        for name in _OPTIONAL_RATE_FIELDS:
            _validate_rate(name, getattr(self, name))

        self.seasonality_level = _to_int("seasonality_level", self.seasonality_level)
        if self.seasonality_level is not None and not (0 <= self.seasonality_level <= 100):
            raise ValueError(
                f"seasonality_level must be between 0 and 100 (it is a 0-100 scale, "
                f"NOT a 0-1 rate like the fields above), got {self.seasonality_level}"
            )

        for name in _OPTIONAL_BOOL_FIELDS:
            _validate_bool(name, getattr(self, name))
