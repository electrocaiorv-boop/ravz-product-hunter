"""Tests for the OAuth -> marketplace-provider credential handoff.

No real credentials, no network. Every fake value starts with "fake-".

The gap being closed: the provider reads one environment variable while
`refresh` writes a new token to the stored credential file. Before this,
the two drifted apart after the first refresh -- the file held a live
token, `.env` held the dead one, and the provider kept sending the dead
one until a human re-copied it.

The properties under test:

- an explicit environment variable still wins (nothing that works today
  stops working);
- a stored, unexpired credential beats a stale `.env` value;
- an expired stored credential defers to `.env` rather than guaranteeing
  a 401;
- a corrupt credential file degrades to "absent" and never raises,
  because raising would escape `search_products()` as something the
  orchestrator does not catch;
- a refresh rotates both tokens and the NEXT authenticated request
  carries the new one, with `.env` untouched;
- no token reaches stdout, a log, an exception or a repr.
"""

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.integrations import mercadolivre, mercadolivre_oauth as oauth

FAKE_ENV_TOKEN = "fake-env-token-0001"
FAKE_DOTENV_TOKEN = "fake-dotenv-token-0002"
FAKE_STORED_TOKEN = "fake-stored-token-0003"
FAKE_ROTATED_TOKEN = "fake-rotated-token-0004"
FAKE_REFRESH_1 = "fake-refresh-first-0001"
FAKE_REFRESH_2 = "fake-refresh-second-0002"

NOW = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
FUTURE = (NOW + timedelta(hours=5)).isoformat()
PAST = (NOW - timedelta(hours=1)).isoformat()


def _write(path, **overrides):
    document = {
        "access_token": FAKE_STORED_TOKEN,
        "refresh_token": FAKE_REFRESH_1,
        "token_type": "Bearer",
        "expires_in": 21600,
        "expires_at": FUTURE,
        "scope": "read",
        "user_id": 123456789,
        "obtained_at": NOW.isoformat(),
    }
    document.update(overrides)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def _resolve(tmp_path, *, env=None, dotenv="", stored=True, now=NOW, **overrides):
    token_path = tmp_path / "tokens.json"
    if stored:
        _write(token_path, **overrides)
    environ = {} if env is None else {oauth.ACCESS_TOKEN_ENV_VAR: env}
    dotenv_file = tmp_path / ".env"
    dotenv_file.write_text(
        f"{oauth.ACCESS_TOKEN_ENV_VAR}={dotenv}\n" if dotenv else "", encoding="utf-8")
    return oauth.resolve_access_token(
        environ=environ, token_path=token_path, dotenv_path=str(dotenv_file),
        now=now)


# -- precedence ---------------------------------------------------------


def test_explicit_environment_variable_wins_over_the_stored_credential(tmp_path):
    """An operator override must never be silently ignored."""
    resolved = _resolve(tmp_path, env=FAKE_ENV_TOKEN)
    assert resolved.token == FAKE_ENV_TOKEN
    assert resolved.source == oauth.TOKEN_SOURCE_ENVIRONMENT


def test_stored_credential_beats_a_stale_dotenv_value(tmp_path):
    """The whole point: a pasted token cannot override a refreshed one."""
    resolved = _resolve(tmp_path, env=FAKE_DOTENV_TOKEN, dotenv=FAKE_DOTENV_TOKEN)
    assert resolved.token == FAKE_STORED_TOKEN
    assert resolved.source == oauth.TOKEN_SOURCE_STORED
    assert resolved.expires_at == FUTURE


def test_dotenv_value_is_used_when_no_credential_file_exists(tmp_path):
    """Preserves the behaviour that existed before the handoff."""
    resolved = _resolve(tmp_path, env=FAKE_DOTENV_TOKEN, dotenv=FAKE_DOTENV_TOKEN,
                        stored=False)
    assert resolved.token == FAKE_DOTENV_TOKEN
    assert resolved.source == oauth.TOKEN_SOURCE_DOTENV


def test_expired_stored_credential_defers_to_dotenv(tmp_path):
    resolved = _resolve(tmp_path, env=FAKE_DOTENV_TOKEN, dotenv=FAKE_DOTENV_TOKEN,
                        expires_at=PAST)
    assert resolved.token == FAKE_DOTENV_TOKEN
    assert resolved.source == oauth.TOKEN_SOURCE_DOTENV
    assert "expired" in resolved.detail


