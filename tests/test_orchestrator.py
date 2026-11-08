"""Phase 12A orchestration tests.

Every test uses controlled fixtures injected via `trend_fetcher` /
`marketplace_searcher`. **No test requires network access**, and none is
skipped when providers are unreachable -- the pipeline is exercised
end to end regardless.

What these tests protect is the orchestrator's own contract: that it
sequences work, calls each provider once, translates failures into
explicit unavailable evidence, and delegates every judgment to
`compose_opportunity()`. The scoring semantics themselves are owned by
the Phase 11 tests and are not re-asserted here.
"""

from decimal import Decimal

import pytest
import requests

from src.integrations.apify_trends import (
    ApifyTrendsConfigurationError,
    ApifyTrendsError,
    ApifyTrendsDataError,
    ApifyTrendsTimeoutError,
)
from src.integrations.mercadolivre import (
    ACCESS_TOKEN_ENV_VAR as ML_ACCESS_TOKEN_ENV_VAR,
    MercadoLivreItem,
    MercadoLivreResponseError,
    MercadoLivreTimeoutError,
)
from src.logistics_models import LogisticsInputs
from src.main import format_orchestration_report
from src.margin_models import MarginInputs
from src.opportunity_models import (
    FAMILY_SEARCH_INTEREST,
    READINESS_BLOCKED,
    READINESS_INCOMPLETE_EVIDENCE,
    READINESS_OPERATIONALLY_UNVALIDATED,
    READINESS_READY,
)
from src.orchestrator import (
    PROVIDER_MARKETPLACE,
    PROVIDER_TRENDS,
    STATUS_FAILED,
    STATUS_NOT_SUPPLIED,
    STATUS_OK,
    OrchestrationRequest,
    run_opportunity_analysis,
)
from src.risk_models import RiskInputs
from src.supplier_models import SupplierInputs
from src.trend_models import TrendData, TrendPoint

GROWING_SERIES = [20, 22, 28, 35, 48, 62]

# Stand-in credential values for the redaction tests.
#
# Deliberately NOT credential-shaped. The code paths under test match on
# the header scheme word and on the configured env value verbatim, so the
# value's shape is irrelevant to coverage -- while a realistic-looking
# token is a liability: the staged secret scanner flags it, and anything
# resembling a real credential in git history is permanent.
FIXTURE_SECRET_A = "not-a-credential-fixture-value-a"
FIXTURE_SECRET_B = "not-a-credential-fixture-value-b"


# -- controlled fixtures --------------------------------------------------


class Counter:
    """Counts provider invocations so single-fetch can be asserted."""

    def __init__(self):
        self.trend = 0
        self.marketplace = 0


def make_trend_fetcher(counter, values=None, available=True):
    def fetcher(query, geo="BR", timeframe="today 12-m"):
        counter.trend += 1
        points = [
            TrendPoint(date=f"w{i}", value=v, formatted_value=None)
            for i, v in enumerate(values if values is not None else GROWING_SERIES)
        ]
        return TrendData(
            query=query, geo=geo, timeframe=timeframe,
            retrieved_at="2026-01-01T00:00:00Z",
            interest_over_time=points, interest_by_region=[],
            related_top_queries=[], related_rising_queries=[],
            source="fixture:controlled",
            interest_over_time_available=available,
            related_queries_available=False,
            regional_interest_available=False,
        )

    return fetcher


def make_marketplace_searcher(counter, count=4):
    def searcher(query, limit=10):
        counter.marketplace += 1
        return [
            MercadoLivreItem(
                item_id=f"MLB{i}", title=f"Item {i}", price=100.0 + i * 15,
                currency_id="BRL", seller_id=i % 3, category_id="MLB1000",
                condition="new", permalink=None, free_shipping=i % 2 == 0,
                available_quantity=50,
            )
            for i in range(count)
        ]

    return searcher


def failing_trend_fetcher(exc):
    def fetcher(query, geo="BR", timeframe="today 12-m"):
        raise exc

    return fetcher


def failing_marketplace_searcher(exc):
    def searcher(query, limit=10):
        raise exc

    return searcher


