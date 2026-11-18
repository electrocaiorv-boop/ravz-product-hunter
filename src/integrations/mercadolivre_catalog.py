"""Mercado Livre category-catalog integration layer (Fase 13).

This is the second, and only other, module allowed to speak HTTP to
Mercado Livre. It exists because `/sites/MLB/search` -- the only
endpoint `mercadolivre.py` calls -- is blocked by a Mercado Livre
policy refusal that persists even with a valid, authenticated token
(see docs/MERCADO_LIVRE_403.md). This module provides a DIFFERENT,
working path to competitive listing evidence, built from documented,
live-validated endpoints:

    keyword -> /sites/MLB/domain_discovery/search   (which category?)
            -> /highlights/MLB/category/{id}          (top sellers there)
            -> /products/{id} + /products/{id}/items  (catalog product:
                   its name, and the real seller offers competing on it)
            -> /items/{id}                             (a highlight that
                   is already a single standalone listing, not a
                   catalog product)

== What this is NOT ==

`/products/search` (the catalog/GTIN endpoint) is never called here and
its results must never be treated as listings: a catalog product
describes a normalized PRODUCT, not a seller's OFFER. Every seller-level
fact this module produces (price, seller_id, condition, free_shipping)
comes from `/products/{id}/items` or `/items/{id}` -- real offers from
real sellers -- never from a catalog record pretending to be one.

`/sites/MLB/search` is NOT called here and is NOT deleted from
`mercadolivre.py` either -- it stays in the code as a disabled source,
per the Fase 13 decision in docs/VISAO_GERAL.md. This module is
additive, not a replacement of that one.

== Request budget (hard bound, enforced by code shape) ==

For one `sample_category_competition(query, top_n)` call:

    1x domain_discovery
    1x highlights
    up to top_n x (1 request per sampled highlight entry: either
       `/products/{id}` + `/products/{id}/items` for a PRODUCT, or
       `/items/{id}` for an ITEM -- never both for the same entry)

Worst case (every sampled entry is a PRODUCT, each needing 2 calls):
    2 + 2 * top_n

`top_n` defaults to 5 (max 12 requests) and is hard-capped at 10 (max 22
requests) -- enforced by `sample_category_competition`, not left to the
caller's discipline. Sequential, no concurrency, no retries, same as
every other integration in this project.

== Partial failure is tolerated at the per-entry level ==

If fetching one highlight entry's detail/offers fails (timeout, 403,
malformed JSON, whatever), that ONE entry is dropped from the sample
with a recorded reason in `CategoryCompetitionSample.skipped` -- the
rest of the chain continues. This is not a silent fallback: the
omission is explicit and inspectable. The whole sample degrades to
"nothing usable" only if every sampled entry fails, or if the category
itself cannot be found -- never a crash that would escape the caller as
something the orchestrator does not catch.

== Highlight entry kinds ==

Live-observed kinds, from `/highlights/MLB/category/MLB196208` for
"fone bluetooth" on 2026-11-17: `PRODUCT` (handled -- catalog product,
fetched via /products/{id} + /products/{id}/items) and `USER_PRODUCT`
(seen in that same response, position 14). `ITEM` is the kind this
project's planning docs anticipated for a standalone single-seller
listing (fetched via /items/{id}) but none appeared in the captured
sample. `USER_PRODUCT` and any other kind this module does not
recognize are recorded as skipped with the literal kind name -- NOT
guessed at, because no endpoint for it has been verified. Extending
support to a new kind requires verifying its resource shape first, the
same discipline `docs/MERCADO_LIVRE_403.md` applies to every endpoint
in this project.

`/items/{id}`'s exact response shape was NOT empirically re-captured in
this session (no ITEM-kind entry was available to probe). It is mapped
here on the strength of Mercado Livre's own documentation, which
describes the single-item resource and the search-result item resource
as the same shape (nested `seller.id`, nested `shipping.free_shipping`,
`title`, `permalink`, `available_quantity`) -- the same shape
`mercadolivre._map_item` already maps. If that assumption is ever
wrong, the affected fields simply read as `None` (every field access
here is `.get()`-based), never a fabricated value and never a crash.
"""

