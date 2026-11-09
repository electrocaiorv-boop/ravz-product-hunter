"""The bounded agent loop (Phase 12B).

One run is: ask the model what to look at, validate and execute the
allowed tool, feed the result back as untrusted data, repeat until the
model stops or a budget stops it, then explain the deterministic
analysis -- with every figure checked against that analysis.

== What the model controls, exactly ==

Which tool to call, with which arguments, in which order, and how many
times within budget. That is all. It never sees a weight, never
receives a scoring formula, and no number it writes becomes a score.

== What stops it ==

The allowlist, the argument validators and the budget tracker, all in
code. The prompt asks for good behaviour; these enforce it.
"""

from dataclasses import replace

from src.agent.budget import BudgetExceeded, BudgetTracker
from src.agent.contracts import (
    OUTCOME_BUDGET_EXHAUSTED,
    OUTCOME_COMPLETED,
    OUTCOME_UNAVAILABLE,
    REJECT_BUDGET,
    AgentRequest,
    AgentResult,
    EvidenceRequest,
    ToolCall,
)
from src.agent.explain import (
    deterministic_explanation,
    learning_notes,
    summarize_for_model,
)
from src.agent.guards import (
    ProvenanceError,
    UNTRUSTED_CONTRACT,
    scrub,
    verify_provenance,
    wrap_untrusted,
)
from src.agent.tools import (
    TOOL_SCHEMAS,
    EvidenceCache,
    ToolContext,
    ToolError,
    dispatch,
)

SYSTEM_PROMPT = f"""\
You are a product-research assistant for RAVZ Product Hunter, a system \
that evaluates ecommerce opportunities on Mercado Livre Brazil.

YOUR ROLE IS NARROW AND IT MATTERS THAT YOU KEEP TO IT.

You decide WHAT EVIDENCE TO LOOK AT. Deterministic engines decide WHAT \
IT MEANS. Those engines already exist and are the only source of any \
number in this system.

You MUST NOT:
- calculate, estimate, adjust, re-weight or invert any score
- state a score, percentage or figure that a tool did not return to you
- invent evidence: no prices, costs, suppliers, sales volumes, review \
counts, margins or marketplace metrics
- substitute a value for missing evidence, not even a neutral or \
"safe" one
- claim a product will sell. A score is never a probability of selling
- a score is never a conversion rate and never an expected return

You MUST:
- call `run_full_analysis` to obtain any score
- call `declare_missing_evidence` when a domain's evidence is absent, \
instead of guessing it
- report missing evidence plainly, as missing

{UNTRUSTED_CONTRACT}

Work efficiently: you have a small, fixed budget of tool calls and \
turns. Prefer one full analysis over many partial fetches unless you \
have a reason to screen first. Repeating an identical call returns the \
cached result and still consumes budget.

When you have what you need, write a short, factual explanation of the \
analysis for a careful reader. Quote only figures the tools gave you.\
"""


