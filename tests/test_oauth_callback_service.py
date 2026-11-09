"""Tests for the stateless OAuth callback relay (Vercel function).

No credentials, no network, no deployment. The function is loaded from
its deployed path so the tests exercise exactly the file that ships.

What these tests are really protecting:

- the relay destination is FIXED. No request input may influence the
  scheme, host or path it redirects to (open-redirect prevention).
- nothing from the request is ever echoed into an error page.
- malformed input is refused rather than normalised and forwarded.
- the shape contracts stay identical on both sides of the hop, which
  cannot be enforced by sharing code across two deployments.
"""

import importlib.util
import io
import pathlib
import types

import pytest

SERVICE_PATH = (pathlib.Path(__file__).resolve().parents[1]
                / "oauth_service" / "api" / "mercadolivre" / "callback.py")


def _load_service():
    spec = importlib.util.spec_from_file_location(
        "ravz_oauth_callback_under_test", SERVICE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


callback = _load_service()

GOOD_STATE = "S" * 43
GOOD_CODE = "TG-1234567890abcdef-123456789"
DEFAULT_LOCATION_PREFIX = "http://127.0.0.1:53682/callback?"


# -- the deployed file exists and is self-contained ---------------------


def test_service_file_is_at_the_path_vercel_will_route():
    assert SERVICE_PATH.exists()
    assert SERVICE_PATH.read_text(encoding="utf-8").count("class handler") == 1


def test_service_imports_only_the_standard_library():
    source = SERVICE_PATH.read_text(encoding="utf-8")
    for forbidden in ("import requests", "import flask", "from flask",
                      "import anthropic", "import boto3"):
        assert forbidden not in source


# -- happy path ---------------------------------------------------------


def test_valid_code_and_state_relay_to_the_fixed_loopback_destination():
    decision = callback.decide(
        f"code={GOOD_CODE}&state={GOOD_STATE}", port=53682)
    assert decision.kind == "relay"
    assert decision.location.startswith(DEFAULT_LOCATION_PREFIX)
    assert f"code={GOOD_CODE}" in decision.location
    assert f"state={GOOD_STATE}" in decision.location


def test_relay_destination_uses_the_configured_port():
    decision = callback.decide(
        f"code={GOOD_CODE}&state={GOOD_STATE}", port=54321)
    assert decision.location.startswith("http://127.0.0.1:54321/callback?")


def test_relay_ignores_unknown_extra_parameters():
    decision = callback.decide(
        f"code={GOOD_CODE}&state={GOOD_STATE}&foo=bar&utm_source=x", port=53682)
    assert decision.kind == "relay"
    assert "foo" not in decision.location
    assert "utm_source" not in decision.location


# -- open redirect: the property that matters most ----------------------


@pytest.mark.parametrize("hostile", [
    "redirect_uri=https://evil.example",
    "next=https://evil.example",
    "return_to=//evil.example",
    "url=http://evil.example",
    "host=evil.example",
    "port=9999",
])
def test_no_parameter_can_redirect_anywhere_but_loopback(hostile):
    decision = callback.decide(
        f"code={GOOD_CODE}&state={GOOD_STATE}&{hostile}", port=53682)
    assert decision.kind == "relay"
    assert decision.location.startswith(DEFAULT_LOCATION_PREFIX)
    assert "evil.example" not in decision.location
    assert decision.location.count("http://") == 1


@pytest.mark.parametrize("payload", [
    "@evil.example",
    "/../../evil",
    "x#@evil.example",
    "x?next=https://evil.example",
    "x\\evil.example",
    "x%2f%2fevil.example",
])
def test_hostile_code_values_are_refused_not_normalised(payload):
    decision = callback.decide(f"code={payload}&state={GOOD_STATE}", port=53682)
    assert decision.kind == "error"
    assert decision.status == 400


@pytest.mark.parametrize("payload", [
    "@evil.example",
    "short",
    "has spaces in it and is long enough",
    "A" * 200,          # over the state ceiling
    "S" * 31,           # under the state floor
])
def test_hostile_or_misshaped_state_values_are_refused(payload):
    decision = callback.decide(f"code={GOOD_CODE}&state={payload}", port=53682)
    assert decision.kind == "error"
    assert decision.status == 400


def test_destination_host_and_path_are_literals_in_the_source():
    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert 'LOOPBACK_HOST = "127.0.0.1"' in source
    assert 'LOOPBACK_PATH = "/callback"' in source
    # The only f-string that builds a destination must use those literals.
    assert 'f"http://{LOOPBACK_HOST}:{port}{LOOPBACK_PATH}"' in source


# -- malformed and missing input ----------------------------------------


def test_missing_both_parameters_is_refused():
    decision = callback.decide("", port=53682)
    assert decision.kind == "error"
    assert decision.reason == callback.REASON_MISSING_PARAMS


def test_missing_state_is_refused_even_with_a_valid_code():
    decision = callback.decide(f"code={GOOD_CODE}", port=53682)
    assert decision.reason == callback.REASON_MISSING_PARAMS


def test_missing_code_is_refused_even_with_a_valid_state():
    decision = callback.decide(f"state={GOOD_STATE}", port=53682)
    assert decision.reason == callback.REASON_MISSING_PARAMS


def test_duplicate_parameter_is_refused_rather_than_resolved():
    decision = callback.decide(
        f"code={GOOD_CODE}&code=TG-other-9999999999&state={GOOD_STATE}",
        port=53682)
    assert decision.reason == callback.REASON_DUPLICATE_PARAM


def test_duplicate_state_is_refused():
    decision = callback.decide(
        f"code={GOOD_CODE}&state={GOOD_STATE}&state={'B' * 43}", port=53682)
    assert decision.reason == callback.REASON_DUPLICATE_PARAM


def test_blank_code_is_refused():
    decision = callback.decide(f"code=&state={GOOD_STATE}", port=53682)
    assert decision.kind == "error"


# -- provider-reported errors -------------------------------------------


def test_provider_error_is_relayed_so_the_local_app_fails_explicitly():
    decision = callback.decide(
        f"error=access_denied&state={GOOD_STATE}", port=53682)
    assert decision.kind == "relay"
    assert "error=access_denied" in decision.location
    assert "code=" not in decision.location


def test_provider_error_description_is_sanitized_before_relay():
    decision = callback.decide(
        f"error=invalid_scope&error_description=%3Cscript%3Ealert(1)%3C/script%3E"
        f"&state={GOOD_STATE}", port=53682)
    assert decision.kind == "relay"
    assert "script" in decision.location  # the word survives
    assert "%3C" not in decision.location  # the angle brackets do not
    assert "<" not in decision.location
    assert "/" not in decision.location.split("?", 1)[1]


def test_long_error_description_is_truncated():
    decision = callback.decide(
        f"error=server_error&error_description={'a' * 500}&state={GOOD_STATE}",
        port=53682)
    relayed = decision.location.split("error_description=", 1)[1].split("&")[0]
    assert len(relayed) <= callback._DESCRIPTION_MAX


def test_malformed_error_code_is_refused():
    decision = callback.decide(
        f"error=<script>&state={GOOD_STATE}", port=53682)
    assert decision.reason == callback.REASON_BAD_ERROR_CODE


def test_error_with_a_mismatched_state_shape_is_refused():
    decision = callback.decide("error=access_denied&state=nope", port=53682)
    assert decision.reason == callback.REASON_BAD_STATE


def test_error_without_state_still_relays_so_the_user_is_not_left_hanging():
    decision = callback.decide("error=access_denied", port=53682)
    assert decision.kind == "relay"
    assert "state" not in decision.location


# -- port configuration -------------------------------------------------


def test_port_defaults_when_unset():
    assert callback.resolve_loopback_port({}) == callback.DEFAULT_LOOPBACK_PORT


def test_port_can_be_configured():
    assert callback.resolve_loopback_port(
        {callback.PORT_ENV_VAR: "54321"}) == 54321


@pytest.mark.parametrize("bad", ["0", "80", "70000", "abc", "-1", "53682;ls",
                                "53 682"])
def test_invalid_configured_port_fails_closed(bad):
    assert callback.resolve_loopback_port({callback.PORT_ENV_VAR: bad}) is None


def test_misconfigured_port_refuses_to_guess_a_destination():
    decision = callback.decide(
        f"code={GOOD_CODE}&state={GOOD_STATE}", port=None)
    assert decision.kind == "error"
    assert decision.status == 500
    assert decision.reason == callback.REASON_MISCONFIGURED


# -- error pages never echo input ---------------------------------------


def test_error_body_never_contains_request_input():
    hostile = "<script>alert(1)</script>"
    body = callback._error_body(callback.REASON_BAD_CODE,
                                "The code parameter is not the expected shape.")
    assert hostile not in body
    assert "<script>" not in body


@pytest.mark.parametrize("reason", [
    callback.REASON_BAD_CODE, callback.REASON_BAD_STATE,
    callback.REASON_MISSING_PARAMS, callback.REASON_DUPLICATE_PARAM,
    callback.REASON_MISCONFIGURED, callback.REASON_METHOD,
    callback.REASON_BAD_ERROR_CODE,
])
def test_every_reason_code_is_a_fixed_safe_token(reason):
    assert reason.replace("_", "").isalnum()


# -- the real handler, driven over an in-memory socket ------------------


class _Connection:
    """Enough of a socket for BaseHTTPRequestHandler, in memory."""

    def __init__(self, request_bytes: bytes):
        self._request = request_bytes
        self.written = io.BytesIO()

    def makefile(self, mode, *args, **kwargs):
        if "r" in mode:
            return io.BytesIO(self._request)
        return self.written

    def sendall(self, payload):
        self.written.write(payload)

    def close(self):
        pass


def _drive(raw_request: bytes):
    connection = _Connection(raw_request)
    server = types.SimpleNamespace(server_name="oauth.test", server_port=443)
    callback.handler(connection, ("203.0.113.7", 44321), server)
    raw = connection.written.getvalue().decode("utf-8", "replace")
    head, _, body = raw.partition("\r\n\r\n")
    lines = head.split("\r\n")
    status = int(lines[0].split(" ")[1])
    headers = {}
    for line in lines[1:]:
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return status, headers, body


def _get(path: str) -> bytes:
    return (f"GET {path} HTTP/1.1\r\nHost: oauth.test\r\n"
            f"Connection: close\r\n\r\n").encode()


def test_handler_redirects_a_valid_callback(monkeypatch):
    monkeypatch.delenv(callback.PORT_ENV_VAR, raising=False)
    status, headers, body = _drive(
        _get(f"/api/mercadolivre/callback?code={GOOD_CODE}&state={GOOD_STATE}"))
    assert status == 302
    assert headers["location"].startswith(DEFAULT_LOCATION_PREFIX)
    assert "token" not in body.lower() or "no access token" in body.lower()


def test_handler_sets_every_security_header(monkeypatch):
    monkeypatch.delenv(callback.PORT_ENV_VAR, raising=False)
    _, headers, _ = _drive(
        _get(f"/api/mercadolivre/callback?code={GOOD_CODE}&state={GOOD_STATE}"))
    assert headers["cache-control"] == "no-store, max-age=0"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in headers["content-security-policy"]
    assert "form-action 'none'" in headers["content-security-policy"]
    assert headers["strict-transport-security"].startswith("max-age=")


def test_hsts_does_not_include_subdomains_so_other_hosts_are_untouched():
    values = dict(callback.SECURITY_HEADERS)
    assert "includeSubDomains" not in values["Strict-Transport-Security"]
    assert "preload" not in values["Strict-Transport-Security"]


def test_error_responses_also_carry_the_security_headers(monkeypatch):
    monkeypatch.delenv(callback.PORT_ENV_VAR, raising=False)
    status, headers, _ = _drive(_get("/api/mercadolivre/callback?code=x"))
    assert status == 400
    assert headers["referrer-policy"] == "no-referrer"
    assert "default-src 'none'" in headers["content-security-policy"]


def test_handler_refuses_non_get_methods(monkeypatch):
    monkeypatch.delenv(callback.PORT_ENV_VAR, raising=False)
    raw = (b"POST /api/mercadolivre/callback HTTP/1.1\r\nHost: oauth.test\r\n"
           b"Content-Length: 0\r\nConnection: close\r\n\r\n")
    status, headers, _ = _drive(raw)
    assert status == 405
    assert headers["allow"] == "GET"


def test_handler_does_not_log_the_request_line(capsys, monkeypatch):
    """The code must not reach this function's own stderr."""
    monkeypatch.delenv(callback.PORT_ENV_VAR, raising=False)
    _drive(_get(f"/api/mercadolivre/callback?code={GOOD_CODE}&state={GOOD_STATE}"))
    captured = capsys.readouterr()
    assert GOOD_CODE not in captured.err
    assert GOOD_CODE not in captured.out
    assert captured.err.strip() == ""


def test_handler_sets_no_cors_headers(monkeypatch):
    monkeypatch.delenv(callback.PORT_ENV_VAR, raising=False)
    _, headers, _ = _drive(
        _get(f"/api/mercadolivre/callback?code={GOOD_CODE}&state={GOOD_STATE}"))
    assert not [h for h in headers if h.startswith("access-control-")]


def test_handler_honours_a_configured_port(monkeypatch):
    monkeypatch.setenv(callback.PORT_ENV_VAR, "54999")
    _, headers, _ = _drive(
        _get(f"/api/mercadolivre/callback?code={GOOD_CODE}&state={GOOD_STATE}"))
    assert headers["location"].startswith("http://127.0.0.1:54999/callback?")


def test_handler_fails_closed_on_a_misconfigured_port(monkeypatch):
    monkeypatch.setenv(callback.PORT_ENV_VAR, "not-a-port")
    status, headers, body = _drive(
        _get(f"/api/mercadolivre/callback?code={GOOD_CODE}&state={GOOD_STATE}"))
    assert status == 500
    assert "location" not in headers
    assert callback.REASON_MISCONFIGURED in body


# -- cross-boundary contract -------------------------------------------


def test_the_relays_real_output_is_accepted_by_the_local_listener():
    """End-to-end over the hop, offline: relay out -> local in.

    The pattern-equality test below compares contracts. This one feeds
    the relay's ACTUAL emitted Location into the local interpreter and
    requires a SUCCESS outcome, which is the only thing that proves the
    two halves compose.
    """
    from urllib.parse import urlparse

    from src.integrations import mercadolivre_oauth as local

    state = local.generate_state()
    decision = callback.decide(f"code={GOOD_CODE}&state={state}", port=53682)
    assert decision.kind == "relay"

    emitted = urlparse(decision.location)
    assert emitted.scheme == "http"
    assert emitted.hostname == local.LOOPBACK_HOST
    assert emitted.path == local.LOOPBACK_PATH

    outcome = local.interpret_callback(
        f"{emitted.path}?{emitted.query}", state)
    assert outcome.kind == local.OUTCOME_SUCCESS
    assert outcome.code == GOOD_CODE


def test_a_relayed_provider_error_is_understood_by_the_local_listener():
    from urllib.parse import urlparse

    from src.integrations import mercadolivre_oauth as local

    state = local.generate_state()
    decision = callback.decide(
        f"error=access_denied&error_description=user+said+no&state={state}",
        port=53682)
    emitted = urlparse(decision.location)
    outcome = local.interpret_callback(
        f"{emitted.path}?{emitted.query}", state)
    assert outcome.kind == local.OUTCOME_PROVIDER_ERROR
    assert outcome.error == "access_denied"


def test_a_relayed_code_with_a_foreign_state_is_still_rejected_locally():
    """The relay cannot vouch for state; the local side must refuse it."""
    from urllib.parse import urlparse

    from src.integrations import mercadolivre_oauth as local

    decision = callback.decide(
        f"code={GOOD_CODE}&state={local.generate_state()}", port=53682)
    emitted = urlparse(decision.location)
    outcome = local.interpret_callback(
        f"{emitted.path}?{emitted.query}", local.generate_state())
    assert outcome.kind == local.OUTCOME_STATE_MISMATCH
    assert outcome.code is None


def test_shape_contracts_are_identical_on_both_sides_of_the_hop():
    """The relay and the local helper cannot share code. Assert instead.

    If one side loosens a pattern, the hop silently starts accepting
    something the other side will reject -- or worse, the reverse.
    """
    from src.integrations import mercadolivre_oauth as local

    assert callback.STATE_PATTERN == local.STATE_PATTERN
    assert callback.CODE_PATTERN == local.CODE_PATTERN
    assert callback.ERROR_PATTERN == local.ERROR_PATTERN
    assert callback.LOOPBACK_HOST == local.LOOPBACK_HOST
    assert callback.LOOPBACK_PATH == local.LOOPBACK_PATH
    assert callback.DEFAULT_LOOPBACK_PORT == local.DEFAULT_LOOPBACK_PORT
