import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "host"))
sys.path.insert(0, str(ROOT / "host" / "tests"))

from desk_host.app import reset_state_for_tests


@pytest.fixture(autouse=True)
def _reset_hub_state():
    reset_state_for_tests()
    yield
    reset_state_for_tests()
