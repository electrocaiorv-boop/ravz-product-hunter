from types import SimpleNamespace

import pytest

from src.competition_models import (
    CompetitionSignals,
    build_competition_signals,
    build_competition_signals_from_category_sample,
)
from src.integrations.mercadolivre import MercadoLivreItem


def make_item(price=None, seller_id=None, free_shipping=None, condition=None, title="Item",
             official_store_id=None):
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
        official_store_id=official_store_id,
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


def make_group(product_id, product_name, offers, is_standalone_item=False):
    return SimpleNamespace(
        product_id=product_id,
        product_name=product_name,
        is_standalone_item=is_standalone_item,
        offers=offers,
    )


def make_sample(query="fone bluetooth", category_id="MLB196208", category_name="Fones de Ouvido", groups=None):
    return SimpleNamespace(
        query=query,
        category_id=category_id,
        category_name=category_name,
        requested_top_n=5,
        groups=groups or [],
        skipped=[],
    )


# --- build_competition_signals_from_category_sample ------------------------


def test_category_sample_none_is_fully_unavailable():
    signals = build_competition_signals_from_category_sample(None)
    assert signals.source_coverage == 0.0
    assert signals.marketplace_sample_size is None
    assert signals.unique_seller_ratio is None
    assert signals.price_dispersion is None
    assert signals.category_id is None
    assert signals.products_sampled is None


def test_category_sample_with_no_groups_is_unavailable():
    signals = build_competition_signals_from_category_sample(make_sample(groups=[]))
    assert signals.source_coverage == 0.0
    assert signals.category_id == "MLB196208"
    assert signals.category_name == "Fones de Ouvido"


def test_category_sample_drops_unnamed_products_entirely():
    group = make_group("MLB1", None, [make_item(price=10.0, seller_id=1)])
    signals = build_competition_signals_from_category_sample(make_sample(groups=[group]))
    assert signals.source_coverage == 0.0
    assert any("no catalog name" in note for note in signals.notes)


def test_category_sample_per_product_averages_not_flattened():
    """seller_concentration_index and price_crowding are per-product averages.

    Product A: 3 offers, 2 distinct sellers -> concentration 1/2 = 0.5;
    prices 100/110/120 -> dispersion = pstdev/mean.
    Product B: 2 offers, 1 seller (same seller twice) -> concentration
    1/1 = 1.0; identical prices -> dispersion 0.
    """
    product_a = make_group(
        "MLB_A", "Produto A",
        [
            make_item(price=100.0, seller_id=1),
            make_item(price=110.0, seller_id=2),
            make_item(price=120.0, seller_id=1),
        ],
    )
    product_b = make_group(
        "MLB_B", "Produto B",
        [
            make_item(price=200.0, seller_id=3),
            make_item(price=200.0, seller_id=3),
        ],
    )
    signals = build_competition_signals_from_category_sample(
        make_sample(groups=[product_a, product_b])
    )

    assert signals.marketplace_sample_size == 5
    assert signals.products_sampled == 2
    assert signals.product_names == ["Produto A", "Produto B"]

    # unique_seller_ratio is left unavailable for this source -- see
    # seller_concentration_index below for the real signal.
    assert signals.unique_seller_ratio is None

    expected_concentration = (0.5 + 1.0) / 2  # 1/2 distinct sellers, 1/1
    assert signals.seller_concentration_index == pytest.approx(expected_concentration)

    import statistics
    dispersion_a = statistics.pstdev([100.0, 110.0, 120.0]) / statistics.fmean([100.0, 110.0, 120.0])
    expected_dispersion = (dispersion_a + 0.0) / 2
    assert signals.price_dispersion == pytest.approx(expected_dispersion)
    assert signals.duplicate_title_ratio is None
    assert signals.source_coverage == 1.0


def test_category_sample_single_offer_product_included_in_concentration_not_price_crowding():
    """Approved rule: a 1-offer catalog product enters
    seller_concentration_index normally (1/1 = 1.0 is defined -- and IS
    the maximal, correct concentration reading for a single-seller
    product) but contributes NOTHING to price_crowding (a dispersion
    needs >= 2 points -- never a fabricated 0).
    """
    product_a = make_group(
        "MLB_A", "Produto A",
        [make_item(price=100.0, seller_id=1), make_item(price=120.0, seller_id=2)],
    )
    product_c = make_group("MLB_C", "Produto C", [make_item(price=50.0, seller_id=9)])

    signals = build_competition_signals_from_category_sample(
        make_sample(groups=[product_a, product_c])
    )

    # product_a: 2 distinct sellers -> 1/2 = 0.5. product_c: 1 seller -> 1/1 = 1.0.
    expected_concentration = (0.5 + 1.0) / 2
    assert signals.seller_concentration_index == pytest.approx(expected_concentration)

    import statistics
    dispersion_a = statistics.pstdev([100.0, 120.0]) / statistics.fmean([100.0, 120.0])
    # product_c contributes NOTHING to the average (not a fabricated 0) --
    # the result equals product_a's own dispersion alone.
    assert signals.price_dispersion == pytest.approx(dispersion_a)


