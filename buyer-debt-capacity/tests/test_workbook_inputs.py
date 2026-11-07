import re

import pytest
from openpyxl import load_workbook

import build_calculator as bc
from base_inputs import base
from calc_math import Addback, Deduction, default_inputs, load_facts
from helpers import cell_value, recalculate

FACTS = load_facts()
TEXT_FIELDS = {"period_basis", "period_end", "seller_standby"}
ADDBACK_CATEGORIES = [
    "personal expense", "family member on payroll who does not work in the business",
    "one-time cost", "non-business cost", "other",
]
DEDUCTION_CATEGORIES = ["one-time income", "below-market cost", "other"]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = tmp_path_factory.mktemp("inputs") / "calc.xlsx"
    bc.build(path, base(), FACTS)
    return path


@pytest.fixture(scope="module")
def wb(built):
    return load_workbook(built)


def list_options(ws, cell):
    """Return the lowercase dropdown options of a cell, or None when it has no list validation."""
    for dv in ws.data_validations.dataValidation:
        if dv.type == "list" and cell in dv.sqref:
            return [o.strip().lower() for o in dv.formula1.strip('"').split(",")]
    return None


def validation(ws, cell):
    for dv in ws.data_validations.dataValidation:
        if cell in dv.sqref:
            return dv
    return None


def amount_cells():
    cols = bc.ADDBACK_COLS["amount"], bc.DEDUCTION_COLS["amount"]
    rows = bc.ADDBACK_ROWS, bc.DEDUCTION_ROWS
    return [f"{c}{r}" for c, (first, last) in zip(cols, rows) for r in range(first, last + 1)]


def test_tab_order(wb):
    assert tuple(wb.sheetnames) == bc.TABS
    assert bc.TABS == ("Start here", "Profit", "Add-backs", "Owner role", "Deal terms", "Results")


def test_liability_text_first_on_start_here(wb):
    assert wb["Start here"]["A1"].value == bc.LIABILITY
    assert bc.LIABILITY.startswith("Designed by LIVMO. LIVMO is not responsible for this output.")


def test_start_here_lists_exclusions(wb):
    text = " ".join(str(c.value) for row in wb["Start here"].iter_rows() for c in row if c.value).lower()
    for phrase in ("income taxes", "working capital", "closing costs"):
        assert phrase in text


def test_no_em_dash(wb):
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                assert "—" not in str(c.value or "")


def test_profit_ebitda_formula(built):
    values = recalculate(built)
    i = base()
    expected = i.net_profit + i.interest + i.income_taxes + i.depreciation + i.amortization
    assert cell_value(values, built, *bc.EBITDA_CELL) == pytest.approx(expected)


def test_owner_pay_row_links_to_profit(wb):
    ws = wb["Add-backs"]
    owner_cell = bc.INPUT_CELLS["owner_pay"]
    assert owner_cell[0] == "Profit"
    row = bc.OWNER_PAY_ROW
    formula = ws[f"{bc.ADDBACK_COLS['amount']}{row}"].value
    assert isinstance(formula, str) and formula.startswith("=")
    assert f"'Profit'!{owner_cell[1]}" in formula
    assert row == bc.ADDBACK_ROWS[0] - 1


def test_addback_and_deduction_capacity():
    assert bc.ADDBACK_ROWS[1] - bc.ADDBACK_ROWS[0] + 1 == 25
    assert bc.DEDUCTION_ROWS[1] - bc.DEDUCTION_ROWS[0] + 1 == 10
    assert len(bc.ANSWER_CELLS) == 6


def test_dropdowns(wb):
    ws = wb["Add-backs"]
    first, last = bc.ADDBACK_ROWS
    for r in (first, last):
        assert list_options(ws, f"{bc.ADDBACK_COLS['category']}{r}") == ADDBACK_CATEGORIES
        assert list_options(ws, f"{bc.ADDBACK_COLS['proof']}{r}") == ["yes", "no"]
    first, last = bc.DEDUCTION_ROWS
    for r in (first, last):
        assert list_options(ws, f"{bc.DEDUCTION_COLS['category']}{r}") == DEDUCTION_CATEGORIES
    for sheet, cell in bc.ANSWER_CELLS:
        assert list_options(wb[sheet], cell) == ["yes", "no"]
    sheet, cell = bc.INPUT_CELLS["seller_standby"]
    assert list_options(wb[sheet], cell) == ["yes", "no"]
    sheet, cell = bc.INPUT_CELLS["period_basis"]
    assert list_options(wb[sheet], cell) == ["last 12 months", "last fiscal year"]


def test_numeric_inputs_have_decimal_validation(wb):
    for field, (sheet, cell) in bc.INPUT_CELLS.items():
        if field in TEXT_FIELDS:
            continue
        dv = validation(wb[sheet], cell)
        assert dv is not None and dv.type == "decimal", field
    for cell in amount_cells():
        dv = validation(wb["Add-backs"], cell)
        assert dv is not None and dv.type == "decimal", cell


def test_addback_and_deduction_amounts_reject_negatives(wb):
    for cell in amount_cells():
        dv = validation(wb["Add-backs"], cell)
        assert dv.operator == "greaterThanOrEqual" and float(dv.formula1) == 0, cell


