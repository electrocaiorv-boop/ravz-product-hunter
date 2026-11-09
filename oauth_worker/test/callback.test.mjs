/**
 * Offline tests for the Mercado Livre OAuth callback relay.
 *
 * No credentials, no network, no deployment, no dependencies: Node's
 * built-in test runner plus the Workers-compatible globals that Node
 * already provides (Request, Response, Headers, URL, URLSearchParams).
 *
 *     npm test --prefix oauth_worker
 *     # or: node --test oauth_worker/test/
 *
 * What these tests are really protecting:
 *
 * - the relay destination is FIXED. No request input may influence the
 *   scheme, host or path it redirects to (open-redirect prevention).
 * - nothing from the request is ever echoed into an error page.
 * - malformed input is refused rather than normalised and forwarded.
 * - only the one documented route answers; everything else is 404.
 *
 * The cross-language contract (that these shapes still match the local
 * Python helper's) is asserted by tests/test_oauth_worker_contract.py,
 * so it runs inside the project's primary pytest gate too.
 */

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import worker, {
  CALLBACK_PATH,
  DEFAULT_LOOPBACK_PORT,
  DESCRIPTION_MAX,
  PORT_VAR,
  REASON_BAD_CODE,
  REASON_BAD_ERROR_CODE,
  REASON_BAD_STATE,
  REASON_DUPLICATE_PARAM,
  REASON_METHOD,
  REASON_MISCONFIGURED,
  REASON_MISSING_PARAMS,
  REASON_NOT_FOUND,
  SECURITY_HEADERS,
  decide,
  errorBody,
  resolveLoopbackPort,
} from "../src/callback.js";

const GOOD_STATE = "S".repeat(43);
const GOOD_CODE = "TG-1234567890abcdef-123456789";
const DEFAULT_PREFIX = "http://127.0.0.1:53682/callback?";
const SOURCE = readFileSync(new URL("../src/callback.js", import.meta.url), "utf8");

const defaultEnv = {};

function get(path, env = defaultEnv) {
  return worker.fetch(new Request(`https://oauth.test${path}`), env);
}

// -- happy path --------------------------------------------------------

test("valid code and state relay to the fixed loopback destination", () => {
  const decision = decide(`code=${GOOD_CODE}&state=${GOOD_STATE}`, { port: 53682 });
  assert.equal(decision.kind, "relay");
  assert.ok(decision.location.startsWith(DEFAULT_PREFIX));
  assert.ok(decision.location.includes(`code=${GOOD_CODE}`));
  assert.ok(decision.location.includes(`state=${GOOD_STATE}`));
});

test("relay destination uses the configured port", () => {
  const decision = decide(`code=${GOOD_CODE}&state=${GOOD_STATE}`, { port: 54321 });
  assert.ok(decision.location.startsWith("http://127.0.0.1:54321/callback?"));
});

test("relay ignores unknown extra parameters", () => {
  const decision = decide(
    `code=${GOOD_CODE}&state=${GOOD_STATE}&foo=bar&utm_source=x`,
    { port: 53682 },
  );
  assert.equal(decision.kind, "relay");
  assert.ok(!decision.location.includes("foo"));
  assert.ok(!decision.location.includes("utm_source"));
});

// -- open redirect: the property that matters most ---------------------

for (const hostile of [
  "redirect_uri=https://evil.example",
  "next=https://evil.example",
  "return_to=//evil.example",
  "url=http://evil.example",
  "host=evil.example",
  "port=9999",
]) {
  test(`no parameter can redirect anywhere but loopback: ${hostile}`, () => {
    const decision = decide(
      `code=${GOOD_CODE}&state=${GOOD_STATE}&${hostile}`,
      { port: 53682 },
    );
    assert.equal(decision.kind, "relay");
    assert.ok(decision.location.startsWith(DEFAULT_PREFIX));
    assert.ok(!decision.location.includes("evil.example"));
    assert.equal(decision.location.split("http://").length - 1, 1);
  });
}

for (const payload of [
  "@evil.example",
  "/../../evil",
  "x#@evil.example",
  "x?next=https://evil.example",
  "x\\evil.example",
  "x%2f%2fevil.example",
]) {
  test(`hostile code value refused, not normalised: ${payload}`, () => {
    const decision = decide(`code=${payload}&state=${GOOD_STATE}`, { port: 53682 });
    assert.equal(decision.kind, "error");
    assert.equal(decision.status, 400);
  });
}

for (const payload of [
  "@evil.example",
  "short",
  "has spaces in it and is long enough",
  "A".repeat(200),
  "S".repeat(31),
]) {
  test(`hostile or misshaped state refused: ${payload.slice(0, 20)}`, () => {
    const decision = decide(`code=${GOOD_CODE}&state=${payload}`, { port: 53682 });
    assert.equal(decision.kind, "error");
    assert.equal(decision.status, 400);
  });
}

