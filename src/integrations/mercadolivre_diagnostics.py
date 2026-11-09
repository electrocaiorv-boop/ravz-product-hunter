"""Read-only Mercado Livre connectivity diagnostic.

Answers one question and refuses to answer any other: with a token now
configured, what does Mercado Livre actually return?

== Two separate probes, reported separately ==

1. `check_site_resource()` -- GET /sites/MLB. A documented, long-standing,
   low-impact read-only resource. This is the decisive experiment from
   `docs/MERCADO_LIVRE_403.md` section 5.
2. `check_listing_search()` -- the Competition provider's existing call,
   made through `search_products()` so the probe exercises the real code
   path rather than a parallel reimplementation.

They are reported as two independent outcomes and never merged into a
single verdict. Probe 1 passing does not imply probe 2 passes: one is a
documented resource, the other is this project's undocumented free-text
`q` usage (see the classification note in `mercadolivre.py`).

== What this module must not do ==

- It must not conclude that authentication "fixed" the 403. Obstacle B
  in `docs/MERCADO_LIVRE_403.md` is a policy refusal that a valid token
  does not necessarily clear, and that cannot be determined from here.
- It must not retry, loop, fan out, or try alternative hosts, headers or
  undocumented endpoints after a refusal. One request per probe.
- It must not call `/products/search`. That endpoint returns CATALOG
  products; Competition scores the field of SELLERS competing on a
  product. Substituting one for the other would silently change what the
  Competition Score measures while leaving its name and weight intact.
- It must not write anything, publish anything, or spend anything.

== Cost and rate limits ==

Free, read-only. Exactly two HTTP requests per run, no retries.

`x-request-id` is captured from the RESPONSE headers because
`docs/MERCADO_LIVRE_403.md` requires it to escalate a confirmed policy
refusal to Mercado Livre support. It is a server-side correlation id,
not a credential. No request header is ever recorded.
"""

import os
from dataclasses import dataclass

import requests

import src.config  # noqa: F401 -- side effect: loads .env
from src.integrations.mercadolivre import (
    ACCESS_TOKEN_ENV_VAR,
    BASE_URL,
    DEFAULT_TIMEOUT,
    SITE_ID,
    MercadoLivreError,
    MercadoLivreResponseError,
    search_products,
)

PROBE_SITE = "site_resource"
PROBE_LISTING_SEARCH = "listing_search"

SITE_ENDPOINT = f"{BASE_URL}/sites/{SITE_ID}"
SEARCH_ENDPOINT = f"{BASE_URL}/sites/{SITE_ID}/search?q=<free text>"

# Mercado Livre's policy-refusal fingerprint. Matching it is how the
# 403 doc's Obstacle B is recognised rather than guessed -- but a match
# is still reported as "consistent with", never as a diagnosis.
POLICY_REFUSAL_MARKER = "policy returned unauthorized"


@dataclass(frozen=True)
class ProbeOutcome:
    """One probe's result. Carries no credential and no verdict."""

    probe: str
    endpoint: str
    token_configured: bool
    succeeded: bool
    status_code: int | None
    request_id: str | None
    detail: str

    @property
    def is_forbidden(self) -> bool:
        return self.status_code == 403

    def describe(self) -> str:
        status = self.status_code if self.status_code is not None else "none"
        return "\n".join([
            f"  probe            : {self.probe}",
            f"  endpoint         : {self.endpoint}",
            f"  token configured : {self.token_configured}",
            f"  http status      : {status}",
            f"  succeeded        : {self.succeeded}",
            f"  x-request-id     : {self.request_id or 'not returned'}",
            f"  detail           : {self.detail}",
        ])


def token_configured() -> bool:
    """Whether a token is set. Never reads or returns the value."""
    value = os.environ.get(ACCESS_TOKEN_ENV_VAR)
    return bool(value and value.strip())


def _authorization_header() -> dict:
    token = os.environ.get(ACCESS_TOKEN_ENV_VAR)
    if token and token.strip():
        return {"Authorization": f"Bearer {token.strip()}"}
    return {}


def check_site_resource(timeout: float = DEFAULT_TIMEOUT) -> ProbeOutcome:
    """ONE authenticated GET /sites/MLB. No retry, no fallback probing."""
    configured = token_configured()

    # Recorded in the handler, raised/used after it: `requests` embeds
    # the Authorization header value in some transport errors.
    transport_failure = None
    response = None

    try:
        response = requests.get(
            SITE_ENDPOINT, headers=_authorization_header(), timeout=timeout)
    except requests.Timeout:
        transport_failure = f"no response within {timeout}s"
    except requests.ConnectionError:
        transport_failure = "could not connect"
    except requests.RequestException as exc:
        transport_failure = (
            f"request failed ({type(exc).__name__}); detail withheld "
            "because transport errors can embed request headers")

    if transport_failure is not None:
        return ProbeOutcome(
            probe=PROBE_SITE, endpoint=SITE_ENDPOINT,
            token_configured=configured, succeeded=False, status_code=None,
            request_id=None, detail=transport_failure)

    request_id = response.headers.get("x-request-id")

    if response.status_code == 200:
        return ProbeOutcome(
            probe=PROBE_SITE, endpoint=SITE_ENDPOINT,
            token_configured=configured, succeeded=True, status_code=200,
            request_id=request_id,
            detail="documented site resource returned 200")

    return ProbeOutcome(
        probe=PROBE_SITE, endpoint=SITE_ENDPOINT, token_configured=configured,
        succeeded=False, status_code=response.status_code,
        request_id=request_id,
        detail=_describe_refusal(response))


