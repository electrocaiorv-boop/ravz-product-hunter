"""Deterministic orchestration of the opportunity pipeline (Phase 12A).

    integrations -> domain engines -> compose_opportunity()

This module is the ONLY place permitted to import both integrations and
domain analyzers. It coordinates; it owns no scoring math.

== What it does ==

1. Resolves the available evidence through the existing integration
   interfaces, calling each provider **at most once** per run.
2. Runs each applicable domain analyzer on that evidence.
3. Translates every provider failure into explicit unavailable evidence
   with a reason -- never a default, never a retry that quietly yields
   partial data.
4. Hands the domain results to `compose_opportunity()` and returns its
   verdict untouched, alongside a provenance record of what was called.

== What it must never do (CLAUDE.md, Phase 12 Orchestrator Contract) ==

- calculate business scores
- re-weight components
- invert scores
- recreate or re-derive domain formulas
- fabricate missing data
- convert `None` to 0, 50, `False`, neutral, average or safe
- bypass `compose_opportunity()`
- persist raw provider payloads
- leak request headers or credentials in logs or error text

It owns sequencing and failure translation, nothing else. Every number in
the returned result traces to a domain engine or the composition layer.

== Shared evidence is fetched once (the central Phase 12A concern) ==

Two provider calls feed five domains. Calling a provider twice would
double its cost and rate-limit exposure, and -- worse -- could yield two
*different* samples silently feeding two domains that are supposed to
describe the same market.

    fetch_trend_data()  -- ONE Apify Google-Trends call
        |-> analyze_trend(TrendData)            -> Trend
        '-> build_demand_signals(trend_data,
                                  trend_metrics) -> Demand

    search_products()   -- ONE Mercado Livre search
        |-> build_competition_signals(items)     -> Competition
        '-> build_demand_signals(marketplace_items)

Note this is NOT the same thing as the Demand/Trend double-counting rule.
Sharing one fetch is required; what is forbidden is letting both Demand
and Trend earn weighted contributions from it. That rule lives in
`compose_opportunity()` and is not re-implemented here -- the
orchestrator simply passes both results in and lets the composition layer
elect one family representative.

== Manually supplied domains ==

Margin, Supplier, Logistics and Risk have no integration in this project
-- their inputs come from a real investigation, not an API. The
orchestrator accepts already-built `*Inputs` objects and runs the
analyzer when one is supplied. Omitting them is honest, not a failure:
the composition layer reports them unavailable and withholds the
classification accordingly.

The orchestrator never fabricates these inputs, and never invents a
provider that does not exist.

== Determinism ==

Given the same request and the same injected providers, the pipeline
produces the same result. The only non-determinism is in *which evidence
the providers return* -- never in how that evidence is scored.

Providers are injectable (`trend_fetcher`, `marketplace_searcher`) so the
whole flow can be exercised with controlled fixtures and no network.
"""

import os
import re
from dataclasses import dataclass

from src.competition_analysis import analyze_competition
from src.competition_models import build_competition_signals
from src.config import get_apify_token
from src.demand_analysis import analyze_demand
from src.demand_models import build_demand_signals
from src.integrations.apify_trends import (
    DEFAULT_GEO,
    DEFAULT_TIMEFRAME,
    ApifyTrendsError,
    fetch_trend_data,
)
from src.integrations.mercadolivre import (
    ACCESS_TOKEN_ENV_VAR as ML_ACCESS_TOKEN_ENV_VAR,
    MercadoLivreError,
    search_products,
)
from src.logistics_analysis import analyze_logistics
from src.logistics_models import LogisticsInputs
from src.margin_analysis import analyze_margin
from src.margin_models import MarginInputs
from src.opportunity_integration import compose_opportunity
from src.risk_analysis import analyze_risk
from src.risk_models import RiskInputs
from src.supplier_analysis import analyze_supplier
from src.supplier_models import SupplierInputs
from src.trend_analysis import analyze_trend

# Default marketplace page size. Mirrors the CLI's existing choice so a
# single run and a manual Competition analysis sample the same way.
DEFAULT_MARKETPLACE_LIMIT = 10

PROVIDER_TRENDS = "apify:google-trends"
PROVIDER_MARKETPLACE = "mercadolivre:search"

