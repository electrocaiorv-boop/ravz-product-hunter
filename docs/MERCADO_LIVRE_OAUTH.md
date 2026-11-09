# Mercado Livre OAuth — architecture, security and runbook

**Status: IMPLEMENTED, TESTED OFFLINE, NOT DEPLOYED, NOT AUTHORIZED.**

This document covers how RAVZ Product Hunter obtains a Mercado Livre
access token. It is the companion to `docs/MERCADO_LIVRE_403.md`, which
records the 403 investigation; that document's status line must not
change until the live diagnostic in section 9 has actually run.

Nothing here has been deployed and no authenticated request has been
made.

---

## 1. The constraint that dictates the architecture

Two verified facts about Mercado Livre's OAuth implementation:

| Fact | Consequence |
|---|---|
| The registered `redirect_uri` must use **HTTPS**, and a loopback/`localhost` address is **not accepted** | The local Python app cannot receive the redirect directly. Something public must catch it. |
| Mercado Livre **does not validate `state`** — it documents that the responsibility is the application's | `state` must be generated *and verified* locally. A relay cannot do it. |

Also relevant: PKCE is per-application and, once enabled, `code_challenge`
becomes mandatory on the authorization request and `code_verifier`
mandatory on the exchange. PKCE **is** enabled on this application.

Access tokens last ~6 hours. Refresh tokens last ~6 months and are
**single-use**: every refresh returns a new one and invalidates the old.

## 2. Chosen architecture: stateless callback relay → fixed loopback

```
  LOCAL PYTHON (owns every secret)        MERCADO LIVRE      RELAY (public, stateless)
  ────────────────────────────────        ─────────────      ─────────────────────────
  generate state + code_verifier
  derive code_challenge (S256)
  open authorization URL ───────────────▶ consent page
                                          redirect ────────▶ validate SHAPE of
                                          (?code&state)      code/state
                                                             302 to a hardcoded
                                                             127.0.0.1 destination
  loopback listener receives  ◀──────────────────────────────
  verify state (constant time)
  exchange code + verifier + secret ────▶ token endpoint
  tokens written to .secrets/   ◀──────── access + refresh token
```

The relay is a *dumb pipe with a shape check*. It holds no state, has no
database, sets no cookie, and never contacts the token endpoint — so no
token can exist in it.

### Why this is acceptable, point by point

- **What crosses the public hop is the `code` and `state`, never a
  token and never the client secret.** The code is single-use,
  short-lived, and PKCE-bound to a `code_verifier` generated inside the
  local process that never leaves it. An intercepted code cannot be
  exchanged by anyone else.
- **`state` is generated and verified where it was created.** Verified
  with `hmac.compare_digest`, after a shape check on both values. A code
  arriving with the wrong state is **discarded unspent** — never
  exchanged "just in case".
- **The loopback hop is a top-level navigation, not a `fetch()`.** This
  matters: an HTTPS page calling `http://127.0.0.1` via `fetch` is
  subject to Private Network Access preflight rules and breaks
  unpredictably across browser versions. A 302 navigation is not.
- **The listener binds before the browser is sent anywhere.** A port
  already in use is therefore an explicit, immediate failure rather than
  a silent handover of the authorization code to whatever was listening.
- **Open redirect is structurally impossible,** not merely filtered —
  see section 4.

### Residual risks, stated rather than hidden

1. **The platform access log may record the request URL,** including the
   `code`, and a function cannot opt out of its platform's own logging.
   Mitigation: the code is single-use, expires in minutes, is burned by
   our own exchange, and is useless without the local verifier. This is
   an accepted residual risk, not a solved one.
2. **Browser history and extensions see the loopback URL** containing
   the code. Same mitigation; this is inherent to every
   authorization-code flow that redirects through a browser.
3. **Any local process could occupy the loopback port first.** It would
   cause our bind to fail loudly (see above), not a silent interception.

### Alternatives considered and rejected

| Alternative | Why not |
|---|---|
| Register `http://127.0.0.1` directly with Mercado Livre | Rejected by Mercado Livre: HTTPS required, loopback not accepted. This is what forces a relay at all. |
| Relay by `fetch()`/XHR from the callback page to the loopback | Private Network Access preflight makes HTTPS→loopback subresource requests fragile and browser-version dependent. A navigation is not subject to it. |
| Store `state`/PKCE in the relay (KV, cookie, DB) | Moves security material into the public tier for no benefit — the only party that can validate them is the local process that created them. Also adds a database the task explicitly does not want. |
| Display the token on the callback page for copy-paste | Would put a live credential on a public page. Never. |
| Add the route to the existing commercial site | Explicitly out of scope: the commercial site must not be modified or redeployed. |

