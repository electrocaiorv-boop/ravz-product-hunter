"""Tests for the Apify Google Trends integration layer.

None of these tests touch the live Apify API: requests.post and
src.config.get_apify_token are monkeypatched with fakes that simulate
success, Actor error rows, summary/info-only responses, a missing
token, timeout, connection failure, non-200 responses, malformed JSON,
an empty dataset, and an unexpected schema.
"""

import io

import requests
import pytest

from src.integrations import apify_trends
from src.integrations.apify_trends import (
    ApifyTrendsActorError,
    ApifyTrendsConfigurationError,
    ApifyTrendsConnectionError,
    ApifyTrendsDataError,
    ApifyTrendsResponseError,
    ApifyTrendsTimeoutError,
    fetch_trend_data,
)

REPORT_ROW = {
    "keyword": "bebedouro automatico gatos",
    "geo": "BR",
    "timeframe": "today 12-m",
    "scraped_at": "2026-10-20T12:00:00Z",
    "interest_over_time": [
        {"date": "2026-01-01", "value": 10, "formatted_value": "10"},
        {"date": "2026-02-01", "value": 20, "formatted_value": "20"},
    ],
    "interest_by_region": [
        {"region_code": "BR-SP", "region_name": "Sao Paulo", "value": 100},
        {"region_code": "BR-RJ", "region_name": "Rio de Janeiro", "value": 80},
    ],
    "related_queries": {
        "top": [
            {
                "query": "bebedouro para gatos",
                "value": 100,
                "formatted_value": "100",
                "link": "https://trends.google.com/x",
            }
        ],
        "rising": [
            {
                "query": "bebedouro gatos automatico eletrico",
                "value": 250,
                "formatted_value": "+250%",
                "link": "https://trends.google.com/y",
            }
        ],
    },
}
SUMMARY_ROW = {"_type": "summary", "totalKeywords": 1}
INFO_ROW = {"_type": "info", "message": "run complete"}
ERROR_ROW = {"_type": "error", "errorMessage": "Google Trends blocked this request"}

# Regression fixture for the Phase 4 production incident: a live run
# returned related/rising queries and regional interest successfully,
# but interest_over_time mapped to zero observations with no error.
# This reduced, sanitized shape models the one concrete, real Google
# Trends raw-API quirk that could cause exactly that: a point's "value"
# arriving as a one-element list (the shape Google's own multiline
# timeseries endpoint uses when comparing multiple keywords) instead of
# a plain scalar.
REPORT_ROW_WITH_LIST_WRAPPED_VALUES = {
    "keyword": "bebedouro para gatos",
    "geo": "BR",
    "timeframe": "today 12-m",
    "scraped_at": "2026-10-29T12:00:00Z",
    "interest_over_time": [
        {"date": "2026-01-01", "value": [36], "formatted_value": ["36"]},
        {"date": "2026-01-08", "value": [57], "formatted_value": ["57"]},
    ],
    "interest_by_region": [],
    "related_queries": {"top": [], "rising": []},
}

# A genuinely broken shape: points are present, but none carry a value
# we can parse into a number. This must raise loudly, not silently
# report zero observations -- that silent-zero behavior was the bug.
REPORT_ROW_WITH_UNPARSEABLE_VALUES = {
    "keyword": "bebedouro para gatos",
    "geo": "BR",
    "timeframe": "today 12-m",
    "scraped_at": "2026-10-29T12:00:00Z",
    "interest_over_time": [
        {"date": "2026-01-01", "value": None, "formatted_value": None},
        {"date": "2026-01-08", "value": {}, "formatted_value": None},
    ],
    "interest_by_region": [],
    "related_queries": {"top": [], "rising": []},
}


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, json_error=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


@pytest.fixture(autouse=True)
def fake_token(monkeypatch):
    monkeypatch.setattr(apify_trends.src.config, "get_apify_token", lambda: "fake-token-123")