test("destination host and path are literals in the source", () => {
  assert.ok(SOURCE.includes('export const LOOPBACK_HOST = "127.0.0.1";'));
  assert.ok(SOURCE.includes('export const LOOPBACK_PATH = "/callback";'));
  assert.ok(
    SOURCE.includes("`http://${LOOPBACK_HOST}:${port}${LOOPBACK_PATH}?${query.toString()}`"),
  );
});

// -- malformed and missing input ---------------------------------------

test("missing both parameters is refused", () => {
  assert.equal(decide("", { port: 53682 }).reason, REASON_MISSING_PARAMS);
});

test("missing state is refused even with a valid code", () => {
  assert.equal(
    decide(`code=${GOOD_CODE}`, { port: 53682 }).reason,
    REASON_MISSING_PARAMS,
  );
});

test("missing code is refused even with a valid state", () => {
  assert.equal(
    decide(`state=${GOOD_STATE}`, { port: 53682 }).reason,
    REASON_MISSING_PARAMS,
  );
});

test("duplicate code is refused rather than resolved", () => {
  const decision = decide(
    `code=${GOOD_CODE}&code=TG-other-9999999999&state=${GOOD_STATE}`,
    { port: 53682 },
  );
  assert.equal(decision.reason, REASON_DUPLICATE_PARAM);
});

test("duplicate state is refused", () => {
  const decision = decide(
    `code=${GOOD_CODE}&state=${GOOD_STATE}&state=${"B".repeat(43)}`,
    { port: 53682 },
  );
  assert.equal(decision.reason, REASON_DUPLICATE_PARAM);
});

test("blank code is refused", () => {
  assert.equal(decide(`code=&state=${GOOD_STATE}`, { port: 53682 }).kind, "error");
});

// -- provider-reported errors ------------------------------------------

test("provider error is relayed so the local app fails explicitly", () => {
  const decision = decide(`error=access_denied&state=${GOOD_STATE}`, { port: 53682 });
  assert.equal(decision.kind, "relay");
  assert.ok(decision.location.includes("error=access_denied"));
  assert.ok(!decision.location.includes("code="));
});

test("provider error description is sanitized before relay", () => {
  const decision = decide(
    `error=invalid_scope&error_description=%3Cscript%3Ealert(1)%3C/script%3E&state=${GOOD_STATE}`,
    { port: 53682 },
  );
  assert.equal(decision.kind, "relay");
  assert.ok(decision.location.includes("script"));
  assert.ok(!decision.location.includes("%3C"));
  assert.ok(!decision.location.includes("<"));
  assert.ok(!decision.location.split("?")[1].includes("/"));
});

test("long error description is truncated", () => {
  const decision = decide(
    `error=server_error&error_description=${"a".repeat(500)}&state=${GOOD_STATE}`,
    { port: 53682 },
  );
  const relayed = decision.location.split("error_description=")[1].split("&")[0];
  assert.ok(relayed.length <= DESCRIPTION_MAX);
});

test("malformed error code is refused", () => {
  const decision = decide(`error=<script>&state=${GOOD_STATE}`, { port: 53682 });
  assert.equal(decision.reason, REASON_BAD_ERROR_CODE);
});

test("error with a mismatched state shape is refused", () => {
  assert.equal(
    decide("error=access_denied&state=nope", { port: 53682 }).reason,
    REASON_BAD_STATE,
  );
});

test("error without state still relays so the user is not left hanging", () => {
  const decision = decide("error=access_denied", { port: 53682 });
  assert.equal(decision.kind, "relay");
  assert.ok(!decision.location.includes("state"));
});

// -- port configuration ------------------------------------------------

test("port defaults when unset", () => {
  assert.equal(resolveLoopbackPort({}), DEFAULT_LOOPBACK_PORT);
  assert.equal(resolveLoopbackPort(undefined), DEFAULT_LOOPBACK_PORT);
});

test("port can be configured", () => {
  assert.equal(resolveLoopbackPort({ [PORT_VAR]: "54321" }), 54321);
});

for (const bad of ["0", "80", "70000", "abc", "-1", "53682;ls", "53 682", "5.3"]) {
  test(`invalid configured port fails closed: ${bad}`, () => {
    assert.equal(resolveLoopbackPort({ [PORT_VAR]: bad }), null);
  });
}

test("misconfigured port refuses to guess a destination", () => {
  const decision = decide(`code=${GOOD_CODE}&state=${GOOD_STATE}`, { port: null });
  assert.equal(decision.kind, "error");
  assert.equal(decision.status, 500);
  assert.equal(decision.reason, REASON_MISCONFIGURED);
});

// -- error pages never echo input --------------------------------------

test("error body never contains request input", () => {
  const body = errorBody(REASON_BAD_CODE, "The code parameter is not the expected shape.");
  assert.ok(!body.includes("<script>alert(1)</script>"));
  assert.ok(!body.includes(GOOD_CODE));
});

test("every reason code is a fixed safe token", () => {
  for (const reason of [
    REASON_BAD_CODE,
    REASON_BAD_STATE,
    REASON_MISSING_PARAMS,
    REASON_DUPLICATE_PARAM,
    REASON_MISCONFIGURED,
    REASON_METHOD,
    REASON_NOT_FOUND,
    REASON_BAD_ERROR_CODE,
  ]) {
    assert.match(reason, /^[a-z_]+$/);
  }
});