### Fallback if a browser refuses the loopback navigation

No extra server surface is added for this. If the browser will not open
the `127.0.0.1` address, the address bar still holds the full URL. The
local helper accepts it pasted in, and runs **exactly the same**
validation — same state check, same shape checks, no relaxed path.

## 3. Exact files created

Nothing was modified in the commercial website, in any domain module, in
the composition layer, or in `models.py` / `scoring.py`.

| File | Lines | Purpose |
|---|---|---|
| `oauth_service/api/mercadolivre/callback.py` | new | The entire relay. One route, stdlib only. |
| `oauth_service/vercel.json` | new | Security headers on every response. |
| `oauth_service/README.md` | new | Service-level deploy notes. |
| `src/integrations/mercadolivre_oauth.py` | new | Local helper: PKCE, state, authorization URL, loopback listener, token exchange, refresh, local credential file. |
| `src/integrations/mercadolivre_diagnostics.py` | new | Read-only 403 diagnostic (two probes, approval-gated). |
| `tests/test_oauth_callback_service.py` | new | Relay tests (loads the deployed file from its deployed path). |
| `tests/test_mercadolivre_oauth.py` | new | Local helper tests. |
| `tests/test_mercadolivre_diagnostics.py` | new | Diagnostic tests. |
| `docs/MERCADO_LIVRE_OAUTH.md` | new | This document. |
| `.env.example` | edited | Two new variable **names**, empty values. |
| `.gitignore` | edited | Added `.secrets/`. |

Architectural placement: both new modules live in `src/integrations/`
because they perform HTTP, and HTTP lives only there. Neither is
imported by any domain, the composition layer, the orchestrator or the
agent — the dependency arrow points nowhere new.

`MercadoLivreOAuthError` is deliberately **not** a subclass of
`MercadoLivreError`. That family means "we do not know this product
fact" and becomes unavailable *evidence*; an authorization failure is a
setup problem and must never be absorbed into a product analysis. A test
asserts the two hierarchies stay disjoint.

## 4. Open-redirect prevention

The destination is assembled from literals:

```python
LOOPBACK_HOST = "127.0.0.1"
LOOPBACK_PATH = "/callback"
f"http://{LOOPBACK_HOST}:{port}{LOOPBACK_PATH}?{urlencode(...)}"
```

Request input contributes **query values only**, each re-encoded by
`urlencode`. The port is the one configurable element and is validated
as an integer in 1024–65535; anything else returns HTTP 500 and relays
nothing. There is no `next`, `return_to`, `url` or `redirect_uri`
parameter to abuse, and tests assert that supplying them changes
nothing.

## 5. Security tests and results

`python -m pytest -q` → **1262 passed, 1 skipped** (was 1055 before this
work; 1 skip is a POSIX file-permission assertion that cannot hold on
Windows). `.claude/skills/invariant-check` → **PASS, 0 FAIL, 0 WARN**.

Relay (`tests/test_oauth_callback_service.py`):

