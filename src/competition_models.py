"""Provider-neutral internal data model for competition signals.

`CompetitionSignals` holds only derived/observed values -- never raw
provider objects (`MercadoLivreItem`, etc.) -- so that
`src/competition_analysis.py` stays completely decoupled from how any
of these numbers were obtained.

Only ONE source family currently exists for competition in this
project: Mercado Livre marketplace listings. Unlike Phase 5's demand
signals (which had two conceivable source families -- trend and
marketplace), there is no second, independent competition source here.
That matters for confidence (see `src/competition_analysis.py`): the
risk is not "did we only reach 1 of 2 families," it's "are five
features all computed from the SAME ~10-item page being mistaken for
five independent confirmations." They are not -- they are one sample,
examined from five angles.

== marketplace_sample_size != total_result_count ==

`marketplace_sample_size` is `len(items)` from one page-limited API
call (capped at whatever `limit` was requested). It is NEVER the total
number of competing listings.

CORRECTED (hardening review): an earlier version of this module set
`total_result_count = marketplace_sample_size` whenever the sample came
back smaller than the requested limit, reasoning "the API returned
fewer than we asked for, so that must be everything." That inference
was removed -- it does not hold in our current abstraction, for two
independent reasons:

1. `search_products()` returns MAPPED `MercadoLivreItem` objects, not
   the provider's raw result list or its paging metadata. The mapped
   count is not guaranteed to equal the provider's raw result count
   (today's `_map_item()` happens to map 1:1, but nothing enforces
   that -- items could be filtered, skipped on malformed data, or the
   provider's own behavior could change, all invisibly to this layer).
2. Even a raw count smaller than the requested limit does not, by
   itself, prove the search was exhaustive/complete unless the
   provider explicitly says so. A smaller-than-limit page is
   suggestive, not sufficient evidence.

`total_result_count` therefore stays `None` unconditionally until a
genuine provider-supplied total/paging field is extracted and mapped
by `src/integrations/mercadolivre.py` (it currently is not). This is
the field's permanent state for now, the same way Phase 5 permanently
excluded its own page-capped marketplace field from scoring.

Fields are None whenever the underlying signal is genuinely
unavailable -- never fabricated, never defaulted to a plausible-looking
placeholder. True market share, total sales, seller revenue,
advertising spend, conversion rate, and exact ranking difficulty are
never computable from any current source and are not represented here.

== Fase 13: a second builder, a different sample shape ==

`/sites/MLB/search` -- the source `build_competition_signals()` above
was written for -- is blocked by a Mercado Livre policy refusal (see
docs/MERCADO_LIVRE_403.md). It stays in the code, untouched, as a
disabled source. `build_competition_signals_from_category_sample()`
below builds the SAME `CompetitionSignals` contract from a working,
different-shaped sample: top-N best-selling catalog products in a
category, and the real seller offers competing on each one (never
catalog records standing in for offers -- see
`src/integrations/mercadolivre_catalog.py`). Because that sample has
two levels (products, then offers within each product) instead of one
flat list, `unique_seller_ratio` and `price_dispersion` are computed
differently there -- see that function's own docstring for exactly how
and why. Every other field keeps its literal meaning; only the
population it is computed over changed.
"""

import statistics
from collections import Counter
from dataclasses import dataclass, field

TOTAL_SOURCE_FAMILIES = 1


def _validate_range(name: str, value, lo: float, hi: float) -> None:
    if value is not None and not lo <= value <= hi:
        raise ValueError(f"{name} must be between {lo} and {hi}, got {value}")


def _validate_non_negative(name: str, value) -> None:
    if value is not None and value < 0:
        raise ValueError(f"{name} must not be negative, got {value}")


