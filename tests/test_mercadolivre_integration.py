"""Tests for the Mercado Livre integration layer.

None of these tests touch the live Mercado Livre API: requests.get is
monkeypatched with fakes that simulate success, timeout, connection
failure, non-200 responses, malformed JSON, and empty results.
"""

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
