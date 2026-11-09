"""Mercado Livre OAuth 2.0 authorization helper (local, one-off).

Obtains a Mercado Livre access token for THIS machine, using the
authorization-code flow with PKCE S256, and keeps every secret local.

== Why this integration exists (CLAUDE.md External Integrations) ==

1. Why needed: `docs/MERCADO_LIVRE_403.md` records that every Mercado
   Livre request so far has been unauthenticated, and that Mercado
   Livre's documentation states a token is expected on its endpoints.
   Obstacle A (we have no credentials) must be removed before the 403
   can be attributed to anything else.
2. What data it provides: an access token, a refresh token, and the
   token's own metadata (type, lifetime, scope, user id). It provides
   NO product evidence and touches no score.
3. Authentication: `MERCADO_LIVRE_CLIENT_ID`,
   `MERCADO_LIVRE_CLIENT_SECRET` and `MERCADO_LIVRE_REDIRECT_URI` from
   the environment / `.env` (git-ignored). Never hardcoded, never
   logged, never placed in an exception message.
4. Cost implications: none. The OAuth endpoints are free.
5. Rate limits: not published for the token endpoint. This module makes
   exactly ONE token request per invocation and never retries, so it
   cannot fan out.

== Flow, and where each secret lives ==

    this process            ML                 relay (public)
    ------------            --                 --------------
    state + verifier  -->   authorize page
                            redirect  -------> validate shape
                                               302 to 127.0.0.1
    validate state   <------------------------ code + state
    exchange code + verifier + secret --> ML
    tokens stay here

The `code_verifier` and `state` are generated here and never leave this
process. The client secret is sent only in the token POST, directly to
Mercado Livre. The public relay sees only `code` and `state`.

Mercado Livre requires an HTTPS `redirect_uri` and does not accept a
loopback address, which is the only reason a public relay is involved.
Mercado Livre also documents that it does NOT validate `state` -- so
that check is performed here, where the nonce was created.

== Exception hierarchy ==

Deliberately NOT a subclass of `MercadoLivreError`. That family means
"we do not know this product fact" and is translated into unavailable
EVIDENCE. An authorization failure is a different kind of event -- a
setup problem -- and must never be absorbed into a product analysis as
missing evidence.
"""

import base64
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qsl, urlencode, urlparse

import requests

import src.config  # noqa: F401 -- side effect: loads .env

# -- configuration ------------------------------------------------------

CLIENT_ID_ENV_VAR = "MERCADO_LIVRE_CLIENT_ID"
CLIENT_SECRET_ENV_VAR = "MERCADO_LIVRE_CLIENT_SECRET"
REDIRECT_URI_ENV_VAR = "MERCADO_LIVRE_REDIRECT_URI"
LOOPBACK_PORT_ENV_VAR = "MERCADO_LIVRE_OAUTH_LOOPBACK_PORT"

TOKEN_URL = "https://api.mercadolibre.com/oauth/token"

# Authorization host is per marketplace site. MLB = Brazil.
AUTHORIZATION_HOSTS = {
    "MLB": "https://auth.mercadolivre.com.br/authorization",
    "MLA": "https://auth.mercadolibre.com.ar/authorization",
    "MLM": "https://auth.mercadolibre.com.mx/authorization",
}
DEFAULT_SITE_ID = "MLB"

DEFAULT_TIMEOUT = 15
DEFAULT_CALLBACK_WAIT_SECONDS = 300

# Must match the destination hardcoded in the relay function.
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PATH = "/callback"
DEFAULT_LOOPBACK_PORT = 53682

# Kept byte-identical to the copies in
# oauth_service/api/mercadolivre/callback.py. The two sides are separate
# deployments and cannot share code, so a test asserts these strings are
# equal instead of assuming they stay in step.
STATE_PATTERN = r"\A[A-Za-z0-9_-]{32,128}\Z"
CODE_PATTERN = r"\A[A-Za-z0-9._~$-]{16,512}\Z"
ERROR_PATTERN = r"\A[A-Za-z0-9_-]{1,64}\Z"

