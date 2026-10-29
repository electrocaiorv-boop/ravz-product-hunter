import pytest

from src.competition_models import CompetitionSignals, build_competition_signals
from src.integrations.mercadolivre import MercadoLivreItem


def make_item(price=None, seller_id=None, free_shipping=None, condition=None, title="Item"):
    return MercadoLivreItem(
        item_id="MLB1",
        title=title,
        price=price,
        currency_id="BRL",
        seller_id=seller_id,
        category_id="MLB1",
        condition=condition,
        permalink=None,
        free_shipping=free_shipping,
        available_quantity=None,
    )


def test_build_with_full_sample_computes_all_fields():
    items = [
        make_item(price=10.0, seller_id=1, free_shipping=True, condition="new", title="Bebedouro A"),
        make_item(price=20.0, seller_id=2, free_shipping=False, condition="new", title="bebedouro a"),
        make_item(price=30.0, seller_id=1, free_shipping=True, condition="used", title="Bebedouro C"),
    ]
    signals = build_competition_signals("bebedouro", marketplace_items=items)

    assert signals.marketplace_sample_size == 3
    assert signals.seller_count == 2
    assert signals.unique_seller_ratio == pytest.approx(2 / 3)
    assert signals.price_min == 10.0
    assert signals.price_max == 30.0
    assert signals.price_mean == pytest.approx(20.0)
    assert signals.price_median == pytest.approx(20.0)
    assert signals.price_dispersion is not None
    assert signals.free_shipping_ratio == pytest.approx(2 / 3)
    assert signals.condition_distribution == {"new": 2, "used": 1}
    # "Bebedouro A" and "bebedouro a" normalize to the same title
    assert signals.duplicate_title_ratio == pytest.approx(2 / 3)
    assert signals.source_coverage == pytest.approx(1.0)


# --- total_result_count: never inferred from sample size ------------------


def test_total_result_count_is_none_regardless_of_sample_size_vs_any_limit():
    """Regression: sample < limit must NOT create a total_result_count.

    This was the Phase 6 hardening bug: an earlier version set
    total_result_count = len(items) whenever the sample came back
    smaller than the caller's requested limit. That inference assumed
    search_products() preserves an exhaustive-search guarantee it does
    not actually make (mapped item count != provider's raw/paging
    total, and a short page does not by itself prove completeness).
    """
    small_sample = build_competition_signals("x", marketplace_items=[make_item(price=10.0) for _ in range(3)])
    full_page = build_competition_signals("x", marketplace_items=[make_item(price=10.0) for _ in range(10)])

    assert small_sample.total_result_count is None
    assert full_page.total_result_count is None
    assert any("total_result_count unavailable" in note for note in small_sample.notes)


def test_build_competition_signals_does_not_accept_requested_limit():
    """requested_limit was removed from this function -- it never
    legitimately belonged here once the total_result_count inference
    was removed (confidence's sample-adequacy check uses it, but that
    lives in src/competition_analysis.py, not here)."""
    with pytest.raises(TypeError):
        build_competition_signals("x", marketplace_items=[], requested_limit=10)


def test_seller_signals_unavailable_without_seller_id():
    items = [make_item(price=10.0, seller_id=None) for _ in range(3)]
    signals = build_competition_signals("x", marketplace_items=items)

    assert signals.seller_count is None
    assert signals.unique_seller_ratio is None
    assert any("seller signals unavailable" in note for note in signals.notes)


def test_price_signals_unavailable_without_price():
    items = [make_item(price=None, seller_id=1) for _ in range(3)]
    signals = build_competition_signals("x", marketplace_items=items)

    assert signals.price_min is None
    assert signals.price_dispersion is None
    assert any("price signals unavailable" in note for note in signals.notes)


def test_shipping_signals_unavailable_without_field():
    items = [make_item(price=10.0, free_shipping=None) for _ in range(3)]
    signals = build_competition_signals("x", marketplace_items=items)

    assert signals.free_shipping_ratio is None
    assert any("free-shipping signal unavailable" in note for note in signals.notes)


def test_shipping_ratio_genuine_zero_is_preserved():
    """All items explicitly have free_shipping=False -- a real 0, not unavailable."""
    items = [make_item(price=10.0, free_shipping=False) for _ in range(3)]
    signals = build_competition_signals("x", marketplace_items=items)

    assert signals.free_shipping_ratio == 0.0
    assert not any("free-shipping signal unavailable" in note for note in signals.notes)


def test_marketplace_unavailable_when_no_items_provided():
    signals = build_competition_signals("x", marketplace_items=None)

    assert signals.marketplace_sample_size is None
    assert signals.seller_count is None
    assert signals.price_min is None
    assert signals.total_result_count is None
    assert signals.source_coverage == pytest.approx(0.0)
    assert any("marketplace signals unavailable" in note for note in signals.notes)


def test_empty_sample_is_source_success_with_zero_items():
    """Source succeeded but found literally nothing -- distinct from unavailable."""
    signals = build_competition_signals("x", marketplace_items=[])

    assert signals.marketplace_sample_size == 0
    assert signals.total_result_count is None  # never inferred, even at 0
    assert signals.source_coverage == pytest.approx(1.0)
    assert signals.seller_count is None  # no items to derive sellers from


@pytest.mark.parametrize(
    "overrides",
    [
        {"unique_seller_ratio": 1.5},
        {"free_shipping_ratio": -0.1},
        {"duplicate_title_ratio": 2.0},
        {"source_coverage": 1.5},
        {"marketplace_sample_size": -1},
        {"price_min": -1},
    ],
)
def test_competition_signals_rejects_invalid_values(overrides):
    base = dict(
        query="x",
        marketplace_sample_size=5,
        total_result_count=5,
        seller_count=3,
        unique_seller_ratio=0.6,
        price_min=10.0,
        price_max=20.0,
        price_mean=15.0,
        price_median=15.0,
        price_dispersion=0.2,
        free_shipping_ratio=0.5,
        condition_distribution={"new": 5},
        duplicate_title_ratio=0.1,
        source_coverage=1.0,
    )
    base.update(overrides)
    with pytest.raises(ValueError):
        CompetitionSignals(**base)


def test_total_result_count_cannot_be_smaller_than_sample_size():
    """Still a valid defensive check for the day a real provider total is mapped."""
    with pytest.raises(ValueError):
        CompetitionSignals(
            query="x",
            marketplace_sample_size=10,
            total_result_count=3,
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
            source_coverage=1.0,
        )