STATUS_OK = "ok"
STATUS_FAILED = "failed"
STATUS_NOT_SUPPLIED = "not_supplied"


@dataclass(frozen=True)
class ProviderCall:
    """Provenance for one provider attempt in this run.

    `detail` carries the failure's exception type and its message, passed
    through `_redact`. This module never adds headers, tokens or raw
    payloads of its own.

    The integrations now withhold transport-error messages at source, so
    `_redact` is a second layer here rather than the only one -- it still
    matters because injected providers are outside that guarantee.
    """

    provider: str
    status: str
    serves: tuple[str, ...]
    detail: str | None = None

    # `status` is genuinely three-valued and the states mean different
    # things: evidence obtained / attempted and lost / never attempted
    # because no provider exists. Each gets its own predicate so no
    # consumer has to infer a third state from a boolean.
    @property
    def succeeded(self) -> bool:
        return self.status == STATUS_OK

    @property
    def failed(self) -> bool:
        return self.status == STATUS_FAILED

    @property
    def not_attempted(self) -> bool:
        return self.status == STATUS_NOT_SUPPLIED


@dataclass(frozen=True)
class OrchestrationRequest:
    """Everything one orchestration run needs.

    `query` is the search term handed to both providers. The
    manually-investigated domains are optional: supply a built `*Inputs`
    to have that domain analyzed, omit it to have it reported
    unavailable.
    """

    product_name: str
    query: str
    geo: str = DEFAULT_GEO
    timeframe: str = DEFAULT_TIMEFRAME
    marketplace_limit: int = DEFAULT_MARKETPLACE_LIMIT

    margin_inputs: MarginInputs | None = None
    supplier_inputs: SupplierInputs | None = None
    logistics_inputs: LogisticsInputs | None = None
    risk_inputs: RiskInputs | None = None

    def __post_init__(self) -> None:
        if not self.product_name or not self.product_name.strip():
            raise ValueError("product_name must not be empty")
        if not self.query or not self.query.strip():
            raise ValueError("query must not be empty")
        if self.marketplace_limit < 1:
            raise ValueError("marketplace_limit must be at least 1")


@dataclass(frozen=True)
class OrchestrationResult:
    """The composed opportunity plus a record of how it was obtained.

    `opportunity` is `compose_opportunity()`'s output, unmodified. The
    orchestrator adds provenance around it and changes nothing inside it.
    """

    request: OrchestrationRequest
    # compose_opportunity()'s OpportunityAnalysisResult. Deliberately not
    # annotated: naming the type requires importing the pure contract
    # layer, and the orchestrator is forbidden from depending on it so it
    # can never assemble a result without the composition engine.
    opportunity: object
    provider_calls: tuple[ProviderCall, ...] = ()
    unavailable: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    @property
    def failed_providers(self) -> tuple[ProviderCall, ...]:
        return tuple(c for c in self.provider_calls if c.status == STATUS_FAILED)


# Credential-bearing header schemes. Everything after the scheme word is
# the credential itself, so the whole remainder is dropped. The scheme
# word itself is KEPT -- it is not a secret, and it is the part that
# tells an operator which header was malformed.
_AUTH_SCHEME = re.compile(
    r"\b(Bearer|Token|Basic|ApiKey)\b[ \t]*\S*", re.IGNORECASE
)

# Credentials also travel as query parameters, which the scheme pattern
# above cannot see. A `requests` error quoting a URL carries the value
# verbatim. Keep the parameter NAME, drop the value.
_CREDENTIAL_PARAM = re.compile(
    r"\b(api[-_]?key|access[-_]?token|refresh[-_]?token|token|secret|"
    r"password|passwd|auth|signature|sig)\s*=\s*[^&\s'\"]*",
    re.IGNORECASE,
)

_REDACTED = "[redacted]"