def run_agent(
    request: AgentRequest,
    *,
    llm_client=None,
    trend_fetcher=None,
    marketplace_searcher=None,
    time_source=None,
) -> AgentResult:
    """Run one bounded agent research task.

    `llm_client` must expose
    `complete(*, system, messages, tools) -> {text, tool_calls,
    input_tokens, output_tokens}`. Injecting it keeps the whole loop
    testable offline; passing `None` resolves the real client at call
    time, and reports UNAVAILABLE if the SDK or key is missing.
    """
    if llm_client is None:
        llm_client, unavailable = _resolve_client()
        if llm_client is None:
            return _unavailable(request, unavailable)

    # Scrub the request BEFORE it is stored on the result.
    #
    # `product_name` and `query` are free text typed by a user, and a
    # user can paste anything into them -- including a token. The
    # original object would otherwise be echoed back through
    # `AgentResult.request`, and through `repr(result)`, which the
    # database phase will persist. Scrubbing a copy keeps the contract
    # layer pure: it must not import these guards.
    request = replace(
        request,
        product_name=scrub(request.product_name),
        query=scrub(request.query),
        goal=scrub(request.goal),
    )

    model_name = getattr(llm_client, "model", "unknown")
    tracker_kwargs = {} if time_source is None else {"time_source": time_source}
    tracker = BudgetTracker(request.budget, model=model_name, **tracker_kwargs)

    context = ToolContext(
        product_name=request.product_name,
        cache=EvidenceCache(),
        trend_fetcher=trend_fetcher,
        marketplace_searcher=marketplace_searcher,
    )

    messages = [{
        "role": "user",
        "content": (
            f"Candidate product: {scrub(request.product_name)}\n"
            f"Search query: {scrub(request.query)}\n"
            f"Goal: {scrub(request.goal)}\n\n"
            f"Budget: {request.budget.max_tool_calls} tool calls, "
            f"{request.budget.max_llm_turns} turns."
        ),
    }]

    calls: list[ToolCall] = []
    notes: list[str] = []
    analysis = None
    model_text = ""
    outcome = OUTCOME_COMPLETED
    budget_note = None

    while True:
        try:
            tracker.check_llm_turn()
        except BudgetExceeded as exc:
            outcome = OUTCOME_BUDGET_EXHAUSTED
            budget_note = exc
            break

        try:
            response = llm_client.complete(
                system=SYSTEM_PROMPT, messages=messages, tools=list(TOOL_SCHEMAS))
        except Exception as exc:
            # A provider failure is explicit unavailability, never a
            # fabricated result. The type is reported, not the message.
            return _unavailable(
                request,
                f"the language model call failed ({type(exc).__name__}); "
                "no analysis was produced",
                tool_calls=tuple(calls),
                usage=tracker.usage,
            )

        tracker.record_llm_turn(
            int(response.get("input_tokens") or 0),
            int(response.get("output_tokens") or 0),
        )

        text = (response.get("text") or "").strip()
        if text:
            model_text = text
        requested = response.get("tool_calls") or []

        if not requested:
            break

        messages.append({"role": "assistant",
                         "content": response.get("raw_assistant_content")
                         or _assistant_echo(text, requested)})

        results_for_model = []
        stop_for_budget = None

        for call in requested:
            name = call.get("name")
            arguments = call.get("arguments")

            try:
                tracker.check_tool_call()
            except BudgetExceeded as exc:
                calls.append(ToolCall(
                    name=str(name), arguments=_safe_args(arguments),
                    accepted=False, rejected_reason=REJECT_BUDGET,
                    detail=str(exc)))
                stop_for_budget = exc
                break

            try:
                payload, reused = dispatch(name, arguments, context)
            except ToolError as exc:
                # Rejections are recorded, surfaced to the model as a
                # plain error, and never widen what is permitted.
                calls.append(ToolCall(
                    name=str(name), arguments=_safe_args(arguments),
                    accepted=False, rejected_reason=exc.reason,
                    detail=exc.detail))
                tracker.record_tool_call()
                results_for_model.append(
                    f"tool '{name}' was REJECTED ({exc.reason}): "
                    f"{exc.detail}. The allowlist cannot be changed.")
                continue

            tracker.record_tool_call()
            calls.append(ToolCall(
                name=name, arguments=_safe_args(arguments), accepted=True,
                reused_evidence=reused,
                detail="reused cached evidence" if reused else None))

            if "orchestration_result" in payload:
                orchestration = payload["orchestration_result"]
                analysis = orchestration.opportunity
                results_for_model.append(wrap_untrusted(
                    "deterministic analysis (engine output)",
                    summarize_for_model(analysis)))
                for entry in orchestration.unavailable:
                    results_for_model.append(wrap_untrusted(
                        "unavailable evidence", entry))
            else:
                results_for_model.append(
                    wrap_untrusted(f"tool:{name}", _render(payload)))

        if results_for_model:
            messages.append({
                "role": "user",
                "content": "\n\n".join(results_for_model),
            })

        if stop_for_budget is not None:
            outcome = OUTCOME_BUDGET_EXHAUSTED
            budget_note = stop_for_budget
            break

    if budget_note is not None:
        notes.append(
            f"stopped early: {budget_note.limit_name} reached "
            f"({budget_note.detail}). Results are PARTIAL and no missing "
            f"evidence was substituted.")

    explanation, provenance_note = _safe_explanation(model_text, analysis)
    if provenance_note:
        notes.append(provenance_note)

    evidence_requests = tuple(
        EvidenceRequest(domain=domain, needed=needed, why=why)
        for domain, needed, why in context.declared)

    if context.cache.hits:
        notes.append(
            f"{context.cache.hits} duplicate provider call(s) served from "
            f"this run's cache instead of re-fetching")

    notes.append(
        f"token usage observed: {tracker.usage.input_tokens} in / "
        f"{tracker.usage.output_tokens} out over "
        f"{tracker.usage.llm_turns} turn(s); estimated cost "
        f"${tracker.usage.estimated_cost_usd:.4f} USD -- an ESTIMATE from a "
        f"local price table, NOT a billed amount")

    return AgentResult(
        request=request,
        outcome=outcome,
        analysis=analysis,
        explanation=explanation,
        learning_notes=learning_notes(analysis) if request.learning_mode else None,
        tool_calls=tuple(calls),
        evidence_requests=evidence_requests,
        usage=tracker.usage,
        notes=tuple(notes),
    )