_STATE_RE = re.compile(STATE_PATTERN)
_CODE_RE = re.compile(CODE_PATTERN)
_ERROR_RE = re.compile(ERROR_PATTERN)

# Where the obtained credentials are written. Git-ignored directory, and
# never printed by this module.
TOKEN_FILE = pathlib.Path(".secrets") / "mercadolivre_tokens.json"


# -- failures -----------------------------------------------------------


class MercadoLivreOAuthError(Exception):
    """Base class for authorization failures. Never product evidence."""


class MercadoLivreOAuthConfigurationError(MercadoLivreOAuthError):
    """A required setting is missing or unusable. Reports NAMES only."""


class MercadoLivreOAuthStateError(MercadoLivreOAuthError):
    """The returned `state` did not match the one generated here."""


class MercadoLivreOAuthTimeoutError(MercadoLivreOAuthError):
    """The token request timed out, or no callback arrived in time."""


class MercadoLivreOAuthConnectionError(MercadoLivreOAuthError):
    """Could not connect to the Mercado Livre token endpoint."""


class MercadoLivreOAuthResponseError(MercadoLivreOAuthError):
    """The token endpoint returned a non-200 status."""

    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class MercadoLivreOAuthDataError(MercadoLivreOAuthError):
    """The token response could not be parsed or lacked a token."""


# -- PKCE and state -----------------------------------------------------


def generate_code_verifier(entropy_bytes: int = 64) -> str:
    """A high-entropy RFC 7636 code verifier.

    `token_urlsafe` emits only unreserved characters, so the result is a
    valid verifier with no post-processing. 64 bytes yields 86
    characters, inside the 43-128 range the RFC allows.
    """
    if entropy_bytes < 32:
        raise ValueError("entropy_bytes must be at least 32")
    verifier = secrets.token_urlsafe(entropy_bytes)
    return verifier[:128]


def derive_code_challenge(code_verifier: str) -> str:
    """S256 challenge: base64url(sha256(verifier)), padding stripped.

    Padding MUST be stripped -- '=' is not valid in a base64url query
    value and Mercado Livre compares the challenge byte for byte.
    """
    if not code_verifier or not 43 <= len(code_verifier) <= 128:
        raise ValueError("code_verifier must be 43-128 characters")
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def generate_state() -> str:
    """A single-use nonce, 43 url-safe characters.

    Mercado Livre does not validate `state`; `verify_state` below is the
    only thing that does, which is why this is generated locally.
    """
    return secrets.token_urlsafe(32)


def verify_state(expected: str, received: str) -> bool:
    """Constant-time comparison, plus a shape check on both sides."""
    if not expected or not received:
        return False
    if not _STATE_RE.match(expected) or not _STATE_RE.match(received):
        return False
    return hmac.compare_digest(expected, received)


# -- configuration resolution -------------------------------------------


def _require_env(name: str, environ=None) -> str:
    env = os.environ if environ is None else environ
    value = (env.get(name) or "").strip()
    if not value:
        raise MercadoLivreOAuthConfigurationError(
            f"{name} is not configured. Set it in .env (git-ignored); see "
            f".env.example for the variable names.")
    return value


def validate_redirect_uri(value: str) -> str:
    """Enforce what Mercado Livre requires of a registered redirect.

    HTTPS, a real host, no query and no fragment. A loopback address is
    rejected here with the reason, because Mercado Livre rejects it at
    registration time and the resulting error is otherwise opaque.
    """
    parsed = urlparse(value)
    if parsed.scheme != "https":
        raise MercadoLivreOAuthConfigurationError(
            f"{REDIRECT_URI_ENV_VAR} must use https -- Mercado Livre "
            "requires HTTPS for a registered redirect URI.")
    if not parsed.hostname:
        raise MercadoLivreOAuthConfigurationError(
            f"{REDIRECT_URI_ENV_VAR} has no host.")
    if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
        raise MercadoLivreOAuthConfigurationError(
            f"{REDIRECT_URI_ENV_VAR} must not be a loopback address -- "
            "Mercado Livre does not accept one. That is exactly why the "
            "public relay exists; register the relay's HTTPS URL here.")
    if parsed.query or parsed.fragment:
        raise MercadoLivreOAuthConfigurationError(
            f"{REDIRECT_URI_ENV_VAR} must not carry a query string or "
            "fragment; it has to match the registered value exactly.")
    return value