def _redact(text: str) -> str:
    """Strip credentials from provider failure text before storing it.

    This is the SECOND of two layers, and deliberately redundant.

    The primary guard is now upstream: both integrations report a
    transport error's exception TYPE and withhold its message, because
    `requests.exceptions.InvalidHeader` embeds the **full header value**
    -- including `Bearer <token>` -- and a token containing a newline
    raises it offline, before any socket opens. That leak was confirmed
    reaching stdout through four CLI paths and is fixed at the
    integration boundary, which protects every caller rather than only
    this one.

    This layer stays because the orchestrator accepts **injected**
    providers (`trend_fetcher`, `marketplace_searcher`). A caller's own
    fetcher is outside the integrations' guarantee and can raise
    anything. Here the text also becomes a field on a returned result
    object, and the next phase persists results to a database -- so
    `None`-safe scrubbing is cheap insurance at the point of storage.

    Two passes, in order:
      1. drop any `Bearer`/`Token`/`Basic`/`ApiKey` value, which covers
         credentials this project never configured itself;
      2. scrub the configured token values verbatim, which covers a
         credential that reaches the text some other way.
    """
    redacted = _AUTH_SCHEME.sub(lambda m: f"{m.group(1)} {_REDACTED}", text)
    redacted = _CREDENTIAL_PARAM.sub(
        lambda m: f"{m.group(1)}={_REDACTED}", redacted
    )

    for value in (
        get_apify_token(),
        os.environ.get(ML_ACCESS_TOKEN_ENV_VAR),
    ):
        if value and value.strip():
            redacted = redacted.replace(value.strip(), _REDACTED)
            redacted = redacted.replace(value, _REDACTED)

    return redacted


def _describe_failure(exc: Exception) -> str:
    """Sanitized one-line failure description: exception type plus message.

    The message is redacted before it is stored or printed -- see
    `_redact` for why the integrations' own guarantee is not relied upon.
    """
    message = _redact(str(exc)).strip() or "no detail provided"
    return f"{type(exc).__name__}: {message}"


def _fetch_trend_evidence(request, trend_fetcher):
    """ONE Apify call, shared by Trend and Demand.

    Returns (trend_data, trend_metrics, ProviderCall). On failure both
    payloads are None -- never a substitute value.
    """
    serves = ("trend", "demand")
    try:
        trend_data = trend_fetcher(
            request.query, geo=request.geo, timeframe=request.timeframe
        )
    except ApifyTrendsError as exc:
        # Every ApifyTrendsError subclass -- configuration, timeout,
        # connection, response, data, actor -- is operationally
        # different but epistemically identical: we do not know.
        return None, None, ProviderCall(
            PROVIDER_TRENDS, STATUS_FAILED, serves, _describe_failure(exc)
        )

    # Derived from the SAME TrendData the Demand builder will read.
    trend_metrics = analyze_trend(trend_data)
    # Report both counts, labelled. `interest_over_time` includes points
    # whose value failed to coerce to a number; only
    # `observation_count` counts usable ones. Collapsing them into one
    # figure overstates the evidence -- a 12-point series with 1 usable
    # value would read as "12 observations" directly above Trend
    # withholding its score for having fewer than 2.
    returned = len(trend_data.interest_over_time)
    usable = trend_metrics.observation_count
    return trend_data, trend_metrics, ProviderCall(
        PROVIDER_TRENDS, STATUS_OK, serves,
        f"{returned} point(s) returned, {usable} usable observation(s) "
        f"from {trend_data.source}",
    )


def _fetch_marketplace_evidence(request, marketplace_searcher):
    """ONE Mercado Livre search, shared by Competition and Demand."""
    serves = ("competition", "demand")
    try:
        items = marketplace_searcher(request.query, limit=request.marketplace_limit)
    except MercadoLivreError as exc:
        return None, ProviderCall(
            PROVIDER_MARKETPLACE, STATUS_FAILED, serves, _describe_failure(exc)
        )

    return items, ProviderCall(
        PROVIDER_MARKETPLACE, STATUS_OK, serves, f"{len(items)} item(s) sampled"
    )


