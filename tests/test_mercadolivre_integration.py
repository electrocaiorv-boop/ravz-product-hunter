"""Tests for the Mercado Livre integration layer.

None of these tests touch the live Mercado Livre API: requests.get is
monkeypatched with fakes that simulate success, timeout, connection
failure, non-200 responses, malformed JSON, and empty results.
"""

import io

import requests
import pytest

from src.integrations import mercadolivre
from src.integrations.mercadolivre import (
    MercadoLivreConnectionError,
    MercadoLivreDataError,
    MercadoLivreResponseError,
    MercadoLivreTimeoutError,
    search_products,
)


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, json_error=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


def test_search_products_maps_successful_response(monkeypatch):
    raw_results = [
        {
            "id": "MLB123",
            "title": "Bebedouro Automatico para Gatos",
            "price": 89.9,
            "currency_id": "BRL",
            "seller": {"id": 42},
            "category_id": "MLB1234",
            "condition": "new",
            "permalink": "https://produto.mercadolivre.com.br/MLB123",
            "shipping": {"free_shipping": True},
            "available_quantity": 15,
        }
    ]

    def fake_get(url, params=None, headers=None, timeout=None):
        assert url == f"{mercadolivre.BASE_URL}/sites/{mercadolivre.SITE_ID}/search"
        assert params == {"q": "bebedouro automatico gatos", "limit": 10}
        return FakeResponse(status_code=200, json_data={"results": raw_results})

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    items = search_products("bebedouro automatico gatos")

    assert len(items) == 1
    item = items[0]
    assert item.item_id == "MLB123"
    assert item.title == "Bebedouro Automatico para Gatos"
    assert item.price == 89.9
    assert item.currency_id == "BRL"
    assert item.seller_id == 42
    assert item.category_id == "MLB1234"
    assert item.condition == "new"
    assert item.permalink == "https://produto.mercadolivre.com.br/MLB123"
    assert item.free_shipping is True
    assert item.available_quantity == 15


def test_search_products_handles_missing_optional_fields(monkeypatch):
    raw_results = [{"id": "MLB999", "title": "Produto sem detalhes"}]

    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=200, json_data={"results": raw_results})

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    items = search_products("produto sem detalhes")

    item = items[0]
    assert item.item_id == "MLB999"
    assert item.title == "Produto sem detalhes"
    assert item.price is None
    assert item.seller_id is None
    assert item.free_shipping is None


def test_search_products_handles_empty_results(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=200, json_data={"results": []})

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    items = search_products("produto inexistente xyz")

    assert items == []


def test_search_products_raises_on_timeout(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        raise requests.Timeout("timed out")

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    with pytest.raises(MercadoLivreTimeoutError):
        search_products("bebedouro automatico gatos")


def test_search_products_raises_on_connection_error(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        raise requests.ConnectionError("no network")

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    with pytest.raises(MercadoLivreConnectionError):
        search_products("bebedouro automatico gatos")


@pytest.mark.parametrize("status_code", [403, 404, 429, 500, 503])
def test_search_products_raises_on_non_200_response(monkeypatch, status_code):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=status_code, json_data={})

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    with pytest.raises(MercadoLivreResponseError) as exc_info:
        search_products("bebedouro automatico gatos")
    assert exc_info.value.status_code == status_code


def test_search_products_raises_on_malformed_json(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=200, json_error=ValueError("bad json"))

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    with pytest.raises(MercadoLivreDataError):
        search_products("bebedouro automatico gatos")


def test_search_products_raises_on_missing_results_field(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=200, json_data={"unexpected": "shape"})

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    with pytest.raises(MercadoLivreDataError):
        search_products("bebedouro automatico gatos")


def test_search_products_rejects_empty_query():
    with pytest.raises(ValueError):
        search_products("   ")


@pytest.mark.parametrize("limit", [0, -1, -10])
def test_search_products_rejects_invalid_limit(limit):
    with pytest.raises(ValueError):
        search_products("bebedouro automatico gatos", limit=limit)


def test_search_products_sends_bearer_token_when_env_var_set(monkeypatch):
    monkeypatch.setenv(mercadolivre.ACCESS_TOKEN_ENV_VAR, "fake-token-123")
    captured_headers = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured_headers.update(headers or {})
        return FakeResponse(status_code=200, json_data={"results": []})

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    search_products("bebedouro automatico gatos")

    assert captured_headers.get("Authorization") == "Bearer fake-token-123"


def test_search_products_sends_no_auth_header_by_default(monkeypatch):
    monkeypatch.delenv(mercadolivre.ACCESS_TOKEN_ENV_VAR, raising=False)
    captured_headers = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured_headers.update(headers or {})
        return FakeResponse(status_code=200, json_data={"results": []})

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)

    search_products("bebedouro automatico gatos")

    assert "Authorization" not in captured_headers


# -- transport errors must not carry request headers ---------------------


def test_request_exception_message_is_not_forwarded_to_callers(monkeypatch):
    """The same guard as apify_trends: see that test for the rationale.

    `requests` embeds the offending header value in some transport
    errors, so this integration reports the exception TYPE and withholds
    its message.
    """
    fixture_value = "not-a-credential-fixture-value"
    monkeypatch.setenv(mercadolivre.ACCESS_TOKEN_ENV_VAR, fixture_value + "\n")

    def exploding_get(*args, **kwargs):
        requests.Request("GET", "https://example.invalid",
                         headers=kwargs.get("headers") or {}).prepare()
        raise AssertionError("expected requests to reject the header")

    monkeypatch.setattr(mercadolivre.requests, "get", exploding_get)

    with pytest.raises(mercadolivre.MercadoLivreError) as excinfo:
        mercadolivre.search_products("fone bluetooth")

    message = str(excinfo.value)
    assert fixture_value not in message
    assert "Bearer" not in message
    assert "InvalidHeader" in message
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
    monkeypatch.setenv(
        mercadolivre.ACCESS_TOKEN_ENV_VAR, fixture_value + "\n")

    def exploding(*args, **kwargs):
        requests.Request("GET", "https://example.invalid",
                         headers=kwargs.get("headers") or {}).prepare()
        raise AssertionError("expected requests to reject the header")

    monkeypatch.setattr(mercadolivre.requests, "get", exploding)

    with pytest.raises(mercadolivre.MercadoLivreError) as excinfo:
        mercadolivre.search_products("fone bluetooth")

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
    logger = logging.getLogger("test.ml.chain")
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
