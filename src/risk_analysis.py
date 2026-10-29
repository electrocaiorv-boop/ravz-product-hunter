"""Deterministic Risk analysis (Phase 10).

This module knows NOTHING about HTTP, Apify, Mercado Livre, carrier
APIs, browser automation, scraping, n8n, or LLMs -- and, deliberately,
nothing about `src.demand_analysis`, `src.trend_analysis`,
`src.competition_analysis`, `src.margin_analysis`,
`src.supplier_analysis`, or `src.logistics_analysis` either. It only
imports `src.risk_models`. Given the same `RiskInputs`, `analyze_risk()`
always returns an identical `RiskAnalysisResult`.

== The business question ==

    "What could make this product opportunity fail, become unstable,
    or create disproportionate downside -- even if the other
    dimensions look good?"

Distinct from Demand ("does the market appear interested?"),
Competition ("how difficult is the competitive environment?"), Margin
("does the known unit economics look attractive?"), Supplier ("can the
product be sourced reliably, right now?"), and Logistics ("can the
product be handled and delivered efficiently?"). A product can score
well on every one of those and still be fragile: one supplier, one
sales channel, a volatile purchase price, a history of damaged
shipments. Risk Analysis exists to surface that fragility explicitly.

== Future orchestration boundary (read before adding an import here) ==

    Trend Analysis --------\\
    Demand Analysis --------\\
    Competition Analysis ----\\
    Margin Analysis ----------> Orchestrator -> RiskInputs -> Risk Analysis
    Supplier Analysis -------/
    Logistics Analysis ------/

A future orchestrator MAY one day compose normalized outputs from those
modules (e.g. a Competition Score, a Margin buffer, Logistics's
observed failure rates) into a `RiskInputs` instance. Risk Analysis
itself must NEVER import any of those analysis modules directly --
doing so would tightly couple this module to their internal formulas
and implementation details. The composition step belongs to the future
orchestrator, not here.

== Risk Score direction: 0 = low risk, 100 = high risk ==

This is the OPPOSITE external contract from Supplier Score, Logistics
Score, and Margin Score (where higher is better). Phase 1 already
treats Risk as an inverted negative dimension, so this phase matches
that existing convention rather than inventing a new one. Unlike Phase
9 (where "ease" had to be computed directly to avoid an internal-vs-
external direction mismatch), every anchor table and sub-signal
function here is written to directly increase with BADNESS -- there is
no internal "goodness" framing to invert at all, which removes an
entire class of the Phase-9-style direction bug. Higher Risk Score =
worse opportunity. See `test_risk_score_direction_*` in
`tests/test_risk_analysis.py` for regression coverage of this
specifically.

== Risk vs. uncertainty (see `src/risk_models.py` for the full policy) ==

`supplier_count = 1` is OBSERVED concentration risk. `supplier_count =
None` is UNCERTAINTY, not evidence of anything. Every dimension
function below excludes unknown (`None`) sub-signals from its weighted
average instead of defaulting them to a "safe" value -- missing
evidence is never silently rewarded with a low risk score, which is
why `risk_score` is reported alongside a separate
`evidence_completeness_score` (see below).

== Hard blockers: NONE are reachable, by design (Phase 9 lesson applied from day one) ==

A hard blocker must mean "we have evidence this is currently
IMPOSSIBLE," not "we have evidence this looks bad." Nothing in
`RiskInputs` reaches that bar: a 100% `observed_return_rate`, a known
`recall_history_present=True`, or a `regulatory_uncertainty=True` flag
are all severe risk EVIDENCE, not proof of impossibility -- a product
with a history of recalls or an unresolved compliance question can
still, today, be sold; it's just risky to do so. `_detect_blockers()`
therefore always returns an empty list, and `BLOCKED` is consequently
UNREACHABLE from any current input combination. Both the function and
the `BLOCKED` status value are kept as a reserved extension point --
not dead code to delete -- for a future field that could genuinely
prove impossibility (none exists in this schema today). This directly
applies the correction made in Phase 9's hardening review, this time
designed in from the start rather than discovered afterward.

Severe evidence (a high observed return/damage rate, recall history,
high volatility or stockout history, simultaneous regulatory + brand/IP
uncertainty) instead flows into the ordinary weighted dimension scores
AND produces an explanatory warning -- it is never hidden, and never
escalated into a fabricated blocker.

== Risk dimensions (0-100 PROVISIONAL business heuristic) ==

Five dimensions, weighted average over whichever are available
(missing dimensions excluded, weights renormalized):

    dependency_risk_score             (base weight 0.25): from
        `supplier_count`, `primary_supplier_dependency_percent`,
        `platform_dependency_percent`, `advertising_dependency_percent`.
        `supplier_count` and `primary_supplier_dependency_percent` are
        COMPLEMENTARY, not duplicate, signals -- see
        `src/risk_models.py`. The percent is weighted higher (1.5) than
        the count (0.8) because it is the more precise, direct measure
        of actual concentration.
    supply_continuity_risk_score      (base weight 0.20): from
        `historical_stockout_rate` (a real OBSERVED frequency, never
        inferred from current stock) plus the mitigating capability
        flags `replacement_supplier_available`/
        `alternative_fulfillment_available`.
    volatility_risk_score             (base weight 0.20): from
        `observed_price_volatility_percent` (an already-computed
        historical metric, never inferred from one price) plus
        `seasonality_level` (already on a 0-100 risk-shaped scale by
        definition, used directly, no interpolation).
    operational_history_risk_score    (base weight 0.20): from
        `observed_return_rate`, `observed_damage_rate`, and
        `recall_history_present` (a concrete historical fact, weighted
        highest of the three).
    compliance_uncertainty_risk_score (base weight 0.15): from
        `regulatory_uncertainty`/`brand_ip_uncertainty` -- investigation
        flags, weighted lowest of the five dimensions deliberately,
        since an unresolved-uncertainty flag is a weaker claim than
        directly observed evidence (the other four dimensions are all
        built from real counts/rates/history), and this project must
        never let an un-investigated flag dominate a score the way a
        concrete observation would.

== Evidence Completeness: WEIGHTED, not a flat count ==

14 evidence items (see `EVIDENCE_WEIGHTS`) summing to exactly 1.0.
`regulatory_uncertainty` and `primary_supplier_dependency_percent` are
weighted among the highest, per this phase's explicit instruction that
they matter more than minor metadata.

`risk_score` is withheld (`None`) unless `evidence_completeness_score`
reaches `MIN_COMPLETENESS_FOR_SCORE` (35%) -- chosen to match Phase 8's
threshold, but NOT copied mechanically: Risk evidence, like Supplier
evidence, is dominated by investigative/relationship-based information
(compliance checks, historical rates, dependency percentages) rather
than directly measurable physical facts (contrast Phase 7's cost
categories at 50%, or Phase 9's weight/dimensions at 40%) -- much of it
requires dedicated investigation beyond a quick glance, so demanding a
higher bar would make the score unusable in exactly the early-stage
situations where a directional risk check is most wanted.

== Risk status ==

    BLOCKED           -- a hard blocker is present. UNREACHABLE today
                         -- reserved for a future field that can prove
                         impossibility.
    INSUFFICIENT_DATA -- no blocker, but `risk_score` is withheld
    SEVERE            -- no blocker, score >= 75
    HIGH              -- no blocker, 50 <= score < 75
    MODERATE          -- no blocker, 25 <= score < 50
    LOW               -- no blocker, score < 25

Unlike Phase 9, no severe-evidence-forces-worse-status override is
needed here: severe observed rates / recall history / uncertainty flags
already flow directly into the weighted dimension scores (they are
score INPUTS, not score-independent blockers-in-waiting the way Phase
9's observed rates were), so their severity is naturally reflected in
`risk_score` itself.

All weights/anchors/thresholds are module-level constants, meant to be
recalibrated once real outcome data exists -- not treated as final.
This Risk Score is NOT wired into the Phase 1 Opportunity Scoring
Engine yet.
"""

