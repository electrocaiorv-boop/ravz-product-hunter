# MAINTENANCE.md — External Integration & Dependency Maintenance

This project depends on systems it does not control: the Mercado Livre
API and third-party Python packages. Those systems can change
independently of this codebase at any time — an endpoint can be
deprecated, a response field can be renamed, a rate limit can tighten, a
package can release a breaking version. This document is a **checklist
only**. It does not implement automation, cron jobs, GitHub Actions, or
monitoring — that belongs to a later phase (see `CLAUDE.md` roadmap).

## Weekly Integration Check

- [ ] Mercado Livre official API documentation checked
- [ ] Endpoints used by the project are still valid
- [ ] Authentication requirements checked
- [ ] Response fields/schema checked
- [ ] Deprecation notices checked
- [ ] Rate limits checked when documented
- [ ] `requests` dependency checked
- [ ] `pytest` dependency checked
- [ ] Other project dependencies checked
- [ ] Full test suite executed
- [ ] README updated if API behavior changed
- [ ] LEARNING.md updated if a new technical concept was learned
- [ ] MAINTENANCE.md updated if the maintenance process itself changes

## Recommended cadence

- **During active development:** Weekly.
- **After the project becomes stable:** Every 2 to 4 weeks, depending on
  the external services used.

## Current integration status (corrected after independent re-check, Phase 3)

A previous draft of this document incorrectly stated that free-text `q`
search on `/sites/MLB/search` was "the current documented endpoint for
free-text item search" and that authentication was "optional" per the
docs. Both statements were corrected after re-checking the current
official documentation. This section reflects the corrected findings.

- **Endpoint called:** `GET https://api.mercadolibre.com/sites/MLB/search?q=...`
- **Official documentation (source of truth):**
  developers.mercadolivre.com.br/pt_br/itens-e-buscas ("Itens e Buscas"),
  last updated by Mercado Livre on **2026-08-31**.
- **What that documentation actually says:** `/sites/{SITE_ID}/search` is
  documented **only** for `nickname` and `seller_id` lookups. Every
  example shown for this endpoint sends
  `Authorization: Bearer ACCESS_TOKEN`. A free-text `q` parameter is
  **not** part of this endpoint's documented contract — the officially
  documented `q` parameter belongs to the separate `/products/search`
  catalog/GTIN endpoint, which this project does not use.
- **Classification:** this project's `q`-based call is **experimental /
  not officially documented** — not "officially documented and
  supported," and not confirmed as "working live" either (see below).
  Kept only for this phase's learning value; not a stable contract.
- **Authentication:** treat as **expected** for this endpoint family
  (every documented example requires a bearer token), even though this
  is unverified for the undocumented `q` usage specifically. The client
  sends `Authorization: Bearer <token>` only if
  `MERCADO_LIVRE_ACCESS_TOKEN` is set; it is never hardcoded and never
  required to import/call the module.
- **`available_quantity` field:** documented as a **reference bucket**,
  not exact stock — a real quantity in a range is rounded down to that
  range's floor before being published (e.g. a real 51-100 in stock is
  returned as the reference value `50`). Never present this field as
  precise inventory.
- **Observed behavior during manual validation (no token configured):**
  a direct call with `q=bebedouro automatico gatos` returned
  `HTTP 403` with body
  `{"message":"forbidden","error":"forbidden","status":403,"cause":[]}`.
  No results were returned. This does not confirm or rule out whether a
  valid bearer token would succeed, nor whether the block is specific to
  this network/IP — both are open questions for the next check.
- **Known risk:** if Mercado Livre fully removes free-text search access
  for third parties, or if a token becomes strictly required, only
  `src/integrations/mercadolivre.py` needs to change — no other module
  touches the API directly.

## How to perform the check

1. Re-read developers.mercadolivre.com.br/pt_br/itens-e-buscas and
   confirm whether `/sites/{SITE_ID}/search` still documents only
   `nickname`/`seller_id`, or whether a free-text `q` parameter has been
   added to its documented contract. Note the page's "last updated" date.
2. If a valid `MERCADO_LIVRE_ACCESS_TOKEN` becomes available, re-run
   `python -m src.main`, choose option 2, search
   `bebedouro automatico gatos`, and record the exact status code and
   whether results came back — with and without the token.
3. Compare the response shape against the fields `_map_item()` in
   `src/integrations/mercadolivre.py` currently extracts
   (`id`, `title`, `price`, `currency_id`, `seller.id`, `category_id`,
   `condition`, `permalink`, `shipping.free_shipping`,
   `available_quantity`). Re-verify the `available_quantity` bucket
   values are unchanged. Update the mapping if fields were renamed,
   removed, or if the bucket values changed.
4. Check `pip list --outdated` for `requests` and `pytest`.
5. Run `python -m pytest -v` and `pytest -v` — both must pass.
6. Update `README.md`, `docs/LEARNING.md`, and this file if anything
   changed.