| Property | Result |
|---|---|
| Valid `code`+`state` relay to the fixed loopback destination | pass |
| Six open-redirect payloads (`redirect_uri`, `next`, `return_to`, `url`, `host`, `port`) cannot move the destination | pass |
| Six hostile `code` values (`@evil`, `../`, `#@`, `?next=`, `\`, `%2f%2f`) refused, not normalised | pass |
| Misshaped `state` (too short, too long, spaces, `@evil`) refused | pass |
| Duplicate `code` / `state` refused rather than resolved | pass |
| Missing `code` or `state` refused | pass |
| Provider `error` relayed so the local app fails explicitly | pass |
| `error_description` containing `<script>` sanitized and truncated | pass |
| Invalid configured port fails closed (500, no `Location`) | pass |
| Error pages never echo request input | pass |
| Every security header present on success *and* error responses | pass |
| HSTS carries neither `includeSubDomains` nor `preload` | pass |
| No CORS headers emitted | pass |
| Non-GET methods → 405 with `Allow: GET` | pass |
| The code never reaches the function's own stdout/stderr | pass |
| Shape patterns identical on both sides of the hop | pass |

Local helper (`tests/test_mercadolivre_oauth.py`):

| Property | Result |
|---|---|
| PKCE S256 matches the **RFC 7636 Appendix B** test vector | pass |
| Challenge is unpadded base64url, 43 chars; verifier 43–128, unreserved charset, unique | pass |
| `state` unique, shape-checked, compared in constant time | pass |
| Redirect URI rules enforced (http, loopback, query, fragment, bad scheme all rejected) | pass |
| Authorization URL carries every required parameter; never contains the verifier or the secret; never offers `plain` | pass |
| Wrong `state` ⇒ code discarded **unspent** | pass |
| Replayed callback refused; first result not overwritten | pass |
| Unsolicited `error` with a foreign `state` cannot abort the flow | pass |
| Pasted-URL fallback applies the same validation; foreign origin / `javascript:` / `file:` refused | pass |
| Exchange sends `grant_type`, `code_verifier`, `redirect_uri`; requires both code and verifier | pass |
| Timeout / connection / non-200 / non-JSON / non-object / missing-token each become a distinct typed failure | pass |
| Response error includes only a safe provider error code; body withheld | pass |
| Transport-error message withholds detail **and** severs `__cause__` *and* `__context__` | pass |
| `JSONDecodeError` (which carries the whole document on `.doc`) left unreachable — token body and credential file | pass |
| `TokenSet` repr/str/f-string redact both tokens; `describe()` reports "configured", never a value | pass |
| Credential file written owner-only, parent dir created, values never printed | pass |
| Missing/corrupt/incomplete credential file → distinct typed errors | pass |
| Missing setting reports the variable **name**, never a value | pass |
| Port already in use fails loudly instead of sharing | pass |
| OAuth failures are not a subclass of the evidence-failure family | pass |

Diagnostic (`tests/test_mercadolivre_diagnostics.py`): token reported as
configured but never shown; `x-request-id` captured; a policy refusal
reported as "consistent with", never as proof; a plain 403 explicitly
not attributed; no interpretation branch ever claims a cause; the
catalog endpoint is never a request target; approval flag required.

**One real defect was found by these tests and fixed in the source**: a
`raise … from None` left the original exception reachable through
`__context__`. For `json` failures that object carries the *entire*
document on `.doc` — the token response in one case, the credential file
in the other. All three sites now record the failure inside the handler
and raise after it, matching the pattern the existing integrations use.

## 6. Environment variables (names only)

Local, in `.env` (git-ignored). `.env.example` carries the names with
empty values.

| Name | Required | Notes |
|---|---|---|
| `MERCADO_LIVRE_CLIENT_ID` | yes | From the developer console. |
| `MERCADO_LIVRE_CLIENT_SECRET` | yes | Sent only to the token endpoint. |
| `MERCADO_LIVRE_REDIRECT_URI` | yes | Must equal the registered value exactly. |
| `MERCADO_LIVRE_OAUTH_LOOPBACK_PORT` | no | Defaults to `53682`. |
| `MERCADO_LIVRE_ACCESS_TOKEN` | yes, after authorizing | Read by the existing integration. |

On Vercel (`ravz-ml-oauth` project only):

| Name | Required | Notes |
|---|---|---|
| `RAVZ_OAUTH_LOOPBACK_PORT` | no | Must match the local port if either is changed. |

**No secret is configured on Vercel.**

## 7. The callback URL to register

```
https://ravz-ml-oauth.vercel.app/api/mercadolivre/callback
```

The currently registered value is
`https://www.ravztech.com.br/api/mercadolivre/callback`, which points at
the commercial site. That site is not being modified, so **that path
will 404 and the flow cannot complete until the registered redirect is
updated** to the relay's own domain. Replace, do not add a second entry
you then forget about.

Optional, only if a vanity host is wanted later: point
`oauth.ravztech.com.br` at the `ravz-ml-oauth` project in Vercel and
register that instead. It is a DNS + Vercel-domain change on the new
project only and still does not touch the commercial site. The default
`.vercel.app` domain needs no DNS work at all and is the recommended
starting point.

## 8. Authorizing the account

Run from the repository root with the venv active. Nothing below sends a
request until step 4.

1. **Register the relay URL** (section 7) in the Mercado Livre developer
   console, and confirm the application still has PKCE enabled and
   read-only permissions wherever configurable.
2. **Fill `.env`** with `MERCADO_LIVRE_CLIENT_ID`,
   `MERCADO_LIVRE_CLIENT_SECRET` and `MERCADO_LIVRE_REDIRECT_URI`.
   Never paste these anywhere else.
3. **Dry run — offline, sends nothing:**
   ```powershell
   python -m src.integrations.mercadolivre_oauth plan
   ```
   Confirm the printed `redirect_uri` matches the registered value
   character for character, and that the loopback destination matches
   the relay's configured port.
4. **Authorize:**
   ```powershell
   python -m src.integrations.mercadolivre_oauth authorize
   ```
   It prints an authorization URL and listens on `127.0.0.1:53682`.
   Open the URL in a browser signed in to the account that owns the
   application, grant access, and the relay returns the browser to the
   listener. The helper verifies `state`, exchanges the code once, and
   writes `.secrets/mercadolivre_tokens.json`.

   If the browser refuses to open the `127.0.0.1` address, copy the URL
   from its address bar and paste it when prompted.

5. **Refresh later** (access tokens last ~6 hours):
   ```powershell
   python -m src.integrations.mercadolivre_oauth refresh
   ```
   The refresh token is single-use; the helper persists the new set
   immediately, because the old one dies on use.

Only metadata is printed at any point — token type, lifetime, scope,
user id, and whether each token is present. No token value is ever
printed, by design: a terminal keeps scrollback.

## 9. How the local Product Hunter receives the tokens

The existing integration (`src/integrations/mercadolivre.py`) reads
`MERCADO_LIVRE_ACCESS_TOKEN` from the environment and sends
`Authorization: Bearer …` when it is set. That behaviour is unchanged —
this work adds no new read path and modifies no existing module.

So after authorizing:

1. Open `.secrets/mercadolivre_tokens.json` in an editor.
2. Copy the `access_token` value into `.env` as
   `MERCADO_LIVRE_ACCESS_TOKEN=…`.
3. Confirm with `python -m src.main` → option 2.

The handoff is deliberately manual. The helper does not write `.env`:
this project's rule is that code may report whether a secret is
configured, never read or rewrite the file that holds it. Copying from a
file also keeps the value out of terminal scrollback entirely.

> `.secrets/` is git-ignored and holds live credentials. Never commit
> it, never paste its contents into a ticket, a chat message or a
> support case.

## 10. How the 403 will be diagnosed

Two probes, run once, reported separately, after a token exists:

```powershell
python -m src.integrations.mercadolivre_diagnostics --i-approve-live-read-only-requests
```

| Probe | Request |
|---|---|
| 1 | `GET /sites/MLB` — a documented, low-impact read-only resource. The decisive experiment from `docs/MERCADO_LIVRE_403.md` §5. |
| 2 | The Competition provider's own listing search, through `search_products()` so the real code path is exercised rather than a parallel copy. |

Exactly two requests, no retries, no concurrency, no probing of
alternative hosts, headers or undocumented endpoints after a refusal.

How each result is read — and what it does **not** establish:

| Outcome | Reading |
|---|---|
| Both 200 | Obstacle A (no credentials) is cleared and listing evidence is available. The free-text `q` usage is still undocumented and must be re-verified before anything depends on it. |
| Site 200, search refused | Authentication works; the refusal is specific to the listing search. This does **not** license substituting catalog data — Competition stays unavailable. |
| Site 403 with the policy message | **Consistent with** Obstacle B, not proof of it. Stop. Open a Mercado Livre support case quoting the captured `x-request-id`. No code change fixes a policy refusal. |
| Anything else | Inconclusive. Nothing is established and no evidence is produced. |

Three rules the diagnostic enforces in code, not merely in prose:

- **Authentication is not assumed to fix the 403.** Every branch names
  what remains unknown, and tests assert that no branch claims a cause.
- **Catalog products are never substituted for listing evidence.**
  `/products/search` describes a *product*; Competition scores the
  *field of sellers competing on it*. Counting catalog entries would
  silently change what the Competition Score measures while leaving its
  name and weight intact.
- **Restrictions are never bypassed.** On a refusal the diagnostic
  stops and reports.

While Competition remains unavailable the existing contracts already
behave correctly and need no change: Competition is a commercial
requirement, so readiness is `INCOMPLETE_EVIDENCE`, the final
classification is withheld, and the false-safety ceiling prevents the
missing negative dimension from inflating the aggregate.

## 11. Explicitly out of scope

Not built, not started, not implied: any change to the RAVZ commercial
website; any deployment; any live authenticated request; an automated
OAuth subsystem or token daemon; multi-user or multi-account token
storage; a database; Phase 13.