from dataclasses import dataclass, field
from decimal import Decimal

from src.risk_models import RiskInputs

WEIGHT_DEPENDENCY_RISK = 0.25
WEIGHT_SUPPLY_CONTINUITY_RISK = 0.20
WEIGHT_VOLATILITY_RISK = 0.20
WEIGHT_OPERATIONAL_HISTORY_RISK = 0.20
WEIGHT_COMPLIANCE_UNCERTAINTY_RISK = 0.15

MIN_COMPLETENESS_FOR_SCORE = 0.35

SEVERE_THRESHOLD = 75.0
HIGH_THRESHOLD = 50.0
MODERATE_THRESHOLD = 25.0

SEVERE_RETURN_RATE_WARNING_THRESHOLD = Decimal("0.5")
SEVERE_DAMAGE_RATE_WARNING_THRESHOLD = Decimal("0.5")
HIGH_STOCKOUT_RATE_WARNING_THRESHOLD = Decimal("0.3")
HIGH_VOLATILITY_WARNING_THRESHOLD = Decimal("0.3")

# Piecewise-linear anchors: (x, risk_score). PROVISIONAL, documented,
# adjustable -- not universal truths. Unlike Phase 9's "ease" anchors,
# these increase directly with badness, matching the external
# contract, so no inversion step exists anywhere in this module.
CONCENTRATION_RISK_ANCHORS = ((0.0, 0.0), (0.5, 35.0), (0.8, 65.0), (1.0, 100.0))
SUPPLIER_COUNT_RISK_ANCHORS = ((1, 100.0), (2, 70.0), (3, 50.0), (5, 20.0), (10, 0.0))
STOCKOUT_RATE_RISK_ANCHORS = ((0.0, 0.0), (0.05, 20.0), (0.15, 50.0), (0.30, 80.0), (0.50, 100.0))
PRICE_VOLATILITY_RISK_ANCHORS = ((0.0, 0.0), (0.05, 15.0), (0.15, 45.0), (0.30, 75.0), (0.50, 100.0))
OPERATIONAL_RATE_RISK_ANCHORS = (
    (0.0, 0.0), (0.05, 15.0), (0.15, 40.0), (0.30, 70.0), (0.50, 95.0), (1.0, 100.0)
)