def test_nothing_configured_resolves_to_none_with_a_reason(tmp_path):
    resolved = _resolve(tmp_path, stored=False)
    assert resolved.token is None
    assert resolved.available is False
    assert resolved.source == oauth.TOKEN_SOURCE_NONE
    assert "not configured" in resolved.detail


def test_expired_stored_credential_with_no_fallback_resolves_to_none(tmp_path):
    resolved = _resolve(tmp_path, expires_at=PAST)
    assert resolved.token is None
    assert resolved.source == oauth.TOKEN_SOURCE_NONE


def test_a_token_expiring_within_the_margin_counts_as_expired(tmp_path):
    expiring = (NOW + timedelta(seconds=oauth.EXPIRY_MARGIN_SECONDS - 1)).isoformat()
    resolved = _resolve(tmp_path, expires_at=expiring)
    assert resolved.source == oauth.TOKEN_SOURCE_NONE


def test_a_token_outside_the_margin_is_still_usable(tmp_path):
    expiring = (NOW + timedelta(seconds=oauth.EXPIRY_MARGIN_SECONDS + 60)).isoformat()
    resolved = _resolve(tmp_path, expires_at=expiring)
    assert resolved.source == oauth.TOKEN_SOURCE_STORED


def test_environment_value_matching_dotenv_is_treated_as_dotenv_sourced(tmp_path):
    """src.config injects .env into os.environ, so they must be told apart."""
    resolved = _resolve(tmp_path, env=FAKE_DOTENV_TOKEN, dotenv=FAKE_DOTENV_TOKEN,
                        stored=False)
    assert resolved.source == oauth.TOKEN_SOURCE_DOTENV


def test_blank_environment_value_is_not_treated_as_configured(tmp_path):
    resolved = _resolve(tmp_path, env="   ", stored=False)
    assert resolved.token is None
    assert resolved.source == oauth.TOKEN_SOURCE_NONE


# -- unknown or unusable stored state ----------------------------------


def test_unrecorded_lifetime_is_not_assumed_expired(tmp_path):
    resolved = _resolve(tmp_path, expires_at=None)
    assert resolved.source == oauth.TOKEN_SOURCE_STORED
    assert "not recorded" in resolved.detail


def test_unparseable_lifetime_is_not_assumed_expired(tmp_path):
    resolved = _resolve(tmp_path, expires_at="whenever")
    assert resolved.source == oauth.TOKEN_SOURCE_STORED
    assert "unparseable" in resolved.detail


def test_naive_timestamp_is_read_as_utc(tmp_path):
    resolved = _resolve(tmp_path, expires_at=(NOW + timedelta(hours=5))
                        .replace(tzinfo=None).isoformat())
    assert resolved.source == oauth.TOKEN_SOURCE_STORED


def test_credential_file_without_a_token_counts_as_absent(tmp_path):
    resolved = _resolve(tmp_path, env=FAKE_DOTENV_TOKEN, dotenv=FAKE_DOTENV_TOKEN,
                        access_token="")
    assert resolved.source == oauth.TOKEN_SOURCE_DOTENV
    assert "no access_token" in resolved.detail


def test_corrupt_credential_file_degrades_instead_of_raising(tmp_path):
    """Raising here would escape search_products() as an uncaught crash."""
    token_path = tmp_path / "tokens.json"
    token_path.write_text("{not json", encoding="utf-8")
    resolved = oauth.resolve_access_token(
        environ={}, token_path=token_path, dotenv_path=str(tmp_path / "absent"),
        now=NOW)
    assert resolved.token is None
    assert resolved.source == oauth.TOKEN_SOURCE_NONE


def test_credential_file_holding_a_json_array_counts_as_absent(tmp_path):
    token_path = tmp_path / "tokens.json"
    token_path.write_text("[]", encoding="utf-8")
    resolved = oauth.resolve_access_token(
        environ={}, token_path=token_path, dotenv_path=str(tmp_path / "absent"),
        now=NOW)
    assert resolved.source == oauth.TOKEN_SOURCE_NONE


def test_a_missing_dotenv_file_is_not_an_error(tmp_path):
    resolved = oauth.resolve_access_token(
        environ={oauth.ACCESS_TOKEN_ENV_VAR: FAKE_ENV_TOKEN},
        token_path=tmp_path / "absent.json",
        dotenv_path=str(tmp_path / "no-such-file"), now=NOW)
    assert resolved.source == oauth.TOKEN_SOURCE_ENVIRONMENT