from dataclasses import dataclass, field

import requests

import src.config  # noqa: F401 -- side effect: loads .env before token resolution
from src.integrations.mercadolivre import (
    BASE_URL,
    DEFAULT_TIMEOUT,
    SITE_ID,
    MercadoLivreConnectionError,
    MercadoLivreDataError,
    MercadoLivreError,
    MercadoLivreItem,
    MercadoLivreResponseError,
    MercadoLivreTimeoutError,
    _map_item,
)
from src.integrations.mercadolivre_oauth import resolve_access_token

DEFAULT_TOP_N = 5
MAX_TOP_N = 10

SUPPORTED_HIGHLIGHT_KINDS = ("PRODUCT", "ITEM")


@dataclass
class CategoryMatch:
    """One `domain_discovery` result: a category guess for a keyword."""

    category_id: str
    category_name: str | None


@dataclass
class HighlightEntry:
    """One entry from a category's best-seller highlights."""

    kind: str
    id: str
    position: int | None


@dataclass
class ProductInfo:
    """Catalog product metadata, fetched only for its human-readable name.

    Never used as seller-offer evidence -- see module docstring.
    """

    product_id: str
    name: str | None


@dataclass
class ProductOfferGroup:
    """Offers sampled for one highlighted catalog product or standalone item.

    `is_standalone_item` is True for a `kind="ITEM"` highlight: a single
    seller's own listing, not a catalog product with competing offers.
    `offers` holds exactly one entry in that case.

    Per the Fase 13 approval: standalone items are excluded from the
    per-product seller_concentration/price_crowding averages computed
    in `src/competition_models.py`. A lone listing's unique-seller ratio
    is trivially 1.0 ("the one seller present is unique"), which would
    read as zero concentration and artificially deflate the score --
    the opposite of what a single-seller, no-competing-offers situation
    actually means. They still count toward the shipping signal and the
    observed/product-name context, where no such artifact exists.
    """

    product_id: str | None
    product_name: str | None
    is_standalone_item: bool
    offers: list[MercadoLivreItem]


@dataclass
class CategoryCompetitionSample:
    """Everything sampled for one query via the category-catalog chain.

    `groups` holds one entry per highlight position that was
    successfully resolved into real seller offers. `skipped` records,
    in order, every sampled position that contributed nothing and why
    (fetch failure, or an unsupported highlight kind) -- never silently
    dropped.
    """

    query: str
    category_id: str
    category_name: str | None
    requested_top_n: int
    groups: list[ProductOfferGroup] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def _build_headers() -> dict:
    """Authorization header for one request, or {} when unauthenticated.

    Duplicated from `mercadolivre._build_headers` rather than imported:
    both are five lines wrapping `resolve_access_token()`, and importing
    a leading-underscore name across modules for that little logic isn't
    worth the coupling.
    """
    resolved = resolve_access_token()
    if resolved.available:
        return {"Authorization": f"Bearer {resolved.token}"}
    return {}


def _get(url: str, params: dict | None = None, timeout: float = DEFAULT_TIMEOUT, context: str = ""):
    """One HTTP GET. Returns the parsed JSON body on HTTP 200.

    Raises a MercadoLivreError subclass for every other outcome. The
    delayed-raise pattern for transport failures (store, then raise
    after the except block closes) is deliberate, not incidental --
    see `search_products()` in mercadolivre.py and
    docs/MERCADO_LIVRE_OAUTH.md section 5, finding 1: raising from
    inside the except block would chain the original exception onto
    `__context__`, and `requests`' own transport exceptions can embed
    the full `Authorization` header value in their message.
    """
    suffix = f" for {context}" if context else ""
    transport_error = None
    try:
        response = requests.get(url, params=params, headers=_build_headers(), timeout=timeout)
    except requests.Timeout:
        transport_error = MercadoLivreTimeoutError(
            f"Mercado Livre did not respond within {timeout}s{suffix}"
        )
    except requests.ConnectionError:
        transport_error = MercadoLivreConnectionError(
            f"Could not connect to Mercado Livre{suffix}"
        )
    except requests.RequestException as exc:
        transport_error = MercadoLivreError(
            f"Mercado Livre request failed ({type(exc).__name__}){suffix}; detail "
            "withheld because transport errors can embed request headers"
        )

    if transport_error is not None:
        raise transport_error

    if response.status_code != 200:
        raise MercadoLivreResponseError(
            status_code=response.status_code,
            message=f"Mercado Livre returned HTTP {response.status_code}{suffix}",
        )

    try:
        return response.json()
    except ValueError as exc:
        raise MercadoLivreDataError(
            f"Mercado Livre returned a response that was not valid JSON{suffix}"
        ) from exc


