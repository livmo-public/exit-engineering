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
from helpers import month_range

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


# ---- fix round 1: Add-backs without the ledger, concentration, bridge check --------

def test_addbacks_render_without_the_ledger(built_without_c3):
    b = built_without_c3
    wb = openpyxl.load_workbook(b.path)
    addbacks = wb["Add-backs"]
    assert addbacks["A4"].value == "Adjustment"
    assert [addbacks.cell(r, 4).value for r in range(5, 9)] == ["approved", "edited", "rejected", "no decision"]
    assert wb["Proof of cash"]["A4"].value == "not available: file missing"
    bridge = wb["Adjusted EBITDA bridge"]
    lines = [r for r in range(5, bridge.max_row + 1)
             if str(bridge.cell(r, 1).value).startswith("Owner-stated adjustment")]
    assert [bridge.cell(r, 1).value for r in lines] == [
        "Owner-stated adjustment: Owner salary above market", "Owner-stated adjustment: One-time legal fee"]
    # TTM is the second label: bridge column C, Add-backs column G (6 + 1). Rows 5 and 6 are counted.
    sheet, cell = b.cell_map["bridge.adjusted.TTM"]
    assert sheet == "Adjusted EBITDA bridge" and cell == f"C{lines[-1] + 1}"
    assert bridge[cell].value == f"=C19+SUM(C{lines[0]}:C{lines[-1]})"
    for r, source in zip(lines, (5, 6)):
        formula = bridge.cell(r, 3).value
        assert f"'Add-backs'!$D${source}" in formula and f"'Add-backs'!$G${source}" in formula
    scope = [d for _, d in scope_lines(b.path)]
    assert any(str(d).startswith("Add-backs: built without C3") for d in scope)
    assert not any("Add-backs tab is not available" in str(d) for d in scope)
    s = build_workbook.chat_summary(b.state, b.canonical_dir, DATA)
    assert s["adjusted_ebitda"]["TTM"] == pytest.approx(b.expected_adjusted_ttm)


def recalc(path):
    formulas = pytest.importorskip("formulas")
    solution = formulas.ExcelModel().loads(str(path)).finish().calculate()
    return {k.upper(): v.value[0][0] for k, v in solution.items() if hasattr(v, "value")}


def value(values, path, sheet, cell):
    return values[f"'[{path.name.upper()}]{sheet.upper()}'!{cell}"]


def test_concentration_and_bridge_check_match_python(tmp_path):
    import conftest
    import metrics
    canonical_dir = conftest._canonical_up_to(tmp_path / "canonical", "2026-03")
    # TTM 2025-04 to 2026-03. Four positive customers, two zero TTM totals (one sold only in
    # 2025-02, one nets +300 - 300), two negative. metrics ranks the 6 non-zero customers:
    # top 5 = 1,000 + 800 + 600 + 400 - 20 = 2,780 of 2,730.
    sales = [("2025-05", "Alpha", 1000.0), ("2025-05", "Bravo", 800.0), ("2025-05", "Charlie", 600.0),
             ("2025-05", "Delta", 400.0), ("2025-02", "Zero Before", 500.0), ("2025-06", "Zero Net", 300.0),
             ("2025-07", "Zero Net", -300.0), ("2025-08", "Credit One", -50.0), ("2025-09", "Credit Two", -20.0)]
    sales_rows = [{"period": p, "customer": c, "amount": a} for p, c, a in sales]
    canonical.write("sales", sales_rows, canonical_dir / "sales.csv")
    # One P&L row with no account type: the bridge check shows it (75 in FY2025 and in the TTM).
    pl = canonical.read("pl", canonical_dir / "pl.csv")
    unmapped = {"period": "2025-06", "account": "Misc", "account_type": "", "amount": 75.0, "basis": "accrual"}
    canonical.write("pl", pl + [unmapped], canonical_dir / "pl.csv")
    intake = {**conftest.WORKBOOK_INTAKE, "business_type": "services", "billing_system": "none"}
    others = tuple(f for f in conftest.FILE_KINDS if f not in ("C1", "C2", "C6"))
    b = conftest._build(tmp_path, canonical_dir, intake, others)
    values = recalc(b.path)
    expected = metrics.concentration(sales_rows, month_range("2025-04", "2026-03"))
    assert expected["top5_pct"] == pytest.approx(2780 / 2730)
    for key in ("top1_pct", "top5_pct", "customer_count"):
        assert value(values, b.path, *b.cell_map[f"revenue.{key}"]) == pytest.approx(expected[key]), key
    assert value(values, b.path, *b.cell_map["revenue.top10_pct"]) == pytest.approx(1.0)
    ws = openpyxl.load_workbook(b.path)["Adjusted EBITDA bridge"]
    check = [c.coordinate for c in ws[ws.max_row] if c.data_type == "f"]
    assert [value(values, b.path, "Adjusted EBITDA bridge", c) for c in check] == [-75.0, -75.0]


def test_ready_next_step_does_not_send_the_seller_to_the_lender_requirement():
    text = build_workbook.NEXT_STEP_READY
    assert "SBA lender" in text and "seller did not order" in text
    assert "Commission" not in text
    assert not any(len(s.split()) > 25 for s in text.split(". "))
    assert "–" not in text and "—" not in text


# ---- final review: owner statements and review findings in the workbook ---------------

def _rebuild(tmp_path, state, canonical_dir):
    path = tmp_path / "workbook.xlsx"
    build_workbook.build(state, canonical_dir, DATA, path)
    return path


def test_scope_lists_owner_answers_and_adjustments_with_no_document(tmp_path, built):
    import run_checks
    owner = run_checks.owner_findings(built.state, {"K12": "We rent from a company I own."}, DATA)
    adjustments = [*built.state["adjustments"],
                   {"id": "A5", "name": "Owner car lease", "source_file": "R3", "amounts": {"TTM": 900.0},
                    "evidence": None, "decision": "approved", "owner_stated": True}]
    state = {**built.state, "findings": [*built.state["findings"], *owner], "adjustments": adjustments}
    lines = scope_lines(_rebuild(tmp_path, state, built.canonical_dir))
    statements = [str(d) for item, d in lines if item == "Owner statement"]
    [k12] = [d for d in statements if d.startswith("K12-1")]
    assert "We rent from a company I own." in k12 and k12.endswith("(owner statement, no document)")
    assert k12.count("no document") == 1
    # A2 (edited) and A5 (approved) have no evidence; A1 has evidence, A3 is rejected, A4 undecided.
    no_document = [d for d in statements if d.startswith("A")]
    assert [d.split(" ")[0] for d in no_document] == ["A2", "A5"]
    assert all(d.endswith("(owner statement, no document)") for d in no_document)


def test_findings_tab_shows_review_findings(tmp_path, built):
    import run_checks
    reviews = run_checks.review_findings(built.state, {"K15": ["2025-11 Equipment purchase 4,000.00"]}, DATA)
    state = {**built.state, "findings": [*built.state["findings"], *reviews]}
    ws = openpyxl.load_workbook(_rebuild(tmp_path, state, built.canonical_dir))["Findings"]
    header = [c.value for c in ws[4]]
    rows = [dict(zip(header, (c.value for c in row))) for row in ws.iter_rows(min_row=5)]
    [row] = [r for r in rows if r["Finding"] == "K15-1"]
    assert row["Status"] == "review" and row["Method"] == "model_review"
    assert row["Detail"].startswith("For review")
    assert "Equipment purchase" in row["Evidence"]