# Boolean sub-signal risk values: (risk_if_true, risk_if_false, weight).
RECALL_HISTORY_SIGNAL = (100.0, 0.0, 1.3)
REPLACEMENT_SUPPLIER_SIGNAL = (0.0, 70.0, 1.0)  # True = mitigant (lower risk)
ALTERNATIVE_FULFILLMENT_SIGNAL = (0.0, 60.0, 0.8)  # True = mitigant (lower risk)
REGULATORY_UNCERTAINTY_SIGNAL = (70.0, 0.0, 1.0)  # True = unresolved, not proven
BRAND_IP_UNCERTAINTY_SIGNAL = (70.0, 0.0, 1.0)  # True = unresolved, not proven

# Weighted evidence completeness -- sums to exactly 1.0.
EVIDENCE_WEIGHTS = {
    "supplier_count": 0.07,
    "primary_supplier_dependency_percent": 0.12,
    "platform_dependency_percent": 0.08,
    "advertising_dependency_percent": 0.05,
    "observed_price_volatility_percent": 0.08,
    "historical_stockout_rate": 0.08,
    "observed_return_rate": 0.07,
    "observed_damage_rate": 0.07,
    "seasonality_level": 0.05,
    "regulatory_uncertainty": 0.11,
    "brand_ip_uncertainty": 0.08,
    "recall_history_present": 0.08,
    "replacement_supplier_available": 0.03,
    "alternative_fulfillment_available": 0.03,
}


def _interpolate(x, anchors) -> float:
    """Piecewise-linear interpolation over (x, y) anchors, clamped at the ends."""
    x = float(x)
    if x <= anchors[0][0]:
        return anchors[0][1]
    if x >= anchors[-1][0]:
        return anchors[-1][1]
    for (x0, y0), (x1, y1) in zip(anchors, anchors[1:]):
        if x0 <= x <= x1:
            ratio = (x - x0) / (x1 - x0)
            return y0 + ratio * (y1 - y0)
    return anchors[-1][1]  # unreachable; anchors are exhaustive by construction


def _bool_risk(value: bool | None, signal: tuple) -> float | None:
    if value is None:
        return None
    risk_if_true, risk_if_false, _weight = signal
    return risk_if_true if value else risk_if_false


def _weighted_average(parts: list[tuple[float, float]]) -> float | None:
    known = [(v, w) for v, w in parts if v is not None]
    if not known:
        return None
    total_weight = sum(w for _, w in known)
    return sum(v * w for v, w in known) / total_weight


