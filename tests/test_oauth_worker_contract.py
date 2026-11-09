"""Cross-boundary contract tests for the Cloudflare Worker relay.

The Worker's own behavioural tests live in
`oauth_worker/test/callback.test.mjs` and run under `node --test`. This
file exists because the contract that matters most spans two languages
and two deployments, and the project's primary gate is pytest: if the
Worker loosens a shape the local helper still rejects -- or worse, the
reverse -- the hop silently breaks or silently widens.

Nothing here needs Node. The single end-to-end test that does is skipped
when Node is unavailable, and CI runs it.
"""

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from src.integrations import mercadolivre_oauth as local

WORKER_DIR = pathlib.Path(__file__).resolve().parents[1] / "oauth_worker"
SOURCE_PATH = WORKER_DIR / "src" / "callback.js"
WRANGLER_PATH = WORKER_DIR / "wrangler.toml"
MANIFEST_PATH = WORKER_DIR / "package.json"

SOURCE = SOURCE_PATH.read_text(encoding="utf-8")
WRANGLER = WRANGLER_PATH.read_text(encoding="utf-8")

_STRING_CONST = re.compile(r'export const (\w+) = "([^"]*)";')
_NUMBER_CONST = re.compile(r"export const (\w+) = (\d+);")

CONSTANTS = {name: value for name, value in _STRING_CONST.findall(SOURCE)}
CONSTANTS.update({name: int(value) for name, value in _NUMBER_CONST.findall(SOURCE)})

# Both files deliberately NAME the things they do not do, so a substring
# search over the raw text flags their own documentation. Same reason
# .claude/skills/invariant-check uses the AST rather than grep: scan the
# code, not the prose that explains the code.
CODE_ONLY = re.sub(r"/\*.*?\*/", "", SOURCE, flags=re.DOTALL)
WRANGLER_CODE_ONLY = "\n".join(
    line for line in WRANGLER.splitlines() if not line.lstrip().startswith("#"))


def _toml_section(name: str) -> str:
    """The body of one TOML section, stopping at the next header."""
    body = WRANGLER_CODE_ONLY.split(f"[{name}]", 1)[1]
    return body.split("\n[", 1)[0]


# -- the shape contract is identical on both sides of the hop ----------


@pytest.mark.parametrize("core_name,python_pattern", [
    ("STATE_CORE", local.STATE_PATTERN),
    ("CODE_CORE", local.CODE_PATTERN),
    ("ERROR_CORE", local.ERROR_PATTERN),
])
def test_validation_shapes_match_the_local_helper(core_name, python_pattern):
    """JavaScript has no \\A/\\Z, so the anchors are added, not compared.

    A JS `^...$` without the `m` flag is equivalent to Python's
    `\\A...\\Z` -- unlike Python's `$`, JS `$` does not also match before
    a trailing newline.
    """
    assert f"\\A{CONSTANTS[core_name]}\\Z" == python_pattern


def test_the_worker_anchors_every_pattern_it_builds():
    for core in ("STATE_CORE", "CODE_CORE", "ERROR_CORE"):
        assert f"`^${{{core}}}$`" in SOURCE


def test_the_worker_never_uses_the_multiline_flag():
    """`m` would make `$` match before a newline and widen every shape."""
    assert not re.search(r'new RegExp\([^)]*,\s*"[a-z]*m[a-z]*"\)', SOURCE)


# -- the destination contract ------------------------------------------


def test_loopback_destination_matches_the_local_listener():
    assert CONSTANTS["LOOPBACK_HOST"] == local.LOOPBACK_HOST
    assert CONSTANTS["LOOPBACK_PATH"] == local.LOOPBACK_PATH
    assert CONSTANTS["DEFAULT_LOOPBACK_PORT"] == local.DEFAULT_LOOPBACK_PORT


def test_the_callback_route_is_the_registered_path():
    assert CONSTANTS["CALLBACK_PATH"] == "/api/mercadolivre/callback"


def test_the_destination_is_assembled_only_from_literals():
    assert (
        "`http://${LOOPBACK_HOST}:${port}${LOOPBACK_PATH}?${query.toString()}`"
        in SOURCE)
    # Exactly one place builds a destination.
    assert SOURCE.count("http://${") == 1


@pytest.mark.parametrize("parameter", [
    "next", "return_to", "redirect_uri", "url", "host", "continue",
])
def test_no_caller_controlled_redirect_parameter_is_read(parameter):
    assert f'get("{parameter}")' not in SOURCE
    assert f'params.get("{parameter}")' not in SOURCE


