"""Tests for the local Mercado Livre OAuth helper.

No real credentials, no network, no sockets. `requests.post` is
monkeypatched with fakes, mirroring the style of
`test_mercadolivre_integration.py`.

Every fake secret below starts with "fake-" so it is obvious in a diff
and recognisable as a placeholder by the repository's secret scanner.

The load-bearing properties under test:

- PKCE S256 is derived correctly (checked against the RFC 7636 vector).
- `state` is validated locally, in constant time -- Mercado Livre does
  not validate it, so this is the only check there is.
- a code arriving with the wrong state is discarded UNSPENT.
- a replayed callback cannot overwrite a completed one.
- no token, code or client secret can reach a repr, a log line or an
  exception message.
"""

import json
import pathlib
import sys

import pytest
import requests

from src.integrations.mercadolivre import MercadoLivreError
from src.integrations import mercadolivre_oauth as oauth

FAKE_CLIENT_ID = "1234567890123456"
FAKE_CLIENT_SECRET = "fake-client-secret-value-0001"
FAKE_CODE = "TG-1234567890abcdef-123456789"
FAKE_ACCESS = "fake-access-token-value-0001"
FAKE_REFRESH = "fake-refresh-token-value-0001"
REDIRECT = "https://ravz-ml-oauth.vercel.app/api/mercadolivre/callback"


def _env(**overrides):
    base = {
        oauth.CLIENT_ID_ENV_VAR: FAKE_CLIENT_ID,
        oauth.CLIENT_SECRET_ENV_VAR: FAKE_CLIENT_SECRET,
        oauth.REDIRECT_URI_ENV_VAR: REDIRECT,
    }
    base.update(overrides)
    return base


def _token_payload(**overrides):
    payload = {
        "access_token": FAKE_ACCESS,
        "refresh_token": FAKE_REFRESH,
        "token_type": "Bearer",
        "expires_in": 21600,
        "scope": "read",
        "user_id": 123456789,
    }
    payload.update(overrides)
    return payload


class _Response:
    def __init__(self, status_code=200, payload=None, raises=None):
        self.status_code = status_code
        self._payload = payload
        self._raises = raises

    def json(self):
        if self._raises is not None:
            raise self._raises
        return self._payload


# -- PKCE ---------------------------------------------------------------


