"""Apify integration layer for Google Trends data.

ANALOGY: Apify is like a delivery company. We give Apify an order (a
keyword, a region, a timeframe). Apify sends its Actor --
`themineworks/google-trends-pro` -- out to collect the Google Trends
information on our behalf. The Actor comes back with a package of
structured data (a dataset). This module is the only place in the
project allowed to open that package and convert it into our own
internal format (`src/trend_models.py`). Nothing downstream of this
module ever sees Apify's raw JSON, an Actor ID, or an HTTP status code.

Actor used: themineworks/google-trends-pro (a third-party, unofficial
Google Trends scraper running on Apify's infrastructure -- Apify's own
platform API is official and documented; the Actor's own scraping logic
is not, and carries real maintenance risk. See docs/MAINTENANCE.md,
which records a known degraded-reliability period starting 2026-07-30
due to Google-side rate limiting).

Endpoint used (official Apify REST API, documented at
https://docs.apify.com/api/v2/act-run-sync-get-dataset-items-post):

    POST https://api.apify.com/v2/actors/{actorId}/run-sync-get-dataset-items

`{actorId}` uses a tilde in place of the `/` in "username/actor-name",
per Apify's documented convention: `themineworks~google-trends-pro`.

Observed live: this endpoint returns `HTTP 201 Created` on success (not
`200`), presumably because the call provisions a new Actor run resource.
Any `2xx` status is treated as success here.

PRODUCTION HOTFIX (post-commit): a live CLI run returned related
queries, rising queries, and regional interest successfully, but mapped
`interest_over_time` to zero observations -- with no error shown. A
fresh live re-test could not reproduce a broken raw shape (4 consecutive
calls all returned the expected `{"date", "value", "formatted_value"}`
points), so this is classified as intermittent Actor inconsistency, not
a confirmed permanent schema change (see docs/MAINTENANCE.md). Two
defenses were added regardless: `_coerce_interest_value()` tolerates a
known real Google Trends raw-API quirk (a point's `value` arriving as a
one-element list instead of a scalar, used when comparing multiple
keywords), and `_map_report_row()` now RAISES `ApifyTrendsDataError`
if the Actor returned interest_over_time entries that all failed to
parse into a number, instead of silently returning zero observations.
Silent zero-with-no-error was the real bug; genuinely empty/missing
`interest_over_time` (an honest "no data") still returns an empty list
without raising.

Authentication: `Authorization: Bearer <APIFY_API_TOKEN>` header (never
a query parameter, and never hardcoded). The token is loaded from the
environment via `src.config` (which loads `.env` through python-dotenv).
This module never prints, logs, or otherwise exposes the token value.

DATA SEMANTICS -- read before using any value from this module:
Google Trends interest values are a RELATIVE index from 0 to 100,
scaled to the peak interest within that keyword's OWN result set. They
are NOT absolute search volume, not a number of searches, not market
size, and not a number of buyers. A value of 100 for one keyword and a
value of 100 for a different keyword do not mean the same number of
real searches -- never compare raw values across unrelated keywords as
if they were absolute demand.
"""

from datetime import datetime, timezone

import requests

import src.config
from src.trend_models import RelatedQuery, TrendData, TrendPoint, TrendRegion

APIFY_BASE_URL = "https://api.apify.com/v2"
ACTOR_ID = "themineworks~google-trends-pro"
DEFAULT_TIMEOUT = 60
SOURCE_NAME = "apify:themineworks/google-trends-pro"
SPECIAL_ROW_TYPES = {"error", "summary", "info"}

DEFAULT_GEO = "BR"
DEFAULT_TIMEFRAME = "today 12-m"


class ApifyTrendsError(Exception):
    """Base class for all Apify trend integration failures."""


class ApifyTrendsConfigurationError(ApifyTrendsError):
    """APIFY_API_TOKEN is missing or not configured."""


class ApifyTrendsTimeoutError(ApifyTrendsError):
    """The request to Apify timed out."""


class ApifyTrendsConnectionError(ApifyTrendsError):
    """Could not connect to Apify (network/DNS failure)."""


