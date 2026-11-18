/**
 * Stateless Mercado Livre OAuth callback relay (Cloudflare Worker).
 *
 * Deployed as its own Cloudflare Worker (`ravz-ml-oauth`). It is NOT part
 * of the RAVZ commercial website and shares no code, domain, DNS record
 * or deployment with it.
 *
 * == Why this service has to exist at all ==
 *
 * Mercado Livre requires the registered `redirect_uri` to use HTTPS and
 * does not accept a loopback/localhost address. The local Python
 * application therefore cannot receive the authorization redirect
 * directly. Something public and HTTPS has to catch it.
 *
 * == What it does, and the whole of what it does ==
 *
 *     browser --(HTTPS, ?code&state)--> /api/mercadolivre/callback
 *     this worker --(302)--> http://127.0.0.1:<fixed port>/callback?code&state
 *
 * That is all. It is a *relay*: it validates the SHAPE of what arrived
 * and forwards it to one hardcoded destination.
 *
 * == What never passes through here ==
 *
 * - No access token, no refresh token. This worker never calls the token
 *   endpoint, so no token ever exists in this isolate.
 * - No client secret. It is not configured here and is not needed here.
 * - No user data, no cookies, no session, no KV, no D1, no R2.
 *
 * What does cross the public hop is the authorization `code` and
 * `state`. Neither is a credential on its own:
 *
 * - the code is single-use, short-lived, and bound by PKCE S256 to a
 *   `code_verifier` that is generated inside the local Python process
 *   and never leaves that process. An intercepted code cannot be
 *   exchanged.
 * - the state is a random nonce generated locally and validated
 *   locally. Mercado Livre documents that it does NOT validate `state`,
 *   so that check belongs to the local application, which is where it
 *   lives.
 *
 * == Why there is no database ==
 *
 * The relay holds no state, so there is nothing to store. `state` and
 * the PKCE verifier live in the local process that created them -- the
 * only place that can validate them. Adding a store here would move
 * security material into the public tier to no benefit.
 *
 * == Open redirect ==
 *
 * Structurally impossible. The destination host is the literal
 * "127.0.0.1" in this file and the path is the literal "/callback". No
 * request input selects, influences or is appended to the destination
 * host, scheme or path. Only `code`, `state`, `error` and a sanitized
 * `error_description` are relayed, each re-encoded. There is no `next`,
 * `return_to` or `redirect_uri` parameter to abuse.
 *
 * == Logging ==
 *
 * This file contains no `console` call of any kind, so no authorization
 * code can reach Workers Logs through application logging, and
 * `observability` is disabled in wrangler.toml. Cloudflare's own
 * edge request logging is outside this file's control and may record
 * the request URL; the code's single-use + PKCE binding is what makes
 * that acceptable rather than a leak. See docs/MERCADO_LIVRE_OAUTH.md.
 *
 * Zero dependencies and zero imports -- Workers runtime built-ins only,
 * so there is no supply chain and no bundling surprise.
 *
 * The shape contracts and the destination literals below are mirrored in
 * src/integrations/mercadolivre_oauth.py. The two sides of this hop are
 * separate deployments and cannot share code, so
 * tests/test_oauth_worker_contract.py asserts they stay identical.
 */

// -- the destination, hardcoded ----------------------------------------
//
// Host and path are literals. The port is the only configurable part and
// it is validated as a port number, so configuration can select WHICH
// local port receives the relay but can never change WHERE it goes.
export const LOOPBACK_HOST = "127.0.0.1";
export const LOOPBACK_PATH = "/callback";
export const DEFAULT_LOOPBACK_PORT = 53682;
export const PORT_VAR = "RAVZ_OAUTH_LOOPBACK_PORT";

// The single route this worker answers. Unlike a filesystem-routed
// platform, a Worker receives every path, so the path is checked here.
export const CALLBACK_PATH = "/api/mercadolivre/callback";

// -- accepted shapes ---------------------------------------------------
//
// Exported as bare "cores" (no anchors) because JavaScript has no \A/\Z.
// The Python side anchors the same cores with \A...\Z; a JS `^...$`
// without the `m` flag is equivalent -- unlike Python's `$`, JS `$`
// does not also match before a trailing newline.
export const STATE_CORE = "[A-Za-z0-9_-]{32,128}";
export const CODE_CORE = "[A-Za-z0-9._~$-]{16,512}";
export const ERROR_CORE = "[A-Za-z0-9_-]{1,64}";

