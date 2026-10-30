# RAVZ Product Hunter

## Objective

Build an AI-powered product research and validation system focused initially on Mercado Livre Brazil.

The system identifies candidate products and evaluates demand, trend, competition, margin, supplier viability, logistics and risk, then composes an explainable opportunity analysis.

The project is both:

1. A real tool for product research and ecommerce opportunities.
2. A professional portfolio project demonstrating AI agents, APIs, automation, Python, data analysis, MCP, n8n, and software engineering practices.

---

## Core Principle

Never claim that a product has a guaranteed probability of selling.

Every score in this project is a **deterministic, provisional business heuristic** built from documented, adjustable constants. None has been calibrated against real sales outcomes.

"Opportunity Score: 82" means "this evidence, under this documented weighting, scores 82 of 100."

It never means, and must never be presented as:

- a probability of selling or succeeding
- a conversion rate
- an expected ROI
- a guarantee of performance

No function may produce a probability from these scores.

---

## Current State

**Phase 11 is complete.** Phases 1–11 are committed; the full suite passes (809 tests).

**Phase 12 is next: Orchestration Layer.** See "Phase 12 Orchestrator Contract" below before writing any code for it.

Completed:

| Phase | Deliverable |
|---|---|
| 1 | Data models + opportunity scoring engine (`models.py`, `scoring.py`) |
| 2 | Manual Product Analyzer CLI |
| 3 | Mercado Livre integration |
| 4 | Deterministic Trend Analysis |
| 5 | Deterministic Demand Analysis |
| 6 | Deterministic Competition Analysis |
| 7 | Deterministic Margin Analysis |
| 8 | Deterministic Supplier Analysis |
| 9 | Deterministic Logistics Analysis |
| 10 | Deterministic Risk Analysis |
| 11 | Integrated Opportunity composition layer |

Remaining work, in order: **Orchestration (Phase 12)**, then database/history, n8n automation, notifications, continuous improvement.

Two numbering systems exist in this repo and must not be conflated:

- **Phase numbers** (1–11 done, 12 next) — used by commit messages, doc section headers and module docstrings. This is the working numbering.
- **Roadmap step numbers** (1–14 in `README.md`) — the original plan. Orchestration is step 10 there. Phases do not map 1:1 onto steps; several phases layer onto a single step.

When referring to work, use **phase numbers**.

Build incrementally. Each stage must work before moving to the next.

---

## Commands

Requires **Python 3.12**.

This project is developed on Windows. Default shell is **PowerShell**:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1     # PowerShell activation
pip install -r requirements.txt

python -m src.main               # CLI entry point (menu options 1-10)
python -m pytest -v              # full suite (809 tests, ~1s)
```

Bash (Git Bash / WSL / CI) activates differently:

```bash
source .venv/Scripts/activate    # Git Bash on Windows
source .venv/bin/activate        # Linux / macOS / CI
```

`pyproject.toml` sets `pythonpath = ["."]`, so `src` resolves as a package under both `pytest` and `python -m pytest`. Ad-hoc scripts run outside pytest need the path set explicitly — and the syntax differs by shell:

```powershell
$env:PYTHONPATH="."; python script.py    # PowerShell
```

```bash
PYTHONPATH=. python script.py            # Bash
```

Do not mix shell syntaxes. PowerShell has no inline `VAR=x cmd` prefix and no bash here-strings (`<< 'EOF'`); Bash has no `$env:` variables. Use a heredoc in Bash or a here-string (`@'...'@`) in PowerShell for multi-line strings, never the other shell's form.

Chaining differs **by PowerShell version**, so do not assume either way: `&&` and `||` are pipeline chain operators added in **PowerShell 7.0** and are available there, but **Windows PowerShell 5.1 does not support them** and will raise a parser error. This machine runs Windows PowerShell 5.1 (`$PSVersionTable` → Desktop 5.1), so prefer `A; if ($?) { B }` for conditional chaining here. Verify the version before relying on `&&` in any script intended to be portable.

Local secrets live in `.env` (git-ignored). Copy `.env.example` and fill it in; the app runs without it but provider-backed features will report themselves unavailable.

---

## Implemented Architecture

```
integrations/        provider-specific fetch + mapping (HTTP lives ONLY here)
      |
      v
*_models.py          provider-neutral input contracts
      |
      v
*_analysis.py        deterministic domain scoring (7 domains)
      |
      v
opportunity_models.py        canonical contract (imports only `dataclasses`)
opportunity_integration.py   adapters + composition (imports only the contract)
      |
      v
