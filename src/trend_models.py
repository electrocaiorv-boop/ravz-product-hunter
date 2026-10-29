"""Provider-neutral internal data models for trend data.

These models are intentionally decoupled from any specific trend data
provider (Apify, a future official Google Trends API, another Apify
Actor, etc.) so that `src/trend_analysis.py` never needs to import or
know anything about where the data came from. An integration layer
(e.g. `src/integrations/apify_trends.py`) is responsible for mapping a
provider's raw response into these shapes; nothing provider-specific
should leak past that boundary.

Only fields actually returned by a provider are populated; anything not
returned is left as None (or an empty list) rather than fabricated.
"""

from dataclasses import dataclass


@dataclass
class TrendPoint:
    """One interest-over-time observation.

    `value` is a relative interest index from 0 to 100 (Google Trends'
    own normalization), scaled to the peak interest for THIS keyword's
    own result set -- it is NOT absolute search volume, and is not
    comparable across unrelated keywords.
    """

    date: str | None
    value: int | None
    formatted_value: str | None


@dataclass
class TrendRegion:
    """Relative interest for one region within the requested geo."""

    region_code: str | None
    region_name: str | None
    value: int | None


@dataclass
class RelatedQuery:
    """One related search term, from either the 'top' or 'rising' list."""

    query: str | None
    value: int | None
    formatted_value: str | None
    link: str | None


@dataclass
class TrendData:
    """Mapped trend result for one keyword, from one provider.

    `source` identifies where this came from (e.g.
    "apify:themineworks/google-trends-pro") so downstream consumers and
    reports can be transparent about provenance without needing to
    import the integration layer itself.

    == Observed zero vs. unavailable/unreliable (added after the
    Phase 4/5 incidents) ==

    The Apify Actor has been observed returning one section correctly
    populated while another is empty, on calls for the exact same
    query -- see docs/MAINTENANCE.md. An empty `related_top_queries` /
    `related_rising_queries` / `interest_by_region` therefore does NOT
    reliably mean "the provider confirmed zero" -- it may equally mean
    "this section silently failed or was omitted."

    The three `*_available` flags below are how the integration layer
    (which has access to the raw provider response) tells every
    downstream consumer which is which, WITHOUT those consumers needing
    to know anything about Apify or the Actor's raw JSON:

        True  -> this section's list is non-empty; trust its contents,
                 including a literal zero WITHIN that list (e.g. a
                 region present with value=0 is a genuine observation).
        False -> this section's list is empty; treat it as missing
                 evidence (None), NOT as a confirmed zero. Exclude it
                 from any score rather than scoring it as zero.

    `interest_over_time_available` follows the same rule, but in
    practice Google Trends has been observed to always return a full
    time series (often with many zero-valued points for very low
    demand -- that IS real signal) -- a genuinely EMPTY points list is
    itself the suspicious/unreliable case here, not a low-interest one.
    """

    query: str
    geo: str
    timeframe: str
    retrieved_at: str
    interest_over_time: list[TrendPoint]
    interest_by_region: list[TrendRegion]
    related_top_queries: list[RelatedQuery]
    related_rising_queries: list[RelatedQuery]
    source: str
    interest_over_time_available: bool = True
    related_queries_available: bool = True
    regional_interest_available: bool = True
