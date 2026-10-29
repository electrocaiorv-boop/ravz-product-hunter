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

    notes: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _validate_non_negative("marketplace_sample_size", self.marketplace_sample_size)
        _validate_non_negative("total_result_count", self.total_result_count)
        _validate_non_negative("seller_count", self.seller_count)
        _validate_range("unique_seller_ratio", self.unique_seller_ratio, 0, 1)
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
