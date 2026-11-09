"""Stateless Mercado Livre OAuth callback relay (Vercel function).

Deployed as its own Vercel project (`ravz-ml-oauth`). It is NOT part of
the RAVZ commercial website and shares no code, domain or deployment
with it.

== Why this service has to exist at all ==

Mercado Livre requires the registered `redirect_uri` to use HTTPS and
does not accept a loopback/localhost address. The local Python
application therefore cannot receive the authorization redirect
directly. Something public and HTTPS has to catch it.

== What it does, and the whole of what it does ==

    browser --(HTTPS, ?code&state)--> this function
    this function --(302)--> http://127.0.0.1:<fixed port>/callback?code&state

That is all. It is a *relay*: it validates the SHAPE of what arrived and
forwards it to one hardcoded destination.

== What never passes through here ==

- No access token, no refresh token. This service never calls the token
  endpoint, so no token ever exists in this process.
- No client secret. It is not configured here and is not needed here.
- No user data, no cookies, no session.

What does cross the public hop is the authorization `code` and `state`.
Neither is a credential on its own:

- the code is single-use, short-lived, and bound by PKCE S256 to a
  `code_verifier` that is generated inside the local Python process and
  never leaves that process. An intercepted code cannot be exchanged.
- the state is a random nonce generated locally and validated locally.
  Mercado Livre documents that it does NOT validate `state`, so that
  check belongs to the local application, which is where it lives.

== Why there is no database ==

The relay holds no state, so there is nothing to store. `state` and the
PKCE verifier live in the local process that created them -- the only
place that can validate them. Adding a store here would move secrets
into the public tier to no benefit.

== Open redirect ==

Structurally impossible. The destination host is the literal
"127.0.0.1" in this file and the path is the literal "/callback". No
request input selects, influences or is appended to the destination
host, scheme or path. Only `code`, `state`, `error` and a sanitized
`error_description` are relayed, each re-encoded. There is no `next`,
`return_to` or `redirect_uri` parameter to abuse.

== Logging ==

`log_message` is overridden to emit nothing, so the authorization code
cannot reach this function's own stderr. Note the platform's own access
log is outside this file's control and may record the request URL; the
code's single-use + PKCE binding is what makes that acceptable rather
than a leak. See docs/MERCADO_LIVRE_OAUTH.md.

Python stdlib only -- no dependencies, so no requirements.txt and no
supply chain.
"""

import os
import re
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qsl, urlencode

# -- the destination, hardcoded -----------------------------------------
#
# Host and path are literals. The port is the only configurable part and
# it is validated as a port number, so configuration can select WHICH
# local port receives the relay but can never change WHERE it goes.
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PATH = "/callback"
DEFAULT_LOOPBACK_PORT = 53682
PORT_ENV_VAR = "RAVZ_OAUTH_LOOPBACK_PORT"

# -- accepted shapes ----------------------------------------------------
#
# These must stay identical to the copies in
# src/integrations/mercadolivre_oauth.py. The two sides of this hop
# cannot share code (separate deployments), so a test asserts the
# pattern strings are equal rather than trusting that they drifted
# together.
STATE_PATTERN = r"\A[A-Za-z0-9_-]{32,128}\Z"
CODE_PATTERN = r"\A[A-Za-z0-9._~$-]{16,512}\Z"
ERROR_PATTERN = r"\A[A-Za-z0-9_-]{1,64}\Z"

_STATE_RE = re.compile(STATE_PATTERN)
_CODE_RE = re.compile(CODE_PATTERN)
_ERROR_RE = re.compile(ERROR_PATTERN)

# `error_description` is provider free text. It is useful for diagnosis,
# so it is relayed -- but reduced to a safe charset and truncated first,
# then re-encoded by urlencode().
_DESCRIPTION_ALLOWED = re.compile(r"[^A-Za-z0-9 .,_:-]")
_DESCRIPTION_MAX = 200