// -- the real fetch handler --------------------------------------------

test("handler redirects a valid callback", async () => {
  const response = await get(
    `${CALLBACK_PATH}?code=${GOOD_CODE}&state=${GOOD_STATE}`,
  );
  assert.equal(response.status, 302);
  assert.ok(response.headers.get("location").startsWith(DEFAULT_PREFIX));
});

test("handler sets every security header", async () => {
  const response = await get(
    `${CALLBACK_PATH}?code=${GOOD_CODE}&state=${GOOD_STATE}`,
  );
  assert.equal(response.headers.get("cache-control"), "no-store, max-age=0");
  assert.equal(response.headers.get("referrer-policy"), "no-referrer");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(response.headers.get("x-frame-options"), "DENY");
  assert.ok(response.headers.get("content-security-policy").includes("default-src 'none'"));
  assert.ok(response.headers.get("content-security-policy").includes("form-action 'none'"));
  assert.ok(response.headers.get("strict-transport-security").startsWith("max-age="));
});

test("hsts does not include subdomains so other hosts are untouched", () => {
  const hsts = SECURITY_HEADERS["Strict-Transport-Security"];
  assert.ok(!hsts.includes("includeSubDomains"));
  assert.ok(!hsts.includes("preload"));
});

test("error responses also carry the security headers", async () => {
  const response = await get(`${CALLBACK_PATH}?code=x`);
  assert.equal(response.status, 400);
  assert.equal(response.headers.get("referrer-policy"), "no-referrer");
  assert.ok(response.headers.get("content-security-policy").includes("default-src 'none'"));
});

test("handler answers only the one documented route", async () => {
  for (const path of ["/", "/callback", "/api", "/api/mercadolivre", "/favicon.ico"]) {
    const response = await get(path);
    assert.equal(response.status, 404, `expected 404 for ${path}`);
    assert.equal(response.headers.get("location"), null);
  }
});

test("handler refuses non-GET methods", async () => {
  for (const method of ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"]) {
    const response = await worker.fetch(
      new Request(`https://oauth.test${CALLBACK_PATH}`, { method }),
      defaultEnv,
    );
    assert.equal(response.status, 405, `expected 405 for ${method}`);
    assert.equal(response.headers.get("allow"), "GET");
  }
});

test("handler sets no CORS headers", async () => {
  const response = await get(
    `${CALLBACK_PATH}?code=${GOOD_CODE}&state=${GOOD_STATE}`,
  );
  for (const name of response.headers.keys()) {
    assert.ok(!name.startsWith("access-control-"), `unexpected CORS header ${name}`);
  }
});

test("handler honours a configured port", async () => {
  const response = await get(
    `${CALLBACK_PATH}?code=${GOOD_CODE}&state=${GOOD_STATE}`,
    { [PORT_VAR]: "54999" },
  );
  assert.ok(response.headers.get("location").startsWith("http://127.0.0.1:54999/callback?"));
});

test("handler fails closed on a misconfigured port", async () => {
  const response = await get(
    `${CALLBACK_PATH}?code=${GOOD_CODE}&state=${GOOD_STATE}`,
    { [PORT_VAR]: "not-a-port" },
  );
  assert.equal(response.status, 500);
  assert.equal(response.headers.get("location"), null);
  assert.ok((await response.text()).includes(REASON_MISCONFIGURED));
});

// -- source-level guarantees -------------------------------------------

test("the worker logs nothing", () => {
  assert.ok(!SOURCE.includes("console."));
});

test("the worker imports nothing and has no dependencies", () => {
  assert.ok(!/^\s*import\s/m.test(SOURCE));
  assert.ok(!SOURCE.includes("require("));
  const manifest = JSON.parse(
    readFileSync(new URL("../package.json", import.meta.url), "utf8"),
  );
  assert.equal(manifest.dependencies, undefined);
  assert.equal(manifest.devDependencies, undefined);
});

test("the worker touches no binding other than the port variable", () => {
  // Checked by ACCESS, not by substring: this file names KV, D1 and R2 in
  // prose precisely to document that it does not use them, so a substring
  // search would flag its own documentation.
  const envAccess = SOURCE.match(/env\s*(?:\.\w+|\[[^\]]+\])/g) || [];
  assert.deepEqual([...new Set(envAccess)], ["env[PORT_VAR]"]);
  assert.ok(!/caches\s*\./.test(SOURCE));
});

test("the worker makes no outbound request", () => {
  // A relay that can call out is a relay that can exfiltrate a code.
  assert.ok(!/await\s+fetch\s*\(/.test(SOURCE));
  assert.ok(!/globalThis\s*\.\s*fetch/.test(SOURCE));
  // The only `fetch` is the exported handler's own entry point.
  const fetchMentions = SOURCE.match(/\bfetch\b/g) || [];
  assert.equal(fetchMentions.length, 1);
});