class ApifyTrendsResponseError(ApifyTrendsError):
    """Apify returned a non-200 HTTP status code."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class ApifyTrendsDataError(ApifyTrendsError):
    """Apify returned a response we could not parse or understand."""


class ApifyTrendsActorError(ApifyTrendsError):
    """The Actor itself reported an error row instead of trend data."""


def _build_headers() -> dict:
    token = src.config.get_apify_token()
    if not token:
        raise ApifyTrendsConfigurationError(src.config.describe_apify_token_status())
    return {"Authorization": f"Bearer {token}"}


def _coerce_interest_value(value):
    """Coerce a raw interest value into a number.

    Google Trends' own underlying API represents a timeseries point's
    value as a list (one entry per compared keyword) when comparing
    multiple keywords, e.g. `[36]` instead of `36` for a single keyword.
    The Actor is expected to flatten this, but has been observed to be
    unreliable (see docs/MAINTENANCE.md) -- so a single-element list is
    unwrapped defensively here rather than assumed away. Anything else
    unrecognized becomes None; nothing is ever guessed or fabricated.
    """
    if isinstance(value, list):
        value = value[0] if len(value) == 1 else None
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            try:
                return float(value)
            except ValueError:
                return None
    return None


def _map_point(raw: dict) -> TrendPoint:
    return TrendPoint(
        date=raw.get("date"),
        value=_coerce_interest_value(raw.get("value")),
        formatted_value=raw.get("formatted_value"),
    )


def _map_region(raw: dict) -> TrendRegion:
    return TrendRegion(
        region_code=raw.get("region_code"),
        region_name=raw.get("region_name"),
        value=raw.get("value"),
    )


def _map_related_query(raw: dict) -> RelatedQuery:
    return RelatedQuery(
        query=raw.get("query"),
        value=raw.get("value"),
        formatted_value=raw.get("formatted_value"),
        link=raw.get("link"),
    )


def _map_report_row(raw: dict, query: str, geo: str, timeframe: str) -> TrendData:
    """Map one real Actor report row (never an error/summary/info row) to TrendData."""
    raw_points = raw.get("interest_over_time") or []
    interest_over_time = [_map_point(p) for p in raw_points]
    if raw_points and all(p.value is None for p in interest_over_time):
        # The Actor returned interest_over_time entries, but none had a
        # value we could parse into a number. This is a REAL mapping
        # failure, not "no data" -- raise loudly instead of silently
        # returning zero observations (that silent-zero shape is exactly
        # the bug this check exists to catch; see docs/MAINTENANCE.md).
        raise ApifyTrendsDataError(
            "Actor returned interest_over_time entries but none had a "
            "recognizable numeric value -- possible schema drift or "
            "Actor inconsistency in the point shape."
        )

    interest_by_region = [_map_region(r) for r in (raw.get("interest_by_region") or [])]

    related = raw.get("related_queries") or {}
    related_top = [_map_related_query(r) for r in (related.get("top") or [])]
    related_rising = [_map_related_query(r) for r in (related.get("rising") or [])]

    retrieved_at = raw.get("scraped_at") or datetime.now(timezone.utc).isoformat()

    return TrendData(
        query=raw.get("keyword", query),
        geo=raw.get("geo", geo),
        timeframe=raw.get("timeframe", timeframe),
        retrieved_at=retrieved_at,
        interest_over_time=interest_over_time,
        interest_by_region=interest_by_region,
        related_top_queries=related_top,
        related_rising_queries=related_rising,
        source=SOURCE_NAME,
    )


def fetch_trend_data(
    query: str,
    geo: str = DEFAULT_GEO,
    timeframe: str = DEFAULT_TIMEFRAME,
    timeout: float = DEFAULT_TIMEOUT,
) -> TrendData:
    """Fetch Google Trends data for `query` via the Apify Actor.

    Raises ValueError for invalid arguments, and an ApifyTrendsError
    subclass for any configuration/network/HTTP/JSON/Actor-level
    failure. Never raises a raw requests/json exception, and never
    returns Apify's raw JSON -- only a mapped TrendData.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    headers = _build_headers()
    payload = {
        "keywords": [query],
        "geo": geo,
        "timeframe": timeframe,
        "includeInterestOverTime": True,
        "includeRelatedQueries": True,
        "includeInterestByRegion": True,
        "includeRelatedTopics": False,
    }

    try:
        response = requests.post(
            f"{APIFY_BASE_URL}/actors/{ACTOR_ID}/run-sync-get-dataset-items",
            headers=headers,
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise ApifyTrendsTimeoutError(
            f"Apify did not respond within {timeout}s"
        ) from exc
    except requests.ConnectionError as exc:
        raise ApifyTrendsConnectionError("Could not connect to Apify") from exc
    except requests.RequestException as exc:
        raise ApifyTrendsError(f"Apify request failed: {exc}") from exc

    if not 200 <= response.status_code < 300:
        raise ApifyTrendsResponseError(
            status_code=response.status_code,
            message=f"Apify returned HTTP {response.status_code}",
        )

    try:
        items = response.json()
    except ValueError as exc:
        raise ApifyTrendsDataError(
            "Apify returned a response that was not valid JSON"
        ) from exc

    if not isinstance(items, list):
        raise ApifyTrendsDataError("Apify response was not a list of dataset items")
    if not items:
        raise ApifyTrendsDataError("Apify returned an empty dataset for this query")

    report_rows = []
    error_rows = []
    for item in items:
        if not isinstance(item, dict):
            continue
        row_type = item.get("_type")
        if row_type in SPECIAL_ROW_TYPES:
            if row_type == "error":
                error_rows.append(item)
            continue
        if "keyword" not in item:
            continue
        report_rows.append(item)

    if not report_rows:
        if error_rows:
            message = (
                error_rows[0].get("errorMessage")
                or error_rows[0].get("message")
                or "Actor reported an error"
            )
            raise ApifyTrendsActorError(message)
        raise ApifyTrendsDataError("Actor returned no report rows for this query")

    return _map_report_row(report_rows[0], query, geo, timeframe)