def run_opportunity_analysis(
    request: OrchestrationRequest,
    *,
    trend_fetcher=None,
    marketplace_searcher=None,
) -> OrchestrationResult:
    """Run the deterministic pipeline for one product candidate.

    Providers are injectable so the whole flow can be exercised with
    controlled fixtures and no network access.

    The defaults are resolved HERE rather than in the signature. A
    default argument binds once at definition time, which would make
    `monkeypatch.setattr("src.orchestrator.fetch_trend_data", ...)`
    silently ineffective -- tests would reach the real network and pass
    for the wrong reason. Resolving the module global at call time keeps
    both injection styles working.

    Raises only `ValueError` for an invalid request. Provider failures
    never propagate: each becomes explicit unavailable evidence with a
    reason, and the run continues so the remaining evidence is still
    composed.
    """
    if trend_fetcher is None:
        trend_fetcher = fetch_trend_data
    if marketplace_searcher is None:
        marketplace_searcher = search_products

    calls: list[ProviderCall] = []
    unavailable: list[str] = []
    notes: list[str] = []

    # -- provider evidence, each fetched at most once -------------------
    trend_data, trend_metrics, trend_call = _fetch_trend_evidence(
        request, trend_fetcher
    )
    calls.append(trend_call)
    if not trend_call.succeeded:
        unavailable.append(
            "search-interest evidence (Google Trends via Apify): "
            f"{trend_call.detail}"
        )

    items, marketplace_call = _fetch_marketplace_evidence(
        request, marketplace_searcher
    )
    calls.append(marketplace_call)
    if not marketplace_call.succeeded:
        unavailable.append(
            f"marketplace evidence (Mercado Livre search): {marketplace_call.detail}"
        )

    notes.append(
        "each provider was called at most once; shared evidence is reused "
        "across the domains that consume it rather than re-fetched"
    )

    # -- provider-backed domains ---------------------------------------
    # Demand reads BOTH sources. It is built even when both are missing:
    # build_demand_signals records each absence honestly and
    # analyze_demand withholds its score rather than guessing.
    demand_result = analyze_demand(
        build_demand_signals(
            request.query,
            request.geo,
            trend_data=trend_data,
            trend_metrics=trend_metrics,
            marketplace_items=items,
        )
    )

    # Competition is analyzed only when the marketplace call succeeded.
    # Running it on `None` produced a component that was correctly
    # unavailable but carried `evidence_value=0.0` -- a number standing
    # in for "we do not know", where every other unavailable component
    # reports None. It also attached the adapter's hardcoded
    # "unreachable" reason to failures that were not unreachability.
    # Passing None lets the ProviderCall above be the sole authority on
    # why the evidence is missing.
    competition_result = None
    if items is not None:
        competition_result = analyze_competition(
            build_competition_signals(request.query, marketplace_items=items),
            requested_limit=request.marketplace_limit,
        )

    # -- manually investigated domains ---------------------------------
    # No integration populates these. An omitted input is reported
    # unavailable, never invented.
    manual = (
        ("margin", request.margin_inputs, analyze_margin,
         "unit economics (sale price, product cost, fee/tax/shipping structure)"),
        ("supplier", request.supplier_inputs, analyze_supplier,
         "supplier terms (MOQ, stock, lead time, dropshipping, invoicing)"),
        ("logistics", request.logistics_inputs, analyze_logistics,
         "physical and fulfillment facts (weight, dimensions, handling flags)"),
        ("risk", request.risk_inputs, analyze_risk,
         "risk evidence (dependency, continuity, volatility, compliance)"),
    )
    results: dict[str, object] = {}
    for name, inputs, analyze, description in manual:
        if inputs is None:
            results[name] = None
            calls.append(
                ProviderCall(f"manual:{name}", STATUS_NOT_SUPPLIED, (name,),
                             "no inputs supplied for this run")
            )
            unavailable.append(
                f"{name} evidence not supplied: {description}. This project has "
                "no integration for it -- it comes from a separate "
                "investigation, never from a provider."
            )
        else:
            results[name] = analyze(inputs)

    # -- composition ---------------------------------------------------
    # The single authority on weighting, direction, family election,
    # readiness and classification. Never bypassed, never second-guessed.
    opportunity = compose_opportunity(
        request.product_name,
        demand_result=demand_result,
        trend_metrics=trend_metrics,
        competition_result=competition_result,
        margin_result=results["margin"],
        supplier_result=results["supplier"],
        logistics_result=results["logistics"],
        risk_result=results["risk"],
    )

    return OrchestrationResult(
        request=request,
        opportunity=opportunity,
        provider_calls=tuple(calls),
        unavailable=tuple(unavailable),
        notes=tuple(notes),
    )
