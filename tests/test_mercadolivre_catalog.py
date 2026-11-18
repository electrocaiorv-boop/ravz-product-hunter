"""Tests for the Mercado Livre category-catalog integration (Fase 13).

No real credentials, no network. `requests.get` is monkeypatched with
fakes dispatched by URL, mirroring `tests/test_mercadolivre_integration.py`.
Two fixture files captured live and read-only on 2026-11-17 (see
tests/fixtures/mercadolivre_catalog/) seed the "realistic shape" tests;
every other case is synthetic.
"""

import json
from pathlib import Path

import pytest
import requests

from src.integrations import mercadolivre_catalog as catalog
from src.integrations.mercadolivre import (
    MercadoLivreConnectionError,
    MercadoLivreDataError,
    MercadoLivreError,
    MercadoLivreResponseError,
    MercadoLivreTimeoutError,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "mercadolivre_catalog"


def _load(name: str):
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


DOMAIN_DISCOVERY_BODY = _load("domain_discovery_fone_bluetooth.json")
HIGHLIGHTS_BODY = _load("highlights_MLB196208.json")
PRODUCT_DETAIL_BODY = _load("product_MLB24028629.json")
PRODUCT_ITEMS_BODY = _load("product_items_MLB24028629.json")

CATEGORY_ID = "MLB196208"
PRODUCT_ID = "MLB24028629"


class FakeResponse:
    def __init__(self, status_code=200, json_data=None, json_error=None):
        self.status_code = status_code
        self._json_data = json_data
        self._json_error = json_error

    def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._json_data


def _router(routes):
    """routes: dict[url_substring] -> callable(params) -> FakeResponse."""

    def fake_get(url, params=None, headers=None, timeout=None):
        for substring, handler in routes.items():
            if substring in url:
                return handler(params)
        raise AssertionError(f"unexpected URL in test: {url}")

    return fake_get


def _ok(body):
    return lambda params=None: FakeResponse(status_code=200, json_data=body)


# -- discover_category ---------------------------------------------------


def test_discover_category_maps_first_match(monkeypatch):
    monkeypatch.setattr(
        catalog.requests, "get", _router({"domain_discovery": _ok(DOMAIN_DISCOVERY_BODY)})
    )
    match = catalog.discover_category("fone bluetooth")
    assert match.category_id == "MLB196208"
    assert match.category_name == "Fones de Ouvido"


def test_discover_category_returns_none_on_empty_match(monkeypatch):
    monkeypatch.setattr(catalog.requests, "get", _router({"domain_discovery": _ok([])}))
    assert catalog.discover_category("xyz nonsense query") is None


def test_discover_category_rejects_empty_query():
    with pytest.raises(ValueError):
        catalog.discover_category("   ")


def test_discover_category_raises_data_error_on_non_list_body(monkeypatch):
    monkeypatch.setattr(catalog.requests, "get", _router({"domain_discovery": _ok({"not": "a list"})}))
    with pytest.raises(MercadoLivreDataError):
        catalog.discover_category("fone bluetooth")


def test_discover_category_raises_response_error_on_non_200(monkeypatch):
    monkeypatch.setattr(
        catalog.requests,
        "get",
        _router({"domain_discovery": lambda params=None: FakeResponse(status_code=500)}),
    )
    with pytest.raises(MercadoLivreResponseError):
        catalog.discover_category("fone bluetooth")


def test_discover_category_raises_timeout(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        raise requests.Timeout()

    monkeypatch.setattr(catalog.requests, "get", fake_get)
    with pytest.raises(MercadoLivreTimeoutError):
        catalog.discover_category("fone bluetooth")


def test_discover_category_raises_connection_error(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        raise requests.ConnectionError()

    monkeypatch.setattr(catalog.requests, "get", fake_get)
    with pytest.raises(MercadoLivreConnectionError):
        catalog.discover_category("fone bluetooth")


def test_discover_category_raises_data_error_on_malformed_json(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        return FakeResponse(status_code=200, json_error=ValueError("boom"))

    monkeypatch.setattr(catalog.requests, "get", fake_get)
    with pytest.raises(MercadoLivreDataError):
        catalog.discover_category("fone bluetooth")


# -- fetch_category_highlights --------------------------------------------


def test_fetch_category_highlights_maps_real_shape(monkeypatch):
    monkeypatch.setattr(catalog.requests, "get", _router({"highlights": _ok(HIGHLIGHTS_BODY)}))
    entries = catalog.fetch_category_highlights(CATEGORY_ID)
    assert len(entries) == 20
    assert entries[0] == catalog.HighlightEntry(kind="PRODUCT", id="MLB24028629", position=1)
    # position 14 in the real capture is "USER_PRODUCT" -- an unsupported
    # kind this module must not guess an endpoint for.
    assert entries[13].kind == "USER_PRODUCT"


def test_fetch_category_highlights_empty_content(monkeypatch):
    monkeypatch.setattr(
        catalog.requests, "get", _router({"highlights": _ok({"content": []})})
    )
    assert catalog.fetch_category_highlights(CATEGORY_ID) == []


def test_fetch_category_highlights_skips_malformed_entries(monkeypatch):
    body = {"content": [{"type": "PRODUCT"}, {"id": "MLB1"}, {"id": "MLB2", "type": "PRODUCT"}]}
    monkeypatch.setattr(catalog.requests, "get", _router({"highlights": _ok(body)}))
    entries = catalog.fetch_category_highlights(CATEGORY_ID)
    assert len(entries) == 1
    assert entries[0].id == "MLB2"


def test_fetch_category_highlights_raises_data_error_without_content_key(monkeypatch):
    monkeypatch.setattr(catalog.requests, "get", _router({"highlights": _ok({"nope": True})}))
    with pytest.raises(MercadoLivreDataError):
        catalog.fetch_category_highlights(CATEGORY_ID)


# -- fetch_product_detail / fetch_product_offers --------------------------


def test_fetch_product_detail_maps_real_shape(monkeypatch):
    monkeypatch.setattr(
        catalog.requests, "get", _router({"/products/": _ok(PRODUCT_DETAIL_BODY)})
    )
    info = catalog.fetch_product_detail(PRODUCT_ID)
    assert info.product_id == PRODUCT_ID
    assert "Soundcore" in info.name


def test_fetch_product_offers_maps_real_shape_flat_seller_id(monkeypatch):
    monkeypatch.setattr(
        catalog.requests, "get", _router({"/items": _ok(PRODUCT_ITEMS_BODY)})
    )
    offers = catalog.fetch_product_offers(PRODUCT_ID, title="Fone X")
    assert len(offers) == 2
    first, second = offers
    assert first.item_id == "MLB5410852112"
    assert first.seller_id == 2440134845  # flat field, not nested under "seller"
    assert first.price == 129
    assert first.currency_id == "BRL"
    assert first.condition == "new"
    assert first.free_shipping is True
    assert first.title == "Fone X"  # supplied by caller, not read per-offer
    assert first.permalink is None
    assert first.available_quantity is None
    # Fase 13: official_store_id confirmed present in the real capture --
    # an int for the first offer, null (-> None) for the second.
    assert first.official_store_id == 190206
    assert second.official_store_id is None


def test_fetch_product_offers_raises_data_error_without_results_key(monkeypatch):
    monkeypatch.setattr(catalog.requests, "get", _router({"/items": _ok({"nope": True})}))
    with pytest.raises(MercadoLivreDataError):
        catalog.fetch_product_offers(PRODUCT_ID, title=None)


# -- fetch_item_detail ------------------------------------------------------


def test_fetch_item_detail_maps_search_result_shape(monkeypatch):
    raw = {
        "id": "MLB777",
        "title": "Fone Standalone",
        "price": 50.0,
        "currency_id": "BRL",
        "seller": {"id": 99},
        "category_id": "MLB196208",
        "condition": "new",
        "permalink": "https://x",
        "shipping": {"free_shipping": False},
        "available_quantity": 3,
    }
    monkeypatch.setattr(catalog.requests, "get", _router({"/items/": _ok(raw)}))
    item = catalog.fetch_item_detail("MLB777")
    assert item.item_id == "MLB777"
    assert item.seller_id == 99
    assert item.title == "Fone Standalone"


# -- sample_category_competition: top_n validation --------------------------


@pytest.mark.parametrize("top_n", [0, -1, 11, 100])
def test_sample_category_competition_rejects_out_of_range_top_n(top_n):
    with pytest.raises(ValueError):
        catalog.sample_category_competition("fone bluetooth", top_n=top_n)


# -- sample_category_competition: end-to-end wiring --------------------------


def test_sample_category_competition_full_success(monkeypatch):
    call_count = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        call_count["n"] += 1
        if "domain_discovery" in url:
            return FakeResponse(200, DOMAIN_DISCOVERY_BODY)
        if "highlights" in url:
            return FakeResponse(200, HIGHLIGHTS_BODY)
        if url.endswith("/items") and "/products/" in url:
            return FakeResponse(200, PRODUCT_ITEMS_BODY)
        if "/products/" in url:
            return FakeResponse(200, PRODUCT_DETAIL_BODY)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(catalog.requests, "get", fake_get)

    sample = catalog.sample_category_competition("fone bluetooth", top_n=1)

    assert sample.category_id == "MLB196208"
    assert sample.category_name == "Fones de Ouvido"
    assert sample.requested_top_n == 1
    assert sample.skipped == []
    assert len(sample.groups) == 1
    group = sample.groups[0]
    assert group.product_id == PRODUCT_ID
    assert "Soundcore" in group.product_name
    assert group.is_standalone_item is False
    assert len(group.offers) == 2
    # request budget: 1 domain_discovery + 1 highlights + 1 product detail
    # + 1 product offers = 4, for top_n=1 (worst case 2 + 2*top_n = 4). Holds.
    assert call_count["n"] == 4


def test_sample_category_competition_bounds_requests_for_top_n(monkeypatch):
    call_count = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        call_count["n"] += 1
        if "domain_discovery" in url:
            return FakeResponse(200, DOMAIN_DISCOVERY_BODY)
        if "highlights" in url:
            return FakeResponse(200, HIGHLIGHTS_BODY)
        if url.endswith("/items") and "/products/" in url:
            return FakeResponse(200, {"paging": {"total": 0}, "results": []})
        if "/products/" in url:
            return FakeResponse(200, {"id": "x", "name": "Produto X"})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(catalog.requests, "get", fake_get)

    top_n = 5
    sample = catalog.sample_category_competition("fone bluetooth", top_n=top_n)
    assert len(sample.groups) == top_n  # all 20 highlighted entries are PRODUCT
    assert call_count["n"] <= 2 + 2 * top_n


def test_sample_category_competition_no_category_found(monkeypatch):
    monkeypatch.setattr(catalog.requests, "get", _router({"domain_discovery": _ok([])}))
    assert catalog.sample_category_competition("asdkjaslkdj") is None


def test_sample_category_competition_category_found_but_no_highlights(monkeypatch):
    monkeypatch.setattr(
        catalog.requests,
        "get",
        _router(
            {
                "domain_discovery": _ok(DOMAIN_DISCOVERY_BODY),
                "highlights": _ok({"content": []}),
            }
        ),
    )
    sample = catalog.sample_category_competition("fone bluetooth")
    assert sample.groups == []
    assert sample.skipped == ["category has no best-seller highlights"]


def test_sample_category_competition_unsupported_kind_is_skipped_not_guessed(monkeypatch):
    highlights_body = {
        "content": [
            {"id": "MLBU123", "position": 1, "type": "USER_PRODUCT"},
        ]
    }
    monkeypatch.setattr(
        catalog.requests,
        "get",
        _router(
            {
                "domain_discovery": _ok(DOMAIN_DISCOVERY_BODY),
                "highlights": _ok(highlights_body),
            }
        ),
    )
    sample = catalog.sample_category_competition("fone bluetooth", top_n=1)
    assert sample.groups == []
    assert sample.skipped == ["unsupported highlight type: USER_PRODUCT (MLBU123)"]


def test_sample_category_competition_partial_failure_degrades_not_aborts(monkeypatch):
    """One product's /items call fails; the sample keeps going with the rest."""
    highlights_body = {
        "content": [
            {"id": "MLB_BAD", "position": 1, "type": "PRODUCT"},
            {"id": "MLB_GOOD", "position": 2, "type": "PRODUCT"},
        ]
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        if "domain_discovery" in url:
            return FakeResponse(200, DOMAIN_DISCOVERY_BODY)
        if "highlights" in url:
            return FakeResponse(200, highlights_body)
        if "MLB_BAD" in url and url.endswith("/items"):
            return FakeResponse(500)
        if "MLB_BAD" in url:
            return FakeResponse(200, {"id": "MLB_BAD", "name": "Produto Ruim"})
        if "MLB_GOOD" in url and url.endswith("/items"):
            return FakeResponse(200, {"paging": {"total": 1}, "results": [
                {"item_id": "i1", "seller_id": 1, "price": 10, "currency_id": "BRL",
                 "condition": "new", "shipping": {"free_shipping": True}},
            ]})
        if "MLB_GOOD" in url:
            return FakeResponse(200, {"id": "MLB_GOOD", "name": "Produto Bom"})
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(catalog.requests, "get", fake_get)

    sample = catalog.sample_category_competition("fone bluetooth", top_n=2)
    assert len(sample.groups) == 1
    assert sample.groups[0].product_id == "MLB_GOOD"
    assert len(sample.skipped) == 1
    assert "MLB_BAD" in sample.skipped[0]


def test_sample_category_competition_total_failure_yields_empty_groups(monkeypatch):
    highlights_body = {"content": [{"id": "MLB1", "position": 1, "type": "PRODUCT"}]}

    def fake_get(url, params=None, headers=None, timeout=None):
        if "domain_discovery" in url:
            return FakeResponse(200, DOMAIN_DISCOVERY_BODY)
        if "highlights" in url:
            return FakeResponse(200, highlights_body)
        return FakeResponse(500)

    monkeypatch.setattr(catalog.requests, "get", fake_get)
    sample = catalog.sample_category_competition("fone bluetooth", top_n=1)
    assert sample.groups == []
    assert len(sample.skipped) == 1


def test_sample_category_competition_standalone_item_entry(monkeypatch):
    highlights_body = {"content": [{"id": "MLB_ITEM1", "position": 1, "type": "ITEM"}]}
    item_raw = {
        "id": "MLB_ITEM1",
        "title": "Fone Solo",
        "price": 80.0,
        "currency_id": "BRL",
        "seller": {"id": 7},
        "category_id": "MLB196208",
        "condition": "new",
        "permalink": "https://x",
        "shipping": {"free_shipping": True},
        "available_quantity": 1,
    }

    def fake_get(url, params=None, headers=None, timeout=None):
        if "domain_discovery" in url:
            return FakeResponse(200, DOMAIN_DISCOVERY_BODY)
        if "highlights" in url:
            return FakeResponse(200, highlights_body)
        if "/items/" in url:
            return FakeResponse(200, item_raw)
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(catalog.requests, "get", fake_get)
    sample = catalog.sample_category_competition("fone bluetooth", top_n=1)
    assert len(sample.groups) == 1
    group = sample.groups[0]
    assert group.is_standalone_item is True
    assert group.product_id is None
    assert group.product_name == "Fone Solo"
    assert len(group.offers) == 1
    assert group.offers[0].seller_id == 7


# -- token never leaks -------------------------------------------------------


def test_token_never_appears_in_exception_text(monkeypatch):
    monkeypatch.setenv("MERCADO_LIVRE_ACCESS_TOKEN", "fake-secret-token-xyz")

    def fake_get(url, params=None, headers=None, timeout=None):
        assert "fake-secret-token-xyz" in headers.get("Authorization", "")  # confirms the header really carries it
        raise requests.exceptions.InvalidHeader(
            f"Invalid header: Authorization: {headers.get('Authorization')}"
        )

    monkeypatch.setattr(catalog.requests, "get", fake_get)
    with pytest.raises(MercadoLivreError) as excinfo:
        catalog.discover_category("fone bluetooth")
    assert "fake-secret-token-xyz" not in str(excinfo.value)
