import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "scripts"
TOOLS = ROOT / "tools"

for _path in (SCRIPTS, TOOLS):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


@pytest.fixture
def data_dir():
    return ROOT / "skill" / "data"


@pytest.fixture
def scripts_dir():
    return SCRIPTS


@pytest.fixture
def sample_dir():
    return ROOT / "examples" / "sample-saas-co"
