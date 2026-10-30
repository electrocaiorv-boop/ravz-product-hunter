"""Deterministic integrated Opportunity composition (Phase 11).

This module is COMPOSITION, not orchestration. It receives
already-computed domain results, translates each through a small pure
adapter into the canonical `OpportunityComponent`, and composes them
into one explainable `OpportunityAnalysisResult`.

    manually/procedurally obtained domain results
              |
              v
          adapters  (one tiny pure function per domain)
              |
              v
    Opportunity composition engine  <- this module

A FUTURE Orchestrator/Agent phase will be the thing that collects
inputs, calls the domain engines, and feeds their results in here. That
is explicitly NOT built yet: nothing in this module fetches, schedules,
retries, or decides what to analyze.

== What this module must never do ==

It imports NOTHING except `src.opportunity_models` -- not a single
domain-analysis module, not `src.integrations.*`, no HTTP client, no
LLM, no database, no n8n, no MCP. Domain results are read by attribute
(duck-typed), so the composition layer is coupled only to the canonical
contract, never to any domain's internals or import graph.

The adapters likewise must never:
    - recompute or re-derive a domain's scoring
    - perform HTTP or fetch anything
    - guess, default, or backfill a missing value
    - mutate the domain result they are given
    - invent a confidence/completeness figure
    - collapse one domain's evidence semantics into another's

They only ever READ a result and RELABEL it into the canonical shape.

== Missing is missing ==

A domain that withheld its score yields `available=False`,
`raw_score=None`, `opportunity_score=None`, `weighted_contribution=None`
and a specific `withheld_reason`. It is never converted to 0, never to
50, never to "safe", never to "average". Its weight is simply not
earned.

== Two validation layers, four readiness states ==

See `src/opportunity_models.py` for the full rationale. In short:
commercial attractiveness (search-interest family, competition, margin,
risk) and operational readiness (supplier, logistics) are separate
questions, so a product whose business case holds up but whose sourcing
and shipping were never checked gets its own readiness state --
`OPERATIONALLY_UNVALIDATED` -- instead of being lumped in with
"incomplete evidence" or, worse, marked READY.

Precedence is strict and checked worst-first:

    BLOCKED > INCOMPLETE_EVIDENCE > OPERATIONALLY_UNVALIDATED > READY

The legacy classification bands are emitted ONLY for READY.

== The false-safety guard (missing NEGATIVE evidence) ==

Naive renormalization over available weights has a dangerous asymmetry.
Suppose everything known scores 90 and Risk (weight 0.15) is unknown:

    renormalize over available only  -> 90.00
    if Risk had been known at 60     -> 0.85*90 + 0.15*40 = 82.50

The Opportunity Score would RISE from 82.50 to 90.00 precisely because
we know NOTHING about risk. That is false safety manufactured from
ignorance, and the same trap applies to Competition.

Two independent protections, because neither alone is sufficient:

1. GATE (primary). Competition and Risk are commercial requirements, so
   a missing one forces `readiness = INCOMPLETE_EVIDENCE`,
   `publishable = False`, and a withheld classification. A result with
   unknown risk can therefore never be labelled "Strong opportunity",
   no matter what the arithmetic says.

2. CEILING (numeric). The aggregate is additionally capped at the value
   it would have if each missing negative dimension were NEUTRAL:

       ceiling = (sum(w_i * o_i) + sum(w_missing_neg * 50))
                 / (sum(w_i) + sum(w_missing_neg))
       score   = min(renormalized_partial, ceiling)

   This is NOT "None -> 50". The component itself stays
   `available=False` with `raw_score=None`; nothing claims risk is 50;
   no component contribution is fabricated. The ceiling constrains only
   the AGGREGATE, so that ignorance cannot pay. It is surfaced
   explicitly via `false_safety_ceiling_applied` and a note.

   Note the deliberate asymmetry: `min()` means the guard can only ever
   LOWER a score that ignorance inflated. When the known evidence is
   already weak (partial < 50), the ceiling does not bind, so missing
   risk evidence is not turned into fake bad news either.

   The guard was re-verified against integrated-v1's hardened weights:
   Competition and Risk now carry 0.15 each (0.30 combined, up from
   0.20), so the ceiling binds HARDER than before -- the mechanism
   remains semantically correct and strictly more protective, with no
   formula change needed.

   Honest limitation: a neutral ceiling is the TIGHTEST bound available
   without fabricating evidence. It cannot make a missing-Risk score
   land exactly where a known-bad Risk would have put it -- doing so
   would require inventing a specific bad value we do not have. The
   gate, not the ceiling, is what guarantees such a result is never
   presented as validated.

Missing POSITIVE components are plainly renormalized, with no ceiling:
excluding them creates unknown upside, not false safety, and the
layered validation gates plus the coverage figures already report that
honestly.

== Blockers are never averaged away ==

A genuine domain blocker (today: only Supplier's zero-stock /
stock-below-MOQ conditions) must not vanish inside a weighted mean. A
product can score Demand 95 / Margin 90 and still be impossible to
source. Blockers are therefore checked FIRST, force
`readiness = BLOCKED` and `publishable = False`, and are surfaced
namespaced by the domain that found them. The analytical score is still
computed and shown, for transparency -- what is withheld is the
RECOMMENDATION, not the arithmetic.

== Determinism ==

Pure functions over the supplied results: no randomness, no wall-clock
reads, no I/O, no mutation. Identical inputs always produce an
identical result.
"""