# -- secret hygiene -----------------------------------------------------


def test_resolved_token_repr_and_str_redact_the_value(tmp_path):
    resolved = _resolve(tmp_path)
    for rendered in (repr(resolved), str(resolved), f"{resolved}"):
        assert FAKE_STORED_TOKEN not in rendered
        assert "<redacted>" in rendered


def test_resolved_token_describe_reports_configured_without_the_value(tmp_path):
    described = _resolve(tmp_path).describe()
    assert FAKE_STORED_TOKEN not in described
    assert "configured (value not shown)" in described
    assert oauth.TOKEN_SOURCE_STORED in described


def test_absent_token_describe_says_not_configured(tmp_path):
    described = _resolve(tmp_path, stored=False).describe()
    assert "NOT configured" in described


def test_resolution_prints_nothing(tmp_path, capsys):
    _resolve(tmp_path)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


# -- the provider actually uses it -------------------------------------


def _captured_headers(monkeypatch, query="fone bluetooth"):
    captured = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured.update(headers or {})

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                return {"results": []}

        return _Response()

    monkeypatch.setattr(mercadolivre.requests, "get", fake_get)
    mercadolivre.search_products(query)
    return captured


def test_provider_sends_the_stored_credential(monkeypatch, tmp_path):
    token_path = _write(tmp_path / "tokens.json")
    monkeypatch.setattr(oauth, "TOKEN_FILE", token_path)
    monkeypatch.setattr(oauth, "_dotenv_access_token", lambda path=None: "")
    monkeypatch.delenv(oauth.ACCESS_TOKEN_ENV_VAR, raising=False)

    headers = _captured_headers(monkeypatch)
    assert headers["Authorization"] == f"Bearer {FAKE_STORED_TOKEN}"


def test_provider_prefers_the_stored_credential_over_a_stale_dotenv(monkeypatch,
                                                                    tmp_path):
    """The regression this whole mechanism exists to prevent."""
    token_path = _write(tmp_path / "tokens.json")
    monkeypatch.setattr(oauth, "TOKEN_FILE", token_path)
    # Simulate src.config having injected a stale .env value.
    monkeypatch.setattr(oauth, "_dotenv_access_token",
                        lambda path=None: FAKE_DOTENV_TOKEN)
    monkeypatch.setenv(oauth.ACCESS_TOKEN_ENV_VAR, FAKE_DOTENV_TOKEN)

    headers = _captured_headers(monkeypatch)
    assert headers["Authorization"] == f"Bearer {FAKE_STORED_TOKEN}"
    assert FAKE_DOTENV_TOKEN not in headers["Authorization"]


def test_provider_sends_no_header_when_nothing_is_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(oauth, "TOKEN_FILE", tmp_path / "absent.json")
    monkeypatch.setattr(oauth, "_dotenv_access_token", lambda path=None: "")
    monkeypatch.delenv(oauth.ACCESS_TOKEN_ENV_VAR, raising=False)

    assert "Authorization" not in _captured_headers(monkeypatch)


def test_provider_still_honours_an_explicit_environment_override(monkeypatch,
                                                                 tmp_path):
    token_path = _write(tmp_path / "tokens.json")
    monkeypatch.setattr(oauth, "TOKEN_FILE", token_path)
    monkeypatch.setattr(oauth, "_dotenv_access_token", lambda path=None: "")
    monkeypatch.setenv(oauth.ACCESS_TOKEN_ENV_VAR, FAKE_ENV_TOKEN)

    headers = _captured_headers(monkeypatch)
    assert headers["Authorization"] == f"Bearer {FAKE_ENV_TOKEN}"


def test_a_corrupt_credential_file_does_not_break_a_search(monkeypatch, tmp_path):
    token_path = tmp_path / "tokens.json"
    token_path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(oauth, "TOKEN_FILE", token_path)
    monkeypatch.setattr(oauth, "_dotenv_access_token", lambda path=None: "")
    monkeypatch.delenv(oauth.ACCESS_TOKEN_ENV_VAR, raising=False)

    # No exception, and the request simply goes out unauthenticated.
    assert "Authorization" not in _captured_headers(monkeypatch)


# -- refresh rotation, end to end --------------------------------------