def test_fetch_trend_data_maps_successful_response(monkeypatch):
    captured = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse(status_code=200, json_data=[SUMMARY_ROW, REPORT_ROW, INFO_ROW])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    data = fetch_trend_data("bebedouro automatico gatos")

    assert captured["url"] == (
        f"{apify_trends.APIFY_BASE_URL}/actors/{apify_trends.ACTOR_ID}/run-sync-get-dataset-items"
    )
    assert captured["headers"] == {"Authorization": "Bearer fake-token-123"}
    assert captured["json"] == {
        "keywords": ["bebedouro automatico gatos"],
        "geo": "BR",
        "timeframe": "today 12-m",
        "includeInterestOverTime": True,
        "includeRelatedQueries": True,
        "includeInterestByRegion": True,
        "includeRelatedTopics": False,
    }

    assert data.query == "bebedouro automatico gatos"
    assert data.geo == "BR"
    assert data.timeframe == "today 12-m"
    assert data.retrieved_at == "2026-10-20T12:00:00Z"
    assert data.source == apify_trends.SOURCE_NAME

    assert len(data.interest_over_time) == 2
    assert data.interest_over_time[0].date == "2026-01-01"
    assert data.interest_over_time[0].value == 10
    assert data.interest_over_time[1].value == 20

    assert len(data.interest_by_region) == 2
    assert data.interest_by_region[0].region_name == "Sao Paulo"

    assert len(data.related_top_queries) == 1
    assert data.related_top_queries[0].query == "bebedouro para gatos"
    assert len(data.related_rising_queries) == 1
    assert "eletrico" in data.related_rising_queries[0].query


def test_fetch_trend_data_accepts_201_as_success(monkeypatch):
    """Apify's sync endpoint has been observed returning 201, not 200, on success."""

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=201, json_data=[REPORT_ROW])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    data = fetch_trend_data("bebedouro automatico gatos")
    assert data.query == "bebedouro automatico gatos"


def test_fetch_trend_data_unwraps_list_wrapped_interest_values(monkeypatch):
    """Regression test for the Phase 4 production incident (reduced/sanitized shape)."""

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=201, json_data=[REPORT_ROW_WITH_LIST_WRAPPED_VALUES])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    data = fetch_trend_data("bebedouro para gatos")

    assert len(data.interest_over_time) == 2
    assert data.interest_over_time[0].value == 36
    assert data.interest_over_time[1].value == 57


def test_fetch_trend_data_raises_instead_of_silent_zero_observations(monkeypatch):
    """Regression test: non-empty interest_over_time that fails to parse must
    raise ApifyTrendsDataError, never silently report zero observations."""

    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=201, json_data=[REPORT_ROW_WITH_UNPARSEABLE_VALUES])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsDataError):
        fetch_trend_data("bebedouro para gatos")


def test_fetch_trend_data_raises_on_actor_error_row(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=200, json_data=[ERROR_ROW])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsActorError) as exc_info:
        fetch_trend_data("bebedouro automatico gatos")
    assert "blocked" in str(exc_info.value)


def test_fetch_trend_data_raises_when_only_summary_info_rows_present(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=200, json_data=[SUMMARY_ROW, INFO_ROW])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsDataError):
        fetch_trend_data("bebedouro automatico gatos")


def test_fetch_trend_data_raises_when_token_missing(monkeypatch):
    monkeypatch.setattr(apify_trends.src.config, "get_apify_token", lambda: None)

    with pytest.raises(ApifyTrendsConfigurationError):
        fetch_trend_data("bebedouro automatico gatos")


def test_fetch_trend_data_raises_on_timeout(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsTimeoutError):
        fetch_trend_data("bebedouro automatico gatos")


def test_fetch_trend_data_raises_on_connection_error(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsConnectionError):
        fetch_trend_data("bebedouro automatico gatos")


@pytest.mark.parametrize("status_code", [400, 401, 404, 429, 500, 503])
def test_fetch_trend_data_raises_on_non_200_response(monkeypatch, status_code):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=status_code, json_data={})

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsResponseError) as exc_info:
        fetch_trend_data("bebedouro automatico gatos")
    assert exc_info.value.status_code == status_code


def test_fetch_trend_data_raises_on_malformed_json(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=200, json_error=ValueError("bad json"))

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsDataError):
        fetch_trend_data("bebedouro automatico gatos")


def test_fetch_trend_data_raises_on_empty_dataset(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=200, json_data=[])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsDataError):
        fetch_trend_data("bebedouro automatico gatos")


