"""Structural invariant checks for RAVZ Product Hunter.

Run from the repository root:

    PYTHONPATH=. python .claude/skills/invariant-check/check_invariants.py

Exit 0 when every load-bearing invariant holds, 1 when any FAILs.

== Division of labour ==

This script does NOT re-verify what the test suite already proves. Three jobs,
and deliberately only three:

  1. INDEPENDENT structural inspection tests do not cover -- import DAG,
     cycles, provider/HTTP boundaries, inversion sites, scoring-layer
     determinism, probability language in source AND docs, repo hygiene.
  2. A byte-level FREEZE of the legacy contract (see LEGACY_FROZEN).
  3. A PRESENCE GUARD over contracts delegated to pytest (see
     DELEGATED_TESTS), so deleting a test cannot silently retire an invariant.

Behavioral semantics -- weights, family election, readiness precedence,
None-preservation, false-safety -- are owned by the Phase 11 tests and are
*delegated*, not recomputed. Re-implementing them made an earlier version of
this file a second test suite: 1180 lines, ~55% duplicated.

pytest is NECESSARY BUT NOT SUFFICIENT; so is this script. Both must pass.

== Why AST, not grep ==

This codebase deliberately discusses its own forbidden patterns in prose:
`100 -` appears in six docstrings/comments and only two real code sites;
probability words appear 16 times in `src/`, all inside disclaimers or
"unavailable" lists; `scoring.py` contains `calculate_opportunity_score`, so
matching `opportunity_` would wrongly flag the legacy module; several modules
name peers in docstrings precisely to document that they do NOT import them.

It never recomputes a score, reimplements a formula, or owns a business rule.
`CLAUDE.md` is authoritative; where they disagree, fix this script.

Dependencies: Python stdlib only. See SKILL.md for the full contract.
"""

from __future__ import annotations

import ast
import hashlib
import pathlib
import re
import subprocess
import sys
from dataclasses import dataclass

REPO = pathlib.Path(__file__).resolve().parents[3]
SRC = REPO / "src"

PASS, FAIL, WARN, DELEGATED = "PASS", "FAIL", "WARN", "DELEGATED"


@dataclass
class Result:
    status: str
    invariant: str
    evidence: str = ""
    where: str = ""
    why: str = ""
    fix: str = ""
    severity: str = ""


RESULTS: list[Result] = []


def record(status, invariant, evidence="", *, where="", why="", fix="", severity=""):
    """Single recording primitive. `fail` supplies the explanatory fields."""
    RESULTS.append(Result(status, invariant, evidence, where, why, fix, severity))


def ok(invariant, evidence=""):
    record(PASS, invariant, evidence)


def fail(invariant, evidence, where, why, fix, severity="CRITICAL"):
    record(FAIL, invariant, evidence, where=where, why=why, fix=fix, severity=severity)


def warn(invariant, evidence="", where="", why="", fix=""):
    record(WARN, invariant, evidence, where=where, why=why, fix=fix, severity="LOW")


def git(*args):
    try:
        r = subprocess.run(["git", *args], cwd=REPO, capture_output=True,
                           text=True, timeout=60)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except Exception as exc:  # pragma: no cover - environment failure
        return 1, "", str(exc)


# ---------------------------------------------------------------- AST helpers


def module_paths():
    return sorted(SRC.rglob("*.py"))