from src.opportunity_models import (
    COMMERCIAL_REQUIREMENTS,
    COMPONENT_FAMILIES,
    COMPONENT_ORDER,
    COMPONENT_VALIDATION_LAYER,
    DIRECTION_NEGATIVE,
    DIRECTION_POSITIVE,
    EVIDENCE_FAMILIES,
    INTEGRATED_MODEL_VERSION,
    INTEGRATED_WEIGHTS,
    NEGATIVE_COMPONENTS,
    NEUTRAL_MIDPOINT,
    OPERATIONAL_REQUIREMENTS,
    READINESS_BLOCKED,
    READINESS_INCOMPLETE_EVIDENCE,
    READINESS_OPERATIONALLY_UNVALIDATED,
    READINESS_READY,
    TOTAL_COMMERCIAL_WEIGHT,
    TOTAL_INTEGRATED_WEIGHT,
    TOTAL_OPERATIONAL_WEIGHT,
    VALIDATION_COMMERCIAL,
    VALIDATION_OPERATIONAL,
    EvidenceProfile,
    OpportunityAnalysisResult,
    OpportunityComponent,
    classify_exact,
    to_opportunity_oriented,
)

SOURCE_DOMAINS = {
    "demand": "Demand Analysis (Phase 5)",
    "trend": "Trend Analysis (Phase 4)",
    "competition": "Competition Analysis (Phase 6)",
    "margin": "Margin Analysis (Phase 7)",
    "supplier": "Supplier Analysis (Phase 8)",
    "logistics": "Logistics Analysis (Phase 9)",
    "risk": "Risk Analysis (Phase 10)",
}

EVIDENCE_LABELS = {
    "demand": "demand confidence",
    "trend": "trend observation count",
    "competition": "competition confidence",
    "margin": "margin cost completeness",
    "supplier": "supplier evidence completeness",
    "logistics": "logistics evidence completeness",
    "risk": "risk evidence completeness",
}

NOT_SUPPLIED_REASON = "no result was supplied for this domain"


def _family_overlap_policy(family) -> str:
    """Explain, on the component itself, why it carries no weight."""
    return (
        f"evidence family '{family.name}': this component is NOT the elected "
        f"representative, so it contributes no weight. It is shown for provenance "
        f"and explainability only. {family.rationale}"
    )


# Kept as a module-level constant for tests and reports that want the
# canonical wording for the project's one declared family.
FAMILY_OVERLAP_POLICY = _family_overlap_policy(EVIDENCE_FAMILIES[0])