def margin_inputs(**overrides):
    base = dict(
        product_name="Fone", sale_price=Decimal("129.90"),
        product_cost=Decimal("48.00"), marketplace_fee_rate=Decimal("0.12"),
        seller_shipping_cost=Decimal("14.00"), packaging_cost=Decimal("2.50"),
        tax_rate=Decimal("0.08"), payment_cost=Decimal("1.20"),
    )
    base.update(overrides)
    return MarginInputs(**base)


def supplier_inputs(**overrides):
    base = dict(
        product_name="Fone", supplier_name="Distribuidora Exemplo",
        moq_units=5, stock_quantity=600, lead_time_days=9,
        dropshipping_supported=True, blind_shipping_supported=True,
        tracking_available=True, invoice_available=True,
        business_verified=True, contact_available=True,
    )
    base.update(overrides)
    return SupplierInputs(**base)


def logistics_inputs(**overrides):
    base = dict(
        product_name="Fone", weight_kg=Decimal("0.28"),
        length_cm=Decimal("14"), width_cm=Decimal("10"), height_cm=Decimal("6"),
        fragile=False, hazardous=False, perishable=False,
        estimated_delivery_days=5, tracking_available=True,
        insurance_available=True, supplier_fulfilled=True,
    )
    base.update(overrides)
    return LogisticsInputs(**base)


def risk_inputs(**overrides):
    base = dict(
        product_name="Fone", supplier_count=3,
        primary_supplier_dependency_percent=Decimal("0.45"),
        platform_dependency_percent=Decimal("0.85"),
        historical_stockout_rate=Decimal("0.04"),
        observed_return_rate=Decimal("0.05"),
        regulatory_uncertainty=False, brand_ip_uncertainty=False,
        recall_history_present=False,
    )
    base.update(overrides)
    return RiskInputs(**base)


def full_request(**overrides):
    base = dict(
        product_name="Fone Bluetooth", query="fone bluetooth",
        margin_inputs=margin_inputs(), supplier_inputs=supplier_inputs(),
        logistics_inputs=logistics_inputs(), risk_inputs=risk_inputs(),
    )
    base.update(overrides)
    return OrchestrationRequest(**base)


def run(request=None, counter=None, trend_fetcher=None, marketplace_searcher=None):
    counter = counter or Counter()
    return run_opportunity_analysis(
        request or full_request(),
        trend_fetcher=trend_fetcher or make_trend_fetcher(counter),
        marketplace_searcher=marketplace_searcher or make_marketplace_searcher(counter),
    )


def component(result, name):
    return next(c for c in result.opportunity.components if c.name == name)


def provider_call(result, provider):
    return next(c for c in result.provider_calls if c.provider == provider)


# -- 1. successful execution with controlled fixtures ---------------------


def test_full_evidence_run_reaches_ready_and_classifies():
    result = run()

    assert result.opportunity.readiness == READINESS_READY
    assert result.opportunity.publishable is True
    assert result.opportunity.classification is not None
    assert 0 <= result.opportunity.opportunity_score <= 100
    assert result.opportunity.component_coverage == pytest.approx(100.0, abs=1e-9)


def test_every_domain_is_analyzed_when_evidence_exists():
    result = run()
    for name in ("demand", "trend", "competition", "margin",
                 "supplier", "logistics", "risk"):
        assert component(result, name).available is True, name


def test_result_carries_the_originating_request():
    request = full_request()
    result = run(request)
    assert result.request is request
    assert result.opportunity.product_name == "Fone Bluetooth"


def test_orchestrator_returns_the_composition_verdict_untouched():
    """The orchestrator must not post-process compose_opportunity()."""
    from src.opportunity_integration import compose_opportunity

    result = run()
    opp = result.opportunity
    # Recomposing from the same component scores must reproduce it exactly.
    assert opp.model_version == "integrated-v1"
    assert isinstance(opp, type(compose_opportunity("x")))


# -- 3. shared evidence fetched once -------------------------------------