def resolve_loopback_port(environ=None) -> int:
    """Local listener port. Must agree with the relay's configuration."""
    env = os.environ if environ is None else environ
    raw = (env.get(LOOPBACK_PORT_ENV_VAR) or "").strip()
    if not raw:
        return DEFAULT_LOOPBACK_PORT
    if not raw.isdigit() or not 1024 <= int(raw) <= 65535:
        raise MercadoLivreOAuthConfigurationError(
            f"{LOOPBACK_PORT_ENV_VAR} must be a port between 1024 and 65535.")
    return int(raw)


def authorization_host(site_id: str = DEFAULT_SITE_ID) -> str:
    host = AUTHORIZATION_HOSTS.get(site_id)
    if host is None:
        raise MercadoLivreOAuthConfigurationError(
            f"unknown site id {site_id!r}; known: "
            f"{', '.join(sorted(AUTHORIZATION_HOSTS))}")
    return host


def build_authorization_url(*, client_id: str, redirect_uri: str, state: str,
                            code_challenge: str,
                            site_id: str = DEFAULT_SITE_ID) -> str:
    """The URL the user opens to grant consent.

    `code_challenge_method` is always S256. The plain method is never
    offered: it would put the verifier itself in the browser.
    """
    validate_redirect_uri(redirect_uri)
    if not _STATE_RE.match(state):
        raise ValueError("state must be 32-128 url-safe characters")
    if not code_challenge or "=" in code_challenge:
        raise ValueError("code_challenge must be unpadded base64url")
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{authorization_host(site_id)}?{urlencode(params)}"


# -- callback interpretation (pure) -------------------------------------

OUTCOME_SUCCESS = "success"
OUTCOME_PROVIDER_ERROR = "provider_error"
OUTCOME_STATE_MISMATCH = "state_mismatch"
OUTCOME_MALFORMED = "malformed"
OUTCOME_REPLAY = "replay"
OUTCOME_IGNORE = "ignore"


@dataclass(frozen=True)
class CallbackOutcome:
    """What one inbound loopback request means. Carries no secret."""

    kind: str
    code: str | None = None
    error: str | None = None
    error_description: str | None = None
    detail: str | None = None

    def __repr__(self) -> str:
        # `code` is single-use and PKCE-bound, but it still has no place
        # in a traceback or a log line.
        return (f"CallbackOutcome(kind={self.kind!r}, "
                f"code={'<present>' if self.code else None}, "
                f"error={self.error!r}, detail={self.detail!r})")