def discover_category(query: str, limit: int = 3, timeout: float = DEFAULT_TIMEOUT) -> CategoryMatch | None:
    """Guess the category for a free-text keyword.

    Returns None when Mercado Livre legitimately found no match (a
    200 with an empty list) -- not a failure, just nothing to sample.
    Raises for a genuine transport/response/data problem.

    Only the first (highest-ranked) match is used. No fallback to a
    second candidate category is attempted if its highlights turn out
    empty -- see module docstring on request-budget discipline.
    """
    if not query or not query.strip():
        raise ValueError("query must not be empty")

    body = _get(
        f"{BASE_URL}/sites/{SITE_ID}/domain_discovery/search",
        params={"q": query, "limit": limit},
        timeout=timeout,
        context="domain_discovery",
    )
    if not isinstance(body, list):
        raise MercadoLivreDataError("domain_discovery response was not a list")
    if not body:
        return None

    first = body[0]
    category_id = first.get("category_id")
    if not category_id:
        raise MercadoLivreDataError("domain_discovery result missing category_id")
    return CategoryMatch(category_id=category_id, category_name=first.get("category_name"))


def fetch_category_highlights(category_id: str, timeout: float = DEFAULT_TIMEOUT) -> list[HighlightEntry]:
    """Best-seller highlights for one category, ranked by position.

    Malformed entries (missing `id` or `type`) are skipped rather than
    guessed at; a category with no highlights returns an empty list.
    """
    body = _get(
        f"{BASE_URL}/highlights/{SITE_ID}/category/{category_id}",
        timeout=timeout,
        context="highlights",
    )
    if not isinstance(body, dict) or "content" not in body:
        raise MercadoLivreDataError("highlights response did not contain 'content'")

    entries = []
    for raw in body.get("content") or []:
        kind = raw.get("type")
        entry_id = raw.get("id")
        if not kind or not entry_id:
            continue
        entries.append(HighlightEntry(kind=kind, id=entry_id, position=raw.get("position")))
    return entries


def fetch_product_detail(product_id: str, timeout: float = DEFAULT_TIMEOUT) -> ProductInfo:
    """A catalog product's own name. Never used as offer/seller evidence."""
    body = _get(f"{BASE_URL}/products/{product_id}", timeout=timeout, context="product detail")
    if not isinstance(body, dict):
        raise MercadoLivreDataError("product detail response was not an object")
    return ProductInfo(product_id=product_id, name=body.get("name"))


def _map_catalog_offer(raw: dict, title: str | None) -> MercadoLivreItem:
    """Map one `/products/{id}/items` offer.

    Different shape from `/sites/MLB/search`: `seller_id` is a flat
    field here, not nested under `seller.id` (confirmed live,
    2026-11-17 -- see tests/fixtures/mercadolivre_catalog/). `title` is
    not present per-offer (all offers under one product share the
    catalog name) so it is supplied by the caller from
    `fetch_product_detail()`, not read from `raw`. `permalink` and
    `available_quantity` are not present in this response shape and
    stay None -- never guessed. `official_store_id` IS present
    (confirmed live the same day): an integer, or `null` meaning
    "confirmed not an official store" -- the key itself is always
    there, so `None` here is a real, verified "no", not a missing-field
    artifact (see competition_models.ProductObservation's docstring).
    """
    shipping = raw.get("shipping") or {}
    return MercadoLivreItem(
        item_id=raw.get("item_id"),
        title=title,
        price=raw.get("price"),
        currency_id=raw.get("currency_id"),
        seller_id=raw.get("seller_id"),
        official_store_id=raw.get("official_store_id"),
        category_id=raw.get("category_id"),
        condition=raw.get("condition"),
        permalink=None,
        free_shipping=shipping.get("free_shipping"),
        available_quantity=None,
    )