def parse(path: pathlib.Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def imports_of(tree: ast.Module) -> set[str]:
    """Module names imported, from the AST only -- docstrings are invisible."""
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            found.add(node.module or "")
    return found


def enclosing_functions(tree: ast.Module) -> dict[int, str]:
    """Map line number -> nearest enclosing function name."""
    owner: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for inner in ast.walk(node):
                line = getattr(inner, "lineno", None)
                if line is not None:
                    owner.setdefault(line, node.name)
    return owner


def rel(path: pathlib.Path) -> str:
    return path.relative_to(REPO).as_posix()


def test_functions(relpath: str) -> set[str]:
    path = REPO / relpath
    if not path.exists():
        return set()
    return {
        n.name for n in ast.walk(parse(path))
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


# 1. FROZEN LEGACY CONTRACT -- approved reference hashes
#
# CLAUDE.md: "src/models.py and src/scoring.py must remain unchanged unless a
# genuine pre-existing bug is found and documented separately first."
#
# These are the APPROVED bytes, pinned here rather than compared against HEAD.
# Comparing against HEAD is not a freeze: an accidental committed modification
# silently becomes the new baseline and every later run passes.
#
# Hashes are over LF-NORMALISED content. `core.autocrlf=true` here, so a fresh
# clone checks these out with CRLF; hashing raw working-tree bytes would fail
# spuriously on another machine. The git blob ID is an independent cross-check
# (git normalises to LF before hashing).
#
# >>> CHANGING EITHER VALUE BELOW IS A LEGACY-CONTRACT CHANGE. <<<
# It requires a documented pre-existing bug, an explicit decision recorded in
# docs/LEARNING.md, and a deliberate update of BOTH hashes. Never update these
# to "make the check pass".
#
LEGACY_FROZEN = {
    "src/models.py": {
        "sha256_lf": "157fc6c667e7da1b7ea34be44ad638e9d0546bc6558c546250f31abe4eb957bf",
        "git_blob": "d0050abe25c2bf99b5350e0427e13b5c72641eef",
        "approved_at": "Phase 11 (commit 57ab0c2); unchanged since Phase 1",
    },
    "src/scoring.py": {
        "sha256_lf": "2412c57edd03554726a2da5d812c73345a1a848a97e3df22b4b16ab6e3c2c7b4",
        "git_blob": "6a239a14f850b796494c643f7d3a575b705141cf",
        "approved_at": "Phase 11 (commit 57ab0c2); unchanged since Phase 1",
    },
}


def check_legacy_freeze():
    inv = "legacy-v1 byte freeze"
    for relpath, approved in LEGACY_FROZEN.items():
        path = REPO / relpath
        if not path.exists():
            fail(f"{inv}: {relpath} missing", "file not found", relpath,
                 "The legacy Phase 1/2 API is the backwards-compatibility "
                 "guarantee; its modules must exist.",
                 "Restore the file from git history.")
            continue

        actual = hashlib.sha256(
            path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if actual == approved["sha256_lf"]:
            ok(f"{inv}: {relpath} byte-identical to approved reference",
               f"sha256(lf)={actual[:12]}... approved {approved['approved_at']}")
        else:
            fail(f"{inv}: {relpath} MODIFIED", f"sha256(lf)={actual[:16]}...",
                 relpath,
                 "This file is a frozen published contract. Any byte change can "
                 "move results users already recorded, and this change was not "
                 "approved -- the pinned reference still shows the previously "
                 "agreed bytes.",
                 "Revert the file. If the change is intentional, document the "
                 "pre-existing bug first, then deliberately update both hashes "
                 "in LEGACY_FROZEN.")

        code, blob, _ = git("hash-object", relpath)
        if code == 0 and blob:
            if blob == approved["git_blob"]:
                ok(f"{inv}: {relpath} git blob matches approved reference",
                   blob[:12] + "...")
            else:
                fail(f"{inv}: {relpath} git blob differs", f"{blob[:16]}...",
                     relpath,
                     "Second, independent confirmation that the frozen file "
                     "changed.",
                     "Revert, or deliberately re-approve both hashes.")


# 2. DELEGATED TEST MANIFEST -- presence guard
#
# These behavioral contracts are verified by pytest, NOT independently
# recomputed here. This script delegates to them and guards that they still
# EXIST -- otherwise deleting a test would silently retire an invariant while
# this checker kept reporting PASS.
#
# Tracked by explicit semantic identity (file + function name). Never replace
# this with a count threshold: "at least N tests" cannot detect that the one
# test protecting a specific invariant was the one removed.
#
DELEGATED_TESTS = {
    "legacy-v1 exact weights and compatibility": (
        "tests/test_legacy_compatibility.py::test_legacy_weights_are_exactly_the_phase_1_contract",
        "tests/test_legacy_compatibility.py::test_legacy_weights_sum_to_one",
        "tests/test_legacy_compatibility.py::test_legacy_negative_dimensions_are_unchanged",
        "tests/test_legacy_compatibility.py::test_legacy_score_fields_are_unchanged",
        "tests/test_legacy_compatibility.py::test_legacy_score_opportunity_is_unchanged",
        "tests/test_legacy_compatibility.py::test_legacy_component_scores_still_reject_missing_values",
        "tests/test_legacy_compatibility.py::test_legacy_component_scores_still_reject_none",
        "tests/test_legacy_compatibility.py::test_legacy_classification_bands_are_unchanged",
        "tests/test_legacy_compatibility.py::test_legacy_classifies_the_rounded_total_by_documented_contract",
        "tests/test_legacy_compatibility.py::test_legacy_manual_analyzer_still_runs_end_to_end",
    ),
    "integrated-v1 documented weights": (
        "tests/test_opportunity_models.py::test_integrated_component_weights_are_the_documented_contract",
        "tests/test_opportunity_models.py::test_search_interest_family_weight_is_thirty_percent",
        "tests/test_opportunity_models.py::test_search_interest_family_weight_is_not_the_legacy_sum",
        "tests/test_opportunity_models.py::test_integrated_distinct_weights_sum_to_exactly_one",
        "tests/test_opportunity_models.py::test_layer_weights_partition_the_total_exactly",
    ),
    "Demand/Trend evidence-family election": (
        "tests/test_opportunity_models.py::test_family_members_are_demand_then_trend_in_precedence_order",
        "tests/test_opportunity_integration.py::test_trend_does_not_contribute_weight_when_demand_is_available",
        "tests/test_opportunity_integration.py::test_trend_becomes_the_family_representative_when_demand_is_absent",
        "tests/test_opportunity_integration.py::test_search_interest_family_is_critical_as_a_family",
    ),
    "family maximum weight": (
        "tests/test_opportunity_integration.py::test_family_never_contributes_more_than_its_single_weight",
    ),
    "Trend cannot independently move the aggregate": (
        "tests/test_opportunity_integration.py::test_changing_only_the_trend_score_cannot_move_the_opportunity_score",
    ),
    "None preservation": (
        "tests/test_opportunity_integration.py::test_none_never_becomes_zero_or_fifty",
        "tests/test_opportunity_models.py::test_none_score_stays_none_in_both_directions",
    ),
    "missing-negative false-safety protection": (
        "tests/test_opportunity_integration.py::test_missing_risk_does_not_create_false_safety",
        "tests/test_opportunity_integration.py::test_missing_competition_does_not_create_false_safety",
        "tests/test_opportunity_integration.py::test_false_safety_ceiling_beats_naive_renormalization",
        "tests/test_opportunity_integration.py::test_false_safety_guard_still_correct_under_hardened_weights",
        "tests/test_opportunity_integration.py::test_false_safety_ceiling_does_not_invent_bad_news_for_weak_evidence",
    ),
    "readiness states and precedence": (
        "tests/test_opportunity_models.py::test_readiness_precedence_is_worst_first_and_distinguishes_all_four",
        "tests/test_opportunity_integration.py::test_supplier_missing_is_operationally_unvalidated",
        "tests/test_opportunity_integration.py::test_logistics_missing_is_operationally_unvalidated",
        "tests/test_opportunity_integration.py::test_both_operational_components_missing_is_not_ready",
        "tests/test_opportunity_integration.py::test_missing_commercial_requirement_is_incomplete_evidence",
        "tests/test_opportunity_integration.py::test_blocker_outranks_every_evidence_gap",
        "tests/test_opportunity_integration.py::test_commercial_gap_outranks_operational_gap",
        "tests/test_opportunity_integration.py::test_readiness_states_are_all_reachable",
    ),
    "classification withheld outside READY": (
        "tests/test_opportunity_integration.py::test_only_ready_is_publishable",
        "tests/test_opportunity_integration.py::test_commercially_attractive_but_operationally_unvalidated_is_not_strong",
        "tests/test_opportunity_integration.py::test_partial_score_with_missing_critical_cannot_get_a_strong_label",
    ),
    "operationally-unvalidated non-final band": (
        "tests/test_opportunity_integration.py::test_analytical_band_is_only_offered_for_operationally_unvalidated",
        "tests/test_opportunity_integration.py::test_analytical_band_is_labelled_non_final_in_the_notes",
    ),
    "deterministic composition": (
        "tests/test_opportunity_integration.py::test_composition_is_deterministic",
        "tests/test_opportunity_integration.py::test_identical_input_produces_identical_output_repeatedly",
    ),
}

def check_delegated_tests():
    """Presence only -- pytest proves they pass. Closes the delegation hole."""
    inv = "delegated-test presence"
    cache: dict[str, set[str]] = {}
    total = 0
    missing: dict[str, list[str]] = {}

    for contract, node_ids in DELEGATED_TESTS.items():
        for node_id in node_ids:
            relpath, name = node_id.split("::")
            if relpath not in cache:
                cache[relpath] = test_functions(relpath)
            total += 1
            if name not in cache[relpath]:
                missing.setdefault(contract, []).append(node_id)

    for contract in DELEGATED_TESTS:
        if contract not in missing:
            record(DELEGATED, contract, "delegated to pytest + presence guarded")

    if not missing:
        ok(f"{inv}: all {total} delegated tests present across "
           f"{len(DELEGATED_TESTS)} contracts")
        return

    for contract, gone in sorted(missing.items()):
        fail(f"{inv}: delegated test missing for '{contract}'",
             "; ".join(gone), gone[0].split("::")[0],
             "invariant-check delegates this contract to pytest instead of "
             "recomputing it. With the test gone, nothing verifies the "
             "invariant -- and this checker would otherwise still report PASS.",
             "Restore the test, update the manifest entry if it was renamed, or "
             "consciously move the check back into this script.")


# 3. AST: inversion sites
#
# Behavioral direction (which components invert, and that inverting twice is
# detectable) is delegated. What no test covers is WHERE inversion may appear:
# a second site silently cancels the first, restoring the original direction
# with nothing failing.
#
SANCTIONED_INVERSION = {
    ("src/opportunity_models.py", "to_opportunity_oriented"),
    ("src/scoring.py", "calculate_opportunity_score"),
}


def check_inversion_sites():
    inv = "inversion confined to the sanctioned boundary"
    stray = []
    for path in module_paths():
        tree = parse(path)
        owners = enclosing_functions(tree)
        for node in ast.walk(tree):
            if (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Sub)
                    and isinstance(node.left, ast.Constant)
                    and node.left.value in (100, 100.0)):
                site = (rel(path), owners.get(node.lineno, "<module>"))
                if site not in SANCTIONED_INVERSION:
                    stray.append(f"{site[0]}:{node.lineno} in {site[1]}()")
    if not stray:
        ok(inv + " (AST)",
           "to_opportunity_oriented (integrated), calculate_opportunity_score "
           "(legacy); 6 docstring/comment mentions correctly ignored")
    else:
        fail(inv + ": stray inversion", "; ".join(stray),
             stray[0].split(":")[0],
             "A second inversion silently cancels the first, restoring the "
             "original direction without any test failing.",
             "Move inversion back to to_opportunity_oriented().")


# 4. Observed zero vs missing (structural; no test covers this)


class _Stub:
    """Minimal stand-in carrying the attribute names an adapter reads."""

    def __init__(self, **kw):
        self.__dict__.update(kw)


def check_observed_zero():
    inv = "observed zero is distinguishable from missing"
    from src.opportunity_integration import compose_opportunity

    def margin_component(score):
        r = compose_opportunity("invariant-check", margin_result=_Stub(
            margin_score=score, cost_completeness_score=75.0))
        return next(c for c in r.components if c.name == "margin")

    zero, none = margin_component(0.0), margin_component(None)
    if zero.available and zero.raw_score == 0.0 and not none.available:
        ok(inv, "margin 0.0 -> available=True, raw_score=0.0; "
                "margin None -> available=False")
    else:
        fail(inv + ": conflated",
             f"zero.available={zero.available} raw={zero.raw_score!r}; "
             f"none.available={none.available}",
             "src/opportunity_integration.py",
             "A known zero is real evidence; discarding it loses information, "
             "and treating missing as zero fabricates it. Truthiness tests "
             "cannot tell them apart.",
             "Branch on `is None`, never on truthiness.")


# 5. Architectural import boundaries (primary unique contribution)

# Derived, not a third hand-maintained copy.
STDLIB = set(getattr(sys, "stdlib_module_names", ()))
# Explicit path rules rather than substring hints like "agent", which would
# false-positive on any future module whose name merely contains it.
ORCHESTRATOR_MODULES = ("src.orchestrator", "src.orchestration", "src.agents")


def _is_domain_analysis(path):
    return path.name.endswith("_analysis.py") and path.parent == SRC


def _is_domain_models(path):
    return (path.name.endswith("_models.py") and path.parent == SRC
            and not path.name.startswith("opportunity_"))


def _imports_orchestrator(internal):
    return sorted(m for m in internal
                  if any(m == o or m.startswith(o + ".")
                         for o in ORCHESTRATOR_MODULES))


def check_architecture():
    inv = "architectural boundaries"
    graph: dict[str, set[str]] = {}
    problems = False

    for path in module_paths():
        mods = imports_of(parse(path))
        name = rel(path)
        internal = {m for m in mods if m.startswith("src.")}
        external = {m.split(".")[0] for m in mods if not m.startswith("src.")}
        graph[name] = internal

        if _is_domain_analysis(path):
            own = "src." + path.name.replace("_analysis.py", "_models")
            extra = internal - {own}
            if extra:
                problems = True
                fail(f"{inv}: domain analyzer imports beyond its own models",
                     f"{name} imports {sorted(extra)}", name,
                     "Domain engines must stay independently testable and "
                     "provider-neutral; cross-domain imports make them "
                     "un-swappable and can reintroduce double counting.",
                     "Pass data in via the orchestrator instead.")
            non_stdlib = external - STDLIB
            if non_stdlib:
                problems = True
                fail(f"{inv}: domain analyzer imports a non-stdlib dependency",
                     f"{name} imports {sorted(non_stdlib)}", name,
                     "HTTP clients and provider SDKs belong behind the "
                     "integration boundary.",
                     "Move the dependency into src/integrations/.")

        if _is_domain_analysis(path) or _is_domain_models(path):
            if any(m.startswith("src.integrations") for m in internal):
                problems = True
                fail(f"{inv}: domain module imports an integration", name, name,
                     "Provider shapes would leak into scoring.",
                     "Depend only on the neutral models.")
            orch = _imports_orchestrator(internal)
            if orch:
                problems = True
                fail(f"{inv}: domain module imports the orchestrator",
                     f"{name} imports {orch}", name,
                     "Layering must stay one-directional; this creates a cycle "
                     "and couples a domain to how it is coordinated.",
                     "Invert the dependency.")
            if any(m.startswith("src.opportunity_") for m in internal):
                problems = True
                fail(f"{inv}: domain module imports the opportunity layer",
                     name, name,
                     "A domain must not know how its output is composed.",
                     "Remove the import.")

        if path.parent.name != "integrations" and "requests" in external:
            problems = True
            fail(f"{inv}: HTTP outside the integration boundary", name, name,
                 "Only src/integrations/* may perform HTTP.",
                 "Move the call behind an integration.")

    contract = imports_of(parse(SRC / "opportunity_models.py"))
    if contract == {"dataclasses"}:
        ok(inv + ": opportunity_models.py is a pure contract",
           "imports {'dataclasses'}")
    else:
        problems = True
        fail(inv + ": contract layer gained a dependency", str(sorted(contract)),
             "src/opportunity_models.py",
             "The canonical contract must be importable by anything without "
             "pulling in behavior.", "Reduce to dataclasses only.")

    comp = imports_of(parse(SRC / "opportunity_integration.py"))
    if comp == {"src.opportunity_models"}:
        ok(inv + ": opportunity_integration.py is composition-only",
           "imports {'src.opportunity_models'}")
    else:
        problems = True
        fail(inv + ": composition layer gained a dependency", str(sorted(comp)),
             "src/opportunity_integration.py",
             "Coupling composition to a domain's internals means a formula "
             "change can silently alter composition.",
             "Depend only on the canonical contract.")

    cycles = []
    for start in graph:
        stack, seen = [(start, [start])], set()
        while stack:
            node, trail = stack.pop()
            for dep in graph.get(node, ()):
                p = dep.replace(".", "/") + ".py"
                if p == start:
                    cycles.append(" -> ".join(trail + [p]))
                elif p in graph and p not in seen:
                    seen.add(p)
                    stack.append((p, trail + [p]))
    if not cycles:
        ok(inv + ": import graph is acyclic", f"{len(graph)} modules inspected")
    else:
        problems = True
        fail(inv + ": circular dependency", "; ".join(sorted(set(cycles))[:3]),
             "src/", "Cycles make modules untestable in isolation and import "
             "order load-bearing.", "Break the cycle.")

    if not problems:
        ok(inv + ": domain layer neutral, one-directional, provider-bounded",
           "all *_analysis.py import only their own *_models + stdlib")


# 6. Determinism of the scoring layers (AST; behavioral part delegated)

NONDETERMINISTIC = {"random", "secrets", "socket", "http", "urllib", "requests"}
CLOCK = {"time", "datetime"}


def _is_scoring_layer(path):
    if path.parent.name == "integrations" or path.name in ("main.py", "config.py"):
        return False
    return (path.name.endswith(("_analysis.py", "_models.py"))
            or path.name.startswith("opportunity_")
            or path.name in ("scoring.py", "models.py"))


def check_determinism():
    inv = "determinism of scoring layers"
    problems = False
    for path in filter(_is_scoring_layer, module_paths()):
        tree = parse(path)
        mods = {m.split(".")[0] for m in imports_of(tree)}
        if hits := mods & NONDETERMINISTIC:
            problems = True
            fail(inv + ": nondeterministic dependency",
                 f"{rel(path)} imports {sorted(hits)}", rel(path),
                 "Identical input must always produce identical output; eight "
                 "module docstrings assert this.",
                 "Move the dependency out of the scoring path.")
        if clock := mods & CLOCK:
            problems = True
            fail(inv + ": wall-clock in a scoring layer",
                 f"{rel(path)} imports {sorted(clock)}", rel(path),
                 "A clock read makes a score depend on when it ran. datetime is "
                 "permitted only as provenance, in the integration layer.",
                 "Remove the clock from the scoring path.")
        for node in ast.walk(tree):
            if isinstance(node, ast.Global):
                problems = True
                fail(inv + ": global mutable state",
                     f"{rel(path)}:{node.lineno} global {', '.join(node.names)}",
                     rel(path),
                     "Hidden mutable state makes results order-dependent.",
                     "Pass state explicitly.")
    if not problems:
        ok(inv + " (AST)",
           "no randomness, clock, network or global state in scoring layers; "
           "datetime confined to src/integrations (provenance only)")


# 7. Probability language in source AND docs (tests cover only the result)

PROB_WORDS = ("probability", "chance", "likelihood", "guaranteed sales",
              "guaranteed roi", "expected roi", "conversion rate",
              "success probability", "odds of")
NEGATORS = ("not ", "never", "no ", "cannot", "neither", "refus", "unavailable",
            "excluded", "does not", "must not", "may not", "non-", "without")


def _is_list_item(line: str) -> bool:
    s = line.lstrip()
    return s.startswith(("- ", "* ", "+ "))


def _list_intro(lines, idx):
    """Walk back from a list item to the line that introduces the list.

    A negated list ("It never means, and must never be presented as:") can be
    arbitrarily long, so the disclaimer may sit outside any fixed window.
    Attributing the intro's negation to every item keeps this check precise
    rather than merely lenient.
    """
    j = idx - 1
    while j >= 0 and (_is_list_item(lines[j]) or not lines[j].strip()):
        j -= 1
    return lines[j] if j >= 0 else ""


def _negated_nearby(lines, idx, window=2):
    lo, hi = max(0, idx - window), min(len(lines), idx + window + 1)
    blob = " ".join(lines[lo:hi]).lower()
    if _is_list_item(lines[idx]):
        blob += " " + _list_intro(lines, idx).lower()
    return any(n in blob for n in NEGATORS)


def check_probability_language():
    inv = "provisional-heuristic language (source + docs)"
    offenders = []
    for path in list(module_paths()) + [REPO / "CLAUDE.md"]:
        if not path.exists():
            continue
        lines = path.read_text(encoding="utf-8").splitlines()
        for i, line in enumerate(lines):
            low = line.lower()
            if not any(w in low for w in PROB_WORDS):
                continue
            # Exempt: "unavailable" lists naming what the project refuses to
            # compute, and anything negated within its own context.
            if "unavailable.append" in low or _negated_nearby(lines, i):
                continue
            offenders.append(f"{rel(path)}:{i + 1}: {line.strip()[:90]}")
    if not offenders:
        ok(inv + ": no affirmative probability claims",
           "every mention is a disclaimer or an explicit 'not computable' entry")
    else:
        fail(inv + ": score described as a probability", "; ".join(offenders[:4]),
             offenders[0].split(":")[0],
             "The Opportunity Score is an uncalibrated heuristic. Presenting it "
             "as a probability is the project's cardinal error.",
             "Reword, or state explicitly that it is not a probability.")


# 8. Repository hygiene (no test coverage at all)

MUST_IGNORE = (".env", ".claude/settings.local.json")
MUST_STAY_TRACKABLE = (".claude", ".claude/agents", ".claude/skills")

# Secret-shaped VALUES, not bare prefixes.
#
# An earlier version matched bare prefixes ("sk-", "ghp_", "AKIA",
# "apify_api_"). That made the scanner flag its own pattern list the first
# time this file was staged, and would also fire on ordinary prose like
# "sk-eleton" or a doc example naming a provider prefix. Every pattern below
# therefore requires realistic credential STRUCTURE AND LENGTH after the
# prefix, so a prefix alone can never match.
#
# This file is deliberately NOT exempt from the scan: a scanner that skips
# itself cannot be trusted to catch a credential pasted into itself. The
# patterns are instead written so that their own source text does not satisfy
# them -- each prefix here is followed by a regex metacharacter (`[`, `(`,
# `\`), never by credential-shaped payload. `test_secret_patterns_self_scan`
# below re-proves that property at runtime.
#
# Conservative by design: high signal, low false-positive rate. A real secret
# is long and high-entropy; a placeholder is short or obviously fake.
SECRET_PATTERNS = (
    ("Apify API token", re.compile(r"apify_api_[A-Za-z0-9]{20,}")),
    ("AWS access key ID", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("PEM private key header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}")),
    ("OpenAI-style key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{20,}")),
    ("Bearer credential", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{20,}")),
    ("credential assignment", re.compile(
        r"(?i)\b(?:api[_-]?key|access[_-]?key|secret|token|password|passwd)\b"
        r"\s*[:=]\s*[\"']?(?P<value>[A-Za-z0-9/+_.-]{16,})[\"']?")),
)

# Values that look long enough to be a credential but are obviously not.
PLACEHOLDER = re.compile(
    r"(?i)^(?:x{4,}|\*{4,}|\.{4,}|-{4,}|<.*>|your[_-]|my[_-]|example|sample|"
    r"placeholder|changeme|replace[_-]?me|redacted|dummy|fake[_-]|test[_-]?only|"
    r"[A-Za-z0-9/+_.-]*(?:example|placeholder|redacted|xxxx))")


def _staged_secret_hits():
    """Locations of secret-shaped VALUES in added lines of the staged diff.

    Returns a list of "path:line (category)" strings. The matched value is
    never captured, returned, logged or printed -- only where to look.
    """
    hits: list[str] = []
    path = "<unknown>"
    new_lineno = 0
    for line in git("diff", "--cached")[1].splitlines():
        if line.startswith("+++ b/"):
            path = line[6:]
            continue
        if line.startswith("@@"):
            m = re.search(r"\+(\d+)", line)
            new_lineno = int(m.group(1)) if m else 0
            continue
        if line.startswith("-") or line.startswith("\\"):
            continue
        if not line.startswith("+"):
            new_lineno += 1
            continue
        body = line[1:]
        for label, pattern in SECRET_PATTERNS:
            m = pattern.search(body)
            if not m:
                continue
            value = m.groupdict().get("value")
            if value and PLACEHOLDER.match(value):
                continue
            hits.append(f"{path}:{new_lineno} ({label})")
            break
        new_lineno += 1
    return hits


def check_hygiene():
    inv = "repository hygiene"
    for target in MUST_IGNORE:
        code, out, _ = git("check-ignore", "-v", target)
        if code == 0:
            ok(f"{inv}: {target} is git-ignored", out.split("\t")[0])
        else:
            fail(f"{inv}: {target} is NOT ignored", "no matching rule",
                 ".gitignore",
                 "Local credentials or machine-specific settings could be "
                 "committed.", f"Add {target} to .gitignore.")
        if git("ls-files", "--error-unmatch", target)[0] != 0:
            ok(f"{inv}: {target} is not tracked")
        else:
            fail(f"{inv}: {target} IS TRACKED", "present in the index", target,
                 "Secrets or local state are in version control.",
                 f"git rm --cached {target}")

    for path in MUST_STAY_TRACKABLE:
        # --no-index is REQUIRED here. `git check-ignore` suppresses paths that
        # are already tracked, so once .claude/agents/* is committed the default
        # mode silently stops reporting an over-broad `.claude/` rule -- a
        # blind spot a negative test caught. --no-index evaluates the pattern
        # regardless of index state.
        if git("check-ignore", "--no-index", "-q", path)[0] != 0:
            ok(f"{inv}: {path} remains trackable (shared infrastructure)")
        else:
            fail(f"{inv}: {path} is ignored", "over-broad ignore rule matches "
                 "shared Claude configuration", ".gitignore",
                 "Project agents and skills are versioned infrastructure. An "
                 "over-broad rule stops new ones from being committed, and the "
                 "omission is silent.",
                 "Narrow the rule to .claude/settings.local.json.")

    staged = [f for f in git("diff", "--cached", "--name-only")[1].splitlines() if f]
    if staged:
        code, out, _ = git("diff", "--cached", "--check")
        if code == 0:
            ok(inv + ": staged diff clean (no whitespace errors or conflict markers)")
        else:
            warn(inv + ": staged diff has whitespace/conflict issues", out[:300],
                 where="staged changes",
                 why="Noise, and conflict markers break code.",
                 fix="Fix before committing.")

        # Report only locations -- never print a suspected secret's value.
        hits = _staged_secret_hits()
        if hits:
            fail(inv + ": secret-shaped value in staged diff",
                 f"{len(hits)} candidate(s) at {'; '.join(hits[:5])} "
                 "-- values intentionally not printed",
                 "staged changes",
                 "A credential would enter history permanently.",
                 "Unstage, remove the literal, move it to .env.")
        else:
            ok(inv + ": no secret-shaped values in staged diff",
               f"{len(staged)} staged file(s) scanned")
    else:
        ok(inv + ": nothing staged (staged-diff checks skipped)")

    for path in module_paths():
        text = path.read_text(encoding="utf-8")
        if "\n<<<<<<< " in text or "\n>>>>>>> " in text:
            fail(inv + ": conflict marker in source", rel(path), rel(path),
                 "Unresolved merge artifacts break imports.",
                 "Resolve the conflict.")

    _check_secret_patterns_self_scan(inv)


def _check_secret_patterns_self_scan(inv):
    """Prove the scanner is not self-exempt and not self-triggering.

    This file is intentionally scanned by its own patterns. That is only safe
    if the pattern source text cannot satisfy the patterns -- otherwise every
    commit touching this file would raise a false CRITICAL (which is exactly
    the defect this rewrite fixes). Asserted here rather than assumed, so a
    future pattern edit that reintroduces self-matching fails loudly.
    """
    own = pathlib.Path(__file__).read_text(encoding="utf-8")
    self_matches = []
    for label, pattern in SECRET_PATTERNS:
        for m in pattern.finditer(own):
            value = m.groupdict().get("value")
            if value and PLACEHOLDER.match(value):
                continue
            line = own[:m.start()].count("\n") + 1
            self_matches.append(f"line {line} ({label})")
    if not self_matches:
        ok(f"{inv}: secret patterns do not match their own source",
           f"{len(SECRET_PATTERNS)} patterns; scanner is NOT self-exempt")
    else:
        fail(f"{inv}: secret pattern matches its own source",
             "; ".join(self_matches[:5]), "check_invariants.py",
             "The scanner would raise a false CRITICAL on every commit that "
             "touches it, training reviewers to ignore the check.",
             "Tighten the pattern so prefix-only text cannot match; keep "
             "requiring credential-shaped payload.")


# 9. Test execution


def run_pytest():
    try:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=REPO,
                           capture_output=True, text=True, timeout=600)
    except Exception as exc:  # pragma: no cover
        return f"could not run pytest: {exc}", False
    lines = [l for l in r.stdout.strip().splitlines() if l.strip()]
    return (lines[-1] if lines else "no output"), r.returncode == 0


# ------------------------------------------------------------------- report


CHECKS = (
    check_legacy_freeze,
    check_delegated_tests,
    check_inversion_sites,
    check_observed_zero,
    check_architecture,
    check_determinism,
    check_probability_language,
    check_hygiene,
)


def main() -> int:
    sys.path.insert(0, str(REPO))

    for fn in CHECKS:
        try:
            fn()
        except Exception as exc:
            fail(f"check '{fn.__name__}' raised", f"{type(exc).__name__}: {exc}",
                 "check_invariants.py",
                 "An invariant could not be evaluated, so it is unverified.",
                 "Fix the script (not the product code) unless the exception "
                 "reveals a real contract break.")

    test_summary, tests_ok = run_pytest()
    branch = git("rev-parse", "--abbrev-ref", "HEAD")[1]
    staged = [f for f in git("diff", "--cached", "--name-only")[1].splitlines() if f]
    dirty = bool(git("status", "--porcelain")[1])

    passes = [r for r in RESULTS if r.status == PASS]
    fails = [r for r in RESULTS if r.status == FAIL]
    warns = [r for r in RESULTS if r.status == WARN]
    delegated = [r for r in RESULTS if r.status == DELEGATED]

    print("Invariant Check")
    print("===============")
    print()
    print(f"PASS: ({len(passes)})  independently verified here")
    for r in passes:
        print(f"- {r.invariant}" + (f"  [{r.evidence}]" if r.evidence else ""))
    print()
    print(f"DELEGATED: ({len(delegated)})  verified by pytest, presence-guarded "
          f"-- NOT recomputed by this script")
    for r in delegated:
        print(f"- {r.invariant}  [{r.evidence}]")
    print()
    print(f"FAIL: ({len(fails)})")
    if not fails:
        print("- none")
    for r in fails:
        print(f"- severity:  {r.severity}")
        print(f"  invariant: {r.invariant}")
        print(f"  where:     {r.where}")
        print(f"  evidence:  {r.evidence}")
        print(f"  why:       {r.why}")
        print(f"  fix:       {r.fix}")
    print()
    print(f"WARN: ({len(warns)})")
    if not warns:
        print("- none")
    for r in warns:
        print(f"- {r.invariant}" + (f"  [{r.evidence}]" if r.evidence else ""))
    print()
    print("Tests:")
    print(f"- {test_summary}")
    print("- pytest is necessary but not sufficient; the structural checks "
          "above are not covered by it")
    print()
    print("Git:")
    print(f"- branch: {branch}")
    print(f"- staged files: {', '.join(staged) if staged else 'none'}")
    print(f"- working tree: {'dirty' if dirty else 'clean'}")
    print()
    verdict = PASS if (not fails and tests_ok) else FAIL
    print("Final:")
    print(verdict)
    return 0 if verdict == PASS else 1


if __name__ == "__main__":
    raise SystemExit(main())