def interpret_callback(path: str, expected_state: str, *,
                       already_consumed: bool = False) -> CallbackOutcome:
    """Decide what an inbound request to the loopback listener means.

    Pure: no sockets, no clock, no mutation. The state check happens
    HERE, before the code is handed to anything that could spend it.
    """
    raw_path, _, query = (path or "").partition("?")
    if raw_path != LOOPBACK_PATH:
        # Browsers probe /favicon.ico and similar. Not an error; keep
        # waiting rather than aborting the authorization.
        return CallbackOutcome(OUTCOME_IGNORE,
                               detail=f"ignored request to {raw_path!r}")

    pairs = parse_qsl(query, keep_blank_values=True)
    params: dict[str, str] = {}
    for key, value in pairs:
        if key in params:
            return CallbackOutcome(
                OUTCOME_MALFORMED,
                detail="a query parameter was supplied more than once")
        params[key] = value

    if already_consumed:
        # A second callback after a successful one is a replay. The first
        # result is kept; this one is refused and recorded.
        return CallbackOutcome(
            OUTCOME_REPLAY,
            detail="this authorization callback was already consumed")

    state = params.get("state", "")

    if "error" in params:
        error = params.get("error", "")
        if not _ERROR_RE.match(error):
            return CallbackOutcome(OUTCOME_MALFORMED,
                                   detail="malformed error parameter")
        # State is still checked when present: an unsolicited "error"
        # must not be able to abort a flow it does not belong to.
        if state and not verify_state(expected_state, state):
            return CallbackOutcome(
                OUTCOME_STATE_MISMATCH,
                detail="state did not match on an error callback")
        return CallbackOutcome(
            OUTCOME_PROVIDER_ERROR, error=error,
            error_description=params.get("error_description") or None,
            detail="the provider reported an authorization failure")

    code = params.get("code", "")
    if not code or not state:
        return CallbackOutcome(OUTCOME_MALFORMED,
                               detail="code and state are both required")
    if not _CODE_RE.match(code):
        return CallbackOutcome(OUTCOME_MALFORMED,
                               detail="malformed code parameter")
    if not verify_state(expected_state, state):
        # The decisive check. A code arriving with the wrong state is
        # discarded unspent -- it is never exchanged "just in case".
        return CallbackOutcome(
            OUTCOME_STATE_MISMATCH,
            detail="state did not match the value generated for this run")

    return CallbackOutcome(OUTCOME_SUCCESS, code=code)


