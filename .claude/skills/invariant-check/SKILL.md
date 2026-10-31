---
name: invariant-check
description: Verify RAVZ Product Hunter's load-bearing repository invariants — legacy byte-freeze, architectural import boundaries and cycles, provider/HTTP boundary, inversion sites, scoring-layer determinism, probability language in source and docs, observed-zero-vs-missing, and repository hygiene — plus a presence guard over the behavioral contracts delegated to pytest. Use before declaring any phase complete, before committing, after changing any weight, threshold, import, adapter, or readiness rule, and whenever asked to "check invariants", "run the phase gate", or "verify the contract".
tools: Read, Glob, Grep, Bash
---

# Invariant Check

Verify this repository's stable, load-bearing invariants. Narrowly scoped to
**contract verification** — not style, not performance, not test quality, not
code review.

`CLAUDE.md` is the authoritative contract. `docs/MAINTENANCE.md` is the
supporting per-phase checklist. **Where this skill and `CLAUDE.md` disagree,
`CLAUDE.md` wins and this skill is the thing to fix.**

## Division of labour — read this first

This skill does **not** re-verify what the test suite already proves. An
earlier version did, and became a second test suite: 1180 lines, ~55%
duplicating the Phase 11 tests. It now has exactly three jobs.

**1. Independent structural inspection** — invariants no test covers:

| Checked here independently | Why no test covers it |
|---|---|
Domain analyzers import only their own `*_models` + stdlib | no test asserts the per-module import rule |
No cross-domain imports | only `risk_analysis` has a bespoke test |
Import graph is acyclic | no cycle detection anywhere |
HTTP confined to `src/integrations/` | no test asserts the provider boundary |
Orchestrator-import guard (forward-looking for Phase 12) | the module does not exist yet |
Contract layer imports only `dataclasses`; composition only the contract | *partially* tested — kept here because it is the same AST pass |
Inversion appears **only** at sanctioned sites | tests prove *that* it inverts, never *where* |
No randomness / clock / network / `global` in scoring layers | tests prove determinism behaviorally, not structurally |
Probability language in **source and `CLAUDE.md`** | tests inspect only the result object |
Observed zero distinguishable from missing | no test covers this distinction |
Repository hygiene (see below) | zero test coverage |

**2. Legacy byte-freeze** — `src/models.py` and `src/scoring.py` are hashed
against **pinned reference values** in `LEGACY_FROZEN`, not against `HEAD`.
Comparing to HEAD is not a freeze: an accidental committed modification
becomes the new baseline and every later run passes. Hashes are over
LF-normalised content (`core.autocrlf=true` here, so raw bytes differ per
checkout), with the git blob ID as an independent cross-check.

**3. Presence guard over delegated contracts** — these behavioral contracts
are verified by **pytest**, not recomputed here:

- legacy-v1 exact weights and compatibility
- integrated-v1 documented weights
- Demand/Trend evidence-family election
- family maximum weight
- Trend cannot independently move the aggregate
- None preservation
- missing-negative false-safety protection
- readiness states and precedence
- classification withheld outside READY
- operationally-unvalidated non-final band
- deterministic composition

`DELEGATED_TESTS` tracks **43 specific test functions by file and name**. If
one is deleted or renamed, this skill FAILs — closing the hole where removing
a test would silently retire an invariant while the checker still reported
PASS. Never replace the manifest with a count threshold: "at least N tests"
cannot detect that the one test protecting a specific invariant was the one
removed.

> The report labels these **DELEGATED**, never PASS. This skill does not
> independently verify them and must not claim to.

**Running pytest is necessary but not sufficient. Running this skill is also
not sufficient. Both run; both must pass.**

## How to run

```bash
PYTHONPATH=. python .claude/skills/invariant-check/check_invariants.py
```

Exit `0` when every load-bearing invariant holds, `1` when any FAILs. The
script runs `python -m pytest -q` itself and folds the result into its verdict.

Run from the repository root. If the output is clean, present it and stop — do
not re-derive the checks by hand. If anything FAILs, read the cited file and
confirm the finding before reporting it as real.

The project's Testing Contract also names the second invocation form:

```bash
pytest -q
```

## Two distinctions the script encodes — preserve them

**A neutral aggregate ceiling is not `None -> 50`.** When a negative dimension
(Competition, Risk) is unknown, the aggregate is capped at the value it would
have if that dimension were neutral, while the component itself stays
`available=False` with `raw_score=None`. Capping an aggregate so ignorance
cannot pay is the opposite of substituting a value for missing evidence. Do not
"simplify" one into the other. *(Behaviorally delegated; listed here because
the distinction is what the delegation protects.)*

**Observed zero is not missing.** `margin_score=0.0` is real evidence and must
stay `available=True`; `margin_score=None` must not. Branch on `is None`, never
on truthiness. *(Checked here independently — no test covers it.)*

## Why AST instead of grep

This codebase deliberately discusses its own forbidden patterns in prose, so
substring matching produces false positives:

- `100 -` appears in six docstrings/comments (worked examples, direction notes)
  and in only two real code sites.
- Probability words appear 16 times in `src/`, every one inside a disclaimer or
  an "unavailable" list naming what the project refuses to compute.
- `scoring.py` contains `calculate_opportunity_score`, so matching
  `opportunity_` would wrongly flag the legacy module as depending on the
  Phase 11 layer.
- Several modules name peers **in docstrings** precisely to document that they
  do *not* import them.

Two further precision details, both found by negative testing:

- The probability check is **list-aware**: a negated introduction ("It never
  means, and must never be presented as:") is attributed to every item in the
  list it introduces, however long. Without this, `CLAUDE.md`'s own disclaimer
  list false-positives.
- The over-broad-ignore check uses `git check-ignore --no-index`. The default
  mode suppresses paths already tracked, so once `.claude/agents/*` is
  committed it silently stops detecting a wholesale `.claude/` rule.

## Reporting

Present the script's output as-is:

```
Invariant Check
===============

PASS:      (n)  independently verified here
DELEGATED: (n)  verified by pytest, presence-guarded -- NOT recomputed
FAIL:      severity / invariant / where / evidence / why / fix
WARN:      (n)

Tests:  X passed
Git:    branch / staged files / working tree

Final:  PASS | FAIL
```

Rules:

- **FAIL** if a load-bearing contract invariant is violated, a frozen legacy
  file changed, a delegated test disappeared, or pytest fails.
- **WARN** for non-contract concerns.
- Never print a suspected secret's value — report only its location.
- If a check raises, that invariant is **unverified**, not passing. The script
  reports the exception as a FAIL; fix the script unless the exception reveals a
  genuine contract break.

## Extending it

Add a check when a new load-bearing invariant enters `CLAUDE.md` — not for
general code quality. Prefer **delegation** when a behavioral test can own the
invariant: add the test, then add its node ID to `DELEGATED_TESTS`. Reserve
this script for what tests structurally cannot see.

Keep each check stdlib-only, AST- or runtime-based rather than grep where
practical, and asserting a *property of the real implementation's output*. The
script must never reimplement a domain formula or become a second scoring
engine.

**Every new check must be negative-tested**: inject the violation into a
throwaway copy of the repo (`git archive HEAD | tar -x -C <tmp>`) and confirm
it FAILs, then restore. A check that cannot fail verifies nothing — and this
is not hypothetical: negative testing is what exposed the
`check-ignore --no-index` blind spot above.

**Updating `LEGACY_FROZEN` is a legacy-contract change**, not maintenance. It
requires a documented pre-existing bug, a decision recorded in
`docs/LEARNING.md`, and a deliberate update of both hashes. Never update a hash
to make the check pass.