@dataclass
class CompetitionSignals:
    """Competition-relevant signals for one query, from one marketplace sample."""

    query: str

    marketplace_sample_size: int | None
    total_result_count: int | None  # ALWAYS None for now -- see module docstring

    seller_count: int | None
    unique_seller_ratio: float | None

    price_min: float | None
    price_max: float | None
    price_mean: float | None
    price_median: float | None
    price_dispersion: float | None  # coefficient of variation (stdev / mean)

    free_shipping_ratio: float | None
    condition_distribution: dict | None
    duplicate_title_ratio: float | None

    source_coverage: float  # 0.0 or 1.0 -- see TOTAL_SOURCE_FAMILIES above

    # Fase 13 (category-catalog sample) only. None for the flat-sample
    # builder below, which never sets them. See
    # build_competition_signals_from_category_sample() for what they mean.
    category_id: str | None = None
    category_name: str | None = None
    products_sampled: int | None = None
    product_names: list[str] | None = None
    # HIGH = more concentrated/harder (opposite "direction" convention
    # from unique_seller_ratio, which is high = diverse/easier). See
    # build_competition_signals_from_category_sample()'s docstring for
    # why this is a separate field rather than a redefinition of
    # unique_seller_ratio.
    seller_concentration_index: float | None = None
    # Per-product decision-support rows (list[ProductObservation]).
    # Purely descriptive -- never consumed by analyze_competition().
    product_table: list | None = None

    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_non_negative("marketplace_sample_size", self.marketplace_sample_size)
        _validate_non_negative("total_result_count", self.total_result_count)
        _validate_non_negative("seller_count", self.seller_count)
        _validate_non_negative("products_sampled", self.products_sampled)
        _validate_range("unique_seller_ratio", self.unique_seller_ratio, 0, 1)
        _validate_range("seller_concentration_index", self.seller_concentration_index, 0, 1)
        _validate_non_negative("price_min", self.price_min)
        _validate_non_negative("price_max", self.price_max)
        _validate_non_negative("price_mean", self.price_mean)
        _validate_non_negative("price_median", self.price_median)
        _validate_non_negative("price_dispersion", self.price_dispersion)
        _validate_range("free_shipping_ratio", self.free_shipping_ratio, 0, 1)
        _validate_range("duplicate_title_ratio", self.duplicate_title_ratio, 0, 1)
        _validate_range("source_coverage", self.source_coverage, 0, 1)
        if (
            self.total_result_count is not None
            and self.marketplace_sample_size is not None
            and self.total_result_count < self.marketplace_sample_size
        ):
            raise ValueError("total_result_count cannot be smaller than marketplace_sample_size")


def _normalize_title(title: str) -> str:
    return " ".join(title.strip().lower().split())