def test_input_cells_filled_formula_cells_not(wb):
    inputs = {s: set() for s in bc.TABS}
    for sheet, cell in list(bc.INPUT_CELLS.values()) + list(bc.ANSWER_CELLS):
        inputs[sheet].add(cell)
    for cell in amount_cells():
        inputs["Add-backs"].add(cell)
    fills = set()
    for sheet, cells in inputs.items():
        for cell in cells:
            fill = wb[sheet][cell].fill
            assert fill.fill_type == "solid", (sheet, cell)
            fills.add(fill.fgColor.rgb)
    assert fills == {bc.INPUT_FILL}
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    assert c.fill.fill_type is None, (ws.title, c.coordinate)


def test_round_trip_inputs(tmp_path):
    path = tmp_path / "rt.xlsx"
    inputs = base(seller_pct=0.2, seller_standby="no")
    bc.build(path, inputs, FACTS)
    wb = load_workbook(path)
    for field, (sheet, cell) in bc.INPUT_CELLS.items():
        assert wb[sheet][cell].value == getattr(inputs, field), field
    for (sheet, cell), answer in zip(bc.ANSWER_CELLS, inputs.answers):
        assert wb[sheet][cell].value == answer
    ws = wb["Add-backs"]
    row = bc.ADDBACK_ROWS[0]
    assert ws[f"{bc.ADDBACK_COLS['category']}{row}"].value == "other"
    assert ws[f"{bc.ADDBACK_COLS['amount']}{row}"].value == 20_000
    assert ws[f"{bc.ADDBACK_COLS['proof']}{row}"].value == "yes"


def test_blank_file_defaults(tmp_path):
    path = tmp_path / "blank.xlsx"
    inputs = default_inputs(FACTS)
    bc.build(path, inputs, FACTS)
    wb = load_workbook(path)
    for field in ("period_basis", "period_end", "revenue", "net_profit", "interest", "income_taxes",
                  "depreciation", "amortization", "owner_pay", "capex", "operator_salary", "asking_price"):
        sheet, cell = bc.INPUT_CELLS[field]
        assert wb[sheet][cell].value is None, field
    for field in ("down_pct", "seller_pct", "seller_standby", "seller_rate", "seller_years",
                  "bank_rate", "bank_years", "coverage_target", "loan_limit"):
        sheet, cell = bc.INPUT_CELLS[field]
        assert wb[sheet][cell].value == getattr(inputs, field), field
    values = recalculate(path)
    sheet, cell = bc.INPUT_CELLS["capex"]
    assert cell_value(values, path, sheet, f"C{cell[1:]}") == "Required"
    sheet, cell = bc.INPUT_CELLS["seller_rate"]
    assert cell_value(values, path, sheet, f"C{cell[1:]}") == ""


def test_required_marker_formulas(wb):
    sheet, cell = bc.INPUT_CELLS["net_profit"]
    assert wb[sheet][f"C{cell[1:]}"].value == f'=IF(ISBLANK({cell}),"Required","")'
    assert "revenue" not in {f for f in bc.INPUT_CELLS if wb[bc.INPUT_CELLS[f][0]][f"C{bc.INPUT_CELLS[f][1][1:]}"].value}
    sheet, cell = bc.INPUT_CELLS["seller_rate"]
    assert wb[sheet][f"C{cell[1:]}"].value.startswith("=IF(AND(")


def test_formulas_use_only_allowed_functions(wb):
    allowed = {"SUM", "IF", "AND", "OR", "COUNTIF", "COUNTA", "COUNTBLANK", "ISBLANK", "IFERROR",
               "MIN", "MAX", "ROUND", "ABS"}
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    assert set(re.findall(r"([A-Z]+)\(", c.value)) <= allowed, (ws.title, c.coordinate)


def test_denylist_terms_absent(wb, denylist):
    text = " ".join(str(c.value) for ws in wb for row in ws.iter_rows() for c in row if c.value).lower()
    for term in denylist:
        assert term not in text


def test_exported_total_cells_hold_the_formulas(tmp_path):
    path = tmp_path / "totals.xlsx"
    inputs = base(
        seller_pct=0.15,
        addbacks=(Addback("other", 20_000.0, "yes"), Addback("one-time cost", 5_000.0, "no")),
        deductions=(Deduction("one-time income", 7_000.0),),
    )
    bc.build(path, inputs, FACTS)
    values = recalculate(path)
    got = lambda ref: cell_value(values, path, *ref)
    assert got(bc.ADDBACK_TOTAL_CELL) == pytest.approx(inputs.owner_pay + 25_000.0)
    assert got(bc.PROOF_MISSING_CELL) == 1
    assert got(bc.DEDUCTION_TOTAL_CELL) == pytest.approx(7_000.0)
    assert got(bc.BANK_SHARE_CELL) == pytest.approx(1 - inputs.down_pct - inputs.seller_pct)
    wb = load_workbook(path)
    for ref in (bc.ADDBACK_TOTAL_CELL, bc.PROOF_MISSING_CELL, bc.DEDUCTION_TOTAL_CELL,
                bc.BANK_SHARE_CELL, bc.EBITDA_CELL):
        assert str(wb[ref[0]][ref[1]].value).startswith("="), ref
    assert wb[bc.OPERATOR_NOTE_CELL[0]][bc.OPERATOR_NOTE_CELL[1]].fill.fill_type == "solid"
    assert wb[bc.ADDBACK_TOTAL_CELL[0]][bc.ADDBACK_TOTAL_CELL[1]].number_format != "General"
    assert wb[bc.DEDUCTION_TOTAL_CELL[0]][bc.DEDUCTION_TOTAL_CELL[1]].number_format != "General"
