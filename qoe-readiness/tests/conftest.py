import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skill" / "scripts"
TOOLS = ROOT / "tools"

for _path in (SCRIPTS, TOOLS):
    if _path.is_dir() and str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


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


@pytest.fixture
def data_dir():
    return ROOT / "skill" / "data"


@pytest.fixture
def scripts_dir():
    return SCRIPTS


@pytest.fixture
def fixtures():
    return ROOT / "tests" / "fixtures"


@pytest.fixture
def sample_dir():
    return ROOT / "examples" / "sample-saas-co"


# ---- workbook fixtures (Task 7) ----------------------------------------------

CANONICAL_FIXTURES = ROOT / "tests" / "fixtures" / "canonical"
FILE_KINDS = {"C1": "pl", "C2": "bs", "C3": "gl", "C4": "bank", "C6": "sales", "C7": "vendor",
              "C8": "aging", "C9": "tax", "S1": "subs", "P1": "inventory"}
WORKBOOK_INTAKE = {
    "business_type": "saas", "revenue_range": "1m_to_5m", "accounting_system": "qbo",
    "billing_system": "stripe", "accounting_basis": "accrual", "fiscal_year_end_month": 12,
    "latest_closed_month": "2026-03", "sale_timeline": "3_to_12_months",
    "buyer_financing": "sba", "price_may_reach_3m": "no", "advisor_name": "",
}
# Owner-stated adjustments. Hand calculation of adjusted EBITDA, TTM 2025-04 to 2026-03:
# EBITDA 9 x 3,050 + 3 x 4,050 = 39,600; A1 approved +12,000; A2 edited, month keys
# 2025-06 and 2026-02 both in the TTM, +4,500; A3 rejected and A4 undecided count 0.
# Total 56,100. FY2025: 36,600 + 12,000 + 3,000 = 51,600.
WORKBOOK_ADJUSTMENTS = [
    {"id": "A1", "name": "Owner salary above market", "source_file": "R1",
     "amounts": {"FY2025": 12000.0, "TTM": 12000.0}, "evidence": "Payroll summary",
     "decision": "approved", "owner_stated": True},
    {"id": "A2", "name": "One-time legal fee", "source_file": "R3",
     "amounts": {"2025-06": 3000.0, "2026-02": 1500.0}, "evidence": None,
     "decision": "edited", "owner_stated": True},
    {"id": "A3", "name": "Personal travel", "source_file": "R3", "amounts": {"TTM": 5000.0},
     "evidence": None, "decision": "rejected", "owner_stated": True},
    {"id": "A4", "name": "Unanswered item", "source_file": "R4", "amounts": {"TTM": 700.0},
     "evidence": None, "decision": None, "owner_stated": True},
]
EXPECTED_ADJUSTED_TTM = 56100.0


def _workbook_state(canonical_dir: Path, intake: dict, missing: tuple = ()) -> dict:
    import progress
    files = {}
    for file_id, kind in FILE_KINDS.items():
        if file_id in missing:
            files[file_id] = {"status": "missing", "reason": "unknown"}
        else:
            files[file_id] = {"status": "uploaded", "source_system": "qbo",
                              "canonical_path": str(canonical_dir / f"{kind}.csv")}
    files.update({"C5": {"status": "uploaded"}, "R1": {"status": "uploaded"},
                  "R3": {"status": "uploaded"}, "R4": {"status": "missing", "reason": "never_kept"}})
    return {**progress.new_state(), "stage": 5, "intake": intake, "files": files,
            "adjustments": [dict(a) for a in WORKBOOK_ADJUSTMENTS]}


def _with_findings(state: dict, data_dir: Path, canonical_dir: Path) -> dict:
    import run_checks
    findings = run_checks.run(state, canonical_dir, data_dir)
    responses = {f["id"]: {"type": "explain", "text": "The bank posted one deposit late."}
                 for f in findings if f["check_id"] == "K04"}
    responses.update({f["id"]: {"type": "accept"} for f in findings if f["check_id"] == "K19"})
    return {**state, "findings": findings, "responses": responses}


def _build(out_dir: Path, canonical_dir: Path, intake: dict, missing: tuple = ()):
    from types import SimpleNamespace
    import build_workbook
    data = ROOT / "skill" / "data"
    state = _with_findings(_workbook_state(canonical_dir, intake, missing), data, canonical_dir)
    path = out_dir / "workbook.xlsx"
    cell_map = build_workbook.build(state, canonical_dir, data, path)
    return SimpleNamespace(path=path, state=state, canonical_dir=canonical_dir, cell_map=cell_map,
                           expected_adjusted_ttm=EXPECTED_ADJUSTED_TTM)


def _canonical_up_to(out_dir: Path, last_month: str) -> Path:
    """Copy the canonical fixture set, keeping only rows dated up to last_month."""
    import canonical
    date_cols = {"pl": "period", "bs": "period", "gl": "date", "bank": "month", "sales": "period",
                 "vendor": "period", "inventory": "period"}
    out_dir.mkdir(parents=True, exist_ok=True)
    for kind in canonical.KINDS:
        rows = canonical.read(kind, CANONICAL_FIXTURES / f"{kind}.csv")
        col = date_cols.get(kind)
        kept = [r for r in rows if col is None or r[col][:7] <= last_month]
        canonical.write(kind, kept, out_dir / f"{kind}.csv")
    return out_dir


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("built"), CANONICAL_FIXTURES, WORKBOOK_INTAKE)


@pytest.fixture(scope="module")
def built_without_c4(tmp_path_factory):
    return _build(tmp_path_factory.mktemp("no_c4"), CANONICAL_FIXTURES, WORKBOOK_INTAKE, ("C4",))


@pytest.fixture(scope="module")
def built_with_advisor(tmp_path_factory):
    intake = {**WORKBOOK_INTAKE, "advisor_name": "Test Advisor"}
    return _build(tmp_path_factory.mktemp("advisor"), CANONICAL_FIXTURES, intake)


@pytest.fixture(scope="module")
def built_14_months(tmp_path_factory):
    # 14 months, 2025-01 to 2026-02, December year end: FY2025 is the one complete year.
    out = tmp_path_factory.mktemp("short")
    canonical_dir = _canonical_up_to(out / "canonical", "2026-02")
    return _build(out, canonical_dir, {**WORKBOOK_INTAKE, "latest_closed_month": "2026-02"})


@pytest.fixture(scope="module")
def built_product(tmp_path_factory):
    intake = {**WORKBOOK_INTAKE, "business_type": "product", "billing_system": "none"}
    return _build(tmp_path_factory.mktemp("product"), CANONICAL_FIXTURES, intake)


@pytest.fixture(scope="module")
def built_without_c3(tmp_path_factory):
    # The ledger (C3) is missing; the bank (C4) and the owner-stated adjustments are present.
    return _build(tmp_path_factory.mktemp("no_c3"), CANONICAL_FIXTURES, WORKBOOK_INTAKE, ("C3",))