def build_competition_signals(
    query: str,
    marketplace_items=None,
) -> CompetitionSignals:
    """Assemble CompetitionSignals from an already-fetched marketplace sample.

    Pass `marketplace_items` (a list of MercadoLivreItem, possibly
    empty) when the marketplace fetch succeeded. Pass None if the
    fetch failed or was never attempted -- every field is then
    honestly reported as unavailable, never guessed.

    `requested_limit` is NOT accepted here (removed in the hardening
    review): it was previously used to infer `total_result_count`,
    which this module no longer does -- see module docstring. The
    requested limit is still meaningful for Confidence's sample-size
    adequacy check, but that happens in
    `src/competition_analysis.analyze_competition()`, not here.
    """
    notes: list[str] = []

    if marketplace_items is None:
        notes.append(
            "marketplace signals unavailable (Mercado Livre search is currently "
            "unreliable in this environment -- see docs/MAINTENANCE.md)"
        )
        return CompetitionSignals(
            query=query,
            marketplace_sample_size=None,
            total_result_count=None,
            seller_count=None,
            unique_seller_ratio=None,
            price_min=None,
            price_max=None,
            price_mean=None,
            price_median=None,
            price_dispersion=None,
            free_shipping_ratio=None,
            condition_distribution=None,
            duplicate_title_ratio=None,
            source_coverage=0.0,
            notes=notes,
        )

    sample_size = len(marketplace_items)

    # total_result_count is intentionally always None: see module
    # docstring for why inferring it from sample size vs. requested
    # limit is not valid in this abstraction.
    total_result_count = None
    notes.append(
        "total_result_count unavailable: this integration does not preserve "
        "a provider-supplied total/paging field, and sample size vs. "
        "requested limit is not sufficient evidence of the true total "
        "(mapped item count is not guaranteed to equal the provider's raw "
        "result count, and a short page does not by itself prove the "
        "search was exhaustive)"
    )

    seller_ids = [item.seller_id for item in marketplace_items if item.seller_id is not None]
    seller_count = None
    unique_seller_ratio = None
    if seller_ids:
        seller_count = len(set(seller_ids))
        unique_seller_ratio = seller_count / len(seller_ids)
    else:
        notes.append("seller signals unavailable (no item in the sample had a seller_id)")

    prices = [item.price for item in marketplace_items if item.price is not None]
    price_min = price_max = price_mean = price_median = price_dispersion = None
    if prices:
        price_min = min(prices)
        price_max = max(prices)
        price_mean = statistics.fmean(prices)
        price_median = statistics.median(prices)
        if len(prices) >= 2 and price_mean > 0:
            price_dispersion = statistics.pstdev(prices) / price_mean
    else:
        notes.append("price signals unavailable (no item in the sample had a price)")

    shipping_flags = [item.free_shipping for item in marketplace_items if item.free_shipping is not None]
    free_shipping_ratio = None
    if shipping_flags:
        free_shipping_ratio = sum(1 for f in shipping_flags if f) / len(shipping_flags)
    else:
        notes.append("free-shipping signal unavailable (no item in the sample had this field)")

    conditions = [item.condition for item in marketplace_items if item.condition]
    condition_distribution = None
    if conditions:
        condition_distribution = dict(Counter(conditions))
    else:
        notes.append("condition signal unavailable (no item in the sample had this field)")

    titles = [_normalize_title(item.title) for item in marketplace_items if item.title]
    duplicate_title_ratio = None
    if titles:
        counts = Counter(titles)
        duplicated_items = sum(count for count in counts.values() if count > 1)
        duplicate_title_ratio = duplicated_items / len(titles)
    else:
        notes.append("title signal unavailable (no item in the sample had a title)")

    return CompetitionSignals(
        query=query,
        marketplace_sample_size=sample_size,
        total_result_count=total_result_count,
        seller_count=seller_count,
        unique_seller_ratio=unique_seller_ratio,
        price_min=price_min,
        price_max=price_max,
        price_mean=price_mean,
        price_median=price_median,
        price_dispersion=price_dispersion,
        free_shipping_ratio=free_shipping_ratio,
        condition_distribution=condition_distribution,
        duplicate_title_ratio=duplicate_title_ratio,
        source_coverage=1.0,
        notes=notes,
    )


OFFICIAL_STORE_YES = "yes"
OFFICIAL_STORE_NO = "no"
OFFICIAL_STORE_UNKNOWN = "unknown"


@dataclass
class ProductObservation:
    """One row of the Fase 13 per-product decision-support table.

    Purely descriptive context for a human choosing which sampled
    product to pursue a supplier for -- never an input to
    `analyze_competition()`.

    `official_store_status` is a tri-state, never a boolean: `"yes"`/
    `"no"` only when the source is confirmed to report store
    affiliation (catalog products, via `/products/{id}/items` --
    live-verified 2026-11-17), `"unknown"` when it was never verified
    for this source (standalone ITEM listings, via `/items/{id}`,
    whose shape this project has not empirically captured). Collapsing
    "confirmed not an official store" and "we never checked" into one
    `False` would fabricate certainty that was never observed.
    """

    product_name: str
    is_standalone_item: bool
    offer_count: int
    distinct_seller_count: int | None
    price_min: float | None
    price_max: float | None
    official_store_status: str  # OFFICIAL_STORE_YES/NO/UNKNOWN
    free_shipping_ratio: float | None