def test_fetch_trend_data_raises_on_unexpected_schema(monkeypatch):
    def fake_post(url, headers=None, json=None, timeout=None):
        return FakeResponse(status_code=200, json_data=[{"foo": "bar"}])

    monkeypatch.setattr(apify_trends.requests, "post", fake_post)

    with pytest.raises(ApifyTrendsDataError):
        fetch_trend_data("bebedouro automatico gatos")


def test_fetch_trend_data_rejects_empty_query():
    with pytest.raises(ValueError):
        fetch_trend_data("   ")


# -- transport errors must not carry request headers ---------------------


def test_request_exception_message_is_not_forwarded_to_callers(monkeypatch):
    """A transport error's message must not reach the raised error.

    `requests` embeds the offending header VALUE in some transport
    errors -- notably `InvalidHeader`, raised offline before any socket
    opens when a token contains a newline (easy to produce with a
    double-quoted `.env` value or `Get-Content -Raw`). Interpolating
    that message leaked `Authorization: Bearer <token>` to every caller.

    Verified reaching stdout through four separate CLI paths before this
    was fixed, so the guard belongs here at the integration boundary
    rather than in any one caller.
    """
    fixture_value = "not-a-credential-fixture-value"
    monkeypatch.setattr(
        apify_trends.src.config, "get_apify_token", lambda: fixture_value + "\n")

    def exploding_post(*args, **kwargs):
        # Let `requests` reject the header the integration actually built.
        requests.Request("POST", "https://example.invalid",
                         headers=kwargs.get("headers") or {}).prepare()
        raise AssertionError("expected requests to reject the header")

    monkeypatch.setattr(apify_trends.requests, "post", exploding_post)

    with pytest.raises(apify_trends.ApifyTrendsError) as excinfo:
        apify_trends.fetch_trend_data("fone bluetooth")

    message = str(excinfo.value)
    assert fixture_value not in message
    assert "Bearer" not in message
    # Still diagnosable: the failure mode is named, just not quoted.
    assert "InvalidHeader" in message

    # The original is NOT chained: see
    # test_transport_error_is_not_chained_as_cause_or_context. Keeping it
    # as __cause__ would re-expose the credential through
    # traceback.format_exception() and logging.exception().
    assert excinfo.value.__cause__ is None


# -- transport errors must not be reachable through the exception chain --


def test_transport_error_is_not_chained_as_cause_or_context(monkeypatch):
    """A sanitized message is not enough: the chain must be severed too.

    EVERY `requests` exception carries `.request.headers`, holding the
    live `Authorization: Bearer <token>`, and some embed the header value
    in their message text. So `raise Public(...) from exc` leaks the
    credential through `traceback.format_exception()` and
    `logging.exception()` even when `str(public)` is clean.

    `from None` is NOT sufficient -- it clears `__cause__` but leaves
    `__context__` holding the original, reachable by anything that walks
    the chain. Clearing `__context__` inside the `except` block is also
    insufficient: `raise` re-sets it afterwards. The integration
    therefore raises the sanitized error AFTER the `except` block
    completes, which is the only option that leaves nothing reachable.
    """
    import logging
    import traceback

    fixture_value = "not-a-credential-fixture-value"
    monkeypatch.setattr(
        apify_trends.src.config, "get_apify_token",
        lambda: fixture_value + "\n")

    def exploding(*args, **kwargs):
        requests.Request("POST", "https://example.invalid",
                         headers=kwargs.get("headers") or {}).prepare()
        raise AssertionError("expected requests to reject the header")

    monkeypatch.setattr(apify_trends.requests, "post", exploding)

    with pytest.raises(apify_trends.ApifyTrendsError) as excinfo:
        apify_trends.fetch_trend_data("fone bluetooth")

    public = excinfo.value

    # 1. the chain is severed in both directions
    assert public.__cause__ is None
    assert public.__context__ is None

    # 2. formatted tracebacks carry nothing
    formatted = "".join(traceback.format_exception(
        type(public), public, public.__traceback__))
    assert fixture_value not in formatted
    assert "Bearer" not in formatted

    # 3. standard exception logging carries nothing
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("test.apify.chain")
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        try:
            raise public
        except Exception:
            logger.exception("integration failure")
    finally:
        logger.removeHandler(handler)
    assert fixture_value not in stream.getvalue()

    # 4. safe diagnostics survive -- the failure mode is still named
    assert "InvalidHeader" in str(public)