def fetch_product_offers(product_id: str, title: str | None, timeout: float = DEFAULT_TIMEOUT) -> list[MercadoLivreItem]:
    """Real seller offers competing on one catalog product."""
    body = _get(
        f"{BASE_URL}/products/{product_id}/items",
        timeout=timeout,
        context="product offers",
    )
    if not isinstance(body, dict) or "results" not in body:
        raise MercadoLivreDataError("product offers response did not contain 'results'")
    return [_map_catalog_offer(raw, title) for raw in body["results"]]


def fetch_item_detail(item_id: str, timeout: float = DEFAULT_TIMEOUT) -> MercadoLivreItem:
    """A standalone listing (a highlight of kind 'ITEM').

    Reuses `mercadolivre._map_item`'s exact field mapping -- see module
    docstring for why this shape is assumed, not re-verified live.
    """
    body = _get(f"{BASE_URL}/items/{item_id}", timeout=timeout, context="item detail")
    if not isinstance(body, dict):
        raise MercadoLivreDataError("item detail response was not an object")
    return _map_item(body)


def sample_category_competition(
    query: str, top_n: int = DEFAULT_TOP_N, timeout: float = DEFAULT_TIMEOUT
) -> CategoryCompetitionSample | None:
    """The full category-catalog chain for one query, bounded and sequential.

    Returns None when no category could be matched at all -- honest
    "nothing to sample", not a failure. Returns a sample with empty
    `groups` (and a `skipped` reason) when a category was found but
    every highlighted entry failed or was unsupported; callers treat
    that the same as "no evidence" without it being an exception.

    Raises a MercadoLivreError subclass only for the two calls that
    gate the whole chain (domain_discovery, highlights) -- a failure
    there means there is nothing to sample at all. Failures fetching an
    individual highlighted product/item are caught per-entry (see
    module docstring) and never propagate.
    """
    if top_n < 1 or top_n > MAX_TOP_N:
        raise ValueError(f"top_n must be between 1 and {MAX_TOP_N}, got {top_n}")

    match = discover_category(query, timeout=timeout)
    if match is None:
        return None

    highlights = fetch_category_highlights(match.category_id, timeout=timeout)
    if not highlights:
        return CategoryCompetitionSample(
            query=query,
            category_id=match.category_id,
            category_name=match.category_name,
            requested_top_n=top_n,
            groups=[],
            skipped=["category has no best-seller highlights"],
        )

    groups: list[ProductOfferGroup] = []
    skipped: list[str] = []

    for entry in highlights[:top_n]:
        if entry.kind == "PRODUCT":
            try:
                info = fetch_product_detail(entry.id, timeout=timeout)
                offers = fetch_product_offers(entry.id, info.name, timeout=timeout)
            except MercadoLivreError as exc:
                skipped.append(f"product {entry.id}: {exc}")
                continue
            groups.append(
                ProductOfferGroup(
                    product_id=entry.id,
                    product_name=info.name,
                    is_standalone_item=False,
                    offers=offers,
                )
            )
        elif entry.kind == "ITEM":
            try:
                item = fetch_item_detail(entry.id, timeout=timeout)
            except MercadoLivreError as exc:
                skipped.append(f"item {entry.id}: {exc}")
                continue
            groups.append(
                ProductOfferGroup(
                    product_id=None,
                    product_name=item.title,
                    is_standalone_item=True,
                    offers=[item],
                )
            )
        else:
            skipped.append(f"unsupported highlight type: {entry.kind} ({entry.id})")

    return CategoryCompetitionSample(
        query=query,
        category_id=match.category_id,
        category_name=match.category_name,
        requested_top_n=top_n,
        groups=groups,
        skipped=skipped,
    )
