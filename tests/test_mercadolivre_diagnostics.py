"""Tests for the read-only Mercado Livre connectivity diagnostic.

No credentials and no network: `requests.get` and `search_products` are
monkeypatched.

The properties that matter here are epistemic, not functional:

- the two probes are reported SEPARATELY and never merged.
- no outcome ever asserts a cause for a 403.
- a token is reported as configured, never shown.
- the diagnostic cannot run without explicit approval.
"""

import pytest
import requests

from src.integrations import mercadolivre_diagnostics as diag
from src.integrations.mercadolivre import (
    MercadoLivreConnectionError,
    MercadoLivreResponseError,
)

FAKE_TOKEN = "fake-access-token-diagnostic-0001"


class _Response:
    def __init__(self, status_code, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = headers or {}

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def _site(monkeypatch, response):
    def fake_get(url, headers=None, timeout=None):
        return response

    monkeypatch.setattr(diag.requests, "get", fake_get)
    return diag.check_site_resource()


# -- token reporting ----------------------------------------------------


def test_token_configured_is_true_when_set(monkeypatch):
    monkeypatch.setenv(diag.ACCESS_TOKEN_ENV_VAR, FAKE_TOKEN)
    assert diag.token_configured() is True


def test_token_configured_is_false_when_blank(monkeypatch):
    monkeypatch.setenv(diag.ACCESS_TOKEN_ENV_VAR, "   ")
    assert diag.token_configured() is False


def test_token_configured_is_false_when_absent(monkeypatch):
    monkeypatch.delenv(diag.ACCESS_TOKEN_ENV_VAR, raising=False)
    assert diag.token_configured() is False


def test_outcome_describe_never_shows_the_token(monkeypatch):
    monkeypatch.setenv(diag.ACCESS_TOKEN_ENV_VAR, FAKE_TOKEN)
    outcome = _site(monkeypatch, _Response(200, {"id": "MLB"}))
    described = outcome.describe()
    assert FAKE_TOKEN not in described
    assert "token configured : True" in described


def test_authorization_header_is_sent_only_when_a_token_exists(monkeypatch):
    monkeypatch.setenv(diag.ACCESS_TOKEN_ENV_VAR, FAKE_TOKEN)
    assert "Authorization" in diag._authorization_header()
    monkeypatch.delenv(diag.ACCESS_TOKEN_ENV_VAR, raising=False)
    assert diag._authorization_header() == {}


# -- site probe ---------------------------------------------------------


def test_site_probe_reports_success_on_200(monkeypatch):
    outcome = _site(monkeypatch, _Response(200, {"id": "MLB"}))
    assert outcome.succeeded is True
    assert outcome.status_code == 200
    assert outcome.probe == diag.PROBE_SITE


def test_site_probe_captures_the_request_id_for_escalation(monkeypatch):
    outcome = _site(monkeypatch, _Response(
        403, {"message": "At least one policy returned UNAUTHORIZED."},
        headers={"x-request-id": "abc-123-def"}))
    assert outcome.request_id == "abc-123-def"
    assert "x-request-id" in outcome.describe()


def test_policy_refusal_is_reported_as_consistent_with_not_proof_of(monkeypatch):
    outcome = _site(monkeypatch, _Response(
        403, {"message": "At least one policy returned UNAUTHORIZED."}))
    assert outcome.is_forbidden is True
    assert "CONSISTENT WITH" in outcome.detail
    assert "not proof" in outcome.detail.lower()


def test_plain_403_is_explicitly_not_attributed(monkeypatch):
    outcome = _site(monkeypatch, _Response(403, {"message": "forbidden"}))
    assert "Not attributable" in outcome.detail
    assert "Do not conclude" in outcome.detail


def test_401_points_at_token_expiry(monkeypatch):
    outcome = _site(monkeypatch, _Response(401, {"message": "invalid token"}))
    assert outcome.succeeded is False
    assert "expired" in outcome.detail


def test_unparseable_body_does_not_crash_the_probe(monkeypatch):
    outcome = _site(monkeypatch, _Response(500, ValueError("not json")))
    assert outcome.succeeded is False
    assert outcome.status_code == 500


@pytest.mark.parametrize("error,fragment", [
    (requests.Timeout("slow"), "within"),
    (requests.ConnectionError("down"), "could not connect"),
])
def test_transport_failures_are_reported_without_a_status(monkeypatch, error,
                                                          fragment):
    def fake_get(url, headers=None, timeout=None):
        raise error

    monkeypatch.setattr(diag.requests, "get", fake_get)
    outcome = diag.check_site_resource()
    assert outcome.succeeded is False
    assert outcome.status_code is None
    assert fragment in outcome.detail


def test_transport_failure_detail_withholds_header_bearing_messages(monkeypatch):
    def fake_get(url, headers=None, timeout=None):
        raise requests.RequestException(f"failed with Authorization {FAKE_TOKEN}")

    monkeypatch.setattr(diag.requests, "get", fake_get)
    outcome = diag.check_site_resource()
    assert FAKE_TOKEN not in outcome.detail
    assert "withheld" in outcome.detail


def test_site_probe_makes_exactly_one_request(monkeypatch):
    calls = []

    def fake_get(url, headers=None, timeout=None):
        calls.append(url)
        return _Response(403, {"message": "forbidden"})

    monkeypatch.setattr(diag.requests, "get", fake_get)
    diag.check_site_resource()
    assert len(calls) == 1
    assert calls[0] == diag.SITE_ENDPOINT


# -- listing probe ------------------------------------------------------


def test_listing_probe_uses_the_competition_providers_own_code_path(monkeypatch):
    captured = {}

    def fake_search(query, limit=10):
        captured["query"] = query
        captured["limit"] = limit
        return ["item-a", "item-b"]

    monkeypatch.setattr(diag, "search_products", fake_search)
    outcome = diag.check_listing_search("fone bluetooth", limit=5)
    assert captured == {"query": "fone bluetooth", "limit": 5}
    assert outcome.succeeded is True
    assert "2 listing(s)" in outcome.detail


def test_listing_probe_reports_a_403_without_substituting_anything(monkeypatch):
    def fake_search(query, limit=10):
        raise MercadoLivreResponseError(403, "forbidden")

    monkeypatch.setattr(diag, "search_products", fake_search)
    outcome = diag.check_listing_search()
    assert outcome.succeeded is False
    assert outcome.status_code == 403
    assert "nothing is substituted" in outcome.detail.lower()


def test_listing_probe_reports_a_transport_failure_as_unavailable(monkeypatch):
    def fake_search(query, limit=10):
        raise MercadoLivreConnectionError("down")

    monkeypatch.setattr(diag, "search_products", fake_search)
    outcome = diag.check_listing_search()
    assert outcome.succeeded is False
    assert "unavailable" in outcome.detail


def test_the_catalog_endpoint_is_never_called():
    source = __import__("pathlib").Path(diag.__file__).read_text(
        encoding="utf-8")
    # Mentioned in the docstring as forbidden, never as a request target.
    assert "/products/search" not in diag.SITE_ENDPOINT
    assert "/products/search" not in diag.SEARCH_ENDPOINT
    assert 'requests.get(\n            SITE_ENDPOINT' in source


# -- interpretation: no causal claims ----------------------------------


def _outcome(probe, succeeded, status=None):
    return diag.ProbeOutcome(
        probe=probe, endpoint="e", token_configured=True, succeeded=succeeded,
        status_code=status, request_id=None, detail="d")


def test_both_succeeding_clears_obstacle_a_only():
    verdict = diag.interpret(_outcome(diag.PROBE_SITE, True, 200),
                             _outcome(diag.PROBE_LISTING_SEARCH, True, 200))
    assert "Obstacle A" in verdict
    assert "undocumented" in verdict


def test_site_ok_but_search_refused_forbids_catalog_substitution():
    verdict = diag.interpret(_outcome(diag.PROBE_SITE, True, 200),
                             _outcome(diag.PROBE_LISTING_SEARCH, False, 403))
    assert "catalog" in verdict.lower()
    assert "Competition stays unavailable" in verdict


def test_site_forbidden_says_stop_and_escalate():
    verdict = diag.interpret(_outcome(diag.PROBE_SITE, False, 403),
                             _outcome(diag.PROBE_LISTING_SEARCH, False, 403))
    assert "Obstacle B" in verdict
    assert "STOP" in verdict
    assert "support case" in verdict


def test_inconclusive_probe_establishes_nothing():
    verdict = diag.interpret(_outcome(diag.PROBE_SITE, False, None),
                             _outcome(diag.PROBE_LISTING_SEARCH, False, None))
    assert "Inconclusive" in verdict
    assert "no evidence was produced" in verdict


@pytest.mark.parametrize("site_ok,listing_ok,status", [
    (True, True, 200), (True, False, 403), (False, False, 403),
    (False, False, None),
])
def test_no_interpretation_ever_claims_a_cause(site_ok, listing_ok, status):
    verdict = diag.interpret(_outcome(diag.PROBE_SITE, site_ok, status),
                             _outcome(diag.PROBE_LISTING_SEARCH, listing_ok,
                                      status))
    lowered = verdict.lower()
    for forbidden in ("because the token", "the cause is", "caused by",
                      "proves", "this means the 403 was"):
        assert forbidden not in lowered


# -- approval gate ------------------------------------------------------


def test_diagnostic_refuses_to_run_without_explicit_approval(monkeypatch, capsys):
    monkeypatch.setattr(diag.requests, "get", _unreachable)
    assert diag.main([]) == 2
    printed = capsys.readouterr().out
    assert diag.APPROVAL_FLAG in printed
    assert "TWO live read-only" in printed


def test_diagnostic_refuses_on_a_wrong_flag(monkeypatch):
    monkeypatch.setattr(diag.requests, "get", _unreachable)
    assert diag.main(["--yes"]) == 2


def test_approved_run_executes_both_probes_and_reports_separately(monkeypatch,
                                                                  capsys):
    monkeypatch.setenv(diag.ACCESS_TOKEN_ENV_VAR, FAKE_TOKEN)
    monkeypatch.setattr(diag.requests, "get",
                        lambda url, headers=None, timeout=None: _Response(
                            403, {"message": "At least one policy returned "
                                             "UNAUTHORIZED."},
                            headers={"x-request-id": "req-99"}))
    monkeypatch.setattr(diag, "search_products",
                        lambda query, limit=10: (_ for _ in ()).throw(
                            MercadoLivreResponseError(403, "forbidden")))
    assert diag.main([diag.APPROVAL_FLAG]) == 1
    printed = capsys.readouterr().out
    assert printed.count("probe            :") == 2
    assert diag.PROBE_SITE in printed
    assert diag.PROBE_LISTING_SEARCH in printed
    assert "req-99" in printed
    assert "Obstacle B" in printed
    assert FAKE_TOKEN not in printed


def _unreachable(*args, **kwargs):
    raise AssertionError("no network call may happen in this test")
