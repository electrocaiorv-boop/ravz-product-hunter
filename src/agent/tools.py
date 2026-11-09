"""The research-tool allowlist (Phase 12B).

Four tools, all read-only research. There is deliberately no tool that
publishes a listing, spends money, writes to a store, or computes a
score. A capability that does not exist cannot be talked into existing
by a prompt.

== Why scoring is not a tool ==

`run_full_analysis` calls the Phase 12A orchestrator, which calls
`compose_opportunity()`. That is the only path to a score, and the
agent cannot reach past it: this module never performs arithmetic on a
score, and the package never imports the pure opportunity contract
module (enforced by an AST test, not just by convention).

== Evidence reuse ==

A run keeps an `EvidenceCache`. Repeating a provider call with the same
arguments returns the first result instead of re-fetching. This is the
Phase 12A single-fetch rule extended across agent turns: a model that
decides to "check trends again" must not double the cost, and must not
hand two different samples to two domains describing one market.
"""

from dataclasses import dataclass, field

from src.agent.contracts import (
    REJECT_INVALID_ARGUMENTS,
    REJECT_NOT_ALLOWLISTED,
)
from src.integrations.apify_trends import (
    DEFAULT_GEO,
    DEFAULT_TIMEFRAME,
    ApifyTrendsError,
)
from src.integrations.mercadolivre import MercadoLivreError
from src.orchestrator import (
    DEFAULT_MARKETPLACE_LIMIT,
    OrchestrationRequest,
    run_opportunity_analysis,
)

TOOL_RUN_FULL_ANALYSIS = "run_full_analysis"
TOOL_FETCH_TREND = "fetch_trend_evidence"
TOOL_SEARCH_MARKETPLACE = "search_marketplace"
TOOL_DECLARE_MISSING = "declare_missing_evidence"

# The allowlist. Membership is checked by exact string match before any
# dispatch; there is no pattern, prefix or fallback that could admit a
# name the application did not declare.
ALLOWED_TOOLS = (
    TOOL_RUN_FULL_ANALYSIS,
    TOOL_FETCH_TREND,
    TOOL_SEARCH_MARKETPLACE,
    TOOL_DECLARE_MISSING,
)

# Domains the agent may declare missing. Bounded so a model cannot
# invent a domain name and have it appear in a report as if the system
# knew about it.
DECLARABLE_DOMAINS = (
    "margin", "supplier", "logistics", "risk", "competition", "demand",
    "trend",
)


