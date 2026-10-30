"""Canonical contract for integrated Opportunity composition (Phase 11).

This module defines the BOUNDARY between the seven independent
domain-analysis engines (Phases 4-10) and the composition engine in
`src/opportunity_integration.py`. It imports nothing but `dataclasses`
-- no HTTP, no integrations, no domain-analysis modules, no LLM. It
holds only the canonical data shapes, the integrated weight contract,
the evidence-family policy, and the readiness vocabulary.

== Why a canonical component at all ==

The composition engine must NOT understand seven different result
structures. Each domain result is translated by its own small adapter
(see `src/opportunity_integration.py`) into an `OpportunityComponent`,
and the engine then only ever reasons about `OpportunityComponent`s.
Adding an eighth domain later means writing one adapter, not editing
the engine's arithmetic.

    Domain Analysis Result -> Domain Adapter -> OpportunityComponent
                                                      -> Composition Engine

== Score direction, inverted EXACTLY once ==

`raw_score` is always the domain's own score in the domain's own
direction. `opportunity_score` is that value re-oriented so higher is
always better for the opportunity:

    positive dimension:  opportunity_score = raw_score
    negative dimension:  opportunity_score = 100 - raw_score

The inversion happens in exactly one place (`to_opportunity_oriented()`,
called by the adapters), never again in the engine and never inside a
domain module. `src/risk_analysis.py` and `src/competition_analysis.py`
both deliberately keep their own high-is-bad direction, and
`src/logistics_analysis.py` deliberately computes "ease" so it is
already high-is-good -- so there is nothing to undo anywhere upstream.

== The search-interest evidence FAMILY (the central Phase 11 finding) ==

Demand and Trend are NOT independent evidence. Both descend from one
Apify Google-Trends Actor call:

    interest_over_time -> recent_average + direction
                            |-> TrendMetrics.provisional_trend_score
                            |-> DemandAnalysis.trend_contribution (w 0.40)
    related_*_queries     -> DemandAnalysis.breadth_contribution  (w 0.25)
    interest_by_region    -> DemandAnalysis.regional_contribution (w 0.20)
    marketplace            -> DemandAnalysis.marketplace_contribution --
                              permanently None (a page-capped item count
                              is not a demand signal)

Because the marketplace component is permanently unavailable, 100% of
today's Demand Score is Google-Trends evidence, and `recent_average` /
`direction` are literally the same two numbers that dominate the Trend
Score. Weighting Demand AND Trend as separate votes would count that
interest series twice. Phase 5 had already rebuilt `trend_contribution`
from atomic fields specifically to avoid reusing Phase 4's blended
score; counting both here would undo that decision one layer up.

The fix is an evidence FAMILY with a single weighted REPRESENTATIVE,
declared once as data (`EvidenceFamilyPolicy`) rather than as ad-hoc
conditionals, so a future refactor cannot quietly reintroduce Trend as
an independent weighted vote without deleting a declared policy object
and failing its tests.

== Integrated weights are NOT legacy weights ==

This is the single most important thing to understand about this
module, and it was the final hardening decision of Phase 11.

Legacy Phase 1 gave Demand 0.30 + Trend 0.20. An earlier draft of the
integrated model preserved that 0.50 as the search-interest family's
combined weight, reasoning that "removing the double count should not
also re-weight the business judgment."

That reasoning was wrong, and here is why: legacy's 0.50 was split
across what it BELIEVED were two independent sources of evidence. Once
the audit proved they are ONE evidence family fed by ONE provider call,
preserving 0.50 does not preserve the original judgment -- it silently
converts "half the score comes from two independent demand signals"
into "half the score comes from one Google Trends call." Those are
materially different claims, and the second is far more concentrated
than Phase 1 ever intended.

    legacy business weights  !=  integrated evidence-justified weights

So integrated-v1 re-derives its weights from the MARGINAL INFORMATION
VALUE each evidence family actually contributes, given what the project
can observe today:

    SEARCH_INTEREST (Demand/Trend family)   0.30
        Genuine evidence of interest, but currently dependent on a
        single Google Trends / Apify evidence family, and search
        interest is NOT observed marketplace sales. Material, not
        dominant.
    COMPETITION                              0.15
        Retains real influence over how attractive the opportunity is
        without dominating commercial viability.
    MARGIN                                   0.20
        Unit economics are directly material to whether the
        opportunity is financially viable at all. Raised above the
        search-interest family deliberately: a product nobody searches
        for is a weak idea, but a product that loses money per unit is
        not an opportunity in the first place.
    SUPPLIER                                 0.12
        Sourcing capability materially determines execution and
        deserves more than a marginal role.
    LOGISTICS                                0.08
        Movement/fulfillment matters, but stays below Margin and
        Supplier.
    RISK                                     0.15
        Downside, concentration and instability deserve material
        influence -- tripled from legacy's 0.05, which was too small
        for a dimension the project treats as mandatory evidence.

    TOTAL                                     1.00

These are PROVISIONAL BUSINESS HEURISTICS chosen from documented
reasoning, NOT calibrated against outcomes. Real outcome data may well
justify recalibrating every one of them; that would be a new model
version, not an edit to this one.

`LEGACY_WEIGHTS` in `src/scoring.py` is untouched and still governs the
Phase 1/2 manual API. The two models coexist on purpose: the legacy one
answers "what do these seven manually supplied numbers combine to," the
integrated one answers "what do these real domain results, with their
real evidence gaps and correlations, support."

== Commercial attractiveness is NOT operational readiness ==

The second hardening decision. A product can look excellent on paper --
strong interest, acceptable competition, healthy margin, low risk --
while nobody has checked whether a supplier can actually provide it or
whether it can be shipped reliably. That opportunity is commercially
attractive and operationally UNVALIDATED, and those are different
statements that must not collapse into one.

So the seven components are partitioned into two validation layers,
and every component is required for its own layer:

    COMMERCIAL layer (0.80 of weight)
        search-interest family, competition, margin, risk
        -> "is the market and economic case validated?"

    OPERATIONAL layer (0.20 of weight)
        supplier, logistics
        -> "is execution validated?"

A family is satisfied when ANY of its members is available (that is the
point of a representative); a non-family component is satisfied only by
itself.

== Readiness, and why it is four states and not two ==

    BLOCKED                     a domain reported a genuine hard
                                blocker. Checked FIRST, before any
                                evidence-completeness question,
                                matching every domain's own
                                blocker-precedence rule.
    INCOMPLETE_EVIDENCE         no blocker, but a COMMERCIAL requirement
                                is missing -- the business case itself
                                cannot be evaluated yet.
    OPERATIONALLY_UNVALIDATED   no blocker, commercial validation
                                COMPLETE, but Supplier and/or Logistics
                                are unavailable -- the business case
                                stands; execution is unchecked.
    READY                       no blocker, both layers complete.

`OPERATIONALLY_UNVALIDATED` is deliberately NOT folded into
`INCOMPLETE_EVIDENCE`. They answer different questions, and conflating
them would throw away the most actionable thing the system can say:
"the commercial case holds up -- go verify sourcing and shipping."

Precedence is strict: BLOCKED > INCOMPLETE_EVIDENCE >
OPERATIONALLY_UNVALIDATED > READY. Commercial outranks operational
because an unevaluable business case makes the execution question moot.

This readiness vocabulary is deliberately distinct from Supplier's
`operational_status`, Logistics' `operational_status`, and Risk's
`risk_status` -- despite the unavoidable word overlap in
"OPERATIONALLY_UNVALIDATED", it is an OPPORTUNITY-level statement about
evidence coverage, never a domain's own verdict.

== Final classification is emitted ONLY when READY ==

The analytical score is still computed and shown whenever any weighted
evidence exists -- hiding useful arithmetic would be its own kind of
dishonesty. But the legacy classification bands ("Strong opportunity",
...) are emitted only when `readiness == READY`.

Outside READY, `classification` is `None` and `withheld_reason`
explains why. For `OPERATIONALLY_UNVALIDATED` only -- the one state
where the commercial case IS fully evaluated -- an explicitly non-final
band is exposed as `analytical_band_non_final`, so the report can say
"the commercial case scores in the Strong band, but execution is
unvalidated" without ever stamping the opportunity approved. It is
deliberately NOT populated for `INCOMPLETE_EVIDENCE` (the commercial
case is not evaluable, so a band would be misleading) or for `BLOCKED`
(the opportunity is moot while the blocker stands).

== Coverage is NOT confidence ==

`component_coverage` = (configured weight of available weighted
components) / (total configured weight). It answers ONLY "how much of
the weight do we have any evidence for."

It is NOT confidence (how trustworthy that evidence is), NOT
completeness (how much of one domain's own field set is populated), and
NOT accuracy. 85% coverage built from four thin, low-confidence domains
is not better evidence than 60% from three well-populated ones.
`commercial_coverage` and `operational_coverage` are the same measure
restricted to one layer. Each domain's own evidence metric is preserved
separately and unaveraged in `EvidenceProfile`.

== Provisional heuristic, never a probability ==

Every component score, and therefore every Opportunity Score produced
from them, is a PROVISIONAL BUSINESS HEURISTIC built from documented,
adjustable constants. None of it has been calibrated against real sales
outcomes. "Opportunity Score: 82" means "this evidence, under this
documented weighting, scores 82 out of 100" -- it does NOT mean an 82%
chance of success, an 82% chance of selling, a conversion probability,
an expected ROI, or any probability of any outcome whatsoever. No
function in this module or in `src/opportunity_integration.py`
produces, or may ever produce, a probability from these scores.
"""