const STATE_RE = new RegExp(`^${STATE_CORE}$`);
const CODE_RE = new RegExp(`^${CODE_CORE}$`);
const ERROR_RE = new RegExp(`^${ERROR_CORE}$`);

// `error_description` is provider free text. It is useful for diagnosis,
// so it is relayed -- but reduced to a safe charset and truncated first,
// then re-encoded by URLSearchParams.
export const DESCRIPTION_DISALLOWED_CORE = "[^A-Za-z0-9 .,_:-]";
export const DESCRIPTION_MAX = 200;
const DESCRIPTION_DISALLOWED = new RegExp(DESCRIPTION_DISALLOWED_CORE, "g");

// Fixed reason codes. The error page shows one of these and NEVER echoes
// any request input, so there is nothing to reflect back at the browser.
export const REASON_METHOD = "method_not_allowed";
export const REASON_NOT_FOUND = "unknown_route";
export const REASON_DUPLICATE_PARAM = "duplicate_parameter";
export const REASON_MISSING_PARAMS = "missing_code_or_state";
export const REASON_BAD_STATE = "malformed_state";
export const REASON_BAD_CODE = "malformed_code";
export const REASON_BAD_ERROR_CODE = "malformed_error";
export const REASON_MISCONFIGURED = "service_misconfigured";

export const SECURITY_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
  Pragma: "no-cache",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  // 'none' everywhere: these pages load no script, style, image or font.
  "Content-Security-Policy":
    "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
  "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
  // Deliberately WITHOUT includeSubDomains: this service must not be
  // able to impose transport policy on any other host, least of all the
  // commercial site.
  "Strict-Transport-Security": "max-age=31536000",
};

/**
 * Resolve the local port to relay to.
 *
 * Returns null when the variable is SET but not a valid port. Failing
 * closed is deliberate: silently falling back to the default would
 * relay the authorization code to a different local listener than the
 * operator configured.
 */
export function resolveLoopbackPort(env) {
  const raw = ((env && env[PORT_VAR]) || "").trim();
  if (raw === "") {
    return DEFAULT_LOOPBACK_PORT;
  }
  if (!/^[0-9]+$/.test(raw)) {
    return null;
  }
  const port = Number(raw);
  // Unprivileged ports only; a loopback listener run by a normal user
  // cannot bind below 1024 anyway.
  if (port < 1024 || port > 65535) {
    return null;
  }
  return port;
}

/**
 * Parse the query, rejecting any repeated parameter.
 *
 * Duplicate parameters are a parameter-pollution vector: one value would
 * be validated and a different one potentially relayed, depending on
 * which side picks first/last. Rejecting outright removes the ambiguity
 * instead of resolving it.
 */
function singleValued(queryString) {
  const params = new Map();
  for (const [key, value] of new URLSearchParams(queryString || "")) {
    if (params.has(key)) {
      return null;
    }
    params.set(key, value);
  }
  return params;
}

function sanitizeDescription(value) {
  return value
    .replace(DESCRIPTION_DISALLOWED, " ")
    .slice(0, DESCRIPTION_MAX)
    .trim();
}

/**
 * Assemble the one permitted destination.
 *
 * Scheme, host and path are literals here. `relayed` only ever
 * contributes query values, and URLSearchParams escapes them, so no
 * input can introduce a second `?`, a `#`, a `\` or a new authority.
 */
function buildLocation(port, relayed) {
  const query = new URLSearchParams(
    [...relayed.entries()].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)),
  );
  return `http://${LOOPBACK_HOST}:${port}${LOOPBACK_PATH}?${query.toString()}`;
}

/**
 * Pure relay logic: query string in, decision out.
 *
 * Every rejection path returns a fixed reason code. No request value is
 * ever placed in an error page.
 */