main.py              presentation layer only -- no scoring math, no HTTP
```

Seven domain engines, each with one responsibility and no knowledge of the others: Trend, Demand, Competition, Margin, Supplier, Logistics, Risk.

Do not create a single module responsible for everything. Agents and modules return structured data (typed models / JSON-compatible dicts), never unstructured prose.

---

## Scoring Models

Two models coexist deliberately. They are separate contracts and must never be merged or harmonized.

### `legacy-v1` — FROZEN

`src/scoring.py` + `src/models.py`. Manual Phase 1/2 API: seven mandatory, non-nullable 0–100 component scores.

| Dimension | Weight |
|---|---|
| Demand | 0.30 |
| Trend | 0.20 |
| Competition | 0.15 |
| Margin | 0.15 |
| Supplier | 0.10 |
| Logistics | 0.05 |
| Risk | 0.05 |

**`src/models.py` and `src/scoring.py` must remain unchanged** unless a genuine pre-existing bug is found and documented separately first. `ComponentScores` stays mandatory-seven; missing-data semantics belong to the integrated layer, not here.

Legacy classifies the **2dp-rounded** total. This is a documented contract quirk, not a bug — do not "fix" it.

### `integrated-v1`

`src/opportunity_integration.py`. Real domain results, with missing-data semantics, blocker propagation and correlated-evidence safeguards.

| Component | Weight | Layer | Direction |
|---|---|---|---|
| search-interest family (Demand/Trend) | 0.30 | commercial | positive |
| competition | 0.15 | commercial | negative |
| margin | 0.20 | commercial | positive |
| supplier | 0.12 | operational | positive |
| logistics | 0.08 | operational | positive |
| risk | 0.15 | commercial | negative |

Distinct weighted slots sum to exactly **1.00**. Commercial layer = 0.80, operational layer = 0.20.

**Integrated weights are NOT derived from legacy weights.** They were re-derived from marginal information value. Legacy's 0.50 for Demand+Trend assumed two independent signals; once they were proven to be one evidence family, preserving 0.50 would have converted "half the score from two independent signals" into "half from one provider call." Preserving a number is not preserving a decision when its premise changes.

Integrated classifies the **exact, unrounded** value. A score of 79.996 displays as `80.00` and must not promote.

Changing any weight, the validation layers, the family policy, the false-safety guard or the readiness rules requires a **new model version**, not an edit.

---

## Evidence Family Invariant (critical)

Demand and Trend both descend from **one** Apify Google-Trends Actor call. Demand's largest component is rebuilt from the same interest level and direction that dominate the Trend Score, and `DemandAnalysis.marketplace_contribution` is permanently `None` — so today's Demand Score is entirely Google-Trends-derived.

Rules:

- Demand and Trend **must never both receive weighted contributions**.
- They share **one** family weight (0.30) declared as an `EvidenceFamilyPolicy`.
- **Demand is the preferred representative** (it consumes the family most completely).
- **Trend is the fallback** when no Demand result is supplied.
- The non-elected member stays visible for provenance with **zero** weighted contribution and an explicit `overlap_policy`.
- Double counting correlated evidence is forbidden.

Before adding, re-weighting or re-enabling **any** component, trace
`raw provider evidence -> domain metric -> domain score -> integrated component`
and verify the evidence is not already consumed upstream.

If `marketplace_contribution` is ever re-enabled, Demand stops being single-source — revisit the family weight and record the new reasoning.

---

## Score Direction

High = favorable: search-interest/Demand, Margin, Supplier, Logistics.

High = unfavorable: **Competition, Risk**.

Negative dimensions are inverted (`100 - score`) **exactly once**, at the opportunity boundary, in `to_opportunity_oriented()`. Never again downstream, never inside a domain module.

`risk_analysis.py` performs no internal inversion and `logistics_analysis.py` computes "ease" (already high-is-good) — there is nothing to undo upstream. Inverting twice silently restores the original value; that is the bug this rule prevents.

---

## Missing Data and Failure Semantics

Missing evidence stays missing. A withheld or unavailable score is reported as `None` with an explicit reason.

**Never convert `None` to** 0, 50, `False`, neutral, average, or "safe".

Never fabricate: sales volume, supplier information, prices, reviews, marketplace metrics, margins, API responses, confidence figures.

**Never hide or omit a cost to make an opportunity appear attractive.** This is why Margin is a commercial requirement: an opportunity with unknown unit economics cannot be recommended.

Clearly distinguish **observed** (measured or provider-reported), **derived** (computed from observed values), **estimated** and **inferred** data. Domain results expose `observed` and `derived` separately for exactly this reason — never move a value between them to make a result look stronger.

### Integration failures

Any integration or provider failure must become:

- explicit unavailable / `None` evidence, **and**
- an explicit reason, status and provenance record

Never:

- a silent fallback
- a plausible substitute value
- a fake success
- a swallowed exception

The integrations expose typed exception hierarchies (`ApifyTrendsError` and `MercadoLivreError` families: configuration / timeout / connection / response / data). These are operationally different but **epistemically identical** — every one of them means "we do not know." Each maps to that domain's score being `None` with a specific reason, never to a default and never to a retry that silently succeeds with partial data.

### Missing negative dimensions

Removing an unknown **negative** dimension must never make a result look more validated. Two protections, both required:

1. **Gate** — Competition and Risk are commercial requirements, so a missing one withholds the classification.
2. **Ceiling** — the aggregate is capped at the value it would have if that dimension were neutral. This is *not* `None -> 50`: the component stays `available=False` with `raw_score=None`; only the aggregate is prevented from profiting from ignorance. It is a `min()`, so it can only lower an inflated score, never invent bad news.

---

## Evidence Semantics

These are **different kinds of metric**. Keep them distinct, under their own names. Never rename them into one another and never average them into a universal "confidence" value.

| Concept | Meaning | Where |
|---|---|---|
| confidence | how trustworthy the evidence is, bounded by source independence | Demand, Competition |
| completeness | how much of one domain's own field set is known | Margin (cost), Supplier, Logistics, Risk |
| coverage | how much of the configured weight has any evidence | opportunity level |
| provenance | which domain produced a value, and from what source family | every component |
| source status | a domain's own verdict vocabulary | Supplier, Logistics, Risk |

Coverage is **not** confidence, **not** completeness, **not** accuracy.

Trend has no evidence-quality metric at all; its honest metadata is `observation_count` and `direction`. Do not invent one.

Domain score-withholding thresholds (each independently justified, not copied): Margin 50% cost completeness · Logistics 40% · Supplier 35% · Risk 35%.

---

## Readiness and Classification

Four states, strict precedence:

```
BLOCKED > INCOMPLETE_EVIDENCE > OPERATIONALLY_UNVALIDATED > READY
```

| State | Condition |
|---|---|
| `BLOCKED` | a domain reported a genuine hard blocker (checked first) |
| `INCOMPLETE_EVIDENCE` | a **commercial** requirement is missing — the business case cannot be evaluated |
| `OPERATIONALLY_UNVALIDATED` | commercial validation complete, but Supplier and/or Logistics unavailable |
| `READY` | both layers complete, no blocker |

**Commercial validation and operational validation are separate questions** and are reported as separate booleans with separate coverages:

- commercial = search-interest family, competition, margin, risk
- operational = supplier, logistics

Required behaviors:

- Supplier and/or Logistics missing **must not** produce `READY`.
- A missing commercial requirement **must** produce `INCOMPLETE_EVIDENCE`, not `OPERATIONALLY_UNVALIDATED`.
- A genuine blocker **must** produce `BLOCKED`, overriding everything else.
- `OPERATIONALLY_UNVALIDATED` must never be collapsed into `INCOMPLETE_EVIDENCE` — they answer different questions.

Classification bands: `>=80` Strong opportunity · `>=65` Worth deeper investigation · `>=50` Weak or uncertain · `<50` Reject.

In `integrated-v1` these are emitted as a **final classification only when `readiness == READY`**. Outside READY the classification is withheld with an explicit reason. Only `OPERATIONALLY_UNVALIDATED` may expose an explicitly **non-final** band describing the commercial case alone.

An analytical score may still be computed and shown whenever weighted evidence exists — hiding useful arithmetic is its own dishonesty. What is withheld is the *recommendation*, never the transparency.

Blockers must be surfaced namespaced by the domain that found them, outside the weighted average. A blocker must never be diluted into a mean.

---

## Architectural Boundaries

- **Domain analysis modules remain provider-neutral.** They import only their own `*_models` sibling. No HTTP, no provider names, no LLM.
- **Integration modules own all provider-specific fetching and mapping.** Nothing provider-specific leaks past that boundary.
- **Domain modules must not import each other.**
- **`opportunity_models.py` is a pure contract layer** — imports only `dataclasses`.
- **`opportunity_integration.py` is composition-only** — imports only the contract.
- **Adapters translate; they do not recompute.** They must not re-derive domain scoring, perform I/O, guess missing values, mutate the result they are given, invent confidence, or collapse one domain's evidence semantics into another's.
- **The orchestrator may import domains and integrations. Domains must never import the orchestrator.** Layering is one-directional.
- `main.py` is presentation only: no scoring math, no HTTP.

Wall-clock, randomness and I/O must not enter any analysis or composition layer. `datetime` may appear only as provenance (e.g. `retrieved_at`), never as a scoring input.

---

## Phase 12 Orchestrator Contract

Phase 12 adds **orchestration**, not intelligence. Phase 11 is composition ("given these results, what do they support?"); Phase 12 is coordination ("go get the results").

The orchestrator **MAY**:

- call integrations
- coordinate the domain analyzers
- call `compose_opportunity()`
- collect provenance, status and failure reasons
- sequence and order work

The orchestrator **MUST NOT**:

- calculate business scores
- re-weight components
- invert scores
- recreate or re-derive domain formulas
- fabricate missing data
- convert `None` to 0, 50, `False`, neutral, average or safe
- bypass `compose_opportunity()`
- persist raw provider payloads
- leak request headers or credentials in logs or error text

It owns sequencing and failure translation. It owns no scoring math.

Do not add caching or silent retries in Phase 12A. A cache raises a provenance question ("how old is this evidence?") that no model field answers yet, and a silent retry can turn a hard failure into partial data.

### Phase 12 is staged: 12A then 12B

**Both stages are part of the AI/agent roadmap. 12B is deferred, not cancelled.**

#### Phase 12A — Deterministic Orchestration Foundation

```
integrations -> domain engines -> compose_opportunity()
```

- deterministic sequencing of the seven domain engines
- explicit failure and provenance handling (see "Integration failures")
- **no LLM required**
- preserves the "identical input -> identical output" guarantee that eight module docstrings assert

Build this first. A deterministic foundation keeps any later behavior change attributable to the right layer.

#### Phase 12B — Agentic Control Layer

**May be added only after Phase 12A is stable and fully tested.**

The LLM **MAY**:

- choose which tools to call
- sequence and re-sequence research
- interpret textual/unstructured evidence
- request additional collection when evidence is thin
- explain results in natural language

The LLM **MUST NEVER**:

- calculate business scores
- re-weight components
- invert scores
- replace `None` with any value
- fabricate evidence
- bypass the deterministic engines or `compose_opportunity()`

The division is strict: **the LLM decides what to look at; the deterministic engines decide what it means.** Every number in a result must still trace to a domain engine and the composition layer, never to a model's judgment. Non-determinism is permitted only in *which evidence gets collected*, never in *how collected evidence is scored*.

---

## Development Rules

### Code Quality

- Prefer simple and readable code.
- Python is the primary backend language.
- Use type hints where useful.
- Modular architecture; avoid unnecessary abstraction and premature optimization.
- Keep business rules separate from integrations.
- Add tests for all scoring and financial calculations.

### External Integrations

Do not add an external integration without documenting:

1. why it is needed
2. what data it provides
3. authentication requirements
4. cost implications
5. rate limits when known

A future adapter may *populate* an existing input model, but must never bypass it.

---

## Security

- Never edit or expose `.env` contents.
- Never log tokens or credentials.
- Never persist raw request headers or raw provider payloads.
- Never include secrets in exception text.
- Never commit secrets. `.env` stays git-ignored; only `.env.example` (empty values) is committed.
- Secrets live in environment variables: API keys, tokens, passwords, private URLs, webhook secrets.
- Code may report whether a secret is *configured*, never its value.

---

## Testing Contract

Before declaring any phase complete:

```bash
python -m pytest -v
pytest -v
```

Both must pass. Additionally verify:

- **architecture invariants** — import DAG one-directional; contract layer imports only `dataclasses`; composition imports only the contract
- **deterministic behavior** — identical input produces identical output
- **missing-data regressions** — `None` never becomes 0/50/safe; missing negative evidence never inflates a score
- **score direction** — negative dimensions inverted exactly once, no double inversion
- **evidence-family regression** — Demand and Trend never both weighted
- **legacy compatibility** — `models.py`/`scoring.py` byte-identical; legacy weights and API unchanged
- **staged diff review** — `git diff --cached`
- **whitespace/conflict check** — `git diff --cached --check`
- **secret scan** of the staged diff

See `docs/MAINTENANCE.md` for the full per-phase checklist.

---

## Git Discipline

- **Do not commit or push until the phase is explicitly approved.**
- Preserve one coherent commit per phase where practical.
- Use conventional prefixes: `feat:`, `fix:`, `test:`, `docs:`, `chore:`.
- Never force push.
- Never rewrite history without explicit approval.
- Never commit `.env`.

---

## Portfolio Goal

This repository should clearly demonstrate: Python · REST APIs · JSON · AI agents · LLM orchestration · MCP · automation · n8n · data processing · ecommerce analytics · Git/GitHub · software architecture · testing · secure credential handling.

**AI agents, LLM orchestration, MCP, n8n and other future capabilities are TARGET capabilities.** Never describe one as implemented until corresponding code and tests actually exist.

This applies to the README, LEARNING.md, commit messages, and any summary written for a reviewer. A planned capability is described as planned. Claiming an unbuilt capability is the same category of error as fabricating data — see "Core Principle" and "Missing Data and Failure Semantics".

Code and documentation must be understandable by another developer reviewing the repository during a hiring process.

Reference docs: `README.md` (what each phase does) · `docs/LEARNING.md` (why, with worked numbers) · `docs/MAINTENANCE.md` (recurring checks). This file holds only the stable, load-bearing rules.
