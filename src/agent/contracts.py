"""Pure data contracts for the agent layer (Phase 12B).

Imports only `dataclasses` and `typing`, mirroring the discipline of
the pure opportunity contract module: a contract layer cannot reach for
a provider,
an LLM, a clock or a scoring engine.

Nothing here computes a business score. `AgentResult.analysis` holds a
composed `OpportunityAnalysisResult` produced elsewhere, unmodified.
"""

from dataclasses import dataclass, field

# Terminal states for one agent run. Every run ends in exactly one.
#
# `BUDGET_EXHAUSTED` and `UNAVAILABLE` are deliberately NOT failures in
# the sense of "something broke" -- they are honest reports that the run
# stopped early or never started. Neither may present a guess as a
# result.
OUTCOME_COMPLETED = "completed"
OUTCOME_BUDGET_EXHAUSTED = "budget_exhausted"
OUTCOME_UNAVAILABLE = "unavailable"
OUTCOME_REFUSED = "refused"

# Why a tool call was rejected. Kept distinct because they mean
# different things to a reviewer: a name that is not on the allowlist is
# a possible injection attempt, while bad arguments are usually a model
# mistake.
REJECT_NOT_ALLOWLISTED = "not_allowlisted"
REJECT_INVALID_ARGUMENTS = "invalid_arguments"
REJECT_BUDGET = "budget_exceeded"
REJECT_DUPLICATE = "duplicate_suppressed"
REJECT_NEEDS_APPROVAL = "requires_approval"


@dataclass(frozen=True)
class Budget:
    """Hard limits for one agent run.

    Enforced in code by `budget.BudgetTracker`, never by asking the
    model to behave. A model that ignores every instruction still cannot
    exceed these.

    `max_estimated_cost_usd` is checked against an ESTIMATE computed
    from observed token counts and a configured price table. It is not
    the billed amount and must never be presented as one.

    == What these limits do and do not guarantee ==

    Each is checked BEFORE a call is dispatched, so the limits bound how
    many calls a run may make and stop it from continuing once a
    threshold is crossed.

    They are NOT a spend ceiling. A call's token usage is only known
    after it returns, so a single call can carry the run past
    `max_estimated_cost_usd` in one step; the limit then refuses the
    NEXT call. It cannot retroactively shrink a request already sent.

    So `max_estimated_cost_usd=0.50` means "stop once roughly $0.50 of
    estimated spend has accumulated", NOT "this run cannot be billed
    more than $0.50". Per-request exposure is bounded separately, and
    only on the output side, by the client's `max_output_tokens`.

    For a hard spend cap, use Anthropic's own account-level billing
    limits. Nothing in this process can enforce one.
    """

    max_tool_calls: int = 8
    max_llm_turns: int = 6
    max_input_tokens: int = 120_000
    max_output_tokens: int = 8_000
    max_estimated_cost_usd: float = 0.50
    max_wall_clock_seconds: float = 120.0

    def __post_init__(self) -> None:
        for name in (
            "max_tool_calls", "max_llm_turns", "max_input_tokens",
            "max_output_tokens",
        ):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")
        if self.max_estimated_cost_usd <= 0:
            raise ValueError("max_estimated_cost_usd must be positive")
        if self.max_wall_clock_seconds <= 0:
            raise ValueError("max_wall_clock_seconds must be positive")


@dataclass(frozen=True)
class Usage:
    """Observed token usage and the cost ESTIMATE derived from it.

    `input_tokens` / `output_tokens` are reported by the provider.
    `estimated_cost_usd` is computed locally from a configured price
    table: it is an estimate, it can drift from real billing, and
    `is_estimate` exists so no caller can forget that.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    llm_turns: int = 0
    is_estimate: bool = True

    def plus(self, input_tokens: int, output_tokens: int,
             estimated_cost_usd: float) -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + input_tokens,
            output_tokens=self.output_tokens + output_tokens,
            estimated_cost_usd=self.estimated_cost_usd + estimated_cost_usd,
            llm_turns=self.llm_turns + 1,
        )


@dataclass(frozen=True)
class ToolCall:
    """One attempted tool invocation and what came of it.

    A rejected call still appears here, with `rejected_reason` set. The
    record of what was *attempted* is part of the audit trail -- it is
    how an injection attempt becomes visible instead of silent.
    """

    name: str
    arguments: dict
    accepted: bool
    rejected_reason: str | None = None
    detail: str | None = None
    reused_evidence: bool = False


@dataclass(frozen=True)
class EvidenceRequest:
    """A structured ask for evidence the agent does not have.

    This is the ONLY thing the agent may do about missing evidence. It
    never fills a gap with a plausible value, and this object carries no
    default, estimate or placeholder -- just the domain and what is
    needed.
    """

    domain: str
    needed: tuple[str, ...]
    why: str


@dataclass(frozen=True)
class AgentRequest:
    """One agent run's input."""

    product_name: str
    query: str
    goal: str = "Assess whether this product is worth deeper investigation."
    learning_mode: bool = False
    budget: Budget = field(default_factory=Budget)

    def __post_init__(self) -> None:
        if not self.product_name or not self.product_name.strip():
            raise ValueError("product_name must not be empty")
        if not self.query or not self.query.strip():
            raise ValueError("query must not be empty")


@dataclass(frozen=True)
class AgentResult:
    """What one agent run produced.

    `analysis` is a composed `OpportunityAnalysisResult` or `None` --
    deliberately not annotated with its type, for the same reason the
    orchestrator does not annotate its own: naming it would require
    importing the pure contract layer, and this package must never be
    able to assemble a result without the composition engine.

    `explanation` is natural language. It is checked against `analysis`
    by `guards.verify_provenance()` before it is ever returned, so a
    number that appears here but not in the analysis fails the run
    rather than reaching a reader.
    """

    request: AgentRequest
    outcome: str
    analysis: object = None
    explanation: str | None = None
    learning_notes: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    evidence_requests: tuple[EvidenceRequest, ...] = ()
    usage: Usage = field(default_factory=Usage)
    unavailable_reason: str | None = None
    notes: tuple[str, ...] = ()

    @property
    def accepted_tool_calls(self) -> tuple[ToolCall, ...]:
        return tuple(c for c in self.tool_calls if c.accepted)

    @property
    def rejected_tool_calls(self) -> tuple[ToolCall, ...]:
        return tuple(c for c in self.tool_calls if not c.accepted)

    @property
    def produced_analysis(self) -> bool:
        return self.analysis is not None
