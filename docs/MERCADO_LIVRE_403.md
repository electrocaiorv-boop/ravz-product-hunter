# Mercado Livre HTTP 403 — Diagnostic and Remediation Plan

**Status: `BLOCKED_BY_CONFIGURATION`**

No Mercado Livre credentials are configured in this environment, so the
integration has never made an authenticated request. That must be fixed
before any further conclusion is possible. A second, independent
obstacle is likely but **unproven from here** — see "Two obstacles"
below.

This document is a plan. **No OAuth subsystem is implemented in Phase
12B**, by instruction and by scope.

---

## 1. What is actually happening

The integration calls:

```
GET https://api.mercadolibre.com/sites/MLB/search?q=<free text>&limit=<n>
Authorization: Bearer <token>   # only when MERCADO_LIVRE_ACCESS_TOKEN is set
```

Observed, read-only, from this machine:

| Request | Status | Body |
|---|---|---|
| `/sites/MLB/search?q=fone+bluetooth` | 403 | `{"message":"forbidden","error":"forbidden","status":403,"cause":[]}` |
| `/sites/MLB/search?seller_id=…` | 403 | same |
| `/sites/MLB` | 403 | `{"message":"At least one policy returned UNAUTHORIZED.","status":403}` |
| `/products/search?site_id=MLB&q=…` | 403 | same |
| `/sites/MLB/categories` | 403 | same |

Three findings follow from that table, and each kills a different
hypothesis:

- **It is not a network block.** Every response is a well-formed JSON
  body from Mercado Livre's own gateway, carrying an `x-request-id`. We
  reach them; we are refused by policy.
- **It is not caused by the free-text `q` parameter.** The documented
  `seller_id` form is refused identically.
- **It is not specific to search.** `/sites/MLB/categories`, a
  long-standing no-auth public resource, is refused too.

The current credential state:

| Key | Configured |
|---|---|
| `MERCADO_LIVRE_CLIENT_ID` | no |
| `MERCADO_LIVRE_CLIENT_SECRET` | no |
| `MERCADO_LIVRE_ACCESS_TOKEN` | no |

So **every request so far has been unauthenticated**. Mercado Livre's
current documentation states the access token must be sent on every
call, for *both public and private resources*. Under that rule a 403 is
documented, expected behaviour — not a bug in this project.

---

## 2. Two obstacles, stacked

**Obstacle A — ours, confirmed.** No OAuth application, no credentials.
Must be fixed regardless of anything else.

**Obstacle B — theirs, likely but unproven from here.** Multiple
independent third-party reports describe this same 403 and the same
`PolicyAgent` message persisting **with valid tokens and all read/write
scopes enabled**, specifically including `/sites/MLB/search`.

Fixing A is **necessary**. It may not be **sufficient**. We cannot tell
which from outside, and we must not guess.

---

## 3. OAuth requirements and minimal scopes

Mercado Livre uses OAuth 2.0. The general documentation describes:

- `authorization_code` — user-delegated access, requires a redirect flow
  and a real seller account granting consent.
- `refresh_token` — renews an access token obtained that way.

**Do not assume `client_credentials` is available for a general
product-search application.** It appears in some community material and
in certain product contexts, but it is **not** what the general
documentation presents for this use case. Treat it as unverified until
confirmed against the live developer console for the specific
application type. (An earlier note in this project asserted it more
confidently than the evidence supported; that claim is withdrawn.)

**Minimal scopes:** request **read-only** access. This project never
writes, never publishes and never transacts, so write and offline scopes
must not be requested. If the console only offers coarse read/write
toggles, record that limitation here rather than silently enabling
write.

Access tokens are short-lived (hours); refresh tokens are longer-lived.
Both are credentials.

---

## 4. Secure application setup and token handling

1. Register an application in the Mercado Livre developer console.
2. Record `CLIENT_ID` and `CLIENT_SECRET` into `.env` only. `.env` is
   git-ignored and must stay that way; only `.env.example` (empty
   values) is committed.
