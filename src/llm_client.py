"""Optional Anthropic client for the Phase 12B agent.

== Why this integration exists (CLAUDE.md External Integrations) ==

1. Why needed: Phase 12B's agent chooses which research tools to call
   and explains deterministic results in natural language. Both require
   a language model. No score comes from it.
2. What data it provides: tool-selection decisions and prose. It never
   provides evidence, never a number that becomes a score.
3. Authentication: `ANTHROPIC_API_KEY` from the environment only, via
   `.env` (git-ignored). Never hardcoded, never logged, never in a
   prompt or report.
4. Cost implications: billed per token. The agent enforces token, turn
   and estimated-cost budgets (`src/agent/budget.py`). Estimates use a
   local price table and are NOT billed amounts.
5. Rate limits: per-account and per-model, set by Anthropic. The agent
   makes at most `Budget.max_llm_turns` calls per run and does not
   retry, so one run cannot fan out.

== Optional by design ==

The SDK is NOT in `requirements.txt`. Every deterministic feature works
without it, and the whole test suite passes with neither the package nor
a key installed. When either is absent, agent mode reports itself
UNAVAILABLE with a specific reason -- it never degrades into a fake
success or a fabricated analysis.

Install only if you want agent mode:

    pip install anthropic
"""

import os

API_KEY_ENV_VAR = "ANTHROPIC_API_KEY"

# A documented, currently-available model. Overridable per run so a
# cheaper or newer model can be selected without touching code.
DEFAULT_MODEL = "claude-sonnet-5"

# Caps on one request. Separate from Budget: these bound a single call,
# Budget bounds the whole run.
DEFAULT_MAX_OUTPUT_TOKENS = 2_000

import src.config  # noqa: E402,F401  -- side effect: loads .env


class LLMUnavailable(Exception):
    """The model cannot be used, with a specific, non-sensitive reason."""


def sdk_installed() -> bool:
    """True if the optional `anthropic` package is importable."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return True


def api_key_configured() -> bool:
    """True if a key is set. Never reveals or returns the value."""
    value = os.environ.get(API_KEY_ENV_VAR)
    return bool(value and value.strip())


def describe_availability() -> str:
    """Human-readable status. Never includes the key's value."""
    if not sdk_installed():
        return (
            "Agent mode UNAVAILABLE: the optional 'anthropic' package is "
            "not installed. Install it with `pip install anthropic`. All "
            "deterministic analysis (options 1-11) works without it."
        )
    if not api_key_configured():
        return (
            f"Agent mode UNAVAILABLE: {API_KEY_ENV_VAR} is not configured. "
            f"Add it to .env (git-ignored). All deterministic analysis "
            f"(options 1-11) works without it."
        )
    return "Agent mode available: anthropic SDK installed, API key configured."


def available() -> bool:
    return sdk_installed() and api_key_configured()


class AnthropicClient:
    """Thin wrapper exposing exactly what the runner needs.

    Deliberately minimal: one method, returning a normalized shape. The
    runner is written against that shape, so the offline fake in the
    tests is a few lines rather than an SDK mock.
    """

    def __init__(self, model: str = DEFAULT_MODEL,
                 max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS):
        if not sdk_installed():
            raise LLMUnavailable(describe_availability())
        if not api_key_configured():
            raise LLMUnavailable(describe_availability())
        import anthropic

        self.model = model
        self._max_output_tokens = max_output_tokens
        # The SDK reads ANTHROPIC_API_KEY itself; the value is never
        # passed through this module's own code or error text.
        self._client = anthropic.Anthropic()

    def complete(self, *, system: str, messages: list, tools: list) -> dict:
        """One turn. Returns `{text, tool_calls, input_tokens, output_tokens}`."""
        # Translated here, raised AFTER the except block. Same rule and
        # same reasoning as the two HTTP integrations:
        #
        # - The exception's MESSAGE is withheld, because provider errors
        #   can quote request content including headers.
        # - The exception is NOT chained. `from None` is insufficient:
        #   it clears `__cause__` but leaves `__context__` holding the
        #   original, which `traceback.format_exception()` does not print
        #   but any chain-walking log formatter can still read. Only
        #   raising outside the handler leaves nothing reachable.
        #
        # `Exception` is caught, not just `anthropic.AnthropicError`: a
        # changed SDK signature raises TypeError, and that message
        # embedded the request too. Verified -- it previously escaped
        # this method with a credential in it.
        failure = None

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self._max_output_tokens,
                system=system,
                messages=messages,
                tools=tools,
            )
        except Exception as exc:
            failure = type(exc).__name__

        if failure is not None:
            raise LLMUnavailable(
                f"Anthropic request failed ({failure}); detail withheld "
                "because provider errors can embed request data"
            )

        text_parts = []
        tool_calls = []
        for block in response.content:
            kind = getattr(block, "type", None)
            if kind == "text":
                text_parts.append(block.text)
            elif kind == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input or {},
                })

        usage = getattr(response, "usage", None)
        return {
            "text": "\n".join(text_parts).strip(),
            "tool_calls": tool_calls,
            "input_tokens": getattr(usage, "input_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or 0,
            "raw_stop_reason": getattr(response, "stop_reason", None),
        }