def test_category_sample_excludes_standalone_items_from_both_averages():
    product_a = make_group(
        "MLB_A", "Produto A",
        [make_item(price=100.0, seller_id=1), make_item(price=200.0, seller_id=2)],
    )
    standalone = make_group(
        None, "Fone Solo",
        [make_item(price=999.0, seller_id=42, free_shipping=True)],
        is_standalone_item=True,
    )

    signals = build_competition_signals_from_category_sample(
        make_sample(groups=[product_a, standalone])
    )

    # seller_concentration_index / price_dispersion reflect product_a ONLY
    import statistics
    expected_concentration = 1 / 2  # product_a: 2 distinct sellers -> 1/2
    assert signals.seller_concentration_index == pytest.approx(expected_concentration)
    expected_dispersion = statistics.pstdev([100.0, 200.0]) / statistics.fmean([100.0, 200.0])
    assert signals.price_dispersion == pytest.approx(expected_dispersion)
    assert any("standalone listing" in note for note in signals.notes)

    # but the standalone item's offer IS part of the flattened context
    assert signals.marketplace_sample_size == 3
    assert signals.price_max == 999.0
    assert signals.product_names == ["Produto A", "Fone Solo"]


def test_category_sample_single_seller_product_reads_as_maximal_concentration():
    """Regression for the bug found live 2026-11-17: a product with
    exactly one seller must score as MAXIMALLY concentrated (hardest
    case for a newcomer), never as "no concentration"."""
    one_seller_product = make_group(
        "MLB_A", "Produto Exclusivo", [make_item(price=100.0, seller_id=1)]
    )
    signals = build_competition_signals_from_category_sample(
        make_sample(groups=[one_seller_product])
    )
    assert signals.seller_concentration_index == pytest.approx(1.0)


def test_category_sample_ten_sellers_reads_as_low_concentration():
    ten_seller_product = make_group(
        "MLB_A", "Produto Popular",
        [make_item(price=100.0 + i, seller_id=i) for i in range(10)],
    )
    signals = build_competition_signals_from_category_sample(
        make_sample(groups=[ten_seller_product])
    )
    assert signals.seller_concentration_index == pytest.approx(0.1)


def test_category_sample_duplicate_title_ratio_always_none_even_with_identical_titles():
    product_a = make_group(
        "MLB_A", "Produto A",
        [make_item(price=10.0, seller_id=1, title="Produto A"), make_item(price=20.0, seller_id=2, title="Produto A")],
    )
    signals = build_competition_signals_from_category_sample(make_sample(groups=[product_a]))
    assert signals.duplicate_title_ratio is None
    assert any("duplicate_title_ratio permanently unavailable" in note for note in signals.notes)


def test_product_table_has_one_row_per_usable_group_with_the_right_shape():
    product_a = make_group(
        "MLB_A", "Produto A",
        [
            make_item(price=100.0, seller_id=1, free_shipping=True, official_store_id=190206),
            make_item(price=120.0, seller_id=2, free_shipping=False),
        ],
    )
    standalone = make_group(
        None, "Fone Solo",
        [make_item(price=80.0, seller_id=7, free_shipping=True)],
        is_standalone_item=True,
    )
    signals = build_competition_signals_from_category_sample(
        make_sample(groups=[product_a, standalone])
    )

    assert len(signals.product_table) == 2
    row_a, row_solo = signals.product_table

    assert row_a.product_name == "Produto A"
    assert row_a.is_standalone_item is False
    assert row_a.offer_count == 2
    assert row_a.distinct_seller_count == 2
    assert row_a.price_min == 100.0
    assert row_a.price_max == 120.0
    assert row_a.official_store_status == "yes"
    assert row_a.free_shipping_ratio == pytest.approx(0.5)

    assert row_solo.product_name == "Fone Solo"
    assert row_solo.is_standalone_item is True
    assert row_solo.offer_count == 1
    assert row_solo.distinct_seller_count == 1
    # Standalone items (via /items/{id}) have an unverified shape for
    # this field -- "unknown", never a guessed "no".
    assert row_solo.official_store_status == "unknown"


def test_product_table_official_store_no_when_all_offers_confirmed_not_official():
    product_a = make_group(
        "MLB_A", "Produto A",
        [
            make_item(price=10.0, seller_id=1, official_store_id=None),
            make_item(price=20.0, seller_id=2, official_store_id=None),
        ],
    )
    signals = build_competition_signals_from_category_sample(make_sample(groups=[product_a]))
    assert signals.product_table[0].official_store_status == "no"


def test_product_table_official_store_yes_when_any_offer_has_a_store_id():
    product_a = make_group(
        "MLB_A", "Produto A",
        [
            make_item(price=10.0, seller_id=1, official_store_id=None),
            make_item(price=20.0, seller_id=2, official_store_id=555),
        ],
    )
    signals = build_competition_signals_from_category_sample(make_sample(groups=[product_a]))
    assert signals.product_table[0].official_store_status == "yes"


def test_product_table_is_none_when_sample_unavailable():
    assert build_competition_signals_from_category_sample(None).product_table is None


def test_category_sample_free_shipping_and_condition_cover_whole_flattened_sample():
    product_a = make_group(
        "MLB_A", "Produto A",
        [make_item(price=10.0, seller_id=1, free_shipping=True, condition="new")],
    )
    standalone = make_group(
        None, "Fone Solo",
        [make_item(price=20.0, seller_id=2, free_shipping=False, condition="used")],
        is_standalone_item=True,
    )
    signals = build_competition_signals_from_category_sample(
        make_sample(groups=[product_a, standalone])
    )
    assert signals.free_shipping_ratio == pytest.approx(0.5)
    assert signals.condition_distribution == {"new": 1, "used": 1}


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
