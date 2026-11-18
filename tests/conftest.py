import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "real_token_path: keep the real default TOKEN_FILE (the test inspects the default itself)",
    )


@pytest.fixture(autouse=True)
def _isolate_stored_mercadolivre_credential(request, monkeypatch, tmp_path):
    """Never let a real `.secrets/mercadolivre_tokens.json` reach a test.

    After `authorize` runs on a developer machine, the real credential file
    sits in the repository root, and any test that calls the provider
    without patching TOKEN_FILE would silently pick it up and send it.
    Tests that need a stored credential set TOKEN_FILE themselves (that
    overrides this); tests that inspect the default path opt out with
    @pytest.mark.real_token_path.
    """
    if request.node.get_closest_marker("real_token_path"):
        return
    from src.integrations import mercadolivre_oauth as oauth
    monkeypatch.setattr(oauth, "TOKEN_FILE", tmp_path / "isolated-tokens.json")