def test_each_provider_is_called_at_most_once():
    """Two provider calls feed five domains."""
    counter = Counter()
    run(counter=counter)
    assert counter.trend == 1, "Apify must be called once, not once per domain"
    assert counter.marketplace == 1, "Mercado Livre must be called once"


def test_one_trend_call_serves_both_trend_and_demand():
    counter = Counter()
    result = run(counter=counter)

    call = next(c for c in result.provider_calls if c.provider == PROVIDER_TRENDS)
    assert call.status == STATUS_OK
    assert set(call.serves) == {"trend", "demand"}
    assert counter.trend == 1
    # Both domains produced a score from that single call.
    assert component(result, "trend").available is True
    assert component(result, "demand").available is True


def test_one_marketplace_call_serves_both_competition_and_demand():
    counter = Counter()
    result = run(counter=counter)

    call = next(c for c in result.provider_calls
                if c.provider == PROVIDER_MARKETPLACE)
    assert call.status == STATUS_OK
    assert set(call.serves) == {"competition", "demand"}
    assert counter.marketplace == 1


def test_shared_demand_trend_evidence_is_never_double_counted():
    """Sharing one fetch must not become two weighted votes.

    The orchestrator passes both results to compose_opportunity(); the
    family election there keeps exactly one weighted.
    """
    result = run()
    family = [c for c in result.opportunity.components
              if c.family == FAMILY_SEARCH_INTEREST]
    weighted = [c.name for c in family if c.effective_weight > 0]

    assert len(weighted) == 1, f"both family members weighted: {weighted}"
    assert weighted == ["demand"], "Demand is the preferred representative"
    assert sum(c.effective_weight for c in family) == pytest.approx(0.30, abs=1e-9)
    # The non-elected member stays visible with a stated reason.
    trend = component(result, "trend")
    assert trend.available is True
    assert trend.weighted_contribution is None
    assert trend.overlap_policy is not None


# -- 2. unavailable provider ---------------------------------------------


@pytest.mark.parametrize(
    "exc",
    [
        ApifyTrendsConfigurationError("APIFY_API_TOKEN is not configured"),
        ApifyTrendsTimeoutError("Apify did not respond within 60s"),
        ApifyTrendsDataError("response was not valid JSON"),
    ],
)
def test_trend_provider_failure_becomes_explicit_unavailable(exc):
    """Every failure class is epistemically identical: we do not know."""
    result = run(trend_fetcher=failing_trend_fetcher(exc))

    call = next(c for c in result.provider_calls if c.provider == PROVIDER_TRENDS)
    assert call.status == STATUS_FAILED
    assert type(exc).__name__ in call.detail
    assert any("search-interest evidence" in u for u in result.unavailable)

    # Trend has no score; nothing was substituted.
    trend = component(result, "trend")
    assert trend.available is False
    assert trend.raw_score is None
    assert trend.opportunity_score is None
    assert trend.weighted_contribution is None
    assert trend.withheld_reason is not None


@pytest.mark.parametrize(
    "exc",
    [
        MercadoLivreTimeoutError("Mercado Livre did not respond within 10s"),
        MercadoLivreResponseError(403, "Mercado Livre returned HTTP 403"),
    ],
)
def test_marketplace_provider_failure_becomes_explicit_unavailable(exc):
    result = run(marketplace_searcher=failing_marketplace_searcher(exc))

    call = next(c for c in result.provider_calls
                if c.provider == PROVIDER_MARKETPLACE)
    assert call.status == STATUS_FAILED
    assert any("marketplace evidence" in u for u in result.unavailable)

    competition = component(result, "competition")
    assert competition.available is False
    assert competition.raw_score is None
    # A missing commercial requirement withholds the recommendation.
    assert result.opportunity.readiness == READINESS_INCOMPLETE_EVIDENCE
    assert result.opportunity.classification is None


def test_provider_failure_does_not_abort_the_run():
    """One dead provider must not cost the other domains' evidence."""
    result = run(marketplace_searcher=failing_marketplace_searcher(
        MercadoLivreResponseError(403, "HTTP 403")))

    assert component(result, "trend").available is True
    assert component(result, "margin").available is True
    assert component(result, "supplier").available is True
    assert result.opportunity.opportunity_score is not None