def _build(
    name: str,
    raw_score: float | None,
    evidence_value: float | None,
    *,
    source_status: str | None = None,
    withheld_reason: str | None = None,
) -> OpportunityComponent:
    """Assemble a canonical component. Inverts negative dimensions ONCE."""
    direction = DIRECTION_NEGATIVE if name in NEGATIVE_COMPONENTS else DIRECTION_POSITIVE
    opportunity_score = to_opportunity_oriented(raw_score, direction)
    weight = INTEGRATED_WEIGHTS[name]
    available = raw_score is not None
    return OpportunityComponent(
        name=name,
        source_domain=SOURCE_DOMAINS[name],
        direction=direction,
        configured_weight=weight,
        validation_layer=COMPONENT_VALIDATION_LAYER[name],
        available=available,
        raw_score=raw_score,
        opportunity_score=opportunity_score,
        weighted_contribution=(
            None if opportunity_score is None else opportunity_score * weight
        ),
        evidence_label=EVIDENCE_LABELS[name],
        evidence_value=evidence_value,
        source_status=source_status,
        withheld_reason=withheld_reason if raw_score is None else None,
        family=COMPONENT_FAMILIES.get(name),
    )


def _withheld_by_domain(domain_label: str) -> str:
    return (
        f"{domain_label} withheld its own score because its evidence did not meet "
        "that domain's documented minimum -- the missing score is preserved as "
        "missing, never substituted with a neutral or zero value"
    )


# --------------------------------------------------------------------------
# Adapters: one per domain. Pure translation -- no recomputation, no I/O.
# Each reads only public attributes of an already-computed domain result.
# --------------------------------------------------------------------------


def from_demand_result(result) -> OpportunityComponent:
    """Adapt a `src.demand_analysis.DemandAnalysisResult`.

    Reads `demand_score` (positive direction) and preserves
    `confidence_score` under its own name -- Demand's confidence is a
    source-independence-bounded figure and is not interchangeable with
    any other domain's evidence metric.
    """
    return _build(
        "demand",
        result.demand_score,
        result.confidence_score,
        withheld_reason=(
            "Demand Analysis could not compute a score: no demand signal was "
            "available at all"
        ),
    )


def from_trend_metrics(metrics) -> OpportunityComponent:
    """Adapt a `src.trend_analysis.TrendMetrics`.

    Reads `provisional_trend_score` (positive direction). Trend has NO
    confidence/completeness metric, so `observation_count` is carried as
    its honest evidence metadata rather than inventing one.
    """
    return _build(
        "trend",
        metrics.provisional_trend_score,
        float(metrics.observation_count),
        source_status=metrics.direction,
        withheld_reason=(
            "Trend Analysis could not compute a provisional score: the interest "
            "series had fewer than 2 usable observations"
        ),
    )


def from_competition_result(result) -> OpportunityComponent:
    """Adapt a `src.competition_analysis.CompetitionAnalysisResult`.

    Competition is a NEGATIVE dimension: `competition_score` is
    high-is-bad and is inverted exactly once here (never upstream,
    never again downstream).
    """
    return _build(
        "competition",
        result.competition_score,
        result.confidence_score,
        withheld_reason=(
            "Competition Analysis could not compute a score: no usable marketplace "
            "evidence (Mercado Livre search is unreachable in this environment)"
        ),
    )


def from_margin_result(result) -> OpportunityComponent:
    """Adapt a `src.margin_analysis.MarginAnalysisResult`.

    Preserves `cost_completeness_score` under its own name -- it counts
    known cost categories and is NOT a confidence figure.
    """
    return _build(
        "margin",
        result.margin_score,
        result.cost_completeness_score,
        withheld_reason=_withheld_by_domain("Margin Analysis"),
    )


def from_supplier_result(result) -> OpportunityComponent:
    """Adapt a `src.supplier_analysis.SupplierAnalysisResult`.

    `unit_cost` is deliberately NOT read: Supplier records it as
    sourcing evidence but never scores it, and Margin owns every
    profitability calculation. Reading it here would duplicate Margin's
    economics inside a second weighted component.
    """
    return _build(
        "supplier",
        result.supplier_score,
        result.evidence_completeness_score,
        source_status=result.operational_status,
        withheld_reason=_withheld_by_domain("Supplier Analysis"),
    )


def from_logistics_result(result) -> OpportunityComponent:
    """Adapt a `src.logistics_analysis.LogisticsAnalysisResult`.

    Logistics is already high-is-good ("ease"), so it is a POSITIVE
    dimension and must NOT be inverted.
    """
    return _build(
        "logistics",
        result.logistics_score,
        result.evidence_completeness_score,
        source_status=result.operational_status,
        withheld_reason=_withheld_by_domain("Logistics Analysis"),
    )