from dataclasses import dataclass, field

INTEGRATED_MODEL_VERSION = "integrated-v1"
LEGACY_MODEL_VERSION = "legacy-v1"

DIRECTION_POSITIVE = "positive"
DIRECTION_NEGATIVE = "negative"

VALIDATION_COMMERCIAL = "commercial"
VALIDATION_OPERATIONAL = "operational"


@dataclass(frozen=True)
class EvidenceFamilyPolicy:
    """A set of components backed by the SAME underlying evidence.

    Declared as data, not as conditionals in the engine, so that the
    no-double-counting rule is a durable, inspectable, testable object.
    Deleting or weakening it breaks its own tests loudly instead of
    quietly restoring a double count.

    `members` is in REPRESENTATIVE-PRECEDENCE order: the first member
    with an available score becomes the single weight-bearing
    representative of the family. Every other member stays visible for
    provenance with zero weighted contribution.

    The family carries ONE `weight` between all its members -- never
    one weight each.
    """

    name: str
    members: tuple[str, ...]
    weight: float
    validation_layer: str
    rationale: str

    @property
    def representative_precedence(self) -> tuple[str, ...]:
        return self.members


SEARCH_INTEREST_FAMILY = EvidenceFamilyPolicy(
    name="search-interest",
    members=("demand", "trend"),
    weight=0.30,
    validation_layer=VALIDATION_COMMERCIAL,
    rationale=(
        "Demand Analysis and Trend Analysis both derive from the SAME Apify "
        "Google-Trends Actor call: Demand's largest component is rebuilt from the "
        "same interest level and direction that dominate the Trend Score, and "
        "Demand's remaining components read other sections of that same call. "
        "They are one witness heard twice, not two independent witnesses, so the "
        "family carries one combined weight and elects one representative. Demand "
        "is preferred because it consumes the family most completely (interest "
        "level, direction, related-query breadth, regional spread) while Trend "
        "reads only the interest series; Trend is the fallback so that supplying "
        "only a Trend result does not leave the family's weight unearned."
    ),
)

