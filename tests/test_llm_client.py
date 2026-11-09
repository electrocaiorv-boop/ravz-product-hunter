"""Tests for the optional Anthropic client (Phase 12B).

**No live paid API call is made or authorized.** The SDK is simulated
with a module matching its documented response shape, which is enough to
verify request parameters, tool-use parsing, usage tracking and failure
containment. What it cannot verify is that the real service accepts
those parameters -- see the Reality Check in the release report.
"""

import sys
import traceback
import types

import pytest

import src.llm_client as llm_client

FIXTURE_VALUE = "not-a-credential-fixture-value"


class _FakeAnthropicError(Exception):
    pass


def install_fake_sdk(monkeypatch, response=None, raises=None):
    """Install a fake `anthropic` module and return the captured kwargs."""
    captured = {}

    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            if raises is not None:
                raise raises
            return response

    class Anthropic:
        def __init__(self, *args, **kwargs):
            self.messages = Messages()

    module = types.ModuleType("anthropic")
    module.Anthropic = Anthropic
    module.AnthropicError = _FakeAnthropicError
    monkeypatch.setitem(sys.modules, "anthropic", module)
    monkeypatch.setenv(llm_client.API_KEY_ENV_VAR, FIXTURE_VALUE)
    return captured


def documented_response(text="Looking at trends.", tool_name="fetch_trend_evidence"):
    block = types.SimpleNamespace
    return block(
        content=[
            block(type="text", text=text),
            block(type="tool_use", id="tu_1", name=tool_name,
                  input={"query": "fone"}),
        ],
        usage=block(input_tokens=1234, output_tokens=56),
        stop_reason="tool_use",
    )


# -- availability and optionality ---------------------------------------


def test_sdk_is_optional_and_absence_is_reported_not_raised(monkeypatch):
    monkeypatch.setitem(sys.modules, "anthropic", None)
    monkeypatch.setattr(llm_client, "sdk_installed", lambda: False)

    assert llm_client.available() is False
    status = llm_client.describe_availability()
    assert "UNAVAILABLE" in status
    assert "pip install anthropic" in status
    assert "options 1-11" in status


def test_missing_key_is_reported_without_the_value(monkeypatch):
    monkeypatch.setattr(llm_client, "sdk_installed", lambda: True)
    monkeypatch.delenv(llm_client.API_KEY_ENV_VAR, raising=False)

    assert llm_client.api_key_configured() is False
    status = llm_client.describe_availability()
    assert llm_client.API_KEY_ENV_VAR in status
    assert "UNAVAILABLE" in status


def test_configured_key_is_never_echoed(monkeypatch):
    monkeypatch.setenv(llm_client.API_KEY_ENV_VAR, FIXTURE_VALUE)
    monkeypatch.setattr(llm_client, "sdk_installed", lambda: True)
    assert FIXTURE_VALUE not in llm_client.describe_availability()


def test_constructing_without_sdk_or_key_raises_unavailable(monkeypatch):
    monkeypatch.setattr(llm_client, "sdk_installed", lambda: False)
    with pytest.raises(llm_client.LLMUnavailable):
        llm_client.AnthropicClient()

    monkeypatch.setattr(llm_client, "sdk_installed", lambda: True)
    monkeypatch.setattr(llm_client, "api_key_configured", lambda: False)
    with pytest.raises(llm_client.LLMUnavailable):
        llm_client.AnthropicClient()


def test_the_api_key_is_never_passed_through_this_module(monkeypatch):
    """The SDK reads the env var itself; we must not handle the value."""
    import inspect

    source = inspect.getsource(llm_client)
    # The key is only ever read for a boolean check, never forwarded.
    assert "api_key=" not in source
    assert "Anthropic()" in source


# -- request parameters -------------------------------------------------


def test_request_parameters_match_the_documented_contract(monkeypatch):
    captured = install_fake_sdk(monkeypatch, response=documented_response())

    client = llm_client.AnthropicClient()
    client.complete(system="SYS", messages=[{"role": "user", "content": "hi"}],
                    tools=[{"name": "fetch_trend_evidence"}])

    assert captured["model"] == llm_client.DEFAULT_MODEL
    assert captured["max_tokens"] == llm_client.DEFAULT_MAX_OUTPUT_TOKENS
    assert captured["system"] == "SYS"
    assert captured["messages"] == [{"role": "user", "content": "hi"}]
    assert captured["tools"] == [{"name": "fetch_trend_evidence"}]
    # No unexpected parameters are sent.
    assert set(captured) == {"model", "max_tokens", "system", "messages",
                             "tools"}