# Fixed reason codes. The error page shows one of these and NEVER echoes
# any request input, so there is nothing to reflect back at the browser.
REASON_METHOD = "method_not_allowed"
REASON_DUPLICATE_PARAM = "duplicate_parameter"
REASON_MISSING_PARAMS = "missing_code_or_state"
REASON_BAD_STATE = "malformed_state"
REASON_BAD_CODE = "malformed_code"
REASON_BAD_ERROR_CODE = "malformed_error"
REASON_MISCONFIGURED = "service_misconfigured"

SECURITY_HEADERS = (
    ("Cache-Control", "no-store, max-age=0"),
    ("Pragma", "no-cache"),
    ("Referrer-Policy", "no-referrer"),
    ("X-Content-Type-Options", "nosniff"),
    ("X-Frame-Options", "DENY"),
    # 'none' everywhere: these pages load no script, style, image or font.
    ("Content-Security-Policy",
     "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
     "form-action 'none'"),
    ("Permissions-Policy", "geolocation=(), camera=(), microphone=()"),
    # Deliberately WITHOUT includeSubDomains: this service must not be
    # able to impose transport policy on any other ravztech.com.br host,
    # least of all the commercial site.
    ("Strict-Transport-Security", "max-age=31536000"),
)


class RelayDecision:
    """What to do with one request. Pure data, no I/O."""

    def __init__(self, kind, *, location=None, status=None, reason=None,
                 detail=None):
        self.kind = kind          # "relay" | "error"
        self.location = location  # relay only
        self.status = status      # error only
        self.reason = reason      # error only, from the fixed set above
        self.detail = detail      # error only, fixed text (never input)

    def __repr__(self):  # pragma: no cover - diagnostics only
        if self.kind == "relay":
            return "<RelayDecision relay>"
        return f"<RelayDecision error {self.status} {self.reason}>"


def resolve_loopback_port(environ=None) -> int | None:
    """Resolve the local port to relay to.

    Returns None when the variable is SET but not a valid port. Failing
    closed is deliberate: silently falling back to the default would
    relay the authorization code to a different local listener than the
    operator configured.
    """
    env = os.environ if environ is None else environ
    raw = (env.get(PORT_ENV_VAR) or "").strip()
    if not raw:
        return DEFAULT_LOOPBACK_PORT
    if not raw.isdigit():
        return None
    port = int(raw)
    # Unprivileged ports only; a loopback listener run by a normal user
    # cannot bind below 1024 anyway.
    if not 1024 <= port <= 65535:
        return None
    return port


def _single_valued(query_string: str):
    """Parse the query, rejecting any repeated parameter.

    Duplicate parameters are a parameter-pollution vector: one value
    would be validated and a different one potentially relayed,
    depending on which side picks first/last. Rejecting outright removes
    the ambiguity instead of resolving it.
    """
    pairs = parse_qsl(query_string, keep_blank_values=True)
    seen: dict[str, str] = {}
    for key, value in pairs:
        if key in seen:
            return None
        seen[key] = value
    return seen


def _sanitize_description(value: str) -> str:
    return _DESCRIPTION_ALLOWED.sub(" ", value)[:_DESCRIPTION_MAX].strip()