def test_refresh_rotation_reaches_the_next_authenticated_request(monkeypatch,
                                                                 tmp_path, capsys):
    """authorize -> request -> refresh -> request, with .env never touched.

    This is the sequence that used to break: after a refresh the provider
    kept sending the pre-refresh token because the only path to it was a
    manual copy into .env.
    """
    token_path = tmp_path / "tokens.json"
    monkeypatch.setattr(oauth, "TOKEN_FILE", token_path)
    # A stale .env value is present throughout and must never be used.
    monkeypatch.setattr(oauth, "_dotenv_access_token",
                        lambda path=None: FAKE_DOTENV_TOKEN)
    monkeypatch.setenv(oauth.ACCESS_TOKEN_ENV_VAR, FAKE_DOTENV_TOKEN)

    # 1. authorize wrote the first credential set.
    first = oauth.TokenSet(
        access_token=FAKE_STORED_TOKEN, refresh_token=FAKE_REFRESH_1,
        token_type="Bearer", expires_in=21600, scope="read", user_id=1,
        obtained_at=NOW.isoformat())
    oauth.write_token_file(first, token_path)

    assert _captured_headers(monkeypatch)["Authorization"] == (
        f"Bearer {FAKE_STORED_TOKEN}")
    assert oauth.read_refresh_token(token_path) == FAKE_REFRESH_1

    # 2. refresh: Mercado Livre rotates BOTH tokens.
    def fake_post(url, data=None, headers=None, timeout=None):
        assert data["grant_type"] == "refresh_token"
        assert data["refresh_token"] == FAKE_REFRESH_1

        class _Response:
            status_code = 200

            @staticmethod
            def json():
                return {
                    "access_token": FAKE_ROTATED_TOKEN,
                    "refresh_token": FAKE_REFRESH_2,
                    "token_type": "Bearer",
                    "expires_in": 21600,
                    "scope": "read",
                    "user_id": 1,
                }

        return _Response()

    monkeypatch.setattr(oauth.requests, "post", fake_post)
    rotated = oauth.refresh_access_token(
        refresh_token=oauth.read_refresh_token(token_path),
        client_id="1234567890123456", client_secret="fake-client-secret-0001")
    oauth.write_token_file(rotated, token_path)

    # 3. the NEXT request carries the rotated token, with no .env edit.
    headers = _captured_headers(monkeypatch)
    assert headers["Authorization"] == f"Bearer {FAKE_ROTATED_TOKEN}"
    assert FAKE_STORED_TOKEN not in headers["Authorization"]
    assert FAKE_DOTENV_TOKEN not in headers["Authorization"]

    # 4. the old refresh token is gone -- it is single-use upstream.
    assert oauth.read_refresh_token(token_path) == FAKE_REFRESH_2
    stored = json.loads(token_path.read_text(encoding="utf-8"))
    assert FAKE_REFRESH_1 not in json.dumps(stored)

    # 5. nothing in the whole sequence printed a credential.
    captured = capsys.readouterr()
    for secret in (FAKE_STORED_TOKEN, FAKE_ROTATED_TOKEN, FAKE_REFRESH_1,
                   FAKE_REFRESH_2, FAKE_DOTENV_TOKEN):
        assert secret not in captured.out
        assert secret not in captured.err


def test_rotation_keeps_working_when_only_the_access_token_changes(monkeypatch,
                                                                   tmp_path):
    """Some providers return no new refresh token; the file must stay sane."""
    token_path = tmp_path / "tokens.json"
    monkeypatch.setattr(oauth, "TOKEN_FILE", token_path)
    monkeypatch.setattr(oauth, "_dotenv_access_token", lambda path=None: "")
    monkeypatch.delenv(oauth.ACCESS_TOKEN_ENV_VAR, raising=False)

    oauth.write_token_file(oauth.TokenSet(
        access_token=FAKE_ROTATED_TOKEN, refresh_token=None, token_type="Bearer",
        expires_in=21600, scope=None, user_id=None,
        obtained_at=NOW.isoformat()), token_path)

    assert _captured_headers(monkeypatch)["Authorization"] == (
        f"Bearer {FAKE_ROTATED_TOKEN}")
    with pytest.raises(oauth.MercadoLivreOAuthConfigurationError):
        oauth.read_refresh_token(token_path)


# -- anti-drift ---------------------------------------------------------


def test_the_two_modules_agree_on_the_variable_name():
    """The provider cannot import this constant without a cycle."""
    assert oauth.ACCESS_TOKEN_ENV_VAR == mercadolivre.ACCESS_TOKEN_ENV_VAR


def test_the_provider_resolves_through_the_shared_helper():
    assert mercadolivre.resolve_access_token is oauth.resolve_access_token