export function decide(queryString, { port }) {
  if (port === null || port === undefined) {
    return {
      kind: "error",
      status: 500,
      reason: REASON_MISCONFIGURED,
      detail:
        `${PORT_VAR} is set to a value that is not a usable port. ` +
        "The service refuses to guess a destination.",
    };
  }

  const params = singleValued(queryString);
  if (params === null) {
    return {
      kind: "error",
      status: 400,
      reason: REASON_DUPLICATE_PARAM,
      detail: "A query parameter was supplied more than once.",
    };
  }

  const relayed = new Map();
  const state = params.get("state") || "";

  if (state !== "" && !STATE_RE.test(state)) {
    return {
      kind: "error",
      status: 400,
      reason: REASON_BAD_STATE,
      detail: "The state parameter is not the expected shape.",
    };
  }

  // Provider-reported failure (user denied consent, bad client, ...).
  // Relayed so the LOCAL application fails explicitly with a reason
  // instead of sitting on a listener that never fires.
  if (params.has("error")) {
    const error = params.get("error") || "";
    if (!ERROR_RE.test(error)) {
      return {
        kind: "error",
        status: 400,
        reason: REASON_BAD_ERROR_CODE,
        detail: "The error parameter is not the expected shape.",
      };
    }
    relayed.set("error", error);
    const description = sanitizeDescription(params.get("error_description") || "");
    if (description !== "") {
      relayed.set("error_description", description);
    }
    if (state !== "") {
      relayed.set("state", state);
    }
    return { kind: "relay", location: buildLocation(port, relayed) };
  }

  const code = params.get("code") || "";
  if (code === "" || state === "") {
    return {
      kind: "error",
      status: 400,
      reason: REASON_MISSING_PARAMS,
      detail: "Both code and state are required.",
    };
  }
  if (!CODE_RE.test(code)) {
    return {
      kind: "error",
      status: 400,
      reason: REASON_BAD_CODE,
      detail: "The code parameter is not the expected shape.",
    };
  }

  relayed.set("code", code);
  relayed.set("state", state);
  return { kind: "relay", location: buildLocation(port, relayed) };
}

export const RELAY_BODY =
  '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
  "<title>RAVZ - returning to the local application</title></head>" +
  "<body><h1>Returning to the local application</h1>" +
  "<p>You are being returned to the RAVZ Product Hunter running on this " +
  "computer. If your browser does not continue automatically, copy the " +
  "address it was about to open (it starts with " +
  "<code>http://127.0.0.1</code>) and paste it into the terminal when " +
  "asked.</p>" +
  "<p>No access token and no credential passed through this page.</p>" +
  "</body></html>";

export function errorBody(reason, detail) {
  return (
    '<!doctype html><html lang="en"><head><meta charset="utf-8">' +
    "<title>RAVZ - authorization could not be relayed</title></head>" +
    "<body><h1>Authorization could not be relayed</h1>" +
    `<p>${detail}</p>` +
    `<p>Reason code: <code>${reason}</code></p>` +
    "<p>Nothing was stored and no credential was exposed. Start the " +
    "authorization again from the local application.</p>" +
    "</body></html>"
  );
}

function respond(status, body, extraHeaders) {
  const headers = new Headers(SECURITY_HEADERS);
  headers.set("Content-Type", "text/html; charset=utf-8");
  for (const [name, value] of Object.entries(extraHeaders || {})) {
    headers.set(name, value);
  }
  return new Response(body, { status, headers });
}

/**
 * Turn a decision into a Response. Separated from `decide` so the
 * decision logic stays testable without the Workers runtime.
 */
export function toResponse(decision) {
  if (decision.kind === "relay") {
    return respond(302, RELAY_BODY, { Location: decision.location });
  }
  return respond(decision.status, errorBody(decision.reason, decision.detail));
}

export function handleRequest(request, env) {
  const url = new URL(request.url);

  // A Worker receives every path on the hostname, so the single
  // supported route is enforced here rather than by a filesystem.
  if (url.pathname !== CALLBACK_PATH) {
    return respond(
      404,
      errorBody(REASON_NOT_FOUND, "This address is not part of the flow."),
    );
  }

  if (request.method !== "GET") {
    return respond(
      405,
      errorBody(REASON_METHOD, "This endpoint only accepts GET."),
      { Allow: "GET" },
    );
  }

  const queryString = url.search.startsWith("?")
    ? url.search.slice(1)
    : url.search;
  return toResponse(decide(queryString, { port: resolveLoopbackPort(env) }));
}

export default {
  fetch(request, env) {
    return handleRequest(request, env);
  },
};