def decide(query_string: str, *, port: int | None) -> RelayDecision:
    """Pure relay logic: query string in, decision out.

    Every rejection path returns a fixed reason code. No request value is
    ever placed in an error page.
    """
    if port is None:
        return RelayDecision(
            "error", status=500, reason=REASON_MISCONFIGURED,
            detail=f"{PORT_ENV_VAR} is set to a value that is not a usable "
                   "port. The service refuses to guess a destination.")

    params = _single_valued(query_string or "")
    if params is None:
        return RelayDecision(
            "error", status=400, reason=REASON_DUPLICATE_PARAM,
            detail="A query parameter was supplied more than once.")

    relayed: dict[str, str] = {}

    state = params.get("state", "")
    if state and not _STATE_RE.match(state):
        return RelayDecision(
            "error", status=400, reason=REASON_BAD_STATE,
            detail="The state parameter is not the expected shape.")

    # Provider-reported failure (user denied consent, bad client, ...).
    # Relayed so the LOCAL application fails explicitly with a reason
    # instead of sitting on a listener that never fires.
    if "error" in params:
        error = params.get("error", "")
        if not _ERROR_RE.match(error):
            return RelayDecision(
                "error", status=400, reason=REASON_BAD_ERROR_CODE,
                detail="The error parameter is not the expected shape.")
        relayed["error"] = error
        description = _sanitize_description(params.get("error_description", ""))
        if description:
            relayed["error_description"] = description
        if state:
            relayed["state"] = state
        return RelayDecision(
            "relay", location=_build_location(port, relayed))

    code = params.get("code", "")
    if not code or not state:
        return RelayDecision(
            "error", status=400, reason=REASON_MISSING_PARAMS,
            detail="Both code and state are required.")
    if not _CODE_RE.match(code):
        return RelayDecision(
            "error", status=400, reason=REASON_BAD_CODE,
            detail="The code parameter is not the expected shape.")

    relayed["code"] = code
    relayed["state"] = state
    return RelayDecision("relay", location=_build_location(port, relayed))


def _build_location(port: int, relayed: dict) -> str:
    """Assemble the one permitted destination.

    Scheme, host and path are literals here. `relayed` only ever
    contributes query values, and urlencode() escapes them, so no input
    can introduce a second `?`, a `#`, a `\\` or a new authority.
    """
    return (f"http://{LOOPBACK_HOST}:{port}{LOOPBACK_PATH}"
            f"?{urlencode(sorted(relayed.items()))}")


RELAY_BODY = (
    "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
    "<title>RAVZ - returning to the local application</title></head>"
    "<body><h1>Returning to the local application</h1>"
    "<p>You are being returned to the RAVZ Product Hunter running on this "
    "computer. If your browser does not continue automatically, copy the "
    "address it was about to open (it starts with "
    "<code>http://127.0.0.1</code>) and paste it into the terminal when "
    "asked.</p>"
    "<p>No access token and no credential passed through this page.</p>"
    "</body></html>"
)


def _error_body(reason: str, detail: str) -> str:
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        "<title>RAVZ - authorization could not be relayed</title></head>"
        "<body><h1>Authorization could not be relayed</h1>"
        f"<p>{detail}</p>"
        f"<p>Reason code: <code>{reason}</code></p>"
        "<p>Nothing was stored and no credential was exposed. Start the "
        "authorization again from the local application.</p>"
        "</body></html>"
    )


class handler(BaseHTTPRequestHandler):  # noqa: N801 - name required by Vercel
    """Vercel entry point. Thin: parse, decide, write."""

    # Keep the relayed code out of this function's own logs.
    def log_message(self, fmt, *args):  # noqa: D102
        return

    def log_request(self, code="-", size="-"):  # noqa: D102
        return

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        _, _, query = self.path.partition("?")
        decision = decide(query, port=resolve_loopback_port())
        if decision.kind == "relay":
            self._write(302, RELAY_BODY, location=decision.location)
        else:
            self._write(decision.status,
                        _error_body(decision.reason, decision.detail))

    def _method_not_allowed(self):
        self._write(405, _error_body(
            REASON_METHOD, "This endpoint only accepts GET."),
            extra=(("Allow", "GET"),))

    do_POST = _method_not_allowed
    do_PUT = _method_not_allowed
    do_PATCH = _method_not_allowed
    do_DELETE = _method_not_allowed
    do_OPTIONS = _method_not_allowed

    def _write(self, status: int, body: str, *, location=None, extra=()):
        payload = body.encode("utf-8")
        self.send_response(status)
        if location is not None:
            self.send_header("Location", location)
        for name, value in SECURITY_HEADERS:
            self.send_header(name, value)
        for name, value in extra:
            self.send_header(name, value)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