EVIDENCE_FAMILIES = (SEARCH_INTEREST_FAMILY,)

# Backwards-compatible alias for the family's identifier.
FAMILY_SEARCH_INTEREST = SEARCH_INTEREST_FAMILY.name

# Derived from EVIDENCE_FAMILIES -- never hand-maintained in parallel.
COMPONENT_FAMILIES = {
    member: family.name
    for family in EVIDENCE_FAMILIES
    for member in family.members
}
FAMILY_BY_NAME = {family.name: family for family in EVIDENCE_FAMILIES}
FAMILY_REPRESENTATIVE_PRECEDENCE = {
    family.name: family.representative_precedence for family in EVIDENCE_FAMILIES
}

SEARCH_INTEREST_FAMILY_WEIGHT = SEARCH_INTEREST_FAMILY.weight

# Integrated weight table. Family members each carry the FAMILY's weight
# here (only one of them is ever counted), so the distinct weighted
# slots sum to exactly 1.0 -- see TOTAL_INTEGRATED_WEIGHT.
INTEGRATED_WEIGHTS = {
    "demand": SEARCH_INTEREST_FAMILY_WEIGHT,
    "trend": SEARCH_INTEREST_FAMILY_WEIGHT,
    "competition": 0.15,
    "margin": 0.20,
    "supplier": 0.12,
    "logistics": 0.08,
    "risk": 0.15,
}

# Which validation layer each component belongs to. Every component is
# REQUIRED for its own layer's validation to be complete.
COMPONENT_VALIDATION_LAYER = {
    "demand": VALIDATION_COMMERCIAL,
    "trend": VALIDATION_COMMERCIAL,
    "competition": VALIDATION_COMMERCIAL,
    "margin": VALIDATION_COMMERCIAL,
    "risk": VALIDATION_COMMERCIAL,
    "supplier": VALIDATION_OPERATIONAL,
    "logistics": VALIDATION_OPERATIONAL,
}