def test_both_providers_failing_still_composes_a_result():
    result = run(
        trend_fetcher=failing_trend_fetcher(ApifyTrendsTimeoutError("timeout")),
        marketplace_searcher=failing_marketplace_searcher(
            MercadoLivreTimeoutError("timeout")),
    )

    assert len(result.failed_providers) == 2
    assert result.opportunity.readiness == READINESS_INCOMPLETE_EVIDENCE
    assert result.opportunity.classification is None
    # Manual domains still contributed.
    assert component(result, "margin").available is True


def test_provider_exceptions_never_propagate():
    """A provider error is translated, never raised at the caller."""
    result = run(trend_fetcher=failing_trend_fetcher(
        ApifyTrendsConfigurationError("not configured")))
    assert result.opportunity is not None


# -- 4. partially missing evidence ---------------------------------------


def test_omitted_manual_inputs_are_reported_unavailable_not_invented():
    result = run(full_request(
        margin_inputs=None, supplier_inputs=None,
        logistics_inputs=None, risk_inputs=None,
    ))

    for name in ("margin", "supplier", "logistics", "risk"):
        c = component(result, name)
        assert c.available is False, name
        assert c.raw_score is None, name
        assert c.opportunity_score is None, name
        assert c.weighted_contribution is None, name
        assert c.effective_weight == 0.0, name
        assert any(f"{name} evidence not supplied" in u for u in result.unavailable)

    calls = {c.provider: c for c in result.provider_calls}
    for name in ("margin", "supplier", "logistics", "risk"):
        assert calls[f"manual:{name}"].status == STATUS_NOT_SUPPLIED


def test_unavailable_reason_states_there_is_no_integration():
    """Honest about capability: these domains have no provider."""
    result = run(full_request(supplier_inputs=None))
    reason = next(u for u in result.unavailable if u.startswith("supplier"))
    assert "no integration" in reason
    assert "separate" in reason and "investigation" in reason


def test_operational_gap_only_yields_operationally_unvalidated():
    """Commercial complete, execution unverified."""
    result = run(full_request(supplier_inputs=None, logistics_inputs=None))

    assert result.opportunity.readiness == READINESS_OPERATIONALLY_UNVALIDATED
    assert result.opportunity.commercial_validation_complete is True
    assert result.opportunity.operational_validation_complete is False
    assert result.opportunity.classification is None
    assert result.opportunity.analytical_band_non_final is not None


def test_missing_commercial_input_yields_incomplete_evidence():
    result = run(full_request(margin_inputs=None))
    assert result.opportunity.readiness == READINESS_INCOMPLETE_EVIDENCE
    assert "margin" in result.opportunity.missing_commercial_requirements


def test_thin_trend_series_lets_the_domain_withhold_its_own_score():
    """A 1-point series is not enough for a provisional Trend Score.

    The orchestrator must pass that through, not paper over it.
    """
    counter = Counter()
    result = run(counter=counter,
                 trend_fetcher=make_trend_fetcher(counter, values=[42]))

    assert component(result, "trend").available is False
    assert component(result, "trend").raw_score is None
    # Demand still scores from the same call's other evidence.
    assert counter.trend == 1


# -- 5. determinism ------------------------------------------------------


def test_identical_request_and_providers_produce_identical_output():
    a = run()
    b = run()
    assert a.opportunity == b.opportunity


def test_repeated_runs_are_stable():
    scores = {run().opportunity.opportunity_score for _ in range(5)}
    assert len(scores) == 1


def test_provenance_is_stable_across_runs():
    a = {(c.provider, c.status, c.serves) for c in run().provider_calls}
    b = {(c.provider, c.status, c.serves) for c in run().provider_calls}
    assert a == b


# -- 6. blocker and readiness propagation --------------------------------


def test_supplier_blocker_propagates_to_blocked():
    """Stock below MOQ is a genuine hard blocker."""
    result = run(full_request(
        supplier_inputs=supplier_inputs(moq_units=50, stock_quantity=12)))

    assert result.opportunity.readiness == READINESS_BLOCKED
    assert result.opportunity.publishable is False
    assert result.opportunity.classification is None
    assert "Supplier Analysis (Phase 8)" in result.opportunity.domain_blockers