def test_model_and_output_cap_are_configurable(monkeypatch):
    captured = install_fake_sdk(monkeypatch, response=documented_response())

    client = llm_client.AnthropicClient(model="claude-haiku-4-5-20251001",
                                        max_output_tokens=256)
    client.complete(system="s", messages=[], tools=[])

    assert captured["model"] == "claude-haiku-4-5-20251001"
    assert captured["max_tokens"] == 256


def test_the_default_model_is_a_documented_id():
    """Guards against a typo or an invented model name.

    Checked against the documented Claude model IDs rather than by
    calling the service, since no live call is authorized.
    """
    documented = {
        "claude-opus-5", "claude-sonnet-5", "claude-fable-5",
        "claude-haiku-4-5-20251001",
    }
    assert llm_client.DEFAULT_MODEL in documented
    # And it must be priced, or cost estimates silently use the fallback.
    from src.agent.budget import PRICE_PER_MTOK_INPUT, PRICE_PER_MTOK_OUTPUT

    assert llm_client.DEFAULT_MODEL in PRICE_PER_MTOK_INPUT
    assert llm_client.DEFAULT_MODEL in PRICE_PER_MTOK_OUTPUT


# -- response handling --------------------------------------------------


def test_tool_use_and_text_blocks_are_parsed(monkeypatch):
    install_fake_sdk(monkeypatch, response=documented_response())

    result = llm_client.AnthropicClient().complete(
        system="s", messages=[], tools=[])

    assert result["text"] == "Looking at trends."
    assert result["tool_calls"] == [{
        "id": "tu_1", "name": "fetch_trend_evidence",
        "arguments": {"query": "fone"}}]
    assert result["raw_stop_reason"] == "tool_use"


def test_usage_is_tracked_from_the_provider_response(monkeypatch):
    install_fake_sdk(monkeypatch, response=documented_response())

    result = llm_client.AnthropicClient().complete(
        system="s", messages=[], tools=[])

    assert result["input_tokens"] == 1234
    assert result["output_tokens"] == 56


def test_missing_usage_is_treated_as_zero_not_guessed(monkeypatch):
    """An absent count must not become an invented one."""
    block = types.SimpleNamespace
    install_fake_sdk(monkeypatch, response=block(
        content=[block(type="text", text="hi")], usage=None,
        stop_reason="end_turn"))

    result = llm_client.AnthropicClient().complete(
        system="s", messages=[], tools=[])
    assert result["input_tokens"] == 0
    assert result["output_tokens"] == 0


def test_unknown_block_types_are_ignored_not_misread(monkeypatch):
    block = types.SimpleNamespace
    install_fake_sdk(monkeypatch, response=block(
        content=[block(type="thinking", thinking="..."),
                 block(type="text", text="visible")],
        usage=block(input_tokens=1, output_tokens=1), stop_reason="end_turn"))

    result = llm_client.AnthropicClient().complete(
        system="s", messages=[], tools=[])
    assert result["text"] == "visible"
    assert result["tool_calls"] == []


# -- failure containment ------------------------------------------------


@pytest.mark.parametrize("exc", [
    _FakeAnthropicError(f"Bearer {FIXTURE_VALUE} rejected"),
    TypeError(f"unexpected keyword; Bearer {FIXTURE_VALUE}"),
    RuntimeError(f"Bearer {FIXTURE_VALUE}"),
    ValueError(FIXTURE_VALUE),
])
def test_provider_failures_leak_nothing_through_any_surface(monkeypatch, exc):
    """Message withheld AND chain severed, for ANY exception type.

    `except anthropic.AnthropicError` alone was not enough: a changed
    SDK signature raises TypeError, which previously escaped this method
    with the credential still in its message. And `from None` was not
    enough either -- it clears `__cause__` but leaves `__context__`
    readable by any chain-walking log formatter.
    """
    install_fake_sdk(monkeypatch, raises=exc)

    client = llm_client.AnthropicClient()
    with pytest.raises(llm_client.LLMUnavailable) as excinfo:
        client.complete(system="s", messages=[], tools=[])

    error = excinfo.value
    assert FIXTURE_VALUE not in str(error)
    assert "Bearer" not in str(error)
    # The chain is severed in both directions.
    assert error.__cause__ is None
    assert error.__context__ is None
    # And a formatted traceback carries nothing.
    formatted = "".join(traceback.format_exception(
        type(error), error, error.__traceback__))
    assert FIXTURE_VALUE not in formatted
    # Still diagnosable: the failure type is named.
    assert type(exc).__name__ in str(error)


def test_a_failure_never_returns_a_fabricated_response(monkeypatch):
    install_fake_sdk(monkeypatch, raises=_FakeAnthropicError("boom"))

    with pytest.raises(llm_client.LLMUnavailable):
        llm_client.AnthropicClient().complete(system="s", messages=[], tools=[])