def extract_callback_from_url(url: str, expected_state: str) -> CallbackOutcome:
    """Manual fallback: interpret a pasted loopback URL.

    Used when a browser refuses to follow the relay's redirect to a
    loopback address. Accepts the path+query of the pasted URL and runs
    exactly the same validation as the listener -- no shortcut, no
    relaxed state check.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme and parsed.scheme not in ("http", "https"):
        return CallbackOutcome(OUTCOME_MALFORMED,
                               detail="pasted value is not an http(s) URL")
    if parsed.hostname and parsed.hostname != LOOPBACK_HOST:
        return CallbackOutcome(
            OUTCOME_MALFORMED,
            detail=f"pasted URL must point at {LOOPBACK_HOST}")
    path = parsed.path or LOOPBACK_PATH
    return interpret_callback(
        f"{path}?{parsed.query}" if parsed.query else path, expected_state)


# -- loopback listener --------------------------------------------------


_LISTENER_PAGE = (
    "<!doctype html><meta charset=\"utf-8\"><title>RAVZ</title>"
    "<h1>{title}</h1><p>{body}</p>"
)


class _CallbackHandler(BaseHTTPRequestHandler):
    """Single-shot handler. Stores the outcome on the server object."""

    def log_message(self, fmt, *args):  # noqa: D102 - silence; see module doc
        return

    def do_GET(self):  # noqa: N802 - BaseHTTPRequestHandler API
        server = self.server
        outcome = interpret_callback(
            self.path, server.expected_state,
            already_consumed=server.outcome is not None
            and server.outcome.kind == OUTCOME_SUCCESS)

        if outcome.kind == OUTCOME_IGNORE:
            self._respond(404, "Not found", "Nothing here.")
            return

        if outcome.kind == OUTCOME_SUCCESS:
            server.outcome = outcome
            self._respond(
                200, "Authorization received",
                "You can close this tab and return to the terminal. No "
                "token was shown here.")
            return

        if outcome.kind == OUTCOME_REPLAY:
            server.replays += 1
            self._respond(409, "Already used",
                          "This callback was already handled.")
            return

        server.outcome = outcome
        self._respond(400, "Authorization could not be completed",
                      "Return to the terminal for the reason.")

    def _respond(self, status: int, title: str, body: str):
        payload = _LISTENER_PAGE.format(title=title, body=body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        self.wfile.write(payload)


class LoopbackCallbackServer(HTTPServer):
    """Loopback-only HTTP server used for exactly one authorization."""

    def __init__(self, port: int, expected_state: str):
        super().__init__((LOOPBACK_HOST, port), _CallbackHandler)
        self.expected_state = expected_state
        self.outcome: CallbackOutcome | None = None
        self.replays = 0


def wait_for_callback(expected_state: str, *, port: int,
                      timeout_seconds: float = DEFAULT_CALLBACK_WAIT_SECONDS,
                      server_factory=LoopbackCallbackServer) -> CallbackOutcome:
    """Serve on 127.0.0.1 until one real callback arrives, or time out.

    Binds BEFORE the browser is sent anywhere, so a port already in use
    is an explicit, immediate failure rather than a silent handover of
    the authorization code to whatever was listening.
    """
    # Recorded in the handler, raised AFTER it. `from None` would be
    # insufficient: it clears __cause__ but leaves __context__ holding
    # the original, which a chain-walking log formatter can still read.
    # Same rule as the token request below and the two HTTP integrations.
    bind_error = None
    server = None

    try:
        server = server_factory(port, expected_state)
    except OSError as exc:
        bind_error = MercadoLivreOAuthConfigurationError(
            f"could not listen on {LOOPBACK_HOST}:{port} "
            f"({type(exc).__name__}). Another process may be using it. "
            f"Choose a different port with {LOOPBACK_PORT_ENV_VAR} and "
            "update the relay's own port setting to match.")

    if bind_error is not None:
        raise bind_error

    deadline = _monotonic() + timeout_seconds
    try:
        server.timeout = 1.0
        while server.outcome is None:
            if _monotonic() >= deadline:
                raise MercadoLivreOAuthTimeoutError(
                    f"no authorization callback arrived within "
                    f"{timeout_seconds:.0f}s")
            server.handle_request()
        return server.outcome
    finally:
        server.server_close()


def _monotonic() -> float:
    """Indirection so the wait loop is testable without sleeping."""
    import time

    return time.monotonic()


# -- tokens -------------------------------------------------------------


@dataclass(frozen=True)
class TokenSet:
    """Credentials obtained from the token endpoint.

    `__repr__` is overridden so neither token can reach a log line, a
    traceback or an f-string by accident. That is the whole reason this
    is not a plain dict.
    """

    access_token: str
    refresh_token: str | None
    token_type: str | None
    expires_in: int | None
    scope: str | None
    user_id: int | None
    obtained_at: str

    def __repr__(self) -> str:
        return (
            "TokenSet(access_token=<redacted>, refresh_token="
            f"{'<redacted>' if self.refresh_token else None}, "
            f"token_type={self.token_type!r}, expires_in={self.expires_in!r}, "
            f"scope={self.scope!r}, user_id={self.user_id!r}, "
            f"obtained_at={self.obtained_at!r})")

    __str__ = __repr__

    def expires_at(self) -> str | None:
        if self.expires_in is None:
            return None
        obtained = datetime.fromisoformat(self.obtained_at)
        return (obtained + timedelta(seconds=self.expires_in)).isoformat()

    def describe(self) -> str:
        """Metadata only. Deliberately cannot render a token value."""
        return "\n".join([
            f"  token_type     : {self.token_type or 'unknown'}",
            f"  expires_in     : {self.expires_in} s",
            f"  expires_at     : {self.expires_at() or 'unknown'}",
            f"  scope          : {self.scope or 'not reported'}",
            f"  user_id        : {self.user_id if self.user_id is not None else 'not reported'}",
            f"  access token   : configured (value not shown)",
            f"  refresh token  : "
            f"{'configured (value not shown)' if self.refresh_token else 'NOT returned'}",
            f"  obtained_at    : {self.obtained_at}",
        ])


def _utc_now_iso() -> str:
    """Provenance only -- never an input to any score."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _post_token_request(payload: dict, timeout: float) -> dict:
    """POST to the token endpoint and return parsed JSON.

    Error translation follows the pattern established by the two
    existing integrations: the failure is recorded inside the handler
    and raised AFTER it, so no original exception stays reachable
    through `__context__`. `requests` embeds request bodies -- here the
    client secret and the code -- in some transport errors, so their
    messages are withheld entirely.
    """
    transport_error = None
    response = None

    try:
        response = requests.post(
            TOKEN_URL,
            data=payload,
            headers={
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
            },
            timeout=timeout,
        )
    except requests.Timeout:
        transport_error = MercadoLivreOAuthTimeoutError(
            f"the Mercado Livre token endpoint did not respond within "
            f"{timeout}s")
    except requests.ConnectionError:
        transport_error = MercadoLivreOAuthConnectionError(
            "could not connect to the Mercado Livre token endpoint")
    except requests.RequestException as exc:
        transport_error = MercadoLivreOAuthError(
            f"the token request failed ({type(exc).__name__}); detail "
            "withheld because transport errors can embed the request body")

    if transport_error is not None:
        raise transport_error

    if response.status_code != 200:
        # The provider's short machine-readable `error` is included only
        # when it matches a safe shape. The body is never echoed: it can
        # restate request parameters.
        code = None
        try:
            body = response.json()
            candidate = str(body.get("error", ""))
            if _ERROR_RE.match(candidate):
                code = candidate
        except Exception:  # noqa: BLE001 - body shape is not trusted
            code = None
        suffix = f" (provider error: {code})" if code else ""
        raise MercadoLivreOAuthResponseError(
            response.status_code,
            f"the token endpoint returned HTTP {response.status_code}"
            f"{suffix}; response body withheld")

    # Raised after the handler, not inside it. A JSONDecodeError keeps
    # the ENTIRE response body on its `.doc` attribute -- here that body
    # is the token payload -- and `from None` would leave it reachable
    # through __context__.
    decode_error = None
    data = None

    try:
        data = response.json()
    except ValueError:
        decode_error = MercadoLivreOAuthDataError(
            "the token endpoint returned a response that was not JSON")

    if decode_error is not None:
        raise decode_error

    if not isinstance(data, dict):
        raise MercadoLivreOAuthDataError(
            "the token endpoint returned JSON that was not an object")
    return data