def test_only_the_four_oauth_parameters_are_read():
    read = sorted(set(re.findall(r'params\.(?:get|has)\("(\w+)"\)', SOURCE)))
    assert read == ["code", "error", "error_description", "state"]


# -- no credential, no state, no logging ------------------------------


def test_the_worker_logs_nothing():
    assert "console." not in SOURCE


def test_the_worker_has_no_imports_and_no_dependencies():
    assert not re.search(r"^\s*import\s", SOURCE, re.MULTILINE)
    assert "require(" not in SOURCE
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert "dependencies" not in manifest
    assert "devDependencies" not in manifest


def test_the_worker_never_evaluates_anything():
    for dangerous in ("eval(", "new Function(", "setTimeout("):
        assert dangerous not in SOURCE


def test_the_worker_touches_no_token_or_secret():
    for forbidden in ("access_token", "refresh_token", "client_secret",
                      "code_verifier"):
        assert forbidden not in CODE_ONLY


def test_the_worker_sets_no_authorization_header():
    assert not re.search(r'set\(\s*"Authorization"', CODE_ONLY)
    assert "Bearer" not in CODE_ONLY


def test_the_worker_reads_only_the_port_variable():
    accesses = sorted(set(re.findall(r"env\s*(?:\.\w+|\[[^\]]+\])", SOURCE)))
    assert accesses == ["env[PORT_VAR]"]


# -- deployment configuration cannot reach the commercial site ---------


def test_wrangler_declares_the_separate_worker():
    assert 'name = "ravz-ml-oauth"' in WRANGLER
    assert 'main = "src/callback.js"' in WRANGLER
    assert "compatibility_date" in WRANGLER


def test_wrangler_declares_no_route_or_custom_domain():
    """A `routes` entry is how a Worker attaches to an existing zone.

    Declaring none, with workers_dev = true, is what guarantees this
    deployment cannot bind itself to ravztech.com.br or change DNS.
    """
    for key in ("routes", "route ", "custom_domain", "zone_id", "zone_name"):
        assert key not in WRANGLER_CODE_ONLY
    assert "workers_dev = true" in WRANGLER_CODE_ONLY


def test_wrangler_declares_no_storage_binding():
    for binding in ("kv_namespaces", "d1_databases", "r2_buckets",
                    "durable_objects", "[[queues", "hyperdrive"):
        assert binding not in WRANGLER_CODE_ONLY


def test_wrangler_disables_worker_log_retention():
    """The authorization code travels in the request URL."""
    assert "enabled = false" in _toml_section("observability")


def test_wrangler_declares_exactly_one_variable_and_no_secret():
    variables = re.findall(r"^(\w+)\s*=", _toml_section("vars"), re.MULTILINE)
    assert variables == ["RAVZ_OAUTH_LOOPBACK_PORT"]


# -- end to end across the two languages -------------------------------


@pytest.mark.skipif(shutil.which("node") is None,
                    reason="Node is required to execute the Worker's own logic")
def test_the_workers_real_output_is_accepted_by_the_local_listener():
    """Relay out -> local in, executing the ACTUAL Worker code.

    The constant comparisons above check the contract; this one proves
    the two halves compose. It runs the Worker's `decide()` under Node
    and feeds the emitted Location straight into the Python interpreter.
    """
    state = local.generate_state()
    code = "TG-1234567890abcdef-123456789"
    script = (
        "const m = await import(process.argv[1]);"
        "const d = m.decide(process.argv[2], {port: m.DEFAULT_LOOPBACK_PORT});"
        "process.stdout.write(JSON.stringify(d));"
    )
    result = subprocess.run(
        ["node", "--input-type=module", "-e", script,
         SOURCE_PATH.resolve().as_uri(), f"code={code}&state={state}"],
        capture_output=True, text=True, timeout=60, check=True)
    decision = json.loads(result.stdout)
    assert decision["kind"] == "relay"

    from urllib.parse import urlparse
    emitted = urlparse(decision["location"])
    assert emitted.scheme == "http"
    assert emitted.hostname == local.LOOPBACK_HOST
    assert emitted.path == local.LOOPBACK_PATH

    outcome = local.interpret_callback(
        f"{emitted.path}?{emitted.query}", state)
    assert outcome.kind == local.OUTCOME_SUCCESS
    assert outcome.code == code