def _official_store_status(group) -> str:
    """Tri-state official-store read for one product/item group.

    Catalog PRODUCT groups come from `/products/{id}/items`, confirmed
    live (2026-11-17, see tests/fixtures/mercadolivre_catalog/) to
    always report `official_store_id` (an integer, or `null` meaning
    "not an official store" -- never an absent key). Standalone ITEM
    groups come from `/items/{id}`, whose shape is NOT empirically
    verified for this field (see mercadolivre_catalog.fetch_item_detail's
    docstring) -- reporting "no" there would claim a verification that
    never happened.
    """
    if group.is_standalone_item:
        return OFFICIAL_STORE_UNKNOWN
    has_store = any(
        getattr(offer, "official_store_id", None) is not None
        for offer in group.offers
    )
    return OFFICIAL_STORE_YES if has_store else OFFICIAL_STORE_NO


def _build_product_table(groups) -> list[ProductObservation]:
    rows = []
    for group in groups:
        offers = group.offers
        seller_ids = [o.seller_id for o in offers if o.seller_id is not None]
        prices = [o.price for o in offers if o.price is not None]
        shipping_flags = [o.free_shipping for o in offers if o.free_shipping is not None]
        rows.append(
            ProductObservation(
                product_name=group.product_name,
                is_standalone_item=group.is_standalone_item,
                offer_count=len(offers),
                distinct_seller_count=len(set(seller_ids)) if seller_ids else None,
                price_min=min(prices) if prices else None,
                price_max=max(prices) if prices else None,
                official_store_status=_official_store_status(group),
                free_shipping_ratio=(
                    sum(1 for f in shipping_flags if f) / len(shipping_flags)
                    if shipping_flags else None
                ),
            )
        )
    return rows