NEGATIVE_COMPONENTS = frozenset({"competition", "risk"})

COMPONENT_ORDER = (
    "demand",
    "trend",
    "competition",
    "margin",
    "supplier",
    "logistics",
    "risk",
)


def _distinct_weighted_slots():
    """Yield (requirement_key, weight, validation_layer) once per slot.

    A family contributes ONE slot keyed by the family name; every
    non-family component contributes its own slot. This is the single
    source of truth for weight totals and for layer membership, so the
    coverage denominators and the readiness requirements can never
    drift apart.
    """
    seen_families = set()
    for name in COMPONENT_ORDER:
        family_name = COMPONENT_FAMILIES.get(name)
        if family_name is not None:
            if family_name in seen_families:
                continue
            seen_families.add(family_name)
            family = FAMILY_BY_NAME[family_name]
            yield family_name, family.weight, family.validation_layer
        else:
            yield name, INTEGRATED_WEIGHTS[name], COMPONENT_VALIDATION_LAYER[name]


DISTINCT_WEIGHTED_SLOTS = tuple(_distinct_weighted_slots())

TOTAL_INTEGRATED_WEIGHT = sum(weight for _key, weight, _layer in DISTINCT_WEIGHTED_SLOTS)

TOTAL_COMMERCIAL_WEIGHT = sum(
    weight
    for _key, weight, layer in DISTINCT_WEIGHTED_SLOTS
    if layer == VALIDATION_COMMERCIAL
)
TOTAL_OPERATIONAL_WEIGHT = sum(
    weight
    for _key, weight, layer in DISTINCT_WEIGHTED_SLOTS
    if layer == VALIDATION_OPERATIONAL
)

# Requirement keys per layer (family names, or plain component names).
COMMERCIAL_REQUIREMENTS = tuple(
    key
    for key, _weight, layer in DISTINCT_WEIGHTED_SLOTS
    if layer == VALIDATION_COMMERCIAL
)
OPERATIONAL_REQUIREMENTS = tuple(
    key
    for key, _weight, layer in DISTINCT_WEIGHTED_SLOTS
    if layer == VALIDATION_OPERATIONAL
)

READINESS_READY = "READY"
READINESS_OPERATIONALLY_UNVALIDATED = "OPERATIONALLY_UNVALIDATED"
READINESS_INCOMPLETE_EVIDENCE = "INCOMPLETE_EVIDENCE"
READINESS_BLOCKED = "BLOCKED"

# Strict precedence, worst first. The engine picks the first state whose
# condition holds.
READINESS_PRECEDENCE = (
    READINESS_BLOCKED,
    READINESS_INCOMPLETE_EVIDENCE,
    READINESS_OPERATIONALLY_UNVALIDATED,
    READINESS_READY,
)

# Neutral midpoint used ONLY as a ceiling on the aggregate when a
# negative component is missing -- never written into any component's
# score. See `src/opportunity_integration.py`.
NEUTRAL_MIDPOINT = 50.0

CLASSIFICATION_BANDS = (
    (80.0, "Strong opportunity"),
    (65.0, "Worth deeper investigation"),
    (50.0, "Weak or uncertain opportunity"),
)
CLASSIFICATION_REJECT = "Reject"


def to_opportunity_oriented(raw_score: float | None, direction: str) -> float | None:
    """Re-orient a domain score so higher is always better. Inverts ONCE.

    This is the ONLY inversion boundary in the project. `None` stays
    `None` -- a missing score is never converted into 0, 50, "safe", or
    "average" anywhere.
    """
    if raw_score is None:
        return None
    if direction == DIRECTION_NEGATIVE:
        return 100.0 - raw_score
    return float(raw_score)


def classify_exact(opportunity_score: float) -> str:
    """Classify an EXACT (unrounded) integrated score.

    Deliberately operates on the unrounded internal value: a score of
    79.996 is below 80 and must not become "Strong opportunity" just
    because it displays as 80.00. `src/scoring.py`'s legacy
    `classify()` is left exactly as it was (it receives an
    already-2dp-rounded total) -- see docs/MAINTENANCE.md for why that
    difference is preserved rather than "fixed".
    """
    for threshold, label in CLASSIFICATION_BANDS:
        if opportunity_score >= threshold:
            return label
    return CLASSIFICATION_REJECT


