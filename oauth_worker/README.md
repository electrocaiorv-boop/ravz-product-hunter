# ravz-ml-oauth — Mercado Livre OAuth callback relay (Cloudflare Worker)

A single-route, stateless HTTPS endpoint whose only job is to receive
Mercado Livre's OAuth redirect and hand the authorization code to the
RAVZ Product Hunter running on a local machine.

**This is not the RAVZ commercial website.** It is a separate Cloudflare
Worker with its own `*.workers.dev` hostname. It shares no code, no
build, no domain and **no DNS record** with `www.ravztech.com.br`, and
deploying it cannot affect that site.

Chosen over Vercel Hobby because Cloudflare's self-serve agreement sets
no non-commercial restriction on its free plan, and the free Workers
tier allows 100,000 requests/day — roughly five orders of magnitude more
than this needs.

---

## Why it exists

Mercado Livre requires a registered `redirect_uri` that uses **HTTPS**
and does not accept a loopback address such as `http://127.0.0.1`. The
local Python application therefore cannot receive the redirect directly.
This Worker is the smallest thing that can bridge that gap.

```
browser  --(HTTPS ?code&state)-->  /api/mercadolivre/callback
                                            |
                                            | 302, fixed destination
                                            v
                              http://127.0.0.1:53682/callback?code&state
```

## What never passes through it

| | |
|---|---|
| access token | never — this Worker never calls the token endpoint |
| refresh token | never |
| client secret | never — not configured here, not needed here |
| user data, cookies, sessions | never — none are set or read |
| KV / D1 / R2 / Durable Objects | no binding of any kind is declared |

What does cross the public hop is the **authorization code** and
**state**. Neither is a credential on its own: the code is single-use,
short-lived, and bound by PKCE S256 to a `code_verifier` that is
generated inside the local Python process and never leaves it. An
intercepted code cannot be exchanged.

## Security properties

- **No open redirect.** The destination host (`127.0.0.1`) and path
  (`/callback`) are literals in `src/callback.js`. No request input
  selects, influences or is appended to the scheme, host or path. There
  is no `next`, `return_to` or `redirect_uri` parameter; only `code`,
  `state`, `error` and a sanitized `error_description` are read.
- **One route.** A Worker receives every path on its hostname, so the
  single supported route is enforced in code; everything else is 404.
- **Shape validation, not normalisation.** `code`, `state` and `error`
  must match fixed patterns or the request is refused. Malformed input
  is never "cleaned up" and forwarded.
- **Duplicate parameters are refused**, not resolved — removing the
  parameter-pollution ambiguity instead of picking a winner.
- **No input is ever echoed.** Error pages show a fixed message and a
  fixed reason code, so there is nothing to reflect back at a browser.
- **No application logging.** The source contains no `console` call, and
  `observability` is disabled in `wrangler.toml`, so the authorization
  code cannot reach Workers Logs. Cloudflare's edge request log is
  outside this file's control — see the residual-risk note in
  `docs/MERCADO_LIVRE_OAUTH.md`.
- **No outbound requests.** A relay that can call out is a relay that
  can exfiltrate a code. A test asserts the only `fetch` in the file is
  the handler's own entry point.
- **Strict headers** on every response: `no-store`, `no-referrer`,
  `nosniff`, `DENY` framing, and a CSP of `default-src 'none'`. HSTS is
  sent **without** `includeSubDomains`, so this service cannot impose
  transport policy on any other host.
- **No state, no database.** `state` and the PKCE verifier live in the
  local process that created them, which is the only place that can
  validate them.
- **No dependencies.** `package.json` declares none — runtime built-ins
  only, so there is no supply chain and no bundling surprise.

---

## Files

```
oauth_worker/
├── src/callback.js              the entire Worker (one route)
├── test/callback.test.mjs       59 offline tests, node --test
├── wrangler.toml                name, entry point, port var, no routes
├── package.json                 "type": "module" + test script; no deps
└── README.md                    this file
```

## Tests

```powershell
npm test --prefix oauth_worker          # 59 tests, no install needed
```

The cross-language contract — that these shapes still match the local
Python helper's — is asserted by `tests/test_oauth_worker_contract.py`,
so it runs inside the project's primary pytest gate as well. Both run in
CI.

## Deploy

Requires a free Cloudflare account. `wrangler` is run through `npx`, so
nothing is installed into this repository.

```powershell
cd oauth_worker
npx wrangler login          # opens a browser; authorizes this machine
npx wrangler deploy
```

The first deploy asks you to pick a `workers.dev` subdomain if the
account has none yet. `wrangler deploy` prints the live URL, which looks
like:

```
https://ravz-ml-oauth.<your-subdomain>.workers.dev
```

**No secrets to configure.** The only variable is the loopback port, and
it is declared in `wrangler.toml` because a port number is not a secret.
Do not add `wrangler secret put` entries: this Worker has nothing to
keep.

### What deployment does not do

`wrangler.toml` declares **no `routes`, no `custom_domain`, no `zone_id`
and no DNS record**, and `workers_dev = true`. That is what guarantees
the deploy cannot attach itself to `ravztech.com.br` or edit any DNS
entry — enforced by a test, not just by intent. Keep it that way.

## Callback URL to register at Mercado Livre

```
https://ravz-ml-oauth.<your-subdomain>.workers.dev/api/mercadolivre/callback
```

Substitute the real subdomain from `wrangler deploy`'s output. It must
match the registered value **exactly**, character for character, and
must also be set locally as `MERCADO_LIVRE_REDIRECT_URI`.