def build_competition_signals_from_category_sample(sample) -> CompetitionSignals:
    """Build CompetitionSignals from a Fase 13 category-catalog sample.

    `sample` is duck-typed like
    `src.integrations.mercadolivre_catalog.CategoryCompetitionSample` --
    this module still imports nothing from `src.integrations`; any
    object exposing `query`, `category_id`, `category_name` and
    `groups` (each a duck-typed `ProductOfferGroup`: `product_id`,
    `product_name`, `is_standalone_item`, `offers`) works. Pass `None`
    when the whole chain found nothing or failed outright (no category
    matched, or every sampled entry failed) -- every field is then
    honestly unavailable, the same contract as `build_competition_signals(None)`.

    == The sample has two levels; this changes HOW two signals are computed ==

    Top-N best-selling catalog PRODUCTS (or standalone ITEM listings) in
    one category, and within each catalog product, the real seller
    OFFERS competing on it. Offers from DIFFERENT products are not
    directly comparable -- different items, often different price
    tiers, disjoint seller pools. Averaging them together would answer
    "how varied is this category's product mix", not "how hard is it to
    compete here". So `seller_concentration_index` and `price_dispersion`
    are each the MEAN of a PER-PRODUCT value, not a value computed over
    the whole flattened sample:

    - `seller_concentration_index` (NOT `unique_seller_ratio` -- see
      below): for each catalog-product group, `1 / distinct_seller_count`,
      then averaged across groups. This is the Herfindahl-Hirschman
      Index of a product with N EQUALLY-weighted sellers (HHI = sum of
      squared market shares; N equal shares of 1/N each gives
      sum((1/N)^2 * N) = 1/N) -- the standard textbook concentration
      index under the best assumption this data supports (we have
      seller PRESENCE, never sales volume or share, so equal weighting
      is the documented approximation, not a precise market share).
      HIGH = few sellers = concentrated = harder for a newcomer. 1
      seller -> 1.0 (maximal concentration). 2 -> 0.5. 10 -> 0.1.
      Standalone ITEM listings are excluded -- a lone listing's
      distinct-seller count is trivially 1, which is the CORRECT
      concentration reading (1.0) for a product-level group, but a
      standalone listing isn't "a product with one seller": it is one
      listing with no catalog competition data at all, a different
      kind of absence. Mixing the two would conflate them.

      CORRECTED (found during review): the first version of this
      function reused `unique_seller_count / offer_count` per product
      -- the flat-sample builder's own concentration proxy, repurposed
      without re-deriving it for the new shape. That ratio is ALWAYS
      ~1.0 here, for any number of sellers: Mercado Livre does not
      return two offers from the same seller for one catalog product,
      so "distinct sellers" and "total offers" are nearly always equal
      BY CONSTRUCTION, regardless of whether there are 1 or 10 sellers.
      Scored through the existing `100 * (1 - ratio)` formula, a
      single-seller product (the single hardest case: no one else even
      lists it) read as "0 -- not concentrated at all", the opposite of
      what it means. The live run that first exposed this
      (`competition_score=14.47`, "easy") contradicted this project's
      own observation, written down the same day, that the top sellers
      sampled were mostly official brand stores with 1-2 offers each --
      a textbook case of taking a wrong number at face value instead of
      checking it against what was already known. `unique_seller_ratio`
      is therefore left `None` for this builder (not repurposed, not
      silently redefined -- a new, separately-named field exists
      precisely so the old one is never asked to mean something else).
    - `price_dispersion`: averaged over catalog-product groups with AT
      LEAST TWO priced offers. Standalone items are excluded for the
      same reason as above. A catalog product with exactly one priced
      offer contributes NOTHING to this average -- not a fabricated
      zero -- because a dispersion needs at least two points to be
      defined (the flat-sample builder above already required this;
      this just applies the same guard per product instead of globally).
      Unlike the concentration index, a product with exactly one offer
      is excluded here, not included at a trivial value: a dispersion
      genuinely has no value at n=1, where a seller-count ratio of 1/1
      does.

    `duplicate_title_ratio` is PERMANENTLY `None` here (unlike the flat
    builder): every offer under one catalog product shares that
    product's own name by construction, so any duplication measured
    across the sample would reflect our own grouping, not templated or
    spam listings. Scoring it would be the same class of error
    `listing_saturation` was permanently disabled for.

    `free_shipping_ratio`, `condition_distribution` and the price
    min/max/mean/median context figures stay computed over the whole
    FLATTENED sample (every offer, from every group, standalone items
    included) -- these are per-offer facts with no product-grouping
    ambiguity.

    A catalog product or standalone item whose name could not be
    resolved is dropped entirely, not just hidden from the report: this
    project's purpose for Competition evidence is finding a supplier,
    and an unnamed catalog entry cannot be matched to one. The drop is
    recorded as a note, never silent.
    """
    empty_kwargs = dict(
        marketplace_sample_size=None,
        total_result_count=None,
        seller_count=None,
        unique_seller_ratio=None,
        price_min=None,
        price_max=None,
        price_mean=None,
        price_median=None,
        price_dispersion=None,
        free_shipping_ratio=None,
        condition_distribution=None,
        duplicate_title_ratio=None,
        source_coverage=0.0,
        products_sampled=None,
        product_names=None,
        seller_concentration_index=None,
        product_table=None,
    )

    if sample is None or not getattr(sample, "groups", None):
        return CompetitionSignals(
            query=sample.query if sample is not None else "",
            category_id=getattr(sample, "category_id", None) if sample is not None else None,
            category_name=getattr(sample, "category_name", None) if sample is not None else None,
            notes=[
                "category-catalog sample unavailable (no category matched, or "
                "no highlighted product/item could be resolved -- see "
                "docs/MERCADO_LIVRE_403.md)"
            ],
            **empty_kwargs,
        )

    notes: list[str] = []
    usable_groups = []
    dropped_unnamed = 0
    for group in sample.groups:
        if not group.product_name:
            dropped_unnamed += 1
            continue
        usable_groups.append(group)

    if dropped_unnamed:
        notes.append(
            f"{dropped_unnamed} sampled product(s)/item(s) dropped: no catalog "
            "name could be resolved, and a nameless entry cannot be matched to "
            "a supplier"
        )

    if not usable_groups:
        notes.append(
            "no sampled product/item had a resolvable name; sample has no "
            "usable evidence"
        )
        return CompetitionSignals(
            query=sample.query,
            category_id=sample.category_id,
            category_name=sample.category_name,
            notes=notes,
            **empty_kwargs,
        )

    flattened = [item for group in usable_groups for item in group.offers]
    sample_size = len(flattened)

    notes.append(
        "total_result_count unavailable: paging returned by the provider is "
        "per catalog product, not a category- or query-wide total"
    )

    seller_ids = [item.seller_id for item in flattened if item.seller_id is not None]
    seller_count = len(set(seller_ids)) if seller_ids else None
    if not seller_ids:
        notes.append("seller signals unavailable (no sampled offer had a seller_id)")

    prices = [item.price for item in flattened if item.price is not None]
    price_min = price_max = price_mean = price_median = None
    if prices:
        price_min = min(prices)
        price_max = max(prices)
        price_mean = statistics.fmean(prices)
        price_median = statistics.median(prices)
    else:
        notes.append("price signals unavailable (no sampled offer had a price)")

    shipping_flags = [item.free_shipping for item in flattened if item.free_shipping is not None]
    free_shipping_ratio = None
    if shipping_flags:
        free_shipping_ratio = sum(1 for f in shipping_flags if f) / len(shipping_flags)
    else:
        notes.append("free-shipping signal unavailable (no sampled offer had this field)")

    conditions = [item.condition for item in flattened if item.condition]
    condition_distribution = dict(Counter(conditions)) if conditions else None
    if not conditions:
        notes.append("condition signal unavailable (no sampled offer had this field)")

    product_groups = [g for g in usable_groups if not g.is_standalone_item]
    excluded_standalone = len(usable_groups) - len(product_groups)
    if excluded_standalone:
        notes.append(
            f"{excluded_standalone} standalone listing(s) excluded from "
            "seller_concentration/price_crowding -- a lone listing's ratio "
            "would read as zero concentration, which is not what a "
            "single-seller listing means"
        )

    per_product_concentration = []
    per_product_dispersions = []
    for group in product_groups:
        group_seller_ids = [o.seller_id for o in group.offers if o.seller_id is not None]
        if group_seller_ids:
            distinct = len(set(group_seller_ids))
            if distinct > 0:
                per_product_concentration.append(1 / distinct)

        group_prices = [o.price for o in group.offers if o.price is not None]
        if len(group_prices) >= 2:
            group_mean = statistics.fmean(group_prices)
            if group_mean > 0:
                per_product_dispersions.append(statistics.pstdev(group_prices) / group_mean)

    seller_concentration_index = (
        statistics.fmean(per_product_concentration) if per_product_concentration else None
    )
    if seller_concentration_index is None:
        notes.append(
            "seller concentration unavailable (no catalog product had an "
            "offer with a seller_id)"
        )
    notes.append(
        "unique_seller_ratio left unavailable for this source (not "
        "repurposed): it is always close to 1.0 here regardless of how "
        "many sellers a product has (Mercado Livre does not return two "
        "offers from the same seller for one catalog product), so it "
        "carries no concentration signal in this sample shape -- use "
        "seller_concentration_index instead"
    )

    price_dispersion = (
        statistics.fmean(per_product_dispersions) if per_product_dispersions else None
    )
    if price_dispersion is None:
        notes.append(
            "price crowding unavailable (no catalog product had at least two "
            "priced offers)"
        )

    notes.append(
        "duplicate_title_ratio permanently unavailable for this source: "
        "offers under one catalog product share its name by construction, "
        "so duplication would measure our own grouping, not templated "
        "listings"
    )

    return CompetitionSignals(
        query=sample.query,
        marketplace_sample_size=sample_size,
        total_result_count=None,
        seller_count=seller_count,
        unique_seller_ratio=None,
        price_min=price_min,
        price_max=price_max,
        price_mean=price_mean,
        price_median=price_median,
        price_dispersion=price_dispersion,
        free_shipping_ratio=free_shipping_ratio,
        condition_distribution=condition_distribution,
        duplicate_title_ratio=None,
        source_coverage=1.0,
        category_id=sample.category_id,
        category_name=sample.category_name,
        products_sampled=len(usable_groups),
        product_names=[g.product_name for g in usable_groups],
        seller_concentration_index=seller_concentration_index,
        product_table=_build_product_table(usable_groups),
        notes=notes,
    )