@dataclass
class RiskAnalysisResult:
    """Deterministic output of analyze_risk(). risk_score is PROVISIONAL."""

    product_name: str
    risk_score: float | None
    evidence_completeness_score: float
    risk_status: str
    dependency_risk_score: float | None
    supply_continuity_risk_score: float | None
    volatility_risk_score: float | None
    operational_history_risk_score: float | None
    compliance_uncertainty_risk_score: float | None
    observed: dict
    derived: dict
    unavailable: list[str]
    blockers: list[str]
    warnings: list[str]
    notes: list[str] = field(default_factory=list)


def _dependency_risk_score(inputs: RiskInputs) -> float | None:
    supplier_count_risk = (
        _interpolate(inputs.supplier_count, SUPPLIER_COUNT_RISK_ANCHORS)
        if inputs.supplier_count is not None
        else None
    )
    primary_dependency_risk = (
        _interpolate(inputs.primary_supplier_dependency_percent, CONCENTRATION_RISK_ANCHORS)
        if inputs.primary_supplier_dependency_percent is not None
        else None
    )
    platform_risk = (
        _interpolate(inputs.platform_dependency_percent, CONCENTRATION_RISK_ANCHORS)
        if inputs.platform_dependency_percent is not None
        else None
    )
    advertising_risk = (
        _interpolate(inputs.advertising_dependency_percent, CONCENTRATION_RISK_ANCHORS)
        if inputs.advertising_dependency_percent is not None
        else None
    )
    return _weighted_average(
        [
            (supplier_count_risk, 0.8),
            (primary_dependency_risk, 1.5),
            (platform_risk, 1.0),
            (advertising_risk, 0.7),
        ]
    )


def _supply_continuity_risk_score(inputs: RiskInputs) -> float | None:
    stockout_risk = (
        _interpolate(inputs.historical_stockout_rate, STOCKOUT_RATE_RISK_ANCHORS)
        if inputs.historical_stockout_rate is not None
        else None
    )
    replacement_risk = _bool_risk(inputs.replacement_supplier_available, REPLACEMENT_SUPPLIER_SIGNAL)
    fulfillment_risk = _bool_risk(inputs.alternative_fulfillment_available, ALTERNATIVE_FULFILLMENT_SIGNAL)
    return _weighted_average(
        [
            (stockout_risk, 1.3),
            (replacement_risk, REPLACEMENT_SUPPLIER_SIGNAL[2]),
            (fulfillment_risk, ALTERNATIVE_FULFILLMENT_SIGNAL[2]),
        ]
    )


def _volatility_risk_score(inputs: RiskInputs) -> float | None:
    price_volatility_risk = (
        _interpolate(inputs.observed_price_volatility_percent, PRICE_VOLATILITY_RISK_ANCHORS)
        if inputs.observed_price_volatility_percent is not None
        else None
    )
    seasonality_risk = float(inputs.seasonality_level) if inputs.seasonality_level is not None else None
    return _weighted_average([(price_volatility_risk, 1.2), (seasonality_risk, 1.0)])


def _operational_history_risk_score(inputs: RiskInputs) -> float | None:
    return_risk = (
        _interpolate(inputs.observed_return_rate, OPERATIONAL_RATE_RISK_ANCHORS)
        if inputs.observed_return_rate is not None
        else None
    )
    damage_risk = (
        _interpolate(inputs.observed_damage_rate, OPERATIONAL_RATE_RISK_ANCHORS)
        if inputs.observed_damage_rate is not None
        else None
    )
    recall_risk = _bool_risk(inputs.recall_history_present, RECALL_HISTORY_SIGNAL)
    return _weighted_average(
        [(return_risk, 1.0), (damage_risk, 1.0), (recall_risk, RECALL_HISTORY_SIGNAL[2])]
    )


def _compliance_uncertainty_risk_score(inputs: RiskInputs) -> float | None:
    regulatory_risk = _bool_risk(inputs.regulatory_uncertainty, REGULATORY_UNCERTAINTY_SIGNAL)
    brand_ip_risk = _bool_risk(inputs.brand_ip_uncertainty, BRAND_IP_UNCERTAINTY_SIGNAL)
    return _weighted_average(
        [(regulatory_risk, REGULATORY_UNCERTAINTY_SIGNAL[2]), (brand_ip_risk, BRAND_IP_UNCERTAINTY_SIGNAL[2])]
    )