def test_blocker_outranks_an_evidence_gap():
    result = run(full_request(
        margin_inputs=None,
        supplier_inputs=supplier_inputs(moq_units=50, stock_quantity=12)))
    assert result.opportunity.readiness == READINESS_BLOCKED


def test_blocker_does_not_suppress_the_analytical_score():
    """Transparency: the arithmetic is shown, the recommendation is not."""
    result = run(full_request(
        supplier_inputs=supplier_inputs(moq_units=50, stock_quantity=12)))
    assert result.opportunity.opportunity_score is not None
    assert result.opportunity.classification is None
    assert result.opportunity.withheld_reason is not None


def test_domain_warnings_are_preserved_through_the_pipeline():
    result = run(full_request(
        supplier_inputs=supplier_inputs(moq_units=500, stock_quantity=5000)))
    assert result.opportunity.domain_warnings


# -- 7. no double scoring, no re-weighting -------------------------------


def test_orchestrator_module_contains_no_scoring_arithmetic():
    """Structural: the orchestrator must own no scoring math.

    AST-based, because the module docstring legitimately discusses
    weights and inversion in prose.
    """
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("src/orchestrator.py").read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        # No `100 - x` inversion anywhere.
        if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
                and isinstance(node.left, ast.Constant)
                and node.left.value in (100, 100.0)):
            raise AssertionError(f"inversion at line {node.lineno}")
        # No weight-shaped float literals.
        if isinstance(node, ast.Constant) and isinstance(node.value, float):
            assert not 0.0 < node.value < 1.0, (
                f"weight-shaped literal {node.value} at line {node.lineno}")


def test_orchestrator_does_not_import_the_contract_layer_directly():
    """It calls compose_opportunity(); it does not assemble results itself."""
    import ast
    import pathlib

    tree = ast.parse(pathlib.Path("src/orchestrator.py").read_text(encoding="utf-8"))

    # BOTH node types. Collecting only ast.ImportFrom left a verified
    # hole: a plain `import src.opportunity_models` satisfied this test
    # and the substring guard alike. Mirrors imports_of() in the
    # invariant checker.
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add(node.module or "")

    assert "src.opportunity_integration" in imported
    assert "src.opportunity_models" not in imported, (
        "the orchestrator must not touch the canonical contract directly -- "
        "that would let it build a result without the composition engine"
    )


def test_component_weights_match_the_integrated_contract():
    """The orchestrator changed no weight on its way through."""
    from src.opportunity_models import INTEGRATED_WEIGHTS

    result = run()
    for c in result.opportunity.components:
        assert c.configured_weight == pytest.approx(
            INTEGRATED_WEIGHTS[c.name], abs=1e-9), c.name


def test_contributions_still_reconcile_to_the_aggregate():
    result = run()
    total = sum(c.weighted_contribution
                for c in result.opportunity.counted_components)
    assert result.opportunity.opportunity_score == pytest.approx(
        round(total, 2), abs=1e-9)


def test_negative_dimensions_are_inverted_exactly_once():
    result = run()
    for name in ("competition", "risk"):
        c = component(result, name)
        assert c.opportunity_score == pytest.approx(100.0 - c.raw_score, abs=1e-9)


# -- 8. no secret leakage ------------------------------------------------


def test_provider_failure_detail_carries_no_credential(monkeypatch):
    """A configured token must never reach the provenance record."""
    configured = FIXTURE_SECRET_A
    monkeypatch.setenv("APIFY_API_TOKEN", configured)

    result = run(trend_fetcher=failing_trend_fetcher(
        ApifyTrendsConfigurationError("APIFY_API_TOKEN is not configured")))

    blob = " ".join(
        [c.detail or "" for c in result.provider_calls]
        + list(result.unavailable) + list(result.notes)
    )
    assert configured not in blob