def _token_set_from_payload(data: dict) -> TokenSet:
    access = data.get("access_token")
    if not access or not isinstance(access, str):
        # No token means no authorization. Never substituted, never
        # partially accepted.
        raise MercadoLivreOAuthDataError(
            "the token response contained no access_token")
    expires_in = data.get("expires_in")
    user_id = data.get("user_id")
    return TokenSet(
        access_token=access,
        refresh_token=data.get("refresh_token") or None,
        token_type=data.get("token_type") or None,
        expires_in=int(expires_in) if isinstance(expires_in, int) else None,
        scope=data.get("scope") or None,
        user_id=int(user_id) if isinstance(user_id, int) else None,
        obtained_at=_utc_now_iso(),
    )


def exchange_code_for_tokens(*, code: str, code_verifier: str, client_id: str,
                             client_secret: str, redirect_uri: str,
                             timeout: float = DEFAULT_TIMEOUT) -> TokenSet:
    """Exchange one authorization code for tokens. One request, no retry.

    `code_verifier` is required: with PKCE enabled on the application,
    Mercado Livre rejects an exchange without it -- which is what makes
    an intercepted code useless.
    """
    if not code:
        raise ValueError("code must not be empty")
    if not code_verifier:
        raise ValueError("code_verifier must not be empty")
    validate_redirect_uri(redirect_uri)
    return _token_set_from_payload(_post_token_request({
        "grant_type": "authorization_code",
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": code_verifier,
    }, timeout))