def _detect_blockers(inputs: RiskInputs) -> list[str]:
    """Genuine proof-of-impossibility contradictions only. Always returns
    `[]` today -- see module docstring ("Hard blockers: NONE are
    reachable, by design"). Kept as a reserved extension point; never
    repurpose it for severity, which belongs in `_detect_warnings()`.
    """
    return []


def _detect_warnings(inputs: RiskInputs) -> list[str]:
    warnings = []
    if (
        inputs.observed_return_rate is not None
        and inputs.observed_return_rate >= SEVERE_RETURN_RATE_WARNING_THRESHOLD
    ):
        warnings.append(
            f"observed return rate is {inputs.observed_return_rate} -- severe negative "
            "evidence of operational history, but it does NOT by itself prove the "
            "opportunity is unworkable"
        )
    if (
        inputs.observed_damage_rate is not None
        and inputs.observed_damage_rate >= SEVERE_DAMAGE_RATE_WARNING_THRESHOLD
    ):
        warnings.append(
            f"observed damage rate is {inputs.observed_damage_rate} -- severe negative "
            "evidence of operational history, but it does NOT by itself prove the "
            "opportunity is unworkable"
        )
    if (
        inputs.historical_stockout_rate is not None
        and inputs.historical_stockout_rate >= HIGH_STOCKOUT_RATE_WARNING_THRESHOLD
    ):
        warnings.append(
            f"historical stockout rate is {inputs.historical_stockout_rate} -- supply "
            "continuity has been unreliable in the observed history"
        )
    if (
        inputs.observed_price_volatility_percent is not None
        and inputs.observed_price_volatility_percent >= HIGH_VOLATILITY_WARNING_THRESHOLD
    ):
        warnings.append(
            f"observed price volatility is {inputs.observed_price_volatility_percent} -- "
            "margin assumptions computed elsewhere should be treated as fragile, not stable"
        )
    if inputs.recall_history_present is True:
        warnings.append(
            "a prior recall is on record -- investigate root cause and current status; "
            "this is evidence, not a safety determination"
        )
    if inputs.regulatory_uncertainty is True and inputs.brand_ip_uncertainty is True:
        warnings.append(
            "both regulatory and brand/IP uncertainty are flagged -- multiple unresolved "
            "compliance questions compound; investigate before scaling. Neither flag is a "
            "legal conclusion"
        )
    if (
        inputs.primary_supplier_dependency_percent is not None
        and inputs.primary_supplier_dependency_percent == Decimal("1")
        and inputs.replacement_supplier_available is False
    ):
        warnings.append(
            "fully dependent on a single supplier with no known replacement -- this "
            "concentration risk is not currently mitigated"
        )
    return warnings


def _evidence_completeness_score(inputs: RiskInputs) -> float:
    known_weight = 0.0
    for field_name, weight in EVIDENCE_WEIGHTS.items():
        if getattr(inputs, field_name) is not None:
            known_weight += weight
    return round(known_weight * 100, 2)