def test_code_challenge_matches_the_rfc_7636_test_vector():
    """RFC 7636 Appendix B. If this breaks, PKCE is silently wrong."""
    verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
    assert (oauth.derive_code_challenge(verifier)
            == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")


def test_code_challenge_is_unpadded_base64url():
    challenge = oauth.derive_code_challenge(oauth.generate_code_verifier())
    assert "=" not in challenge
    assert "+" not in challenge
    assert "/" not in challenge
    assert len(challenge) == 43


def test_generated_verifier_is_within_the_rfc_length_range():
    verifier = oauth.generate_code_verifier()
    assert 43 <= len(verifier) <= 128


def test_generated_verifier_uses_only_unreserved_characters():
    verifier = oauth.generate_code_verifier()
    allowed = set(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")
    assert set(verifier) <= allowed


def test_generated_verifiers_are_unique():
    assert len({oauth.generate_code_verifier() for _ in range(50)}) == 50


@pytest.mark.parametrize("bad", ["", "short", "x" * 42, "x" * 129])
def test_derive_rejects_a_verifier_outside_the_legal_range(bad):
    with pytest.raises(ValueError):
        oauth.derive_code_challenge(bad)


def test_verifier_entropy_floor_is_enforced():
    with pytest.raises(ValueError):
        oauth.generate_code_verifier(entropy_bytes=16)


# -- state --------------------------------------------------------------


def test_generated_state_matches_the_shared_shape_contract():
    import re
    assert re.match(oauth.STATE_PATTERN, oauth.generate_state())


def test_generated_states_are_unique():
    assert len({oauth.generate_state() for _ in range(50)}) == 50


def test_verify_state_accepts_the_matching_value():
    state = oauth.generate_state()
    assert oauth.verify_state(state, state) is True


def test_verify_state_rejects_a_different_value():
    assert oauth.verify_state(oauth.generate_state(),
                              oauth.generate_state()) is False


@pytest.mark.parametrize("expected,received", [
    ("", "S" * 43),
    ("S" * 43, ""),
    ("", ""),
    ("short", "short"),
    ("S" * 43, "S" * 42),
    ("S" * 43, "S" * 43 + "!"),
])
def test_verify_state_rejects_misshaped_or_empty_values(expected, received):
    assert oauth.verify_state(expected, received) is False


# -- redirect URI rules ------------------------------------------------


def test_https_relay_uri_is_accepted():
    assert oauth.validate_redirect_uri(REDIRECT) == REDIRECT


@pytest.mark.parametrize("bad", [
    "http://ravz-ml-oauth.vercel.app/api/mercadolivre/callback",
    "https://127.0.0.1/api/mercadolivre/callback",
    "https://localhost/api/mercadolivre/callback",
    "https://ravz-ml-oauth.vercel.app/cb?x=1",
    "https://ravz-ml-oauth.vercel.app/cb#frag",
    "ftp://ravz-ml-oauth.vercel.app/cb",
    "https:///cb",
])
def test_redirect_uri_rules_are_enforced(bad):
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        oauth.validate_redirect_uri(bad)


def test_loopback_rejection_explains_why_the_relay_exists():
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError) as info:
        oauth.validate_redirect_uri("https://127.0.0.1/cb")
    assert "relay" in str(info.value)


# -- authorization URL -------------------------------------------------


def _auth_url(**overrides):
    kwargs = {
        "client_id": FAKE_CLIENT_ID,
        "redirect_uri": REDIRECT,
        "state": oauth.generate_state(),
        "code_challenge": oauth.derive_code_challenge(
            oauth.generate_code_verifier()),
    }
    kwargs.update(overrides)
    return oauth.build_authorization_url(**kwargs)


def test_authorization_url_targets_the_brazilian_auth_host():
    assert _auth_url().startswith("https://auth.mercadolivre.com.br/authorization?")


def test_authorization_url_carries_every_required_parameter():
    from urllib.parse import parse_qs, urlparse
    params = parse_qs(urlparse(_auth_url()).query)
    assert params["response_type"] == ["code"]
    assert params["client_id"] == [FAKE_CLIENT_ID]
    assert params["redirect_uri"] == [REDIRECT]
    assert params["code_challenge_method"] == ["S256"]
    assert len(params["state"][0]) >= 32
    assert len(params["code_challenge"][0]) == 43


def test_authorization_url_never_contains_the_verifier_or_the_secret():
    verifier = oauth.generate_code_verifier()
    url = _auth_url(code_challenge=oauth.derive_code_challenge(verifier))
    assert verifier not in url
    assert FAKE_CLIENT_SECRET not in url


def test_authorization_url_never_offers_the_plain_pkce_method():
    assert "plain" not in _auth_url()
    source = pathlib.Path(oauth.__file__).read_text(encoding="utf-8")
    assert '"S256"' in source
    assert '"plain"' not in source


def test_authorization_url_rejects_a_bad_state():
    with pytest.raises(ValueError):
        _auth_url(state="too-short")


def test_authorization_url_rejects_a_padded_challenge():
    with pytest.raises(ValueError):
        _auth_url(code_challenge="abc=")


def test_authorization_url_revalidates_the_redirect_uri():
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        _auth_url(redirect_uri="http://insecure.example/cb")


def test_unknown_site_id_is_refused():
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        oauth.authorization_host("MLX")


# -- callback interpretation ------------------------------------------


def test_valid_callback_is_accepted():
    state = oauth.generate_state()
    outcome = oauth.interpret_callback(
        f"/callback?code={FAKE_CODE}&state={state}", state)
    assert outcome.kind == oauth.OUTCOME_SUCCESS
    assert outcome.code == FAKE_CODE


def test_callback_to_another_path_is_ignored_not_failed():
    """A favicon probe must not abort an authorization in progress."""
    state = oauth.generate_state()
    outcome = oauth.interpret_callback("/favicon.ico", state)
    assert outcome.kind == oauth.OUTCOME_IGNORE


def test_wrong_state_discards_the_code_unspent():
    outcome = oauth.interpret_callback(
        f"/callback?code={FAKE_CODE}&state={oauth.generate_state()}",
        oauth.generate_state())
    assert outcome.kind == oauth.OUTCOME_STATE_MISMATCH
    assert outcome.code is None


def test_replayed_callback_is_refused():
    state = oauth.generate_state()
    outcome = oauth.interpret_callback(
        f"/callback?code={FAKE_CODE}&state={state}", state,
        already_consumed=True)
    assert outcome.kind == oauth.OUTCOME_REPLAY
    assert outcome.code is None


@pytest.mark.parametrize("query", [
    "",
    f"code={FAKE_CODE}",
    "state=STATE",
    "code=&state=STATE",
    "code=short&state=STATE",
    f"code={FAKE_CODE}&code=TG-other-0000000000&state=STATE",
    f"code=@evil.example&state=STATE",
])
def test_malformed_callbacks_are_refused(query):
    state = oauth.generate_state()
    outcome = oauth.interpret_callback(
        f"/callback?{query.replace('STATE', state)}", state)
    assert outcome.kind in (oauth.OUTCOME_MALFORMED,
                            oauth.OUTCOME_STATE_MISMATCH)
    assert outcome.code is None


def test_provider_error_is_reported_with_its_code():
    state = oauth.generate_state()
    outcome = oauth.interpret_callback(
        f"/callback?error=access_denied&state={state}", state)
    assert outcome.kind == oauth.OUTCOME_PROVIDER_ERROR
    assert outcome.error == "access_denied"


def test_unsolicited_error_with_a_foreign_state_cannot_abort_the_flow():
    outcome = oauth.interpret_callback(
        f"/callback?error=access_denied&state={oauth.generate_state()}",
        oauth.generate_state())
    assert outcome.kind == oauth.OUTCOME_STATE_MISMATCH


def test_malformed_error_code_is_refused():
    state = oauth.generate_state()
    outcome = oauth.interpret_callback(
        f"/callback?error=<script>&state={state}", state)
    assert outcome.kind == oauth.OUTCOME_MALFORMED


def test_callback_outcome_repr_never_exposes_the_code():
    state = oauth.generate_state()
    outcome = oauth.interpret_callback(
        f"/callback?code={FAKE_CODE}&state={state}", state)
    assert FAKE_CODE not in repr(outcome)
    assert "<present>" in repr(outcome)


# -- pasted-URL fallback ----------------------------------------------


def test_pasted_loopback_url_is_accepted():
    state = oauth.generate_state()
    outcome = oauth.extract_callback_from_url(
        f"http://127.0.0.1:53682/callback?code={FAKE_CODE}&state={state}",
        state)
    assert outcome.kind == oauth.OUTCOME_SUCCESS


def test_pasted_url_still_validates_state():
    outcome = oauth.extract_callback_from_url(
        f"http://127.0.0.1:53682/callback?code={FAKE_CODE}"
        f"&state={oauth.generate_state()}", oauth.generate_state())
    assert outcome.kind == oauth.OUTCOME_STATE_MISMATCH


@pytest.mark.parametrize("pasted", [
    "http://evil.example/callback?code=TG-1234567890abcdef-1&state=STATE",
    "file:///etc/passwd",
    "javascript:alert(1)",
])
def test_pasted_url_from_the_wrong_origin_is_refused(pasted):
    state = oauth.generate_state()
    outcome = oauth.extract_callback_from_url(
        pasted.replace("STATE", state), state)
    assert outcome.kind == oauth.OUTCOME_MALFORMED


# -- token exchange ---------------------------------------------------


def test_exchange_sends_the_pkce_verifier_and_the_documented_grant():
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured["url"] = url
        captured["data"] = data
        captured["headers"] = headers
        return _Response(200, _token_payload())

    original = requests.post
    requests.post = fake_post
    try:
        tokens = oauth.exchange_code_for_tokens(
            code=FAKE_CODE, code_verifier="v" * 64, client_id=FAKE_CLIENT_ID,
            client_secret=FAKE_CLIENT_SECRET, redirect_uri=REDIRECT)
    finally:
        requests.post = original

    assert captured["url"] == "https://api.mercadolibre.com/oauth/token"
    assert captured["data"]["grant_type"] == "authorization_code"
    assert captured["data"]["code_verifier"] == "v" * 64
    assert captured["data"]["redirect_uri"] == REDIRECT
    assert captured["headers"]["accept"] == "application/json"
    assert tokens.access_token == FAKE_ACCESS
    assert tokens.refresh_token == FAKE_REFRESH
    assert tokens.expires_in == 21600
    assert tokens.user_id == 123456789


def test_exchange_requires_a_verifier():
    with pytest.raises(ValueError):
        oauth.exchange_code_for_tokens(
            code=FAKE_CODE, code_verifier="", client_id=FAKE_CLIENT_ID,
            client_secret=FAKE_CLIENT_SECRET, redirect_uri=REDIRECT)


def test_exchange_requires_a_code():
    with pytest.raises(ValueError):
        oauth.exchange_code_for_tokens(
            code="", code_verifier="v" * 64, client_id=FAKE_CLIENT_ID,
            client_secret=FAKE_CLIENT_SECRET, redirect_uri=REDIRECT)


def _exchange_with(monkeypatch, response=None, raises=None):
    def fake_post(url, data=None, headers=None, timeout=None):
        if raises is not None:
            raise raises
        return response

    monkeypatch.setattr(oauth.requests, "post", fake_post)
    return oauth.exchange_code_for_tokens(
        code=FAKE_CODE, code_verifier="v" * 64, client_id=FAKE_CLIENT_ID,
        client_secret=FAKE_CLIENT_SECRET, redirect_uri=REDIRECT)


def test_timeout_becomes_an_explicit_oauth_timeout(monkeypatch):
    with pytest.raises(oauth.MercadoLivreOAuthTimeoutError):
        _exchange_with(monkeypatch, raises=requests.Timeout("boom"))


def test_connection_failure_becomes_an_explicit_oauth_connection_error(monkeypatch):
    with pytest.raises(oauth.MercadoLivreOAuthConnectionError):
        _exchange_with(monkeypatch, raises=requests.ConnectionError("boom"))


@pytest.mark.parametrize("status", [400, 401, 403, 429, 500])
def test_non_200_becomes_a_response_error_carrying_the_status(monkeypatch, status):
    with pytest.raises(oauth.MercadoLivreOAuthResponseError) as info:
        _exchange_with(monkeypatch,
                       response=_Response(status, {"error": "invalid_grant"}))
    assert info.value.status_code == status
    assert str(status) in str(info.value)


def test_response_error_includes_only_a_safe_provider_error_code(monkeypatch):
    with pytest.raises(oauth.MercadoLivreOAuthResponseError) as info:
        _exchange_with(monkeypatch,
                       response=_Response(400, {"error": "invalid_grant"}))
    assert "invalid_grant" in str(info.value)


def test_response_error_drops_an_unsafe_provider_error_code(monkeypatch):
    with pytest.raises(oauth.MercadoLivreOAuthResponseError) as info:
        _exchange_with(monkeypatch, response=_Response(
            400, {"error": "<script>alert(1)</script>",
                  "message": FAKE_CLIENT_SECRET}))
    assert "script" not in str(info.value)
    assert FAKE_CLIENT_SECRET not in str(info.value)


def test_response_error_never_echoes_the_body(monkeypatch):
    with pytest.raises(oauth.MercadoLivreOAuthResponseError) as info:
        _exchange_with(monkeypatch, response=_Response(400, {
            "error": "invalid_client",
            "message": f"client_secret {FAKE_CLIENT_SECRET} is wrong",
            "code": FAKE_CODE,
        }))
    rendered = str(info.value)
    assert FAKE_CLIENT_SECRET not in rendered
    assert FAKE_CODE not in rendered
    assert "withheld" in rendered


def test_non_json_response_becomes_a_data_error(monkeypatch):
    with pytest.raises(oauth.MercadoLivreOAuthDataError):
        _exchange_with(monkeypatch,
                       response=_Response(200, raises=ValueError("not json")))


def test_undecodable_token_body_is_not_left_reachable_on_the_chain(monkeypatch):
    """A JSONDecodeError carries the whole body on `.doc` -- the tokens."""
    leaky = json.JSONDecodeError(
        "Expecting value", f'{{"access_token": "{FAKE_ACCESS}"', 0)
    with pytest.raises(oauth.MercadoLivreOAuthDataError) as info:
        _exchange_with(monkeypatch, response=_Response(200, raises=leaky))
    assert info.value.__cause__ is None
    assert info.value.__context__ is None
    assert FAKE_ACCESS not in str(info.value)


def test_corrupt_credential_file_is_not_left_reachable_on_the_chain(tmp_path):
    target = tmp_path / "tokens.json"
    target.write_text(f'{{"refresh_token": "{FAKE_REFRESH}"', encoding="utf-8")
    with pytest.raises(oauth.MercadoLivreOAuthDataError) as info:
        oauth.read_refresh_token(target)
    assert info.value.__cause__ is None
    assert info.value.__context__ is None
    assert FAKE_REFRESH not in str(info.value)


def test_non_object_json_becomes_a_data_error(monkeypatch):
    with pytest.raises(oauth.MercadoLivreOAuthDataError):
        _exchange_with(monkeypatch, response=_Response(200, ["unexpected"]))


def test_missing_access_token_becomes_a_data_error_not_a_blank_token(monkeypatch):
    payload = _token_payload()
    del payload["access_token"]
    with pytest.raises(oauth.MercadoLivreOAuthDataError):
        _exchange_with(monkeypatch, response=_Response(200, payload))


def test_absent_refresh_token_stays_none_rather_than_empty_string(monkeypatch):
    tokens = _exchange_with(
        monkeypatch, response=_Response(200, _token_payload(refresh_token="")))
    assert tokens.refresh_token is None


def test_unexpected_field_types_stay_none_rather_than_being_coerced(monkeypatch):
    tokens = _exchange_with(monkeypatch, response=_Response(
        200, _token_payload(expires_in="six hours", user_id="me")))
    assert tokens.expires_in is None
    assert tokens.user_id is None


def test_transport_failure_message_withholds_detail_and_severs_the_chain(monkeypatch):
    """A requests error can embed the POST body -- secret and code."""
    leaky = requests.RequestException(
        f"POST failed: client_secret={FAKE_CLIENT_SECRET} code={FAKE_CODE}")
    with pytest.raises(oauth.MercadoLivreOAuthError) as info:
        _exchange_with(monkeypatch, raises=leaky)
    rendered = str(info.value)
    assert FAKE_CLIENT_SECRET not in rendered
    assert FAKE_CODE not in rendered
    assert "RequestException" in rendered
    # Neither __cause__ nor __context__ may keep the original reachable.
    assert info.value.__cause__ is None
    assert info.value.__context__ is None


# -- refresh ----------------------------------------------------------


def test_refresh_sends_the_documented_grant(monkeypatch):
    captured = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        captured.update(data)
        return _Response(200, _token_payload(refresh_token="fake-refresh-0002"))

    monkeypatch.setattr(oauth.requests, "post", fake_post)
    tokens = oauth.refresh_access_token(
        refresh_token=FAKE_REFRESH, client_id=FAKE_CLIENT_ID,
        client_secret=FAKE_CLIENT_SECRET)
    assert captured["grant_type"] == "refresh_token"
    assert captured["refresh_token"] == FAKE_REFRESH
    assert "code" not in captured
    assert "code_verifier" not in captured
    # Rotation: the new set must carry the NEW refresh token.
    assert tokens.refresh_token == "fake-refresh-0002"


def test_refresh_requires_a_stored_token():
    with pytest.raises(ValueError):
        oauth.refresh_access_token(
            refresh_token="", client_id=FAKE_CLIENT_ID,
            client_secret=FAKE_CLIENT_SECRET)


# -- TokenSet secret hygiene ------------------------------------------


def _tokens():
    return oauth.TokenSet(
        access_token=FAKE_ACCESS, refresh_token=FAKE_REFRESH,
        token_type="Bearer", expires_in=21600, scope="read",
        user_id=123456789, obtained_at="2026-11-08T12:00:00+00:00")


def test_token_repr_redacts_both_tokens():
    rendered = repr(_tokens())
    assert FAKE_ACCESS not in rendered
    assert FAKE_REFRESH not in rendered
    assert "<redacted>" in rendered


def test_token_str_and_fstring_also_redact():
    tokens = _tokens()
    assert FAKE_ACCESS not in str(tokens)
    assert FAKE_ACCESS not in f"{tokens}"
    assert FAKE_ACCESS not in "{}".format(tokens)


def test_token_describe_reports_configured_without_the_value():
    described = _tokens().describe()
    assert FAKE_ACCESS not in described
    assert FAKE_REFRESH not in described
    assert "configured (value not shown)" in described


def test_describe_distinguishes_a_missing_refresh_token():
    tokens = oauth.TokenSet(
        access_token=FAKE_ACCESS, refresh_token=None, token_type="Bearer",
        expires_in=None, scope=None, user_id=None,
        obtained_at="2026-11-08T12:00:00+00:00")
    assert "NOT returned" in tokens.describe()
    assert "not reported" in tokens.describe()


def test_expires_at_is_derived_from_the_reported_lifetime():
    assert _tokens().expires_at() == "2026-11-08T18:00:00+00:00"


def test_expires_at_is_none_when_the_lifetime_is_unknown():
    tokens = oauth.TokenSet(
        access_token=FAKE_ACCESS, refresh_token=None, token_type=None,
        expires_in=None, scope=None, user_id=None,
        obtained_at="2026-11-08T12:00:00+00:00")
    assert tokens.expires_at() is None


# -- local credential file --------------------------------------------


def test_token_file_is_written_with_the_values_and_not_printed(tmp_path, capsys):
    path = oauth.write_token_file(_tokens(), tmp_path / "sub" / "tokens.json")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["access_token"] == FAKE_ACCESS
    assert document["refresh_token"] == FAKE_REFRESH
    assert document["expires_at"] == "2026-11-08T18:00:00+00:00"
    assert "Never commit" in document["_warning"]
    captured = capsys.readouterr()
    assert FAKE_ACCESS not in captured.out
    assert FAKE_ACCESS not in captured.err


def test_token_file_parent_directory_is_created(tmp_path):
    target = tmp_path / "deeper" / "still" / "tokens.json"
    assert oauth.write_token_file(_tokens(), target).exists()


def test_token_file_overwrites_rather_than_appending(tmp_path):
    target = tmp_path / "tokens.json"
    oauth.write_token_file(_tokens(), target)
    oauth.write_token_file(_tokens(), target)
    assert len(json.loads(target.read_text(encoding="utf-8"))) == 9


@pytest.mark.skipif(sys.platform == "win32",
                    reason="POSIX mode bits are advisory on Windows")
def test_token_file_is_owner_only_on_posix(tmp_path):
    target = oauth.write_token_file(_tokens(), tmp_path / "tokens.json")
    assert oct(target.stat().st_mode)[-3:] == "600"


def test_default_token_path_is_inside_the_git_ignored_directory():
    assert oauth.TOKEN_FILE.parts[0] == ".secrets"


def test_reading_a_missing_token_file_is_a_configuration_error(tmp_path):
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        oauth.read_refresh_token(tmp_path / "absent.json")


def test_reading_a_corrupt_token_file_is_a_data_error(tmp_path):
    target = tmp_path / "tokens.json"
    target.write_text("{not json", encoding="utf-8")
    with pytest.raises(oauth.MercadoLivreOAuthDataError):
        oauth.read_refresh_token(target)


def test_token_file_without_a_refresh_token_is_a_configuration_error(tmp_path):
    target = tmp_path / "tokens.json"
    target.write_text(json.dumps({"access_token": FAKE_ACCESS}),
                      encoding="utf-8")
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        oauth.read_refresh_token(target)


def test_stored_refresh_token_round_trips(tmp_path):
    target = oauth.write_token_file(_tokens(), tmp_path / "tokens.json")
    assert oauth.read_refresh_token(target) == FAKE_REFRESH


# -- configuration ----------------------------------------------------


def test_missing_setting_reports_the_name_and_never_the_value():
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError) as info:
        oauth._require_env(oauth.CLIENT_SECRET_ENV_VAR, {})
    assert oauth.CLIENT_SECRET_ENV_VAR in str(info.value)
    assert ".env" in str(info.value)


