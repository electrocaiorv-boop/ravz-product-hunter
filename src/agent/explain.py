"""Deterministic rendering of a composed analysis for the agent.

The agent explains results; it does not compute them. This module turns
a composed `OpportunityAnalysisResult` into the factual digest the model
is allowed to narrate, and provides the fallback explanation used when
no model is available or when a model's prose fails the provenance
check.

Every figure here is copied from the analysis, never recomputed. There
is no arithmetic on scores in this file.
"""


def summarize_for_model(result) -> str:
    """A compact, factual digest of one composed analysis.

    This is what the model reads. It contains only what the engines
    produced, so the model has nothing to extrapolate from. Figures are
    formatted, never adjusted.
    """
    lines = [
        f"model_version: {result.model_version}",
        f"product: {result.product_name}",
        f"opportunity_score: {_fmt(result.opportunity_score)}"
        f"{' (PARTIAL)' if result.score_is_partial else ''}",
        f"readiness: {result.readiness}",
        f"publishable_recommendation: {result.publishable}",
        f"final_classification: "
        f"{result.classification if result.classification else 'WITHHELD'}",
    ]
    if result.withheld_reason:
        lines.append(f"withheld_reason: {result.withheld_reason}")
    if result.analytical_band_non_final:
        lines.append(
            f"non_final_band: {result.analytical_band_non_final}")

    lines += [
        f"component_coverage: {_fmt(result.component_coverage)}%",
        f"commercial_validation_complete: "
        f"{result.commercial_validation_complete} "
        f"(coverage {_fmt(result.commercial_coverage)}%)",
        f"operational_validation_complete: "
        f"{result.operational_validation_complete} "
        f"(coverage {_fmt(result.operational_coverage)}%)",
    ]

    lines.append("components:")
    for component in result.components:
        if component.available:
            detail = (
                f"raw {_fmt(component.raw_score)} -> opportunity "
                f"{_fmt(component.opportunity_score)}, weight "
                f"{component.configured_weight}, contribution "
                f"{_fmt(component.weighted_contribution)}"
            )
            if not component.counted:
                detail += f" (NOT COUNTED: {component.overlap_policy})"
        else:
            detail = f"UNAVAILABLE -- {component.withheld_reason}"
        lines.append(
            f"  {component.name} [{component.validation_layer}, "
            f"{component.direction}]: {detail}")

    if result.missing_commercial_requirements:
        lines.append("missing_commercial: "
                     + ", ".join(result.missing_commercial_requirements))
    if result.missing_operational_requirements:
        lines.append("missing_operational: "
                     + ", ".join(result.missing_operational_requirements))
    if result.domain_blockers:
        lines.append("BLOCKERS:")
        lines += [f"  {b}" for b in result.domain_blockers]
    if result.domain_warnings:
        lines.append("warnings:")
        lines += [f"  {w}" for w in result.domain_warnings]
    if result.false_safety_ceiling_applied:
        lines.append(
            "false_safety_ceiling_applied: true (a negative dimension is "
            "unknown, so the aggregate was capped at its neutral value)")
    return "\n".join(lines)


def deterministic_explanation(result) -> str:
    """The fallback explanation, built without a model.

    Used when agent mode is unavailable, and when a model's prose is
    rejected by the provenance guard. It is plain, complete and
    trivially traceable -- every figure is copied from `result`.
    """
    if result is None:
        return ("No analysis was produced, so there is nothing to explain. "
                "No score, classification or recommendation is implied.")

    score = _fmt(result.opportunity_score)
    partial = " (partial)" if result.score_is_partial else ""
    parts = [
        f"{result.product_name} scores {score}{partial} of 100 under "
        f"{result.model_version}, a documented weighting of the evidence "
        f"collected -- not a probability of selling.",
        f"Readiness is {result.readiness}.",
    ]
    if result.classification:
        parts.append(f"Final classification: {result.classification}.")
    else:
        parts.append(
            "No final classification is issued"
            + (f": {result.withheld_reason}" if result.withheld_reason else ".")
        )

    if result.missing_commercial_requirements:
        parts.append(
            "Missing commercial evidence: "
            + ", ".join(result.missing_commercial_requirements) + ".")
    if result.missing_operational_requirements:
        parts.append(
            "Missing operational evidence: "
            + ", ".join(result.missing_operational_requirements) + ".")
    if result.domain_blockers:
        parts.append("Blockers: " + "; ".join(result.domain_blockers) + ".")
    return " ".join(parts)


def learning_notes(result) -> str:
    """Optional Learning mode: why the result is shaped as it is.

    Explains the MECHANISM, using only figures already in `result`. It
    teaches the model of the system, not a sales pitch for the product.
    """
    if result is None:
        return ("Nothing was computed, so there is no mechanism to walk "
                "through.")

    notes = [
        "How this result was produced:",
        "",
        f"1. Each domain engine scored its own evidence independently. "
        f"{len([c for c in result.components if c.available])} of "
        f"{len(result.components)} components had evidence; the rest are "
        f"reported unavailable rather than filled in.",
        "",
        "2. Negative dimensions (competition, risk) are inverted exactly "
        "once so that high always means favorable, then every available "
        "component is multiplied by its configured weight:",
    ]
    for component in result.components:
        if component.available and component.counted:
            notes.append(
                f"     {component.name}: "
                f"{_fmt(component.opportunity_score)} x "
                f"{component.configured_weight} = "
                f"{_fmt(component.weighted_contribution)}")
        elif component.available and not component.counted:
            notes.append(
                f"     {component.name}: not counted -- "
                f"{component.overlap_policy}")

    notes += [
        "",
        f"3. Coverage is {_fmt(result.component_coverage)}% of the "
        f"configured weight. Coverage is not confidence, not evidence "
        f"completeness, and not accuracy -- it only says how much of the "
        f"weighting had any evidence behind it.",
        "",
        f"4. Readiness ({result.readiness}) is decided separately from the "
        f"score. Commercial validation asks whether the business case is "
        f"evaluable; operational validation asks whether execution is. A "
        f"final classification is issued only when both are complete and "
        f"no blocker fired.",
    ]
    if result.false_safety_ceiling_applied:
        notes += [
            "",
            "5. A false-safety ceiling was applied: a negative dimension "
            "was unknown, so the aggregate was capped at the value it "
            "would have had if that dimension were neutral. Without the "
            "cap, missing bad news would have raised the score. No "
            "component was given a substitute value.",
        ]
    return "\n".join(notes)


def _fmt(value) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, (int, float)):
        return f"{value:.2f}"
    return str(value)