class ToolError(Exception):
    """A tool call was rejected. `reason` is a REJECT_* constant."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


# -- argument validation ------------------------------------------------
#
# Validated in code against explicit types and bounds. The model's
# arguments are untrusted input, exactly like a web form's.


def _require_str(arguments: dict, key: str, *, max_length: int = 200,
                 required: bool = True, default: str = "") -> str:
    if key not in arguments or arguments[key] is None:
        if required:
            raise ToolError(REJECT_INVALID_ARGUMENTS, f"missing '{key}'")
        return default
    value = arguments[key]
    if not isinstance(value, str):
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        f"'{key}' must be a string, got {type(value).__name__}")
    if not value.strip():
        raise ToolError(REJECT_INVALID_ARGUMENTS, f"'{key}' must not be blank")
    if len(value) > max_length:
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        f"'{key}' exceeds {max_length} characters")
    return value


def _require_int(arguments: dict, key: str, *, lo: int, hi: int,
                 default: int) -> int:
    if key not in arguments or arguments[key] is None:
        return default
    value = arguments[key]
    # bool is an int subclass; a boolean limit is a type error, not a 1.
    if isinstance(value, bool) or not isinstance(value, int):
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        f"'{key}' must be an integer")
    if not lo <= value <= hi:
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        f"'{key}' must be between {lo} and {hi}")
    return value


def _reject_unknown_keys(arguments: dict, allowed: tuple[str, ...]) -> None:
    """Unknown keys are an error, not ignored.

    Silently dropping them would let a model (or injected text) smuggle
    a field that a future version might start honouring.
    """
    unknown = sorted(set(arguments) - set(allowed))
    if unknown:
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        f"unknown argument(s): {', '.join(unknown)}")


# JSON schemas advertised to the model. Advisory only -- the validators
# above are what actually enforce anything.
TOOL_SCHEMAS = (
    {
        "name": TOOL_RUN_FULL_ANALYSIS,
        "description": (
            "Run the complete deterministic opportunity pipeline for the "
            "candidate and return the composed analysis. This is the only "
            "way to obtain any score. You cannot compute or adjust scores "
            "yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string",
                          "description": "Search term to research."},
                "geo": {"type": "string", "description": "Market, e.g. BR."},
                "timeframe": {"type": "string",
                              "description": "Google Trends timeframe."},
                "marketplace_limit": {"type": "integer", "minimum": 1,
                                      "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": TOOL_FETCH_TREND,
        "description": (
            "Fetch search-interest evidence only. Cheaper than a full "
            "analysis; use it to screen a candidate before committing."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "geo": {"type": "string"},
                "timeframe": {"type": "string"},
            },
            "required": ["query"],
        },
    },
    {
        "name": TOOL_SEARCH_MARKETPLACE,
        "description": (
            "Search marketplace listings only. Returns listing facts, not "
            "a competition score."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["query"],
        },
    },
    {
        "name": TOOL_DECLARE_MISSING,
        "description": (
            "Record that a domain's evidence is missing and must be "
            "gathered by a human. Use this INSTEAD of estimating, "
            "assuming, or filling in a plausible value. There is no tool "
            "that invents evidence."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "enum": list(DECLARABLE_DOMAINS)},
                "needed": {"type": "array", "items": {"type": "string"},
                           "description": "Specific facts required."},
                "why": {"type": "string"},
            },
            "required": ["domain", "needed"],
        },
    },
)


@dataclass
class EvidenceCache:
    """Per-run memo of provider results, keyed by call arguments.

    Enforces the single-fetch rule across agent turns. `hits` is
    recorded so a run can report that evidence was reused rather than
    re-fetched.
    """

    # Per-TOOL result memos (what a tool returned).
    trend: dict = field(default_factory=dict)
    marketplace: dict = field(default_factory=dict)
    analysis: dict = field(default_factory=dict)
    # Per-PROVIDER memos, shared by every tool including the orchestrator's
    # own fetches. This is what makes the single-fetch rule hold across
    # tools and not merely within one.
    provider_trend: dict = field(default_factory=dict)
    provider_marketplace: dict = field(default_factory=dict)
    hits: int = 0

    def remember(self, store: dict, key, factory):
        if key in store:
            self.hits += 1
            return store[key], True
        value = factory()
        store[key] = value
        return value, False


@dataclass
class ToolContext:
    """Everything the tools need, injected so tests need no network."""

    product_name: str
    cache: EvidenceCache = field(default_factory=EvidenceCache)
    # Annotated as `object` deliberately: these are callables, and
    # without an annotation a dataclass does not treat them as fields
    # at all.
    trend_fetcher: object = None
    marketplace_searcher: object = None
    declared: list = field(default_factory=list)

    def __post_init__(self) -> None:
        # Wrap the providers in ONE memo shared by every tool.
        #
        # Without this the caches were per-tool and independent, so
        # evidence fetched inside `run_full_analysis` was invisible to
        # `fetch_trend_evidence` and vice versa. Measured: four tool
        # calls over one query produced TWO trend fetches and TWO
        # marketplace fetches of identical evidence -- double the cost
        # and double the rate-limit exposure, and two samples of one
        # market where there should be one.
        #
        # Wrapping at the injection seam means the orchestrator's own
        # fetches go through the same memo, with no change to the
        # orchestrator: it already accepts injected providers.
        object.__setattr__(self, "trend_fetcher",
                           _memoized_trend(self.trend_fetcher, self.cache))
        object.__setattr__(
            self, "marketplace_searcher",
            _memoized_marketplace(self.marketplace_searcher, self.cache))


def _memoized_trend(fetcher, cache: "EvidenceCache"):
    """Memoize trend fetches by (query, geo, timeframe) for one run."""

    def wrapped(query, geo=DEFAULT_GEO, timeframe=DEFAULT_TIMEFRAME):
        resolved = fetcher
        if resolved is None:
            # Resolved at CALL time, never at definition time, so
            # module-level patching stays effective.
            from src.integrations.apify_trends import fetch_trend_data
            resolved = fetch_trend_data
        key = (query, geo, timeframe)
        if key in cache.provider_trend:
            cache.hits += 1
            outcome = cache.provider_trend[key]
        else:
            try:
                outcome = ("ok", resolved(query, geo=geo, timeframe=timeframe))
            except ApifyTrendsError as exc:
                # The FAILURE is memoized too. Retrying inside one run
                # could turn a hard failure into partial data, which is
                # exactly what Phase 12A forbids.
                outcome = ("error", exc)
            cache.provider_trend[key] = outcome
        if outcome[0] == "error":
            raise outcome[1]
        return outcome[1]

    return wrapped


def _memoized_marketplace(searcher, cache: "EvidenceCache"):
    """Memoize marketplace searches by (query, limit) for one run."""

    def wrapped(query, limit=DEFAULT_MARKETPLACE_LIMIT):
        resolved = searcher
        if resolved is None:
            from src.integrations.mercadolivre import search_products
            resolved = search_products
        key = (query, limit)
        if key in cache.provider_marketplace:
            cache.hits += 1
            outcome = cache.provider_marketplace[key]
        else:
            try:
                outcome = ("ok", resolved(query, limit=limit))
            except MercadoLivreError as exc:
                outcome = ("error", exc)
            cache.provider_marketplace[key] = outcome
        if outcome[0] == "error":
            raise outcome[1]
        return outcome[1]

    return wrapped


# -- tool implementations -----------------------------------------------


def _run_full_analysis(arguments: dict, context: ToolContext) -> tuple[dict, bool]:
    _reject_unknown_keys(
        arguments, ("query", "geo", "timeframe", "marketplace_limit"))
    query = _require_str(arguments, "query")
    geo = _require_str(arguments, "geo", required=False, default=DEFAULT_GEO,
                       max_length=10)
    timeframe = _require_str(arguments, "timeframe", required=False,
                             default=DEFAULT_TIMEFRAME, max_length=40)
    limit = _require_int(arguments, "marketplace_limit", lo=1, hi=50,
                         default=DEFAULT_MARKETPLACE_LIMIT)

    key = (query, geo, timeframe, limit)

    def run():
        request = OrchestrationRequest(
            product_name=context.product_name, query=query, geo=geo,
            timeframe=timeframe, marketplace_limit=limit,
        )
        return run_opportunity_analysis(
            request,
            trend_fetcher=context.trend_fetcher,
            marketplace_searcher=context.marketplace_searcher,
        )

    result, reused = context.cache.remember(context.cache.analysis, key, run)
    return {"orchestration_result": result}, reused


def _fetch_trend(arguments: dict, context: ToolContext) -> tuple[dict, bool]:
    _reject_unknown_keys(arguments, ("query", "geo", "timeframe"))
    query = _require_str(arguments, "query")
    geo = _require_str(arguments, "geo", required=False, default=DEFAULT_GEO,
                       max_length=10)
    timeframe = _require_str(arguments, "timeframe", required=False,
                             default=DEFAULT_TIMEFRAME, max_length=40)

    # `context.trend_fetcher` is the shared memo installed by
    # ToolContext, so this hits the same evidence the orchestrator uses.
    def run():
        try:
            return {"trend_data": context.trend_fetcher(
                query, geo=geo, timeframe=timeframe)}
        except ApifyTrendsError as exc:
            # Failure becomes explicit unavailable evidence, never a
            # default and never a silent retry.
            return {"trend_data": None,
                    "unavailable": f"{type(exc).__name__}: {exc}"}

    return context.cache.remember(
        context.cache.trend, (query, geo, timeframe), run)


def _search_marketplace(arguments: dict,
                        context: ToolContext) -> tuple[dict, bool]:
    _reject_unknown_keys(arguments, ("query", "limit"))
    query = _require_str(arguments, "query")
    limit = _require_int(arguments, "limit", lo=1, hi=50,
                         default=DEFAULT_MARKETPLACE_LIMIT)

    def run():
        try:
            return {"items": context.marketplace_searcher(query, limit=limit)}
        except MercadoLivreError as exc:
            return {"items": None,
                    "unavailable": f"{type(exc).__name__}: {exc}"}

    return context.cache.remember(
        context.cache.marketplace, (query, limit), run)


def _declare_missing(arguments: dict,
                     context: ToolContext) -> tuple[dict, bool]:
    _reject_unknown_keys(arguments, ("domain", "needed", "why"))
    domain = _require_str(arguments, "domain", max_length=40)
    if domain not in DECLARABLE_DOMAINS:
        raise ToolError(
            REJECT_INVALID_ARGUMENTS,
            f"'{domain}' is not a known domain; allowed: "
            f"{', '.join(DECLARABLE_DOMAINS)}")

    needed = arguments.get("needed")
    if not isinstance(needed, (list, tuple)) or not needed:
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        "'needed' must be a non-empty list of strings")
    if len(needed) > 25:
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        "'needed' may list at most 25 items")
    items = []
    for entry in needed:
        if not isinstance(entry, str) or not entry.strip():
            raise ToolError(REJECT_INVALID_ARGUMENTS,
                            "'needed' entries must be non-blank strings")
        items.append(entry.strip()[:200])

    why = _require_str(arguments, "why", required=False,
                       default="requested by the research agent",
                       max_length=400)

    context.declared.append((domain, tuple(items), why))
    # Returns the ASK only. No value, no estimate, no placeholder.
    return {"declared": {"domain": domain, "needed": tuple(items),
                         "why": why}}, False


_DISPATCH = {
    TOOL_RUN_FULL_ANALYSIS: _run_full_analysis,
    TOOL_FETCH_TREND: _fetch_trend,
    TOOL_SEARCH_MARKETPLACE: _search_marketplace,
    TOOL_DECLARE_MISSING: _declare_missing,
}


def dispatch(name: str, arguments: dict,
             context: ToolContext) -> tuple[dict, bool]:
    """Validate and run one tool call.

    Raises `ToolError` for anything not explicitly permitted. The
    allowlist check comes FIRST and is an exact-match lookup: an
    unrecognized name never reaches a validator, let alone an
    implementation.
    """
    if not isinstance(name, str) or name not in ALLOWED_TOOLS:
        raise ToolError(
            REJECT_NOT_ALLOWLISTED,
            f"'{name}' is not an allowed tool; allowed: "
            f"{', '.join(ALLOWED_TOOLS)}")
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise ToolError(REJECT_INVALID_ARGUMENTS,
                        "arguments must be an object")
    return _DISPATCH[name](arguments, context)