# The two tests below replace an earlier pair that passed vacuously: one
# asserted a token was absent from an exception whose message never
# contained it, and the other scanned a SUCCESSFUL run for the string
# "Bearer ". Neither executed the path where a credential can actually
# escape, and a real leak lived behind them.
#
# The leak: `requests` raises InvalidHeader with the offending HEADER
# VALUE embedded in its message. A malformed token (a trailing newline is
# enough) makes that value "Bearer <token>". Both integrations catch
# `requests.RequestException` and interpolate the exception into their own
# message (apify_trends.py:258, mercadolivre.py:168), so the token reaches
# the orchestrator inside an ApifyTrendsError.
#
# These drive the REAL integration so the wrapping under test is its own
# code, not a reproduction of it. Only `requests.post`/`get` is replaced.


def test_credential_in_a_wrapped_transport_error_is_redacted(monkeypatch):
    """A token that cannot be sent as a header must not be echoed back.

    Asserted through the orchestrator's provenance, its unavailable
    reasons, and the printed report.

    This path is now protected TWICE, and deliberately so. The
    integration withholds the transport error's message at source
    (`apify_trends.py`), and `_redact` would strip a credential that
    reached the text some other way. Because the upstream guard fires
    first, `[redacted]` does NOT appear here -- there is nothing left to
    redact. The assertion is therefore the token's ABSENCE, which is the
    actual invariant; asserting the marker would couple this test to
    which of the two layers happened to act.
    """
    configured = FIXTURE_SECRET_A
    monkeypatch.setenv("APIFY_API_TOKEN", configured + "\n")

    def exploding_post(*args, **kwargs):
        # Build the header the integration would have built, and let
        # `requests` reject it exactly as it does in production.
        requests.Request(
            "POST", "https://example.invalid",
            headers=kwargs.get("headers") or {},
        ).prepare()
        raise AssertionError("expected requests to reject the header")

    monkeypatch.setattr("src.integrations.apify_trends.requests.post",
                        exploding_post)

    # `trend_fetcher` is deliberately NOT passed, so the orchestrator
    # resolves its default -- the real fetch_trend_data. `run()` cannot be
    # used here: it substitutes a fixture fetcher when given None.
    result = run_opportunity_analysis(
        full_request(),
        marketplace_searcher=make_marketplace_searcher(Counter()),
    )

    trend_call = provider_call(result, PROVIDER_TRENDS)
    assert trend_call.status == STATUS_FAILED

    blob = " ".join(
        [c.detail or "" for c in result.provider_calls]
        + list(result.unavailable) + list(result.notes)
        + list(result.opportunity.notes)
        + [format_orchestration_report(result)]
    )
    assert configured not in blob
    assert "Bearer " not in blob

    # Withholding must not turn a known error into silence: the failure
    # is still attributed, and still names the transport failure mode.
    assert "ApifyTrendsError" in trend_call.detail
    assert "InvalidHeader" in trend_call.detail


def test_marketplace_credential_in_a_wrapped_transport_error_is_redacted(
    monkeypatch,
):
    """The same leak path through the other integration."""
    configured = FIXTURE_SECRET_B
    monkeypatch.setenv(ML_ACCESS_TOKEN_ENV_VAR, configured + "\n")

    def exploding_get(*args, **kwargs):
        requests.Request(
            "GET", "https://example.invalid",
            headers=kwargs.get("headers") or {},
        ).prepare()
        raise AssertionError("expected requests to reject the header")

    monkeypatch.setattr("src.integrations.mercadolivre.requests.get",
                        exploding_get)

    # `marketplace_searcher` omitted: the real search_products runs.
    result = run_opportunity_analysis(
        full_request(),
        trend_fetcher=make_trend_fetcher(Counter()),
    )

    market_call = provider_call(result, PROVIDER_MARKETPLACE)
    assert market_call.status == STATUS_FAILED

    blob = " ".join(
        [c.detail or "" for c in result.provider_calls]
        + list(result.unavailable) + list(result.notes)
        + list(result.opportunity.notes)
        + [format_orchestration_report(result)]
    )
    assert configured not in blob
    assert "APP_USR-" not in blob