def from_risk_result(result) -> OpportunityComponent:
    """Adapt a `src.risk_analysis.RiskAnalysisResult`.

    Risk is a NEGATIVE dimension: `risk_score` is high-is-bad and is
    inverted exactly once here. `src/risk_analysis.py` performs no
    internal inversion, so there is no double inversion.
    """
    return _build(
        "risk",
        result.risk_score,
        result.evidence_completeness_score,
        source_status=result.risk_status,
        withheld_reason=_withheld_by_domain("Risk Analysis"),
    )


def _not_supplied(name: str) -> OpportunityComponent:
    return _build(name, None, None, withheld_reason=NOT_SUPPLIED_REASON)


ADAPTERS = {
    "demand": from_demand_result,
    "trend": from_trend_metrics,
    "competition": from_competition_result,
    "margin": from_margin_result,
    "supplier": from_supplier_result,
    "logistics": from_logistics_result,
    "risk": from_risk_result,
}


# --------------------------------------------------------------------------
# Composition engine
# --------------------------------------------------------------------------


def _elect_family_representatives(
    components: dict[str, OpportunityComponent],
) -> dict[str, OpportunityComponent]:
    """Mark exactly one member of each evidence family as weight-bearing.

    Correlated evidence must not vote twice. For each declared
    `EvidenceFamilyPolicy`, the first AVAILABLE member in its
    precedence order keeps `counted=True`; every other member is kept
    for provenance with `counted=False` and an explicit
    `overlap_policy`. If no member is available, the first by
    precedence stays the (unavailable) representative so the family is
    reported coherently as missing.
    """
    resolved = dict(components)
    for family in EVIDENCE_FAMILIES:
        members = [n for n in family.representative_precedence if n in resolved]
        if not members:
            continue
        elected = next((n for n in members if resolved[n].available), members[0])
        policy = _family_overlap_policy(family)
        for name in members:
            if name == elected:
                continue
            loser = resolved[name]
            resolved[name] = OpportunityComponent(
                **{
                    **loser.__dict__,
                    "counted": False,
                    "weighted_contribution": None,
                    "overlap_policy": policy,
                }
            )
    return resolved


def _requirement_satisfied(
    key: str, components: dict[str, OpportunityComponent]
) -> bool:
    """Is one weighted slot backed by any available evidence?

    A family slot is satisfied by ANY available member (that is the
    point of electing a representative); a plain component slot is
    satisfied only by itself.
    """
    members = [c for c in components.values() if c.family == key]
    if members:
        return any(c.available for c in members)
    component = components.get(key)
    return component is not None and component.available


def _missing_requirements(
    requirement_keys: tuple[str, ...], components: dict[str, OpportunityComponent]
) -> tuple[str, ...]:
    return tuple(
        key for key in requirement_keys if not _requirement_satisfied(key, components)
    )


def _collect_namespaced(results: dict, attribute: str) -> dict:
    """Gather per-domain blocker/warning lists, keyed by source domain."""
    collected = {}
    for name, result in results.items():
        if result is None:
            continue
        values = list(getattr(result, attribute, []) or [])
        if values:
            collected[SOURCE_DOMAINS[name]] = values
    return collected


def _build_evidence_profile(results: dict) -> EvidenceProfile:
    """Carry each domain's evidence metric across under its ORIGINAL name.

    No renaming, no averaging -- see `EvidenceProfile`'s docstring for
    why aggregating unlike evidence concepts is refused by default.
    """
    demand = results.get("demand")
    trend = results.get("trend")
    competition = results.get("competition")
    margin = results.get("margin")
    supplier = results.get("supplier")
    logistics = results.get("logistics")
    risk = results.get("risk")
    return EvidenceProfile(
        demand_confidence=None if demand is None else demand.confidence_score,
        competition_confidence=(
            None if competition is None else competition.confidence_score
        ),
        margin_cost_completeness=(
            None if margin is None else margin.cost_completeness_score
        ),
        supplier_evidence_completeness=(
            None if supplier is None else supplier.evidence_completeness_score
        ),
        logistics_evidence_completeness=(
            None if logistics is None else logistics.evidence_completeness_score
        ),
        risk_evidence_completeness=(
            None if risk is None else risk.evidence_completeness_score
        ),
        trend_observation_count=None if trend is None else trend.observation_count,
        trend_direction=None if trend is None else trend.direction,
    )


