"""Tests for build_workbook.py. Fixtures `built*` live in conftest.py.

The fixture company (tests/fixtures/canonical) covers 2025-01 to 2026-03, December year end.
The recalculated values are Task 8's value check; these tests check layout and formula rules.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import openpyxl
import pytest

import build_workbook
import canonical

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "skill" / "data"
SCRIPT = ROOT / "skill" / "scripts" / "build_workbook.py"
HEADER = "Owner-prepared QoE readiness workbook. Designed by LIVMO. LIVMO is not responsible for this output."
FULL_HEADER = (HEADER + " This is not an independent Quality of Earnings report, an audit, a review, or a "
               "compilation. The owner supplied the source files, and no one verified them. Do not give "
               "this workbook to a lender or buyer as a QoE.")
ALLOWED = {"SUM", "SUMIFS", "COUNTIFS", "INDEX", "MATCH", "LARGE", "RANK", "MIN", "MAX", "IF",
           "IFERROR", "ABS", "ROUND", "AVERAGE", "EOMONTH"}


def catalog():
    return json.loads((DATA / "workbook.json").read_text(encoding="utf-8"))


def formula_cells(path):
    wb = openpyxl.load_workbook(path)
    return [(ws.title, c) for ws in wb.worksheets for row in ws.iter_rows() for c in row
            if c.data_type == "f"]


def all_formulas(path):
    return "\n".join(c.value for _, c in formula_cells(path))


@pytest.fixture
def tabs(built):
    present = openpyxl.load_workbook(built.path).sheetnames
    return [t for t in catalog() if t["title"] in present]


# ---- brief tests -------------------------------------------------------------

def test_header_on_every_tab(built):
    wb = openpyxl.load_workbook(built.path)
    assert all(ws["A1"].value.startswith(HEADER) for ws in wb.worksheets)


def test_computed_cells_are_formulas(built, tabs):
    wb = openpyxl.load_workbook(built.path)
    for t in (t for t in tabs if t["kind"] == "computed"):
        for row in wb[t["title"]].iter_rows(min_row=5):
            for c in row:
                if isinstance(c.value, (int, float)):
                    pytest.fail(f"{t['title']}!{c.coordinate} holds a value")


def test_only_allowed_functions(built):
    used = set(re.findall(r"([A-Z]+)\(", all_formulas(built.path)))
    assert used <= ALLOWED


def test_sheet_names_quoted_and_short(built):
    wb = openpyxl.load_workbook(built.path)
    assert all(len(ws.title) <= 31 for ws in wb.worksheets)
    assert not re.search(r"(?<!')\b(Inputs - P&L|Proof of cash)!", all_formulas(built.path))


def test_missing_file_tab_and_scope(built_without_c4):
    wb = openpyxl.load_workbook(built_without_c4.path)
    assert wb["Proof of cash"]["A4"].value == "not available: file missing"
    assert any("C4" in str(c.value) for c in wb["Scope and limitations"]["B"])


def test_advisor_line(built_with_advisor):
    assert openpyxl.load_workbook(built_with_advisor.path)["Summary"]["A2"].value == \
        "Facilitated by Test Advisor, LIVMO. Facilitator only."


def test_chat_summary_uses_owner_stated_adjustments_only(built):
    s = build_workbook.chat_summary(built.state, built.canonical_dir, DATA)
    assert len(s["top_findings"]) <= 5 and s["adjusted_ebitda"]["TTM"] == pytest.approx(built.expected_adjusted_ttm)


def test_workbook_short_history(built_14_months):
    m = built_14_months.cell_map
    assert "bridge.ebitda.TTM" in m and len([k for k in m if k.startswith("bridge.ebitda.FY")]) == 1


# ---- formula rules across module sets ------------------------------------------

@pytest.mark.parametrize("name", ["built", "built_product", "built_without_c4", "built_14_months"])
def test_rules_hold_for_every_fixture(name, request):
    b = request.getfixturevalue(name)
    wb = openpyxl.load_workbook(b.path)
    computed = [t["title"] for t in catalog() if t["kind"] == "computed" and t["title"] in wb.sheetnames]
    for title in computed:
        for row in wb[title].iter_rows(min_row=5):
            assert not any(isinstance(c.value, (int, float)) for c in row), title
    text = all_formulas(b.path)
    assert set(re.findall(r"([A-Z]+)\(", text)) <= ALLOWED
    assert not re.search(r"(?<!')\b(Inputs - [A-Za-z&]+|Add-backs|Findings|File inventory|"
                         r"Adjusted EBITDA bridge)!", text)
    assert all(len(ws.title) <= 31 for ws in wb.worksheets)


@pytest.mark.parametrize("name", ["built", "built_product", "built_14_months"])
def test_every_rendered_computed_tab_ends_with_check_row(name, request):
    wb = openpyxl.load_workbook(request.getfixturevalue(name).path)
    for t in catalog():
        if t["kind"] != "computed" or t["title"] not in wb.sheetnames:
            continue
        ws = wb[t["title"]]
        if ws["A4"].value == "not available: file missing":
            continue
        last = ws.max_row
        assert ws.cell(last, 1).value == "Check", t["title"]
        assert any(c.data_type == "f" for c in ws[last][1:]), t["title"]


def test_cell_map_has_required_keys_and_points_at_formulas(built):
    m = built.cell_map
    required = [f"bridge.{k}.{label}" for k in ("ebitda", "adjusted", "revenue") for label in ("FY2025", "TTM")]
    required += ["proof_cash.diff.2025-08", "nwc.peg", "revenue.top1_pct", "deferred.closing.2026-03"]
    assert set(required) <= set(m)
    wb = openpyxl.load_workbook(built.path)
    for key, (sheet, cell) in m.items():
        assert wb[sheet][cell].data_type == "f", key


def test_cell_map_months_follow_the_data(built):
    months = {k.rsplit(".", 1)[1] for k in built.cell_map if k.startswith("deferred.closing.")}
    assert months == {f"2025-{n:02d}" for n in range(1, 13)} | {"2026-01", "2026-02", "2026-03"}
    assert not [k for k in built.cell_map if k.startswith("bridge.ebitda.FY2026")]


# ---- tabs and modules ----------------------------------------------------------

def test_tabs_follow_catalog_order_and_modules(built, built_product):
    saas = openpyxl.load_workbook(built.path).sheetnames
    product = openpyxl.load_workbook(built_product.path).sheetnames
    assert saas == [t["title"] for t in catalog() if t["module"] in ("core", "saas")]
    assert product == [t["title"] for t in catalog() if t["module"] in ("core", "product")]
    assert "Deferred revenue" not in product and "Inventory and WIP" not in saas


def test_summary_repeats_full_header_above_figures(built):
    ws = openpyxl.load_workbook(built.path)["Summary"]
    assert ws["A1"].value == FULL_HEADER
    assert ws["A2"].value is None
    assert "'Adjusted EBITDA bridge'!" in str(ws["B6"].value)


def test_input_tabs_hold_canonical_columns_and_values(built):
    wb = openpyxl.load_workbook(built.path)
    ws = wb["Inputs - P&L"]
    assert [c.value for c in ws[4]] == canonical.KINDS["pl"]
    rows = canonical.read("pl", built.canonical_dir / "pl.csv")
    assert ws.max_row == 4 + len(rows)
    assert ws["D5"].value == rows[0]["amount"]
    for t in catalog():
        if t["kind"] == "input" and t["title"] in wb.sheetnames:
            assert not any(c.data_type == "f" for row in wb[t["title"]].iter_rows() for c in row)
    assert wb["Inputs - Subscriptions"]["E5"].value is None  # blank end date stays blank


def test_bridge_counts_approved_and_edited_adjustments_only(built):
    wb = openpyxl.load_workbook(built.path)
    addbacks = wb["Add-backs"]
    decisions = [addbacks.cell(r, 4).value for r in range(5, 9)]
    assert decisions == ["approved", "edited", "rejected", "no decision"]
    assert addbacks.cell(9, 1).value is None
    bridge = wb["Adjusted EBITDA bridge"]
    labels = [bridge.cell(r, 1).value or "" for r in range(5, bridge.max_row + 1)]
    lines = [text for text in labels if text.startswith("Owner-stated adjustment")]
    assert lines == ["Owner-stated adjustment: Owner salary above market",
                     "Owner-stated adjustment: One-time legal fee"]
    assert "'Add-backs'!" in all_formulas(built.path)


def test_addbacks_amounts_are_owner_statements(built):
    ws = openpyxl.load_workbook(built.path)["Add-backs"]
    header = [c.value for c in ws[4]]
    fy, ttm = header.index("FY2025") + 1, header.index("TTM") + 1
    # A2 states month amounts 2025-06 (3,000) and 2026-02 (1,500): FY2025 3,000, TTM 4,500.
    assert (ws.cell(6, fy).value, ws.cell(6, ttm).value) == (3000.0, 4500.0)


def test_bridge_uses_the_intake_basis(built):
    formulas = [c.value for title, c in formula_cells(built.path) if title == "Adjusted EBITDA bridge"]
    sums = [f for f in formulas if "SUMIFS(" in f]
    assert sums and all('"accrual"' in f for f in sums)


def test_month_criteria_force_text_matching(built):
    # A bare "2025-01" criterion parses as a date in Excel; the wildcard keeps it a text match.
    text = all_formulas(built.path)
    assert not re.search(r'"\d{4}-\d{2}"', text)


# ---- scope and limitations -----------------------------------------------------

def scope_lines(path):
    ws = openpyxl.load_workbook(path)["Scope and limitations"]
    return [(ws.cell(r, 1).value, ws.cell(r, 2).value) for r in range(5, ws.max_row + 1)]


def test_scope_lists_gaps_statements_and_checks_not_run(built_without_c4):
    lines = scope_lines(built_without_c4.path)
    details = " | ".join(str(d) for _, d in lines)
    assert "Proof of cash" in details and "Proof of revenue" in details
    assert any("C4" in str(d) and "missing" in str(d) for _, d in lines)
    assert any(str(d).startswith("K04") and "C4" in str(d) for _, d in lines)
    assert "R4" in details  # optional bridge input


def test_scope_marks_explain_responses(built):
    lines = scope_lines(built.path)
    statements = [d for _, d in lines if "owner statement, no document" in str(d)]
    assert statements and "The bank posted one deposit late." in statements[0]


def test_short_history_has_no_error_cells(built_14_months):
    wb = openpyxl.load_workbook(built_14_months.path)
    assert all(not str(c.value).startswith("#") for ws in wb.worksheets for row in ws.iter_rows()
               for c in row if c.value is not None)


# ---- chat summary and CLI ------------------------------------------------------

def test_chat_summary_figures_come_from_metrics(built):
    s = build_workbook.chat_summary(built.state, built.canonical_dir, DATA)
    # Accrual rows only: 2025 EBITDA 12 x 3,050 = 36,600; TTM 9 x 3,050 + 3 x 4,050 = 39,600.
    assert s["reported_ebitda"] == pytest.approx({"FY2025": 36600.0, "TTM": 39600.0})
    assert s["adjusted_ebitda"] == pytest.approx({"FY2025": 51600.0, "TTM": 56100.0})
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    ranks = [order[f["severity"]] for f in s["top_findings"]]
    assert ranks == sorted(ranks)
    assert "LIVMO" in s["next_step"] or "QoE" in s["next_step"]


def test_chat_summary_gaps_name_missing_files(built_without_c4):
    s = build_workbook.chat_summary(built_without_c4.state, built_without_c4.canonical_dir, DATA)
    files = [g for g in s["gaps"] if g["type"] == "file"]
    assert files[0]["id"] == "C4"
    assert set(files[0]["blocks_tabs"]) >= {"Proof of cash", "Proof of revenue"}
    assert "LIVMO exit assessment" in s["next_step"]


def test_cli_writes_workbook_and_prints_summary(built, tmp_path):
    state_path = tmp_path / "progress.json"
    state_path.write_text(json.dumps(built.state), encoding="utf-8")
    out = tmp_path / "out.xlsx"
    result = subprocess.run([sys.executable, str(SCRIPT), "--state", str(state_path), "--canonical",
                             str(built.canonical_dir), "--data", str(DATA), "--out", str(out)],
                            capture_output=True, text=True, check=True)
    summary = json.loads(result.stdout)
    assert out.is_file() and summary["adjusted_ebitda"]["TTM"] == pytest.approx(56100.0)


def test_next_step_sees_open_findings_beyond_the_gap_list(built):
    # R1 missing plus R4, R5, R6, and S3 absent: 5 optional file gaps fill the capped list.
    # The open critical K04 finding must still lead to the exit assessment.
    files = {**built.state["files"], "R1": {"status": "missing"}}
    state = {**built.state, "files": files}
    s = build_workbook.chat_summary(state, built.canonical_dir, DATA)
    assert len(s["gaps"]) == 5 and all(g["type"] == "file" for g in s["gaps"])
    assert any(f["severity"] == "critical" for f in state["findings"])
    assert s["next_step"] == build_workbook.NEXT_STEP_GAPS