def test_blank_setting_counts_as_missing():
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        oauth._require_env(oauth.CLIENT_ID_ENV_VAR,
                           {oauth.CLIENT_ID_ENV_VAR: "   "})


def test_configured_setting_is_returned_but_never_logged(capsys):
    value = oauth._require_env(oauth.CLIENT_SECRET_ENV_VAR,
                               _env()[oauth.CLIENT_SECRET_ENV_VAR]
                               and _env())
    assert value == FAKE_CLIENT_SECRET
    assert FAKE_CLIENT_SECRET not in capsys.readouterr().out


def test_loopback_port_defaults_when_unset():
    assert oauth.resolve_loopback_port({}) == oauth.DEFAULT_LOOPBACK_PORT


def test_loopback_port_can_be_configured():
    assert oauth.resolve_loopback_port(
        {oauth.LOOPBACK_PORT_ENV_VAR: "54321"}) == 54321


@pytest.mark.parametrize("bad", ["0", "80", "70000", "abc", "-1", "5 3"])
def test_invalid_loopback_port_is_a_configuration_error(bad):
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        oauth.resolve_loopback_port({oauth.LOOPBACK_PORT_ENV_VAR: bad})


# -- listener wiring (no real sockets) --------------------------------


class _FakeServer:
    """Stands in for the loopback server; never binds a port."""

    def __init__(self, port, expected_state, outcomes=()):
        self.port = port
        self.expected_state = expected_state
        self.outcome = None
        self.replays = 0
        self.timeout = None
        self.closed = False
        self._outcomes = list(outcomes)

    def handle_request(self):
        if self._outcomes:
            self.outcome = self._outcomes.pop(0)

    def server_close(self):
        self.closed = True


