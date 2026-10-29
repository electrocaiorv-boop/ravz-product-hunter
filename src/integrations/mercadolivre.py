"""Mercado Livre integration layer.

This is the ONLY module in the project allowed to know about HTTP, JSON,
or the Mercado Livre API. Everything else in the application (CLI,
scoring engine, models) talks to this module through `search_products()`
and never touches `requests` or raw API responses directly.

Endpoint called: GET https://api.mercadolibre.com/sites/MLB/search?q=...

CLASSIFICATION OF THIS INTEGRATION: EXPERIMENTAL / NOT OFFICIALLY
DOCUMENTED. Re-verified against the current official docs
(developers.mercadolivre.com.br/pt_br/itens-e-buscas, "Itens e Buscas",
last updated by Mercado Livre on 2026-08-31):

- That documentation describes /sites/{SITE_ID}/search ONLY for
  `nickname` and `seller_id` lookups. Every example for this endpoint
  sends `Authorization: Bearer ACCESS_TOKEN`.
- A free-text `q` parameter is NOT part of that documented contract for
  this endpoint. The officially documented `q` parameter lives on the
  separate `/products/search` catalog/GTIN endpoint (a different
  resource, used for catalog/publishing lookups, not general search),
  which this module does NOT call.
- Therefore: calling `/sites/MLB/search?q=<free text>` as this module
  does is NOT an officially documented or guaranteed contract. It is
  kept for this learning phase only because it is useful for
  demonstrating safe HTTP/error handling end to end, NOT because its
  behavior is promised by Mercado Livre. It may change shape, stop
  working, or be restricted further at any time without notice. Do not
  build anything beyond this learning phase on top of it without
  re-verifying the official docs first (see docs/MAINTENANCE.md).

Authentication: because every current example for /sites/{SITE_ID}/search
(for its documented nickname/seller_id use) requires a bearer token,
authentication should be treated as EXPECTED by Mercado Livre for this
endpoint family -- even though it is unverified for this module's
undocumented `q` usage specifically. This module sends
`Authorization: Bearer <token>` automatically if
MERCADO_LIVRE_ACCESS_TOKEN is set in the environment; it still runs
without one (never hardcoded, never required to import/call this
module), but a request without a token is more likely to fail. A 403
response should not be read as proof that `q` search itself is broken --
it may simply mean no token was supplied, or that Mercado Livre is
blocking this endpoint or this caller's network entirely. See
docs/MAINTENANCE.md for what was actually observed when this was last
checked.
"""

import os
from dataclasses import dataclass

import requests

BASE_URL = "https://api.mercadolibre.com"
SITE_ID = "MLB"
DEFAULT_TIMEOUT = 10
ACCESS_TOKEN_ENV_VAR = "MERCADO_LIVRE_ACCESS_TOKEN"


class MercadoLivreError(Exception):
    """Base class for all Mercado Livre integration failures."""


class MercadoLivreTimeoutError(MercadoLivreError):
    """The request to Mercado Livre timed out."""


class MercadoLivreConnectionError(MercadoLivreError):
    """Could not connect to Mercado Livre (network/DNS failure)."""


class MercadoLivreResponseError(MercadoLivreError):
    """Mercado Livre returned a non-200 HTTP status code."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class MercadoLivreDataError(MercadoLivreError):
    """Mercado Livre returned a response we could not parse or understand."""


@dataclass
class MercadoLivreItem:
    """A single search result, mapped from the raw Mercado Livre JSON.

    Only fields actually present in the API response are populated; any
    field not returned by Mercado Livre for a given item is left as None
    rather than guessed or fabricated.

    `available_quantity` is NOT exact real-time stock. Mercado Livre's
    public item/search resources report it as a reference bucket: a real
    quantity in a range is rounded down to that range's floor (e.g. a
    real stock of 51-100 units is returned as the reference value 50).
    Treat it as "at least roughly this many," never as precise inventory.
    """

    item_id: str
    title: str
    price: float | None
    currency_id: str | None
    seller_id: int | None
    category_id: str | None
    condition: str | None
    permalink: str | None
    free_shipping: bool | None
    available_quantity: int | None


def _map_item(raw: dict) -> MercadoLivreItem:
    """Map one raw result object from the search response to MercadoLivreItem."""
    seller = raw.get("seller") or {}
    shipping = raw.get("shipping") or {}
    return MercadoLivreItem(
        item_id=raw.get("id"),
        title=raw.get("title"),
        price=raw.get("price"),
        currency_id=raw.get("currency_id"),
        seller_id=seller.get("id"),
        category_id=raw.get("category_id"),
        condition=raw.get("condition"),
        permalink=raw.get("permalink"),
        free_shipping=shipping.get("free_shipping"),
        available_quantity=raw.get("available_quantity"),
    )


def _build_headers() -> dict:
    token = os.environ.get(ACCESS_TOKEN_ENV_VAR)
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}


def search_products(
    query: str, limit: int = 10, timeout: float = DEFAULT_TIMEOUT
) -> list[MercadoLivreItem]:
    """Search Mercado Livre Brazil (MLB) for items matching `query`.

    Raises ValueError for invalid arguments, and a MercadoLivreError
    subclass for any network/HTTP/JSON failure. Never raises a raw
    requests or JSON-decoding exception to callers.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")
    if limit < 1:
        raise ValueError("limit must be at least 1")

    params = {"q": query, "limit": limit}

    try:
        response = requests.get(
            f"{BASE_URL}/sites/{SITE_ID}/search",
            params=params,
            headers=_build_headers(),
            timeout=timeout,
        )
    except requests.Timeout as exc:
        raise MercadoLivreTimeoutError(
            f"Mercado Livre did not respond within {timeout}s"
        ) from exc
    except requests.ConnectionError as exc:
        raise MercadoLivreConnectionError(
            "Could not connect to Mercado Livre"
        ) from exc
    except requests.RequestException as exc:
        raise MercadoLivreError(f"Mercado Livre request failed: {exc}") from exc

    if response.status_code == 403:
        raise MercadoLivreResponseError(
            status_code=403,
            message=(
                "Mercado Livre returned 403 Forbidden for this search. "
                "This free-text 'q' usage is not part of the documented "
                "contract for this endpoint, authentication may be "
                "expected, and the caller's network may be blocked -- "
                "see docs/MAINTENANCE.md for what was actually observed."
            ),
        )
    if response.status_code != 200:
        raise MercadoLivreResponseError(
            status_code=response.status_code,
            message=f"Mercado Livre returned HTTP {response.status_code}",
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise MercadoLivreDataError(
            "Mercado Livre returned a response that was not valid JSON"
        ) from exc

    results = data.get("results")
    if results is None:
        raise MercadoLivreDataError(
            "Mercado Livre response did not contain a 'results' field"
        )

    return [_map_item(raw) for raw in results]