def refresh_access_token(*, refresh_token: str, client_id: str,
                         client_secret: str,
                         timeout: float = DEFAULT_TIMEOUT) -> TokenSet:
    """Renew an access token.

    Mercado Livre's refresh token is SINGLE USE: a successful refresh
    returns a new one and invalidates the old. The caller must persist
    the new set immediately or the next refresh will fail.
    """
    if not refresh_token:
        raise ValueError("refresh_token must not be empty")
    return _token_set_from_payload(_post_token_request({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }, timeout))


# -- local credential file ----------------------------------------------


def write_token_file(tokens: TokenSet, path: pathlib.Path = TOKEN_FILE) -> pathlib.Path:
    """Write credentials to a git-ignored local file, owner-only.

    The values are written to disk and NOT printed: a terminal keeps
    scrollback, and this project's rule is that code may report whether
    a secret is configured, never its value. Copy the value from this
    file into `.env` yourself.

    On Windows the POSIX mode bits are advisory; the containing
    directory is the real boundary there.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    document = {
        "_warning": "CREDENTIALS. Never commit, paste or share this file.",
        "access_token": tokens.access_token,
        "refresh_token": tokens.refresh_token,
        "token_type": tokens.token_type,
        "expires_in": tokens.expires_in,
        "expires_at": tokens.expires_at(),
        "scope": tokens.scope,
        "user_id": tokens.user_id,
        "obtained_at": tokens.obtained_at,
    }
    descriptor = os.open(str(path), os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2, sort_keys=True)
        handle.write("\n")
    return path


def read_refresh_token(path: pathlib.Path = TOKEN_FILE) -> str:
    """Read the stored refresh token, for the refresh subcommand."""
    path = pathlib.Path(path)
    if not path.exists():
        raise MercadoLivreOAuthConfigurationError(
            f"no stored credentials at {path}; run the authorize step first.")
    # Same reasoning as the token response: a JSONDecodeError carries the
    # whole document, and this document is the credential file.
    decode_error = None
    document = None

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        decode_error = MercadoLivreOAuthDataError(f"{path} is not valid JSON")

    if decode_error is not None:
        raise decode_error

    value = document.get("refresh_token")
    if not value:
        raise MercadoLivreOAuthConfigurationError(
            f"{path} holds no refresh_token; re-run the authorize step.")
    return value


# -- CLI ----------------------------------------------------------------


def _resolved_settings(environ=None, *, need_secret: bool):
    env = os.environ if environ is None else environ
    client_id = _require_env(CLIENT_ID_ENV_VAR, env)
    redirect_uri = validate_redirect_uri(_require_env(REDIRECT_URI_ENV_VAR, env))
    client_secret = _require_env(CLIENT_SECRET_ENV_VAR, env) if need_secret else None
    return client_id, client_secret, redirect_uri, resolve_loopback_port(env)


def _command_plan() -> int:
    """Offline: print exactly what the authorize step would do."""
    client_id, _, redirect_uri, port = _resolved_settings(need_secret=False)
    state = generate_state()
    verifier = generate_code_verifier()
    challenge = derive_code_challenge(verifier)
    print("Mercado Livre OAuth -- PLAN (nothing was sent, no listener opened)")
    print(f"  authorization host : {authorization_host()}")
    print(f"  token endpoint     : {TOKEN_URL}")
    print(f"  redirect_uri       : {redirect_uri}")
    print(f"  loopback relay to  : http://{LOOPBACK_HOST}:{port}{LOOPBACK_PATH}")
    print(f"  client_id          : configured (value not shown)")
    print(f"  client_secret      : not required for this subcommand")
    print(f"  state              : freshly generated, {len(state)} chars "
          "(discarded -- this is a dry run)")
    print(f"  code_challenge     : S256, {len(challenge)} chars")
    print("\nThe verifier for this dry run is discarded. Nothing is reusable.")
    return 0


def _command_authorize(wait_seconds: float) -> int:
    client_id, client_secret, redirect_uri, port = _resolved_settings(
        need_secret=True)
    state = generate_state()
    verifier = generate_code_verifier()
    url = build_authorization_url(
        client_id=client_id, redirect_uri=redirect_uri, state=state,
        code_challenge=derive_code_challenge(verifier))

    print("Open this URL in a browser signed in to the Mercado Livre account")
    print("that owns the application, and grant access:\n")
    print(url)
    print(f"\nWaiting up to {wait_seconds:.0f}s for the relay to return to "
          f"http://{LOOPBACK_HOST}:{port}{LOOPBACK_PATH} ...")

    try:
        outcome = wait_for_callback(state, port=port,
                                    timeout_seconds=wait_seconds)
    except MercadoLivreOAuthTimeoutError as exc:
        print(f"\n{exc}")
        print("If the browser refused to open the 127.0.0.1 address, copy the")
        print("address it tried to open and paste it here.")
        pasted = input("Callback URL (or blank to abort): ").strip()
        if not pasted:
            print("Aborted. No code was exchanged.")
            return 1
        outcome = extract_callback_from_url(pasted, state)

    if outcome.kind == OUTCOME_PROVIDER_ERROR:
        print(f"\nAuthorization FAILED: provider reported {outcome.error!r}")
        if outcome.error_description:
            print(f"  description: {outcome.error_description}")
        print("No code was issued, so nothing was exchanged.")
        return 1
    if outcome.kind != OUTCOME_SUCCESS:
        print(f"\nAuthorization REJECTED locally: {outcome.kind} -- "
              f"{outcome.detail}")
        print("The code (if any) was discarded unspent.")
        return 1

    print("\nState verified. Exchanging the code (one request, no retry) ...")
    tokens = exchange_code_for_tokens(
        code=outcome.code, code_verifier=verifier, client_id=client_id,
        client_secret=client_secret, redirect_uri=redirect_uri)
    path = write_token_file(tokens)
    print(f"\nAuthorization COMPLETE. Credentials written to {path}")
    print(tokens.describe())
    print("\nNext: open that file, copy the access_token value into .env as")
    print("  MERCADO_LIVRE_ACCESS_TOKEN=<value>")
    print("Nothing was printed here that could be pasted into a ticket.")
    return 0


def _command_refresh() -> int:
    client_id, client_secret, _, _ = _resolved_settings(need_secret=True)
    stored = read_refresh_token()
    print("Refreshing (one request, no retry) ...")
    tokens = refresh_access_token(
        refresh_token=stored, client_id=client_id, client_secret=client_secret)
    # Persist immediately: the old refresh token is now dead.
    path = write_token_file(tokens)
    print(f"Refreshed. New credentials written to {path}")
    print(tokens.describe())
    print("\nThe previous refresh token is now invalid (Mercado Livre rotates")
    print("it on every refresh). The stored file already holds the new one.")
    return 0


USAGE = """Usage: python -m src.integrations.mercadolivre_oauth <command>

Commands:
  plan       Offline. Print the endpoints, redirect URI and loopback
             destination that would be used. Sends nothing.
  authorize  Run the authorization-code + PKCE flow once and store the
             resulting credentials locally.
  refresh    Exchange the stored refresh token for a new token set.

Environment variable NAMES (values live in .env, never here):
  MERCADO_LIVRE_CLIENT_ID
  MERCADO_LIVRE_CLIENT_SECRET
  MERCADO_LIVRE_REDIRECT_URI
  MERCADO_LIVRE_OAUTH_LOOPBACK_PORT   (optional)
"""


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""
    try:
        if command == "plan":
            return _command_plan()
        if command == "authorize":
            return _command_authorize(DEFAULT_CALLBACK_WAIT_SECONDS)
        if command == "refresh":
            return _command_refresh()
        print(USAGE)
        return 2
    except MercadoLivreOAuthError as exc:
        # One line, no credential, no chained provider exception.
        print(f"{type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
