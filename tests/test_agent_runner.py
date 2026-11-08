"""Behavioural tests for the Phase 12B agent loop.

Budgets, evidence reuse, missing-evidence handling, determinism and
Learning mode. All offline with a scripted model.
"""

import pytest

from src.agent.budget import (
    FALLBACK_PRICE_PER_MTOK_INPUT,
    BudgetExceeded,
    BudgetTracker,
    estimate_cost_usd,
)
from src.agent.contracts import (
    OUTCOME_BUDGET_EXHAUSTED,
    OUTCOME_COMPLETED,
    REJECT_BUDGET,
    AgentRequest,
    Budget,
    Usage,
)
from src.agent.runner import run_agent
from src.agent.tools import (
    TOOL_DECLARE_MISSING,
    TOOL_FETCH_TREND,
    TOOL_RUN_FULL_ANALYSIS,
    TOOL_SEARCH_MARKETPLACE,
)
from tests.conftest_agent import (
    ScriptedLLM,
    make_marketplace_searcher,
    make_trend_fetcher,
)


def call(name, **arguments):
    return {"id": "x", "name": name, "arguments": arguments}


def run(turns, request=None, **kwargs):
    kwargs.setdefault("trend_fetcher", make_trend_fetcher())
    kwargs.setdefault("marketplace_searcher", make_marketplace_searcher())
    return run_agent(
        request or AgentRequest(product_name="Fone", query="fone bluetooth"),
        llm_client=ScriptedLLM(turns), **kwargs)