def _layer_coverage(
    components: dict[str, OpportunityComponent], layer: str, total: float
) -> float:
    """Share of ONE validation layer's weight that has any evidence."""
    earned = sum(
        c.effective_weight
        for c in components.values()
        if c.validation_layer == layer
    )
    return earned / total if total else 0.0


def _aggregate(components: dict[str, OpportunityComponent]) -> tuple:
    """Return (score, coverage, ceiling_applied, notes).

    `score` is the exact (unrounded) aggregate, or None when no weighted
    component is available at all.
    """
    notes: list[str] = []
    counted = [c for c in components.values() if c.counted]

    earned = [c for c in counted if c.available]
    earned_weight = sum(c.configured_weight for c in earned)
    numerator = sum(c.opportunity_score * c.configured_weight for c in earned)

    coverage = earned_weight / TOTAL_INTEGRATED_WEIGHT

    if not earned:
        notes.append(
            "no domain supplied a usable score: the Opportunity Score cannot be "
            "computed at all (it is reported as unavailable, never as 0)"
        )
        return None, coverage, False, notes

    partial = numerator / earned_weight

    # False-safety guard: a missing NEGATIVE dimension must not raise the
    # aggregate. See module docstring -- the component itself stays
    # unknown; only the aggregate is capped.
    missing_negative_weight = sum(
        c.configured_weight
        for c in counted
        if not c.available and c.name in NEGATIVE_COMPONENTS
    )

    ceiling_applied = False
    score = partial
    if missing_negative_weight > 0:
        ceiling = (numerator + missing_negative_weight * NEUTRAL_MIDPOINT) / (
            earned_weight + missing_negative_weight
        )
        if ceiling < partial:
            score = ceiling
            ceiling_applied = True
            notes.append(
                "false-safety guard applied: a negative dimension (competition "
                "and/or risk) is unknown, so the aggregate was capped at the value "
                "it would have if that dimension were neutral. Renormalizing "
                "without this cap would have RAISED the score purely because that "
                "evidence is missing. No component was assigned a substitute "
                "value -- it remains explicitly unknown"
            )

    return score, coverage, ceiling_applied, notes


