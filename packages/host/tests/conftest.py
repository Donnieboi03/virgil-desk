import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))


@pytest.fixture(autouse=True)
def _force_mock_backend(monkeypatch):
    """CI and local dev may have DESK_AGENT_BACKEND=hermes in .env; tests use mock."""
    monkeypatch.setenv("DESK_AGENT_BACKEND", "mock")
    # Existing extension-path tests; harness suites set DESK_BROWSER_DRIVER=harness.
    monkeypatch.setenv("DESK_BROWSER_DRIVER", "extension")
    from desk_host.config import clear_config_cache

    clear_config_cache()
    yield
    clear_config_cache()


@pytest.fixture
def fake_extension_connected(monkeypatch):
    """Simulate extension WS without a live socket (unit/integration helpers)."""

    async def _fake_send(_message: dict) -> bool:
        return True

    import desk_host.app as app_mod

    monkeypatch.setattr(app_mod, "_extension_connected", True)
    monkeypatch.setattr(app_mod, "_extension_ws", object())
    monkeypatch.setattr(app_mod, "_send_to_extension", _fake_send)
    yield