FULL_RUN = [
    {"text": "Running the pipeline.",
     "tool_calls": [call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth")]},
    {"text": "Evidence is incomplete, so no recommendation is issued.",
     "tool_calls": []},
]


# -- 1. a complete flow -------------------------------------------------


def test_a_full_run_produces_the_engine_analysis():
    result = run(FULL_RUN)
    assert result.outcome == OUTCOME_COMPLETED
    assert result.produced_analysis
    assert result.analysis.model_version == "integrated-v1"
    assert len(result.accepted_tool_calls) == 1


def test_the_model_may_screen_before_committing():
    """Tool ORDER is the model's choice; that is the whole latitude."""
    result = run([
        {"text": "Screening interest first.",
         "tool_calls": [call(TOOL_FETCH_TREND, query="fone bluetooth")]},
        {"text": "Interest looks real; running the full pipeline.",
         "tool_calls": [call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth")]},
        {"text": "No recommendation yet.", "tool_calls": []},
    ])
    assert [c.name for c in result.accepted_tool_calls] == [
        TOOL_FETCH_TREND, TOOL_RUN_FULL_ANALYSIS]
    assert result.produced_analysis


def test_a_run_with_no_tool_calls_still_returns_cleanly():
    result = run([{"text": "I need nothing.", "tool_calls": []}])
    assert result.outcome == OUTCOME_COMPLETED
    assert result.analysis is None
    assert not result.tool_calls


# -- 2. budgets, enforced in code --------------------------------------


def test_tool_call_budget_stops_further_calls():
    budget = Budget(max_tool_calls=2, max_llm_turns=5)
    request = AgentRequest(product_name="Fone", query="fone bluetooth",
                           budget=budget)
    result = run([
        {"text": "a", "tool_calls": [
            call(TOOL_FETCH_TREND, query="one"),
            call(TOOL_FETCH_TREND, query="two"),
            call(TOOL_FETCH_TREND, query="three"),
        ]},
        {"text": "done", "tool_calls": []},
    ], request=request)

    assert len(result.accepted_tool_calls) == 2
    rejected = [c for c in result.tool_calls
                if c.rejected_reason == REJECT_BUDGET]
    assert len(rejected) == 1
    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED
    assert any("max_tool_calls" in n for n in result.notes)


def test_llm_turn_budget_stops_the_loop():
    budget = Budget(max_llm_turns=2, max_tool_calls=10)
    request = AgentRequest(product_name="Fone", query="q", budget=budget)
    result = run([
        {"text": "a", "tool_calls": [call(TOOL_FETCH_TREND, query="one")]},
        {"text": "b", "tool_calls": [call(TOOL_FETCH_TREND, query="two")]},
        {"text": "c", "tool_calls": [call(TOOL_FETCH_TREND, query="three")]},
    ], request=request)

    assert result.usage.llm_turns == 2
    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED
    assert any("max_llm_turns" in n for n in result.notes)


def test_input_token_budget_stops_the_loop():
    budget = Budget(max_input_tokens=1_000, max_llm_turns=10)
    request = AgentRequest(product_name="Fone", query="q", budget=budget)
    result = run([
        {"text": "a", "tool_calls": [call(TOOL_FETCH_TREND, query="one")],
         "input_tokens": 900, "output_tokens": 10},
        {"text": "b", "tool_calls": [call(TOOL_FETCH_TREND, query="two")],
         "input_tokens": 900, "output_tokens": 10},
        {"text": "c", "tool_calls": []},
    ], request=request)

    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED
    assert any("max_input_tokens" in n for n in result.notes)


def test_output_token_budget_stops_the_loop():
    budget = Budget(max_output_tokens=100, max_llm_turns=10)
    request = AgentRequest(product_name="Fone", query="q", budget=budget)
    result = run([
        {"text": "a", "tool_calls": [call(TOOL_FETCH_TREND, query="one")],
         "input_tokens": 10, "output_tokens": 90},
        {"text": "b", "tool_calls": [call(TOOL_FETCH_TREND, query="two")],
         "input_tokens": 10, "output_tokens": 90},
        {"text": "c", "tool_calls": []},
    ], request=request)

    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED
    assert any("max_output_tokens" in n for n in result.notes)


def test_estimated_cost_budget_stops_the_loop():
    budget = Budget(max_estimated_cost_usd=0.001, max_llm_turns=10)
    request = AgentRequest(product_name="Fone", query="q", budget=budget)
    result = run([
        {"text": "a", "tool_calls": [call(TOOL_FETCH_TREND, query="one")],
         "input_tokens": 50_000, "output_tokens": 1_000},
        {"text": "b", "tool_calls": [call(TOOL_FETCH_TREND, query="two")]},
        {"text": "c", "tool_calls": []},
    ], request=request)

    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED
    assert any("max_estimated_cost_usd" in n for n in result.notes)


def test_wall_clock_budget_stops_the_loop():
    """Tested with an injected clock, so no test ever sleeps."""
    ticks = iter([0.0] + [100.0] * 50)

    budget = Budget(max_wall_clock_seconds=5.0, max_llm_turns=10)
    request = AgentRequest(product_name="Fone", query="q", budget=budget)
    result = run([
        {"text": "a", "tool_calls": [call(TOOL_FETCH_TREND, query="one")]},
        {"text": "b", "tool_calls": []},
    ], request=request, time_source=lambda: next(ticks))

    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED
    assert any("max_wall_clock_seconds" in n for n in result.notes)


def test_a_partial_run_never_substitutes_missing_evidence():
    """Stopping early must not quietly complete the picture."""
    budget = Budget(max_tool_calls=1, max_llm_turns=2)
    request = AgentRequest(product_name="Fone", query="fone bluetooth",
                           budget=budget)
    result = run([
        {"text": "a", "tool_calls": [
            call(TOOL_FETCH_TREND, query="fone bluetooth"),
            call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth"),
        ]},
    ], request=request)

    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED
    # The full analysis never ran, so there is no analysis -- not a
    # partially-invented one.
    assert result.analysis is None
    assert any("PARTIAL" in n for n in result.notes)
    assert any("no missing evidence was substituted" in n
               for n in result.notes)


@pytest.mark.parametrize("kwargs", [
    {"max_tool_calls": 0},
    {"max_llm_turns": 0},
    {"max_input_tokens": 0},
    {"max_output_tokens": 0},
    {"max_estimated_cost_usd": 0},
    {"max_estimated_cost_usd": -1},
    {"max_wall_clock_seconds": 0},
])
def test_invalid_budgets_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Budget(**kwargs)


# -- 3. cost estimation is an estimate ---------------------------------


def test_cost_estimate_is_labelled_an_estimate():
    usage = Usage(input_tokens=1000, output_tokens=100,
                  estimated_cost_usd=0.01)
    assert usage.is_estimate is True


def test_unknown_models_are_priced_at_the_highest_known_rate():
    """An unpriced model must over-estimate, so the budget stops early."""
    unknown = estimate_cost_usd("some-future-model", 1_000_000, 0)
    assert unknown == pytest.approx(FALLBACK_PRICE_PER_MTOK_INPUT)
    known = estimate_cost_usd("claude-haiku-4-5-20251001", 1_000_000, 0)
    assert unknown > known


def test_negative_token_counts_are_rejected():
    with pytest.raises(ValueError):
        estimate_cost_usd("claude-sonnet-5", -1, 0)


def test_the_run_reports_usage_as_an_estimate():
    result = run(FULL_RUN)
    assert any("ESTIMATE" in n and "NOT a billed amount" in n
               for n in result.notes)


def test_budget_checks_happen_before_the_work():
    """A limit must prevent a call, not notice it afterwards."""
    tracker = BudgetTracker(Budget(max_tool_calls=1), model="claude-sonnet-5")
    tracker.check_tool_call()
    tracker.record_tool_call()
    with pytest.raises(BudgetExceeded) as excinfo:
        tracker.check_tool_call()
    assert excinfo.value.limit_name == "max_tool_calls"
    assert tracker.tool_calls_made == 1  # not incremented by the refusal


# -- 4. evidence reuse within one run ----------------------------------


def test_identical_provider_calls_are_served_from_cache():
    seen = []
    result = run([
        {"text": "a", "tool_calls": [call(TOOL_FETCH_TREND, query="fone")]},
        {"text": "b", "tool_calls": [call(TOOL_FETCH_TREND, query="fone")]},
        {"text": "c", "tool_calls": []},
    ], trend_fetcher=make_trend_fetcher(counter=seen))

    assert len(seen) == 1, "provider was called more than once"
    assert len(result.accepted_tool_calls) == 2
    assert result.accepted_tool_calls[1].reused_evidence is True
    assert any("served from this run's cache" in n for n in result.notes)


def test_different_arguments_are_fetched_separately():
    seen = []
    run([
        {"text": "a", "tool_calls": [
            call(TOOL_FETCH_TREND, query="fone"),
            call(TOOL_FETCH_TREND, query="caixa de som"),
        ]},
        {"text": "b", "tool_calls": []},
    ], trend_fetcher=make_trend_fetcher(counter=seen))
    assert len(seen) == 2


def test_a_repeated_full_analysis_reuses_the_whole_pipeline():
    trend_seen, market_seen = [], []
    result = run([
        {"text": "a", "tool_calls": [
            call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth")]},
        {"text": "b", "tool_calls": [
            call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth")]},
        {"text": "c", "tool_calls": []},
    ], trend_fetcher=make_trend_fetcher(counter=trend_seen),
       marketplace_searcher=make_marketplace_searcher(counter=market_seen))

    assert len(trend_seen) == 1
    assert len(market_seen) == 1
    assert result.accepted_tool_calls[1].reused_evidence is True


def test_reuse_still_consumes_tool_call_budget():
    """Otherwise a loop of cached calls would be free and unbounded."""
    budget = Budget(max_tool_calls=2, max_llm_turns=5)
    request = AgentRequest(product_name="Fone", query="q", budget=budget)
    result = run([
        {"text": "a", "tool_calls": [
            call(TOOL_FETCH_TREND, query="same"),
            call(TOOL_FETCH_TREND, query="same"),
            call(TOOL_FETCH_TREND, query="same"),
        ]},
        {"text": "b", "tool_calls": []},
    ], request=request)
    assert len(result.accepted_tool_calls) == 2
    assert result.outcome == OUTCOME_BUDGET_EXHAUSTED


# -- 5. missing evidence is requested, never invented -------------------


def test_declaring_missing_evidence_produces_a_structured_request():
    result = run([
        {"text": "a", "tool_calls": [
            call(TOOL_DECLARE_MISSING, domain="margin",
                 needed=["sale_price", "product_cost"],
                 why="unit economics are unknown")]},
        {"text": "No recommendation without unit economics.",
         "tool_calls": []},
    ])

    assert len(result.evidence_requests) == 1
    ask = result.evidence_requests[0]
    assert ask.domain == "margin"
    assert ask.needed == ("sale_price", "product_cost")
    assert "unknown" in ask.why


def test_declaring_missing_evidence_returns_no_value():
    """The ask must carry no default, estimate or placeholder."""
    from src.agent.tools import EvidenceCache, ToolContext, dispatch

    context = ToolContext(product_name="P", cache=EvidenceCache())
    payload, _ = dispatch(TOOL_DECLARE_MISSING,
                          {"domain": "supplier", "needed": ["moq_units"]},
                          context)
    declared = payload["declared"]
    assert set(declared) == {"domain", "needed", "why"}
    # No value/estimate/default key exists at all.
    for forbidden in ("value", "estimate", "default", "assumed"):
        assert forbidden not in declared


def test_a_failed_provider_becomes_explicit_unavailable_evidence():
    from src.integrations.mercadolivre import MercadoLivreTimeoutError

    def dead(query, limit=10):
        raise MercadoLivreTimeoutError("timed out")

    result = run([
        {"text": "a", "tool_calls": [
            call(TOOL_SEARCH_MARKETPLACE, query="fone")]},
        {"text": "Marketplace evidence is unavailable.", "tool_calls": []},
    ], marketplace_searcher=dead)

    assert result.outcome == OUTCOME_COMPLETED
    assert result.accepted_tool_calls  # the call happened and was handled
    # And the failure did not become an analysis or a score.
    assert result.analysis is None


# -- 6. determinism and Learning mode ----------------------------------


def test_identical_inputs_and_script_produce_identical_output():
    trend = make_trend_fetcher()
    market = make_marketplace_searcher()
    request = AgentRequest(product_name="Fone", query="fone bluetooth")

    first = run_agent(request, llm_client=ScriptedLLM(FULL_RUN),
                      trend_fetcher=trend, marketplace_searcher=market)
    second = run_agent(request, llm_client=ScriptedLLM(FULL_RUN),
                       trend_fetcher=trend, marketplace_searcher=market)

    assert first.analysis.opportunity_score == second.analysis.opportunity_score
    assert first.explanation == second.explanation
    assert first.outcome == second.outcome
    assert [c.name for c in first.tool_calls] == [
        c.name for c in second.tool_calls]


def test_learning_mode_is_optional_and_off_by_default():
    assert run(FULL_RUN).learning_notes is None


def test_learning_mode_explains_the_mechanism_with_traceable_numbers():
    from src.agent.guards import verify_provenance

    request = AgentRequest(product_name="Fone", query="fone bluetooth",
                           learning_mode=True)
    result = run(FULL_RUN, request=request)

    notes = result.learning_notes
    assert notes is not None
    assert "inverted exactly once" in notes
    assert "Coverage is not confidence" in notes
    # Learning mode is held to the same provenance rule as the
    # explanation: every figure must trace to the analysis.
    verify_provenance(notes, result.analysis)


def test_explanation_never_claims_a_probability_of_selling():
    result = run(FULL_RUN)
    lowered = (result.explanation or "").lower()
    for phrase in ("probability of selling", "chance of selling",
                   "guaranteed", "will sell"):
        assert phrase not in lowered


# -- 7. what the budget does and does not guarantee ---------------------


def test_every_limit_is_checked_before_dispatch_not_after():
    """A limit must prevent the next call, with no side effect on refusal."""
    tracker = BudgetTracker(Budget(max_tool_calls=1, max_llm_turns=1),
                            model="claude-sonnet-5")
    tracker.check_tool_call()
    tracker.record_tool_call()
    with pytest.raises(BudgetExceeded):
        tracker.check_tool_call()
    assert tracker.tool_calls_made == 1

    tracker = BudgetTracker(Budget(max_llm_turns=1), model="claude-sonnet-5")
    tracker.check_llm_turn()
    tracker.record_llm_turn(100, 10)
    with pytest.raises(BudgetExceeded):
        tracker.check_llm_turn()
    assert tracker.usage.llm_turns == 1


def test_a_single_call_can_exceed_the_cost_budget():
    """Documents a real limitation rather than implying a ceiling.

    Token usage is only known after a call returns, so one large call
    can carry a run past `max_estimated_cost_usd` in a single step. The
    budget then refuses the NEXT call. `max_estimated_cost_usd=0.50`
    therefore means "stop once ~$0.50 of estimated spend has
    accumulated", NOT "this run cannot be billed more than $0.50".

    This test exists so that claim can never be quietly made.
    """
    tracker = BudgetTracker(
        Budget(max_llm_turns=10, max_input_tokens=1_000,
               max_estimated_cost_usd=0.01),
        model="claude-opus-5")

    tracker.check_llm_turn()                 # nothing consumed yet: allowed
    tracker.record_llm_turn(500_000, 50_000)  # one enormous call

    # The overrun has already happened.
    assert tracker.usage.input_tokens > 1_000
    assert tracker.usage.estimated_cost_usd > 0.01

    # And the next call is refused.
    with pytest.raises(BudgetExceeded):
        tracker.check_llm_turn()


def test_the_budget_contract_does_not_promise_a_spend_ceiling():
    """The docstring must say so, since the number invites the reading."""
    doc = " ".join((Budget.__doc__ or "").split())
    assert "NOT a spend ceiling" in doc
    assert "cannot retroactively shrink" in doc
    assert "account-level billing limits" in doc


def test_estimated_cost_is_never_presented_as_billed():
    result = run(FULL_RUN)
    cost_notes = [n for n in result.notes if "cost" in n.lower()]
    assert cost_notes
    for note in cost_notes:
        assert "ESTIMATE" in note
        assert "NOT a billed amount" in note
    assert result.usage.is_estimate is True


# -- 8. the single-fetch rule holds ACROSS tools, not just within one ---


def test_evidence_is_shared_between_the_full_pipeline_and_single_tools():
    """One provider call per distinct request, whichever tool asks.

    The caches used to be per-tool and independent, so evidence fetched
    inside `run_full_analysis` was invisible to `fetch_trend_evidence`
    and vice versa. Measured before the fix: these four tool calls
    produced TWO trend fetches and TWO marketplace fetches of identical
    evidence -- double cost, double rate-limit exposure, and two samples
    of one market where Phase 12A requires one.
    """
    trend_hits, market_hits = [], []
    result = run([
        {"text": "a", "tool_calls": [
            call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth")]},
        {"text": "b", "tool_calls": [
            call(TOOL_FETCH_TREND, query="fone bluetooth"),
            call(TOOL_SEARCH_MARKETPLACE, query="fone bluetooth"),
        ]},
        {"text": "c", "tool_calls": [
            call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth")]},
        {"text": "d", "tool_calls": []},
    ], trend_fetcher=make_trend_fetcher(counter=trend_hits),
       marketplace_searcher=make_marketplace_searcher(counter=market_hits))

    assert len(trend_hits) == 1, trend_hits
    assert len(market_hits) == 1, market_hits
    assert result.produced_analysis


def test_the_orchestrators_own_fetches_go_through_the_shared_memo():
    """Order must not matter: single tool first, then the pipeline."""
    trend_hits, market_hits = [], []
    run([
        {"text": "a", "tool_calls": [
            call(TOOL_FETCH_TREND, query="fone bluetooth"),
            call(TOOL_SEARCH_MARKETPLACE, query="fone bluetooth"),
        ]},
        {"text": "b", "tool_calls": [
            call(TOOL_RUN_FULL_ANALYSIS, query="fone bluetooth")]},
        {"text": "c", "tool_calls": []},
    ], trend_fetcher=make_trend_fetcher(counter=trend_hits),
       marketplace_searcher=make_marketplace_searcher(counter=market_hits))

    assert len(trend_hits) == 1, trend_hits
    assert len(market_hits) == 1, market_hits


def test_a_provider_failure_is_not_retried_within_one_run():
    """Memoizing the failure prevents a retry yielding partial data.

    CLAUDE.md forbids a silent retry that turns a hard failure into
    partial evidence. The memo stores the failure, so a second ask gets
    the same explicit failure rather than a fresh attempt.
    """
    from src.integrations.mercadolivre import MercadoLivreTimeoutError

    attempts = []

    def flaky(query, limit=10):
        attempts.append(query)
        raise MercadoLivreTimeoutError("timed out")

    run([
        {"text": "a", "tool_calls": [
            call(TOOL_SEARCH_MARKETPLACE, query="fone"),
        ]},
        {"text": "b", "tool_calls": [
            call(TOOL_RUN_FULL_ANALYSIS, query="fone"),
        ]},
        {"text": "c", "tool_calls": []},
    ], marketplace_searcher=flaky)

    assert len(attempts) == 1, attempts


def test_different_queries_are_still_fetched_separately():
    """The memo must not collapse genuinely different requests."""
    trend_hits = []
    run([
        {"text": "a", "tool_calls": [
            call(TOOL_FETCH_TREND, query="fone bluetooth"),
            call(TOOL_FETCH_TREND, query="caixa de som"),
        ]},
        {"text": "b", "tool_calls": []},
    ], trend_fetcher=make_trend_fetcher(counter=trend_hits))
    assert len(trend_hits) == 2