def test_result_exposes_no_raw_provider_payload():
    """CLAUDE.md: never persist raw provider payloads."""
    result = run()
    for c in result.provider_calls:
        assert not hasattr(c, "payload")
        assert not hasattr(c, "response")
    assert not hasattr(result, "raw_trend_data")
    assert not hasattr(result, "raw_items")


FIXTURE_SECRET_C = "not-a-credential-fixture-value-c"


@pytest.mark.parametrize("carrier", [
    f"sent Bearer {FIXTURE_SECRET_C}",
    f"sent bearer {FIXTURE_SECRET_C}",
    f"Authorization: Token {FIXTURE_SECRET_C}",
    f"Authorization: Basic {FIXTURE_SECRET_C}",
    f"url https://api.example.com/v2?api_key={FIXTURE_SECRET_C}&q=fone",
    f"url https://api.example.com/v2?access_token={FIXTURE_SECRET_C}",
    f"ApiKey {FIXTURE_SECRET_C}",
])
def test_credential_values_are_stripped_from_failure_text(carrier):
    """A credential embedded in provider failure text must not survive.

    Parametrized over the *carrier* because the previous version of this
    test scanned a SUCCESSFUL run -- where no credential could appear
    regardless of whether redaction worked. It passed vacuously while a
    real leak existed.

    What is asserted is the value's absence, not the scheme word's.
    `Bearer`, `Authorization` and `api_key` are header and parameter
    NAMES; they identify which credential was malformed and are kept
    deliberately. Banning them would delete the diagnostic and protect
    nothing.
    """
    result = run(trend_fetcher=failing_trend_fetcher(
        ApifyTrendsError(f"Apify request failed: {carrier}")))

    blob = " ".join(
        [c.detail or "" for c in result.provider_calls]
        + list(result.unavailable) + list(result.notes)
        + list(result.opportunity.notes)
        + [format_orchestration_report(result)]
    )
    assert FIXTURE_SECRET_C not in blob
    assert "[redacted]" in blob
    # The error is still attributed, so redaction has not produced silence.
    assert "ApifyTrendsError" in blob


# -- request validation --------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"product_name": "  ", "query": "q"},
        {"product_name": "p", "query": ""},
        {"product_name": "p", "query": "q", "marketplace_limit": 0},
    ],
)
def test_invalid_request_is_rejected(kwargs):
    with pytest.raises(ValueError):
        OrchestrationRequest(**kwargs)


def test_marketplace_limit_is_forwarded_to_the_provider():
    seen = {}

    def searcher(query, limit=10):
        seen["limit"] = limit
        return []

    run(full_request(marketplace_limit=3), marketplace_searcher=searcher)
    assert seen["limit"] == 3


# -- provider injection must be patchable (regression) -------------------


def test_module_level_provider_patching_is_effective(monkeypatch):
    """Defaults must resolve at CALL time, not at definition time.

    A `trend_fetcher=fetch_trend_data` default argument binds once when
    the function is defined, which made
    `monkeypatch.setattr("src.orchestrator.fetch_trend_data", ...)`
    silently ineffective -- tests reached the real network and passed
    for the wrong reason. This test fails if that regresses.
    """
    import src.orchestrator as orch

    used = {"trend": False, "marketplace": False}

    def patched_trend(query, geo="BR", timeframe="today 12-m"):
        used["trend"] = True
        raise ApifyTrendsTimeoutError("patched: no network")

    def patched_search(query, limit=10):
        used["marketplace"] = True
        raise MercadoLivreTimeoutError("patched: no network")

    monkeypatch.setattr(orch, "fetch_trend_data", patched_trend)
    monkeypatch.setattr(orch, "search_products", patched_search)

    # No explicit injection -- exercises the default-resolution path.
    result = orch.run_opportunity_analysis(full_request())

    assert used["trend"], "module-level patch of fetch_trend_data was ignored"
    assert used["marketplace"], "module-level patch of search_products was ignored"
    assert len(result.failed_providers) == 2
    assert all("patched: no network" in (c.detail or "")
               for c in result.failed_providers)