def test_wait_for_callback_returns_the_outcome_and_closes_the_server():
    state = oauth.generate_state()
    expected = oauth.CallbackOutcome(oauth.OUTCOME_SUCCESS, code=FAKE_CODE)
    created = {}

    def factory(port, expected_state):
        server = _FakeServer(port, expected_state, outcomes=[expected])
        created["server"] = server
        return server

    outcome = oauth.wait_for_callback(state, port=53682, timeout_seconds=5,
                                      server_factory=factory)
    assert outcome is expected
    assert created["server"].closed is True


def test_wait_for_callback_times_out_without_sleeping(monkeypatch):
    clock = iter([0.0, 1.0, 2.0, 99.0, 100.0, 101.0])
    monkeypatch.setattr(oauth, "_monotonic", lambda: next(clock))
    with pytest.raises(oauth.MercadoLivreOAuthTimeoutError):
        oauth.wait_for_callback(
            oauth.generate_state(), port=53682, timeout_seconds=5,
            server_factory=lambda port, state: _FakeServer(port, state))


def test_wait_for_callback_closes_the_server_on_timeout(monkeypatch):
    clock = iter([0.0, 100.0])
    monkeypatch.setattr(oauth, "_monotonic", lambda: next(clock))
    created = {}

    def factory(port, expected_state):
        created["server"] = _FakeServer(port, expected_state)
        return created["server"]

    with pytest.raises(oauth.MercadoLivreOAuthTimeoutError):
        oauth.wait_for_callback(oauth.generate_state(), port=53682,
                                timeout_seconds=1, server_factory=factory)
    assert created["server"].closed is True