def analyze_risk(inputs: RiskInputs) -> RiskAnalysisResult:
    """Compute a deterministic, provisional Risk Score and Evidence Completeness."""
    notes: list[str] = []

    dependency_risk = _dependency_risk_score(inputs)
    supply_continuity_risk = _supply_continuity_risk_score(inputs)
    volatility_risk = _volatility_risk_score(inputs)
    operational_history_risk = _operational_history_risk_score(inputs)
    compliance_uncertainty_risk = _compliance_uncertainty_risk_score(inputs)

    components = (
        (dependency_risk, WEIGHT_DEPENDENCY_RISK),
        (supply_continuity_risk, WEIGHT_SUPPLY_CONTINUITY_RISK),
        (volatility_risk, WEIGHT_VOLATILITY_RISK),
        (operational_history_risk, WEIGHT_OPERATIONAL_HISTORY_RISK),
        (compliance_uncertainty_risk, WEIGHT_COMPLIANCE_UNCERTAINTY_RISK),
    )
    available = [(c, w) for c, w in components if c is not None]

    unavailable = []
    if dependency_risk is None:
        unavailable.append("dependency risk (supplier count / primary supplier / platform / advertising dependency)")
    if supply_continuity_risk is None:
        unavailable.append("supply continuity risk (historical stockout rate / replacement supplier / alternative fulfillment)")
    if volatility_risk is None:
        unavailable.append("volatility risk (observed price volatility / seasonality level)")
    if operational_history_risk is None:
        unavailable.append("operational history risk (observed return rate / observed damage rate / recall history)")
    if compliance_uncertainty_risk is None:
        unavailable.append("compliance/IP uncertainty risk (regulatory uncertainty / brand/IP uncertainty)")
    unavailable.append("legal/regulatory determination (regulatory_uncertainty is an investigation flag, never a legal conclusion)")
    unavailable.append("IP/trademark infringement determination (brand_ip_uncertainty is an investigation flag, never an infringement finding)")
    unavailable.append("projected future price volatility (only an already-observed historical metric, if supplied, is ever shown -- never estimated from a single price)")
    unavailable.append("projected future stockout probability (only an already-observed historical rate, if supplied, is ever shown -- never inferred from current stock level)")

    evidence_completeness_score = _evidence_completeness_score(inputs)

    blockers = _detect_blockers(inputs)
    warnings = _detect_warnings(inputs)

    if evidence_completeness_score / 100.0 >= MIN_COMPLETENESS_FOR_SCORE and available:
        total_weight = sum(w for _, w in available)
        risk_score = round(sum(c * w for c, w in available) / total_weight, 2)
    else:
        risk_score = None
        notes.append(
            f"Risk Score withheld: evidence completeness is "
            f"{evidence_completeness_score:.2f}% (below the "
            f"{int(MIN_COMPLETENESS_FOR_SCORE * 100)}% minimum) -- a single 0-100 score "
            "from this little evidence would be misleading"
        )

    if blockers:
        risk_status = "BLOCKED"
    elif risk_score is None:
        risk_status = "INSUFFICIENT_DATA"
    elif risk_score >= SEVERE_THRESHOLD:
        risk_status = "SEVERE"
    elif risk_score >= HIGH_THRESHOLD:
        risk_status = "HIGH"
    elif risk_score >= MODERATE_THRESHOLD:
        risk_status = "MODERATE"
    else:
        risk_status = "LOW"

    observed = {
        "supplier_count": inputs.supplier_count,
        "primary_supplier_dependency_percent": inputs.primary_supplier_dependency_percent,
        "platform_dependency_percent": inputs.platform_dependency_percent,
        "advertising_dependency_percent": inputs.advertising_dependency_percent,
        "observed_price_volatility_percent": inputs.observed_price_volatility_percent,
        "historical_stockout_rate": inputs.historical_stockout_rate,
        "observed_return_rate": inputs.observed_return_rate,
        "observed_damage_rate": inputs.observed_damage_rate,
        "seasonality_level": inputs.seasonality_level,
        "regulatory_uncertainty": inputs.regulatory_uncertainty,
        "brand_ip_uncertainty": inputs.brand_ip_uncertainty,
        "recall_history_present": inputs.recall_history_present,
        "replacement_supplier_available": inputs.replacement_supplier_available,
        "alternative_fulfillment_available": inputs.alternative_fulfillment_available,
    }
    derived = {
        "dependency_risk_score": dependency_risk,
        "supply_continuity_risk_score": supply_continuity_risk,
        "volatility_risk_score": volatility_risk,
        "operational_history_risk_score": operational_history_risk,
        "compliance_uncertainty_risk_score": compliance_uncertainty_risk,
    }

    return RiskAnalysisResult(
        product_name=inputs.product_name,
        risk_score=risk_score,
        evidence_completeness_score=evidence_completeness_score,
        risk_status=risk_status,
        dependency_risk_score=dependency_risk,
        supply_continuity_risk_score=supply_continuity_risk,
        volatility_risk_score=volatility_risk,
        operational_history_risk_score=operational_history_risk,
        compliance_uncertainty_risk_score=compliance_uncertainty_risk,
        observed=observed,
        derived=derived,
        unavailable=unavailable,
        blockers=blockers,
        warnings=warnings,
        notes=notes,
    )
