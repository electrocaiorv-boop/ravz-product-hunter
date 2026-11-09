# ravz-ml-oauth — Mercado Livre OAuth callback relay

A single-route, stateless HTTPS endpoint whose only job is to receive
Mercado Livre's OAuth redirect and hand the authorization code to the
RAVZ Product Hunter running on a local machine.

**This is not the RAVZ commercial website.** It is a separate Vercel
project with its own domain and its own deployment. It shares no code,
no build and no domain with `www.ravztech.com.br`, and deploying it
cannot affect that site.

---

## Why it exists

Mercado Livre requires a registered `redirect_uri` that uses **HTTPS**
and does not accept a loopback address such as `http://127.0.0.1`. The
local Python application therefore cannot receive the redirect directly.
This service is the smallest thing that can bridge that gap.

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
| access token | never — this service never calls the token endpoint |
| refresh token | never |
| client secret | never — not configured here, not needed here |
| user data, cookies, sessions | never — none are set or read |

What does cross the public hop is the **authorization code** and
**state**. Neither is a credential on its own: the code is single-use,
short-lived, and bound by PKCE S256 to a `code_verifier` that is
generated inside the local Python process and never leaves it. An
intercepted code cannot be exchanged.

## Security properties

- **No open redirect.** The destination host (`127.0.0.1`) and path
  (`/callback`) are literals in `api/mercadolivre/callback.py`. No
  request input selects, influences or is appended to the scheme, host
  or path. There is no `next`, `return_to` or `redirect_uri` parameter.
- **Shape validation, not normalisation.** `code`, `state` and `error`
  must match fixed patterns or the request is refused. Malformed input
  is never "cleaned up" and forwarded.
- **Duplicate parameters are refused**, not resolved — removing the
  parameter-pollution ambiguity instead of picking a winner.
- **No input is ever echoed.** Error pages show a fixed message and a
  fixed reason code, so there is nothing to reflect back at a browser.
- **No request logging in this function.** `log_message` is overridden
  to emit nothing, so the code cannot reach this function's stderr.
  (Vercel's own platform access log is outside this file's control and
  may record the request URL — see the residual-risk note in
  `docs/MERCADO_LIVRE_OAUTH.md`.)
- **Strict headers** on every response: `no-store`, `no-referrer`,
  `nosniff`, `DENY` framing, and a CSP of `default-src 'none'`. HSTS is
  sent **without** `includeSubDomains`, so this service cannot impose
  transport policy on any other `ravztech.com.br` host.
- **No database, no KV, no state.** There is nothing to store: `state`
  and the PKCE verifier live in the local process that created them,
  which is the only place that can validate them.
- **No dependencies.** Python standard library only, so there is no
  `requirements.txt` and no supply chain to audit.

---

## Files

```
oauth_service/
├── api/mercadolivre/callback.py   the entire service (one route)
├── vercel.json                    security headers for every response
└── README.md                      this file
```

`api/mercadolivre/callback.py` → `GET /api/mercadolivre/callback`.
No other route exists; the project root returns 404 by design.

## Create the Vercel project

1. Vercel dashboard → **Add New… → Project** → import this Git
   repository.
2. **Project Name:** `ravz-ml-oauth`
3. **Root Directory:** `oauth_service` ← *this is the step that keeps
   the commercial site untouched.* Vercel then builds only this
   subdirectory and ignores the rest of the repository.
4. **Framework Preset:** Other. Leave build and output settings empty —
   Vercel detects `api/*.py` and uses its Python runtime automatically.
5. Deploy.

Do **not** attach this project to `www.ravztech.com.br`, and do not
change that project's settings. The default `ravz-ml-oauth.vercel.app`
domain is sufficient.

## Environment variables (names only)

| Name | Required | Purpose |
|---|---|---|
| `RAVZ_OAUTH_LOOPBACK_PORT` | no | Local port to relay to. Omit to use `53682`. Must match `MERCADO_LIVRE_OAUTH_LOOPBACK_PORT` on the local machine. |

No secret is configured here. If this variable is set to anything that
is not a usable port, the service returns HTTP 500 and relays nothing —
it fails closed rather than guessing a destination.

## Callback URL to register at Mercado Livre

```
https://ravz-ml-oauth.vercel.app/api/mercadolivre/callback
```

Replace the host with the deployment's real production domain if Vercel
assigns a different one. It must match the registered value **exactly**,
character for character.

## Tests

Covered by the repository's own suite — no separate runner:

```powershell
python -m pytest tests/test_oauth_callback_service.py -v
```

Those tests load this exact file from this exact path, so what is tested
is what deploys.
