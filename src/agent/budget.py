"""Deterministic budget enforcement for one agent run (Phase 12B).

Every limit is checked in code. None is delegated to the prompt. A model
that ignores every instruction in its system prompt still cannot make a
ninth tool call when the budget allows eight.

Wall-clock time appears here and ONLY here. CLAUDE.md forbids clocks in
any analysis or composition layer; this is neither -- it is a resource
guard, and the time it reads never becomes a scoring input.
"""

import time

from src.agent.contracts import Budget, Usage

# Price table for cost ESTIMATION only, in USD per million tokens.
# Observed token counts come from the provider; these rates are a local
# configuration used to estimate spend so a run can be stopped before it
# grows. They are not billing data and will drift from real invoices.
PRICE_PER_MTOK_INPUT = {
    "claude-sonnet-5": 3.00,
    "claude-opus-5": 15.00,
    "claude-haiku-4-5-20251001": 1.00,
}
PRICE_PER_MTOK_OUTPUT = {
    "claude-sonnet-5": 15.00,
    "claude-opus-5": 75.00,
    "claude-haiku-4-5-20251001": 5.00,
}

# Used when a model name is not in the table. Deliberately the HIGHEST
# rate, not an average: an unknown model must over-estimate its cost so
# the budget stops the run early rather than late. Guessing low would
# let an unpriced model spend past the ceiling.
FALLBACK_PRICE_PER_MTOK_INPUT = max(PRICE_PER_MTOK_INPUT.values())
FALLBACK_PRICE_PER_MTOK_OUTPUT = max(PRICE_PER_MTOK_OUTPUT.values())


def estimate_cost_usd(model: str, input_tokens: int,
                      output_tokens: int) -> float:
    """Estimate the cost of one call. NEVER the billed amount.

    Unknown models are priced at the highest known rate so the estimate
    errs toward stopping work, not toward continuing it.
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("token counts must not be negative")
    rate_in = PRICE_PER_MTOK_INPUT.get(model, FALLBACK_PRICE_PER_MTOK_INPUT)
    rate_out = PRICE_PER_MTOK_OUTPUT.get(model, FALLBACK_PRICE_PER_MTOK_OUTPUT)
    return (input_tokens / 1_000_000) * rate_in + (
        output_tokens / 1_000_000) * rate_out


class BudgetExceeded(Exception):
    """A budget limit was reached. Carries which one, for reporting."""

    def __init__(self, limit_name: str, detail: str):
        super().__init__(f"{limit_name}: {detail}")
        self.limit_name = limit_name
        self.detail = detail


class BudgetTracker:
    """Tracks consumption against a `Budget` and refuses to exceed it.

    Call `check_*` BEFORE doing the work and `record_*` after. The
    check/record split matters: a limit must stop a call from happening,
    not merely notice afterwards that it should not have.

    `time_source` is injectable so the wall-clock limit is testable
    without sleeping.
    """

    def __init__(self, budget: Budget, model: str = "unknown",
                 time_source=time.monotonic):
        self._budget = budget
        self._model = model
        self._time = time_source
        self._started_at = self._time()
        self._tool_calls = 0
        self.usage = Usage()

    # -- introspection ---------------------------------------------------

    @property
    def budget(self) -> Budget:
        return self._budget

    @property
    def tool_calls_made(self) -> int:
        return self._tool_calls

    @property
    def elapsed_seconds(self) -> float:
        return self._time() - self._started_at

    def remaining_tool_calls(self) -> int:
        return max(0, self._budget.max_tool_calls - self._tool_calls)

    def remaining_llm_turns(self) -> int:
        return max(0, self._budget.max_llm_turns - self.usage.llm_turns)

    # -- checks (before the work) ----------------------------------------

    def check_time(self) -> None:
        elapsed = self.elapsed_seconds
        if elapsed >= self._budget.max_wall_clock_seconds:
            raise BudgetExceeded(
                "max_wall_clock_seconds",
                f"{elapsed:.1f}s elapsed of "
                f"{self._budget.max_wall_clock_seconds:.1f}s allowed",
            )

    def check_tool_call(self) -> None:
        self.check_time()
        if self._tool_calls >= self._budget.max_tool_calls:
            raise BudgetExceeded(
                "max_tool_calls",
                f"{self._tool_calls} of {self._budget.max_tool_calls} used",
            )

    def check_llm_turn(self) -> None:
        self.check_time()
        if self.usage.llm_turns >= self._budget.max_llm_turns:
            raise BudgetExceeded(
                "max_llm_turns",
                f"{self.usage.llm_turns} of {self._budget.max_llm_turns} used",
            )
        if self.usage.input_tokens >= self._budget.max_input_tokens:
            raise BudgetExceeded(
                "max_input_tokens",
                f"{self.usage.input_tokens} of "
                f"{self._budget.max_input_tokens} used",
            )
        if self.usage.output_tokens >= self._budget.max_output_tokens:
            raise BudgetExceeded(
                "max_output_tokens",
                f"{self.usage.output_tokens} of "
                f"{self._budget.max_output_tokens} used",
            )
        if self.usage.estimated_cost_usd >= self._budget.max_estimated_cost_usd:
            raise BudgetExceeded(
                "max_estimated_cost_usd",
                f"${self.usage.estimated_cost_usd:.4f} estimated of "
                f"${self._budget.max_estimated_cost_usd:.4f} allowed "
                f"(ESTIMATE, not billed cost)",
            )

    # -- records (after the work) ----------------------------------------

    def record_tool_call(self) -> None:
        self._tool_calls += 1

    def record_llm_turn(self, input_tokens: int, output_tokens: int) -> None:
        cost = estimate_cost_usd(self._model, input_tokens, output_tokens)
        self.usage = self.usage.plus(input_tokens, output_tokens, cost)