def test_a_port_already_in_use_fails_loudly_rather_than_sharing():
    """A squatter must not quietly receive the authorization code."""

    def factory(port, expected_state):
        raise OSError(98, "Address already in use")

    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError) as info:
        oauth.wait_for_callback(oauth.generate_state(), port=53682,
                                server_factory=factory)
    assert oauth.LOOPBACK_PORT_ENV_VAR in str(info.value)
    assert info.value.__context__ is None


# -- layering ---------------------------------------------------------


def test_oauth_failures_are_not_mistaken_for_missing_product_evidence():
    """An auth problem must never be absorbed as unavailable evidence."""
    assert not issubclass(oauth.MercadoLivreOAuthError, MercadoLivreError)
    assert not issubclass(MercadoLivreError, oauth.MercadoLivreOAuthError)


def test_helper_does_not_import_any_scoring_or_agent_module():
    source = pathlib.Path(oauth.__file__).read_text(encoding="utf-8")
    for forbidden in ("src.orchestrator", "src.agent", "src.opportunity",
                      "src.scoring", "src.models", "_analysis"):
        assert forbidden not in source


def test_cli_usage_lists_variable_names_only(capsys):
    assert oauth.main([]) == 2
    printed = capsys.readouterr().out
    assert oauth.CLIENT_SECRET_ENV_VAR in printed
    assert FAKE_CLIENT_SECRET not in printed


def test_cli_reports_a_configuration_error_without_a_traceback(monkeypatch, capsys):
    monkeypatch.delenv(oauth.CLIENT_ID_ENV_VAR, raising=False)
    monkeypatch.delenv(oauth.REDIRECT_URI_ENV_VAR, raising=False)
    assert oauth.main(["plan"]) == 1
    printed = capsys.readouterr().out
    assert "MercadoLivreOAuthConfigurationError" in printed
    assert oauth.CLIENT_ID_ENV_VAR in printed


def test_cli_plan_is_offline_and_shows_no_secret(monkeypatch, capsys):
    for name, value in _env().items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(oauth.requests, "post", _unreachable)
    assert oauth.main(["plan"]) == 0
    printed = capsys.readouterr().out
    assert REDIRECT in printed
    assert "http://127.0.0.1:53682/callback" in printed
    assert FAKE_CLIENT_SECRET not in printed
    assert FAKE_CLIENT_ID not in printed
    assert "value not shown" in printed


def _unreachable(*args, **kwargs):
    raise AssertionError("no network call may happen in this test")
