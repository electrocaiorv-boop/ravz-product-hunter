"""Deterministic trend-analysis layer.

This module knows NOTHING about HTTP, Apify, API tokens, or Actor JSON.
It only ever imports `src.trend_models` -- the provider-neutral internal
data models. It receives a `TrendData` (already mapped by whichever
integration layer fetched it) and derives explainable metrics from the
`interest_over_time` series it contains.

This separation is deliberate: the trend data source can later be
swapped (official Google Trends API, a different Apify Actor, another
provider entirely) without rewriting a single line of this module.

Given the same input, this module always produces the same output --
no randomness, no LLM calls, no wall-clock-dependent behavior.

ASSUMPTION: `interest_over_time` points are in chronological order
(oldest first), as returned by the provider. This module does not parse
or re-sort dates itself.

== Windowing ==

The series is split in half to compare a "previous" period against a
"recent" period: `previous = points[:n // 2]`, `recent = points[n // 2:]`.
For an odd-length series, the extra point goes to the recent half. This
needs at least 2 valid observations to produce a previous/recent split;
with exactly 1 observation, direction and percentage change are reported
as unavailable rather than guessed.

== Direction thresholds (provisional, easy to change) ==

    percentage_change >= GROWING_THRESHOLD_PCT    -> "growing"
    percentage_change <= DECLINING_THRESHOLD_PCT   -> "declining"
    otherwise                                      -> "stable"

== Provisional Trend Score (0-100) -- PROVISIONAL, not yet validated ==

This score has NOT been validated against real sales outcomes. It is a
documented, deterministic, adjustable starting point, not a final
model. Formula:

    growth_score      = clamp(50 + percentage_change * GROWTH_PCT_SCALE, 0, 100)
                         (50 = neutral baseline if percentage_change is undefined)
    level_score        = recent_average
                         (0-100 already, since Google Trends values are 0-100)
    base               = WEIGHT_GROWTH * growth_score + WEIGHT_LEVEL * level_score
    direction_adjustment = +DIRECTION_BONUS if growing, -DIRECTION_BONUS if
                         declining, 0 if stable/unknown
    volatility_penalty = min(volatility * VOLATILITY_PENALTY_SCALE,
                         VOLATILITY_PENALTY_CAP)

    provisional_trend_score = clamp(
        base + direction_adjustment - volatility_penalty, 0, 100
    )

This deliberately does NOT depend only on raw average interest: it
blends recent-vs-previous growth, a sustained-direction bonus/penalty,
the current interest level, and a volatility penalty for erratic series.
All weights/scales/caps are module-level constants so they can be
recalibrated later without touching the formula's structure.

This score is NOT wired into the Phase 1 Opportunity Scoring Engine.
"""

import statistics
from dataclasses import dataclass, field

from src.trend_models import TrendData, TrendPoint

GROWING_THRESHOLD_PCT = 10.0
DECLINING_THRESHOLD_PCT = -10.0

GROWTH_PCT_SCALE = 0.5
WEIGHT_GROWTH = 0.6
WEIGHT_LEVEL = 0.4
DIRECTION_BONUS = 8.0
VOLATILITY_PENALTY_SCALE = 0.4
VOLATILITY_PENALTY_CAP = 15.0


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


@dataclass
class TrendMetrics:
    """Deterministic metrics derived from one TrendData's interest series."""

    observation_count: int
    average_interest: float | None
    recent_average: float | None
    previous_average: float | None
    percentage_change: float | None
    direction: str
    volatility: float | None
    provisional_trend_score: float | None
    notes: list[str] = field(default_factory=list)


def analyze_interest_series(points: list[TrendPoint]) -> TrendMetrics:
    """Compute deterministic trend metrics from a list of TrendPoint.

    This is the pure, provider-agnostic core: it takes plain TrendPoint
    objects, not a TrendData, so it can be tested in isolation.
    """
    notes: list[str] = []
    values = [p.value for p in points if p.value is not None]
    n = len(values)

    if n == 0:
        return TrendMetrics(
            observation_count=0,
            average_interest=None,
            recent_average=None,
            previous_average=None,
            percentage_change=None,
            direction="unknown",
            volatility=None,
            provisional_trend_score=None,
            notes=["no interest data points available"],
        )

    average_interest = statistics.fmean(values)

    if n == 1:
        return TrendMetrics(
            observation_count=1,
            average_interest=average_interest,
            recent_average=values[0],
            previous_average=None,
            percentage_change=None,
            direction="unknown",
            volatility=0.0,
            provisional_trend_score=None,
            notes=[
                "series has only 1 observation; direction, percentage "
                "change, and provisional score are not computable"
            ],
        )

    split = n // 2
    previous_values = values[:split]
    recent_values = values[split:]
    previous_average = statistics.fmean(previous_values)
    recent_average = statistics.fmean(recent_values)
    volatility = statistics.pstdev(values)

    if previous_average == 0:
        percentage_change = None
        notes.append("previous-period average is zero; percentage change is undefined")
        direction = "growing" if recent_average > 0 else "stable"
    else:
        percentage_change = (recent_average - previous_average) / previous_average * 100
        if percentage_change >= GROWING_THRESHOLD_PCT:
            direction = "growing"
        elif percentage_change <= DECLINING_THRESHOLD_PCT:
            direction = "declining"
        else:
            direction = "stable"

    if percentage_change is None:
        growth_score = 50.0
        notes.append("provisional score uses a neutral growth component (percentage change undefined)")
    else:
        growth_score = _clamp(50 + percentage_change * GROWTH_PCT_SCALE, 0, 100)

    level_score = _clamp(recent_average, 0, 100)
    direction_adjustment = (
        DIRECTION_BONUS if direction == "growing"
        else -DIRECTION_BONUS if direction == "declining"
        else 0.0
    )
    volatility_penalty = min(volatility * VOLATILITY_PENALTY_SCALE, VOLATILITY_PENALTY_CAP)

    provisional_trend_score = _clamp(
        WEIGHT_GROWTH * growth_score + WEIGHT_LEVEL * level_score
        + direction_adjustment - volatility_penalty,
        0,
        100,
    )

    return TrendMetrics(
        observation_count=n,
        average_interest=average_interest,
        recent_average=recent_average,
        previous_average=previous_average,
        percentage_change=percentage_change,
        direction=direction,
        volatility=volatility,
        provisional_trend_score=provisional_trend_score,
        notes=notes,
    )


def analyze_trend(data: TrendData) -> TrendMetrics:
    """Compute deterministic trend metrics for a TrendData's interest series."""
    return analyze_interest_series(data.interest_over_time)
