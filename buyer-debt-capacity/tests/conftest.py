import os
from pathlib import Path

import pytest

DEFAULT_DENYLIST = Path(r"C:\Users\khale\Projects\exit-engineering-specs\denylist.txt")


def load_denylist() -> list[str]:
    """Read the naming denylist from outside the repo; return [] when the file is absent.

    The path comes from the QOE_DENYLIST environment variable, or the default above.
    One lowercase term per line; blank lines and lines starting with # are skipped.
    """
    path = Path(os.environ.get("QOE_DENYLIST", str(DEFAULT_DENYLIST)))
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    return [t.strip().lower() for t in lines if t.strip() and not t.lstrip().startswith("#")]


@pytest.fixture
def denylist():
    return load_denylist()