def compose_opportunity(
    product_name: str,
    *,
    demand_result=None,
    trend_metrics=None,
    competition_result=None,
    margin_result=None,
    supplier_result=None,
    logistics_result=None,
    risk_result=None,
) -> OpportunityAnalysisResult:
    """Compose domain results into one explainable Opportunity analysis.

    Every domain argument is optional: pass the results you actually
    have. A domain you omit is reported as unavailable with an explicit
    reason -- never silently defaulted, and never treated as neutral,
    zero, or safe.

    This function performs NO fetching and NO orchestration: it does not
    know how any result was obtained and cannot obtain one itself.
    """
    if not product_name or not product_name.strip():
        raise ValueError("product_name must not be empty")

    results = {
        "demand": demand_result,
        "trend": trend_metrics,
        "competition": competition_result,
        "margin": margin_result,
        "supplier": supplier_result,
        "logistics": logistics_result,
        "risk": risk_result,
    }

    components = {
        name: (ADAPTERS[name](result) if result is not None else _not_supplied(name))
        for name, result in results.items()
    }
    components = _elect_family_representatives(components)

    score, coverage, ceiling_applied, notes = _aggregate(components)

    domain_blockers = _collect_namespaced(results, "blockers")
    domain_warnings = _collect_namespaced(results, "warnings")

    missing_components = tuple(
        sorted(name for name, c in components.items() if not c.available)
    )
    missing_commercial = _missing_requirements(COMMERCIAL_REQUIREMENTS, components)
    missing_operational = _missing_requirements(OPERATIONAL_REQUIREMENTS, components)

    commercial_complete = not missing_commercial
    operational_complete = not missing_operational

    # Strict precedence: BLOCKED > INCOMPLETE_EVIDENCE >
    # OPERATIONALLY_UNVALIDATED > READY. Commercial outranks operational
    # because an unevaluable business case makes execution moot.
    if domain_blockers:
        readiness = READINESS_BLOCKED
        withheld_reason = (
            "a domain reported a hard blocker, which cannot be averaged away: "
            + "; ".join(
                f"{domain}: {', '.join(items)}"
                for domain, items in sorted(domain_blockers.items())
            )
            + ". The analytical score above is shown for transparency only -- no "
            "recommendation is issued while a blocker stands"
        )
    elif not commercial_complete:
        readiness = READINESS_INCOMPLETE_EVIDENCE
        withheld_reason = (
            "commercial validation is incomplete (missing: "
            + ", ".join(missing_commercial)
            + "), so the business case itself cannot be evaluated yet and no "
            "classification is issued. The analytical score is shown for "
            "transparency and must NOT be read as a validated recommendation"
        )
    elif not operational_complete:
        readiness = READINESS_OPERATIONALLY_UNVALIDATED
        withheld_reason = (
            "commercial validation is COMPLETE, but operational validation is not "
            "(missing: "
            + ", ".join(missing_operational)
            + "). The opportunity looks commercially attractive and is "
            "operationally unvalidated -- nobody has confirmed it can actually be "
            "sourced and shipped. The analytical score is shown for transparency; "
            "a final recommendation is withheld until the operational evidence "
            "arrives"
        )
    else:
        readiness = READINESS_READY
        withheld_reason = None

    publishable = readiness == READINESS_READY
    classification = (
        classify_exact(score) if publishable and score is not None else None
    )

    # An explicitly NON-FINAL band, only where the commercial case is
    # fully evaluated. Deliberately not offered for INCOMPLETE_EVIDENCE
    # (the business case is not evaluable, so a band would mislead) or
    # for BLOCKED (the opportunity is moot while the blocker stands).
    analytical_band_non_final = (
        classify_exact(score)
        if readiness == READINESS_OPERATIONALLY_UNVALIDATED and score is not None
        else None
    )

    score_is_partial = coverage < 1.0
    if score_is_partial and score is not None:
        notes.append(
            f"partial analytical score: computed over {coverage * 100:.2f}% of the "
            "configured component weight. Component coverage is NOT confidence, NOT "
            "evidence completeness, and NOT accuracy"
        )

    if analytical_band_non_final is not None:
        notes.append(
            f"the analytical band '{analytical_band_non_final}' describes the "
            "COMMERCIAL case only and is explicitly NON-FINAL -- it is not a "
            "recommendation and must never be presented as one while operational "
            "validation is incomplete"
        )

    notes.append(
        "the Opportunity Score is a deterministic, PROVISIONAL BUSINESS HEURISTIC "
        "built from documented, adjustable weights. It has NOT been calibrated "
        "against real sales outcomes. It is NOT a probability of selling, NOT a "
        "probability of success, NOT a conversion rate, NOT an expected ROI, and "
        "NOT a guarantee of performance"
    )

    return OpportunityAnalysisResult(
        model_version=INTEGRATED_MODEL_VERSION,
        product_name=product_name,
        opportunity_score=None if score is None else round(score, 2),
        score_is_partial=score_is_partial,
        classification=classification,
        withheld_reason=withheld_reason,
        analytical_band_non_final=analytical_band_non_final,
        readiness=readiness,
        publishable=publishable,
        commercial_validation_complete=commercial_complete,
        operational_validation_complete=operational_complete,
        component_coverage=round(coverage * 100, 2),
        commercial_coverage=round(
            _layer_coverage(components, VALIDATION_COMMERCIAL, TOTAL_COMMERCIAL_WEIGHT)
            * 100,
            2,
        ),
        operational_coverage=round(
            _layer_coverage(
                components, VALIDATION_OPERATIONAL, TOTAL_OPERATIONAL_WEIGHT
            )
            * 100,
            2,
        ),
        components=tuple(components[name] for name in COMPONENT_ORDER),
        missing_components=missing_components,
        missing_commercial_requirements=missing_commercial,
        missing_operational_requirements=missing_operational,
        domain_blockers=domain_blockers,
        domain_warnings=domain_warnings,
        evidence_profile=_build_evidence_profile(results),
        false_safety_ceiling_applied=ceiling_applied,
        notes=tuple(notes),
    )