@dataclass(frozen=True)
class OpportunityComponent:
    """One domain's contribution to the integrated Opportunity Score.

    Produced only by an adapter in `src/opportunity_integration.py`.
    Adapters translate; they never recompute a domain's scoring, never
    fetch anything, and never invent a missing value.
    """

    name: str
    source_domain: str
    direction: str
    configured_weight: float
    validation_layer: str

    available: bool
    raw_score: float | None
    opportunity_score: float | None
    weighted_contribution: float | None

    # Each domain's OWN evidence metric, under its OWN name -- these are
    # not interchangeable and are never averaged together.
    evidence_label: str
    evidence_value: float | None

    # The domain's own status vocabulary, when it has one.
    source_status: str | None = None

    # Why this component contributes nothing: either the domain withheld
    # its score, or it lost its evidence family's representative
    # election (see `overlap_policy`).
    withheld_reason: str | None = None
    overlap_policy: str | None = None
    family: str | None = None
    counted: bool = True

    @property
    def effective_weight(self) -> float:
        """Weight this component actually contributes with.

        Zero when the component is unavailable or when it lost the
        family representative election -- never partially credited.
        """
        if not self.counted or not self.available:
            return 0.0
        return self.configured_weight


@dataclass(frozen=True)
class EvidenceProfile:
    """Each domain's evidence metric, preserved under its ORIGINAL name.

    These are deliberately NOT renamed to a single "confidence" field
    and deliberately NOT averaged into one number:

        demand_confidence / competition_confidence
            -- sampling-and-source-independence bounded confidence
               (Phases 5/6). Competition's is hard-capped at 55 because
               only one source family structurally exists.
        margin_cost_completeness
            -- how many of 8 optional cost categories were supplied
               (Phase 7). No sampling, no source-independence question.
        supplier_/logistics_/risk_evidence_completeness
            -- WEIGHTED share of each domain's own evidence fields that
               are known (Phases 8/9/10).
        trend_observation_count / trend_direction
            -- Trend has NO evidence-quality metric at all; its honest
               metadata is how many observations the series had and
               which direction they implied.

    Averaging a bounded-confidence figure with a field-count
    completeness figure would produce a number with no definable
    meaning, so no aggregate is offered. Anyone needing one must define
    and justify it explicitly.
    """

    demand_confidence: float | None = None
    competition_confidence: float | None = None
    margin_cost_completeness: float | None = None
    supplier_evidence_completeness: float | None = None
    logistics_evidence_completeness: float | None = None
    risk_evidence_completeness: float | None = None
    trend_observation_count: int | None = None
    trend_direction: str | None = None


@dataclass(frozen=True)
class OpportunityAnalysisResult:
    """Deterministic output of the integrated composition engine.

    `opportunity_score` is an ANALYTICAL, PROVISIONAL BUSINESS
    HEURISTIC, never a probability of any outcome -- see module
    docstring. It is a final recommendation only when
    `readiness == READY`.
    """

    model_version: str
    product_name: str

    opportunity_score: float | None
    score_is_partial: bool

    # Emitted ONLY when readiness == READY.
    classification: str | None
    withheld_reason: str | None

    # Explicitly NON-FINAL band, populated only for
    # OPERATIONALLY_UNVALIDATED (the one non-READY state where the
    # commercial case is fully evaluated). Never a recommendation.
    analytical_band_non_final: str | None

    readiness: str
    publishable: bool

    commercial_validation_complete: bool
    operational_validation_complete: bool

    component_coverage: float
    commercial_coverage: float
    operational_coverage: float

    components: tuple[OpportunityComponent, ...]
    missing_components: tuple[str, ...]
    missing_commercial_requirements: tuple[str, ...]
    missing_operational_requirements: tuple[str, ...]

    # Namespaced by originating domain, never flattened into ambiguous
    # strings -- a blocker must stay attributable to the domain that
    # found it.
    domain_blockers: dict = field(default_factory=dict)
    domain_warnings: dict = field(default_factory=dict)

    evidence_profile: EvidenceProfile = field(default_factory=EvidenceProfile)

    # True when a missing NEGATIVE component's weight was prevented from
    # inflating the aggregate -- see the false-safety guard in
    # `src/opportunity_integration.py`.
    false_safety_ceiling_applied: bool = False

    notes: tuple[str, ...] = ()

    @property
    def counted_components(self) -> tuple[OpportunityComponent, ...]:
        """Components that actually contributed weight to the score."""
        return tuple(c for c in self.components if c.effective_weight > 0)