def _describe_refusal(response) -> str:
    """Describe a non-200 without quoting an unbounded provider body."""
    body = ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            body = str(payload.get("message", ""))[:200]
    except Exception:  # noqa: BLE001 - body shape is not trusted
        body = ""

    if response.status_code == 403 and POLICY_REFUSAL_MARKER in body.lower():
        return ("403 with Mercado Livre's policy-refusal message. This is "
                "CONSISTENT WITH Obstacle B in docs/MERCADO_LIVRE_403.md "
                "(a refusal a valid token does not clear). It is not proof: "
                "only Mercado Livre support can confirm, using the "
                "x-request-id above.")
    if response.status_code == 403:
        return ("403 Forbidden. Not attributable from here -- it may be the "
                "token, the scopes, the endpoint policy or the caller's "
                "network. Do not conclude, and do not probe around it.")
    if response.status_code == 401:
        return ("401 Unauthorized -- the token was rejected or has expired "
                "(Mercado Livre access tokens last about 6 hours). Refresh "
                "and re-run.")
    return f"HTTP {response.status_code}" + (f": {body}" if body else "")


def check_listing_search(query: str = "fone bluetooth",
                         limit: int = 5) -> ProbeOutcome:
    """ONE call through the Competition provider's own code path.

    Deliberately routed through `search_products()` rather than a fresh
    request: a parallel implementation could pass here while the code
    Competition actually uses still fails.
    """
    configured = token_configured()
    try:
        items = search_products(query, limit=limit)
    except MercadoLivreResponseError as exc:
        return ProbeOutcome(
            probe=PROBE_LISTING_SEARCH, endpoint=SEARCH_ENDPOINT,
            token_configured=configured, succeeded=False,
            status_code=exc.status_code, request_id=None,
            detail=(f"HTTP {exc.status_code} from the listing search this "
                    "project's Competition analysis depends on. Competition "
                    "stays unavailable; nothing is substituted."))
    except MercadoLivreError as exc:
        return ProbeOutcome(
            probe=PROBE_LISTING_SEARCH, endpoint=SEARCH_ENDPOINT,
            token_configured=configured, succeeded=False, status_code=None,
            request_id=None,
            detail=f"{type(exc).__name__}: evidence unavailable")

    return ProbeOutcome(
        probe=PROBE_LISTING_SEARCH, endpoint=SEARCH_ENDPOINT,
        token_configured=configured, succeeded=True, status_code=200,
        request_id=None,
        detail=f"{len(items)} listing(s) returned; listing evidence is "
               "available to Competition")


def interpret(site: ProbeOutcome, listing: ProbeOutcome) -> str:
    """State what the two outcomes DO and DO NOT establish.

    Never asserts a cause. Each branch says what is now known and what
    remains unknown, because attributing a 403 from outside Mercado
    Livre's infrastructure is not possible.
    """
    if site.succeeded and listing.succeeded:
        return ("Obstacle A (no credentials) is cleared and the listing "
                "search returns data. Competition can be scored from live "
                "listing evidence. Re-verify that the free-text 'q' usage "
                "is acceptable long term -- it remains undocumented for "
                "this endpoint.")
    if site.succeeded and not listing.succeeded:
        return ("The documented site resource works, so authentication is "
                "functioning. The refusal is specific to the listing "
                "search. This does NOT license substituting catalog data: "
                "Competition stays unavailable until a documented listing "
                "source exists.")
    if not site.succeeded and site.is_forbidden:
        return ("Even the documented site resource is refused with a token "
                "configured. That is consistent with Obstacle B, and is the "
                "point at which docs/MERCADO_LIVRE_403.md says to STOP and "
                "open a support case with the x-request-id. No code change "
                "fixes a policy refusal.")
    return ("Inconclusive: the probe did not complete. Nothing is "
            "established about the 403, and no evidence was produced.")


APPROVAL_FLAG = "--i-approve-live-read-only-requests"

USAGE = f"""Usage: python -m src.integrations.mercadolivre_diagnostics {APPROVAL_FLAG}

Makes exactly TWO live read-only GET requests to Mercado Livre:
  1. {SITE_ENDPOINT}
  2. the Competition provider's listing search

No writes, no retries, no catalog substitution. Requires explicit
approval via the flag above so it can never run by accident.
"""


def main(argv=None) -> int:
    import sys

    args = list(sys.argv[1:] if argv is None else argv)
    if APPROVAL_FLAG not in args:
        print(USAGE)
        return 2

    print("Mercado Livre read-only diagnostic (2 requests, no retries)")
    print(f"{ACCESS_TOKEN_ENV_VAR}: "
          f"{'configured' if token_configured() else 'NOT configured'} "
          "(value never shown)")
    print()
    site = check_site_resource()
    print(site.describe())
    print()
    listing = check_listing_search()
    print(listing.describe())
    print()
    print("What this does and does not establish:")
    print(f"  {interpret(site, listing)}")
    return 0 if site.succeeded else 1


if __name__ == "__main__":
    raise SystemExit(main())