3. Complete the authorization-code flow manually, once, to obtain an
   access token. Store it as `MERCADO_LIVRE_ACCESS_TOKEN` in `.env`.
4. **Never** commit any of the three values, paste them into an issue,
   or include them in a report.
5. **Never** log a token. This project's rule is that code may report
   whether a secret is *configured*, never its value —
   `src/config.py` and `describe_availability()` are the pattern to
   follow.
6. Treat the refresh token as equal in sensitivity to the access token.
7. When a token expires, the integration must surface an explicit
   failure, never a silent retry that returns partial data.

Note that `requests` embeds the `Authorization` header value in some
transport errors. Both integrations already withhold transport-error
messages and sever the exception chain for exactly this reason — any
new Mercado Livre code must keep that behaviour.

---

## 5. A small authorized connectivity test

Once credentials exist, run **one** request against a documented,
low-impact, read-only resource:

```
GET https://api.mercadolibre.com/sites/MLB
Authorization: Bearer <token>
```

This is the decisive experiment, and it is cheap:

- **200** → Obstacle A was the whole problem. Re-test
  `/sites/MLB/search` next.
- **403 with `At least one policy returned UNAUTHORIZED`** → Obstacle B
  is real and confirmed. No code change fixes it; escalate to Mercado
  Livre developer support with the `x-request-id`.

Rules for this test: one request, read-only, no retry loop, no
concurrency, no scraping, and no attempt to work around the refusal. If
it fails, **stop and report** — do not probe alternative hosts, headers
or undocumented endpoints.

---

## 6. Which documented APIs provide listing evidence

Competition Analysis needs **live listing facts**: per-listing prices,
distinct sellers, listing counts, free-shipping flags, available
quantity.

| API | Provides | Suitable for Competition? |
|---|---|---|
| `/sites/{SITE}/search` | live listings, prices, sellers, shipping | **Yes** — this is the right shape. Free-text `q` is undocumented for it; `seller_id`/`nickname` are documented. |
| `/products/search` | **catalog products** with datasheets | **No** |
| `/items/{id}` | one listing's detail | Partial — needs IDs from a search first |
| `/highlights/...` | trending items per category | Partial — a ranking, not a competitive field |

**Catalog results must not be substituted for listing evidence.** A
catalog product is a normalized description of a *product*; Competition
scores the *field of sellers competing on that product*. Counting
catalog entries instead of listings would silently change what the
Competition Score measures while leaving its name and weight intact —
the exact class of error this project's evidence rules exist to
prevent. Competition stays `None` rather than accept a substitute.

---

## 7. Impact while blocked

- Competition is a **commercial requirement**, so a missing Competition
  score forces `INCOMPLETE_EVIDENCE` and withholds the final
  classification.
- No live run can reach `READY` while this is unresolved, even with all
  four manual domains supplied.
- The false-safety ceiling fires, capping the aggregate so that the
  missing negative dimension cannot inflate the score.

This is correct behaviour under the current contracts, not a
workaround.

---

## 8. Next steps, in order

1. Register the application; populate `CLIENT_ID` / `CLIENT_SECRET`.
2. Complete the authorization-code flow once, manually, to obtain a
   token. Do not build an OAuth subsystem to do it.
3. Run the single connectivity test in section 5.
4. Record the outcome here, with the `x-request-id`, and update this
   document's status line.
5. **If 200:** re-test `/sites/MLB/search`, then decide whether the
   undocumented free-text `q` usage should be replaced by a documented
   access pattern.
6. **If still 403:** mark Obstacle B confirmed, open a support case, and
   treat marketplace evidence as structurally unavailable. That becomes
   a roadmap decision about finding a different provider for listing
   evidence — not a bug to fix in code.

Do not attempt to bypass, scrape, or evade the refusal under any
outcome.