# -- helpers ------------------------------------------------------------


def _resolve_client():
    """Resolve the real client at CALL time, never at import time."""
    from src import llm_client as module

    if not module.available():
        return None, module.describe_availability()
    try:
        return module.AnthropicClient(), None
    except module.LLMUnavailable as exc:
        return None, str(exc)


def _unavailable(request, reason, tool_calls=(), usage=None):
    from src.agent.contracts import Usage

    # Scrubbed here too: this path can be reached before the main
    # scrubbing above (no SDK, no key), and it still returns the request.
    request = replace(
        request,
        product_name=scrub(request.product_name),
        query=scrub(request.query),
        goal=scrub(request.goal),
    )
    return AgentResult(
        request=request,
        outcome=OUTCOME_UNAVAILABLE,
        analysis=None,
        explanation=deterministic_explanation(None),
        tool_calls=tool_calls,
        usage=usage or Usage(),
        unavailable_reason=scrub(reason),
        notes=("agent mode did not run; no analysis, score or "
               "recommendation is implied",),
    )


def _safe_explanation(model_text: str, analysis):
    """Return prose only if every figure in it traces to the analysis.

    A model that writes a confident, invented score fails here and its
    prose is replaced wholesale by the deterministic rendering. The
    substitution is reported in the notes rather than hidden -- a reader
    should know the model's text was rejected.
    """
    fallback = deterministic_explanation(analysis)
    if not model_text:
        return fallback, None

    cleaned = scrub(model_text)
    try:
        verify_provenance(cleaned, analysis)
    except ProvenanceError as exc:
        return fallback, (
            "the model's explanation was DISCARDED because it contained "
            f"figures absent from the deterministic analysis "
            f"({sorted(exc.untraceable)}); the explanation below is "
            "generated directly from the engine output")
    return cleaned, None


def _assistant_echo(text: str, tool_calls: list) -> str:
    """Minimal transcript entry for the assistant's turn."""
    names = ", ".join(str(c.get("name")) for c in tool_calls)
    return (text or "") + (f"\n[requested tools: {names}]" if names else "")


def _safe_args(arguments) -> dict:
    """Record arguments without letting a credential into the record."""
    if not isinstance(arguments, dict):
        return {"_raw_type": type(arguments).__name__}
    return {str(k): scrub(str(v))[:200] for k, v in arguments.items()}


def _render(payload: dict) -> str:
    lines = []
    for key, value in payload.items():
        if value is None:
            lines.append(f"{key}: unavailable")
        elif isinstance(value, (list, tuple)):
            lines.append(f"{key}: {len(value)} item(s)")
            for entry in value[:10]:
                lines.append(f"  - {entry}")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines)