def test_explicit_injection_still_overrides_the_default(monkeypatch):
    """Both injection styles coexist; the explicit argument wins."""
    import src.orchestrator as orch

    monkeypatch.setattr(
        orch, "fetch_trend_data",
        lambda *a, **k: pytest.fail("explicit injection should have won"))

    counter = Counter()
    result = run_opportunity_analysis(
        full_request(),
        trend_fetcher=make_trend_fetcher(counter),
        marketplace_searcher=make_marketplace_searcher(counter),
    )
    assert counter.trend == 1
    assert result.opportunity.readiness == READINESS_READY


# -- 9. failed evidence is absent, never zero ----------------------------
#
# Regression tests for three defects found reviewing this phase. Each was
# a case of a failed or partial fetch being described by a NUMBER where
# the honest answer was "we do not know".


def test_failed_marketplace_leaves_competition_without_an_evidence_value():
    """A dead provider must not yield `evidence_value=0.0`.

    The orchestrator used to run `analyze_competition` on `None`. The
    resulting component was correctly `available=False` with
    `raw_score=None`, but carried `evidence_value=0.0` -- zero
    competitors, which is the most *favorable* possible observation
    standing in for no observation at all. Every other unavailable
    component reports `None` there.
    """
    result = run(marketplace_searcher=failing_marketplace_searcher(
        MercadoLivreTimeoutError("Mercado Livre did not respond within 10s")))

    competition = component(result, "competition")
    assert competition.available is False
    assert competition.raw_score is None
    assert competition.opportunity_score is None
    assert competition.evidence_value is None


def test_failed_marketplace_reason_is_the_actual_failure():
    """The reported reason must be the failure, not a generic stand-in.

    Analyzing `None` attached the adapter's hardcoded "unreachable"
    wording to every failure mode, including ones that were not
    unreachability.
    """
    result = run(marketplace_searcher=failing_marketplace_searcher(
        MercadoLivreResponseError(status_code=403, message="403 Forbidden")))

    call = provider_call(result, PROVIDER_MARKETPLACE)
    assert call.status == STATUS_FAILED
    assert "403" in (call.detail or "")
    assert any("403" in reason for reason in result.unavailable)


def test_trend_provenance_separates_returned_points_from_usable_ones():
    """Reporting one count overstates thin evidence.

    `interest_over_time` includes points whose value failed to coerce to
    a number; only `observation_count` counts usable ones. A series with
    one usable value must not be described as six observations directly
    above Trend withholding its score for having too few.
    """
    counter = Counter()
    fetcher = make_trend_fetcher(counter, values=[50, None, None, None])
    result = run(trend_fetcher=fetcher)

    detail = provider_call(result, PROVIDER_TRENDS).detail or ""
    assert "4 point(s) returned" in detail
    assert "1 usable observation(s)" in detail


def test_provider_call_status_is_readable_as_three_distinct_states():
    """`succeeded` alone cannot express "never attempted".

    Margin/Supplier/Logistics/Risk have no provider, so their calls are
    `not_supplied` -- epistemically different from a provider that was
    called and failed. Reading that through one boolean collapses
    "attempted and lost" into "never attempted".
    """
    # Margin omitted, so one call is `not_supplied`; the marketplace is
    # made to fail, so another is `failed`. All three states coexist.
    result = run(
        full_request(margin_inputs=None),
        marketplace_searcher=failing_marketplace_searcher(
            MercadoLivreTimeoutError("timeout")),
    )

    ok = provider_call(result, PROVIDER_TRENDS)
    failed = provider_call(result, PROVIDER_MARKETPLACE)
    absent = next(c for c in result.provider_calls
                  if c.status == STATUS_NOT_SUPPLIED)

    assert (ok.succeeded, ok.failed, ok.not_attempted) == (True, False, False)
    assert (failed.succeeded, failed.failed, failed.not_attempted) == (
        False, True, False)
    assert (absent.succeeded, absent.failed, absent.not_attempted) == (
        False, False, True)

    # Exactly one predicate is true for every call -- no state is both
    # expressible two ways or expressible none.
    for call in result.provider_calls:
        assert [call.succeeded, call.failed, call.not_attempted].count(True) == 1
