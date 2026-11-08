"""Results tab: recalculate scenario workbooks and compare every Results cell to calc_math."""
from __future__ import annotations

import re

import pytest
from openpyxl import load_workbook

import build_calculator as bc
from calc_math import (
    BLOCK_CODES, MESSAGE_ORDER, STATUS_NO, STATUS_TIGHT, STATUS_YES, WARNING_CODES,
)
from helpers import (
    blank, cell_value, compare, error_cells, recalculate,
)
from scenarios import FACTS, NULL_FACTS, SCENARIOS

ALLOWED = {"SUM", "IF", "AND", "OR", "COUNTIF", "COUNTA", "COUNTBLANK", "ISBLANK", "IFERROR",
           "MIN", "MAX", "ROUND", "ABS"}
BRIEF_KEYS = ("ebitda", "total_addbacks", "total_deductions", "cash_available", "max_debt_service",
              "supported_price", "max_bank_loan", "coverage_at_ask", "status", "price_gap",
              "dependence_score")
EXCEL_STRING_LIMIT = 255


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    """Build and recalculate each scenario once. Return (path, cell map, values) per name."""
    cache: dict = {}

    def get(name: str, facts: dict = FACTS, label: str | None = None):
        key = label or name
        if key not in cache:
            path = tmp_path_factory.mktemp(key) / f"{key}.xlsx"
            cells = bc.build(path, SCENARIOS[name], facts)
            cache[key] = (path, cells, recalculate(path))
        return cache[key]

    return get


@pytest.fixture(scope="module")
def base_wb(tmp_path_factory):
    path = tmp_path_factory.mktemp("formulas") / "base.xlsx"
    cells = bc.build(path, SCENARIOS["base"], FACTS)
    return load_workbook(path), cells


def formulas_of(wb):
    for ws in wb:
        for row in ws.iter_rows():
            for c in row:
                if isinstance(c.value, str) and c.value.startswith("="):
                    yield ws.title, c.coordinate, c.value


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_results_match_python(name, solved):
    path, cells, values = solved(name)
    compare(SCENARIOS[name], name, path, cells, values, FACTS)


# Scenario intent, written out by hand so that a change in calc_math cannot move it.
EXPECTED_STATUS = {
    "ask_not_financeable": STATUS_NO, "ask_tight_low_edge": STATUS_TIGHT,
    "ask_tight_high_edge": STATUS_TIGHT, "ask_financeable": STATUS_YES,
}
EXPECTED_FLAGS = {"qoe_at_3m": {"qoe"}, "qoe_below_3m": set(), "loan_limit": {"loan_limit"}}
EXPECTED_BLOCKS = {
    "blank_file": {"missing_inputs", "missing_answers", "operator_blank"},
    "missing_net_profit": {"missing_inputs"}, "missing_net_profit_low_cash": {"missing_inputs"},
    "missing_bank_term": {"missing_inputs"}, "missing_answer": {"missing_answers"},
    "missing_answer_and_no_cash": {"missing_answers", "no_cash"}, "answer_not_yes_no": {"missing_answers"},
    "padded_text": {"missing_answers"},
    "operator_blank": {"operator_blank"}, "operator_blank_no_operator": {"operator_blank"},
    "operator_zero_no_operator": {"operator_zero"},
    "seller_missing_terms": {"missing_inputs"}, "seller_missing_standby": {"missing_inputs"},
    "seller_missing_years": {"missing_inputs"},
    "pct_as_whole_number": {"bad_terms"}, "shares_over_100": {"bad_terms"}, "rate_whole_number": {"bad_terms"},
    "seller_rate_whole_number": {"bad_terms"}, "coverage_too_high": {"bad_terms"},
    "term_in_months": {"bad_terms"}, "seller_term_in_months": {"bad_terms"},
    "no_cash": {"no_cash"}, "missing_and_bad_terms": {"missing_inputs", "bad_terms"},
    "heavy_and_blocked": {"missing_inputs"},
    "negative_owner_pay": {"negative_inputs"}, "negative_operator_salary": {"negative_inputs"},
    "negative_capex": {"negative_inputs"}, "negative_addback": {"negative_inputs"},
    "negative_deduction": {"negative_inputs"}, "negative_and_missing": {"missing_inputs", "negative_inputs"},
}
SBA_CODES = ("sba_down", "sba_term", "sba_coverage", "sba_standby")
EXPECTED_SBA = {
    "base": set(), "sba_down": {"sba_down"}, "sba_term": {"sba_term"}, "sba_coverage": {"sba_coverage"},
    "sba_standby": {"sba_down", "sba_standby"}, "sba_all": set(SBA_CODES),
    "standby_10_10": set(), "standby_90_10": set(), "standby_5_5": set(), "seller_standby": set(),
    "standby_too_small": {"sba_down"}, "paid_note_low_down": {"sba_down"},
}
# Add-backs with an amount above 0 and proof not "yes".
EXPECTED_PROOF = {"base": 0, "proof_missing": 2, "proof_one": 1, "proof_blank": 1, "padded_text": 1}


def shown_codes(values, path, cells, codes) -> set[str]:
    return {c for c in codes if not blank(cell_value(values, path, *cells[f"msg.{c}"]))}


@pytest.mark.parametrize("name", sorted(set(EXPECTED_STATUS) | set(EXPECTED_FLAGS) | set(EXPECTED_BLOCKS)
                                        | set(EXPECTED_SBA) | set(EXPECTED_PROOF) | {"shares_100_float"}))
def test_scenario_intent(name, solved):
    path, cells, values = solved(name)

    def got(key: str):
        return cell_value(values, path, *cells[key])

    if name in EXPECTED_STATUS:
        assert got("status") == EXPECTED_STATUS[name]
    if name in EXPECTED_FLAGS:
        assert shown_codes(values, path, cells, ("qoe", "loan_limit")) == EXPECTED_FLAGS[name]
    blocks = shown_codes(values, path, cells, BLOCK_CODES)
    assert blocks == EXPECTED_BLOCKS.get(name, set())
    if name in EXPECTED_SBA:
        assert shown_codes(values, path, cells, SBA_CODES) == EXPECTED_SBA[name]
    if name in EXPECTED_PROOF:
        assert cell_value(values, path, *bc.PROOF_MISSING_CELL) == EXPECTED_PROOF[name]
        assert (not blank(got("msg.proof"))) == (EXPECTED_PROOF[name] > 0)
    if name == "shares_100_float":
        assert blank(got("supported_price")) and blank(got("max_bank_loan"))
        assert got("bank_loan_at_price") == 0 and got("status") == STATUS_YES


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_no_error_values(name, solved):
    _, _, values = solved(name)
    assert error_cells(values, ["Results", "Deal terms"]) == []


def test_null_facts_never_fire(solved):
    path, cells, values = solved("sba_all", NULL_FACTS, label="sba_all_null_facts")
    compare(SCENARIOS["sba_all"], "sba_all", path, cells, values, NULL_FACTS)
    for code in ("sba_down", "sba_term", "sba_coverage", "sba_standby", "qoe"):
        assert blank(cell_value(values, path, *cells[f"msg.{code}"])), code
    assert error_cells(values, ["Results", "Deal terms"]) == []


def test_cell_map_keys(base_wb):
    _, cells = base_wb
    for key in BRIEF_KEYS:
        assert cells[key][0] == "Results", key
    for code in MESSAGE_ORDER:
        assert cells[f"msg.{code}"][0] == "Results", code


def test_allowed_functions_only(base_wb):
    wb, _ = base_wb
    for sheet, cell, formula in formulas_of(wb):
        assert set(re.findall(r"([A-Z]+)\(", formula)) <= ALLOWED, (sheet, cell)


def test_annuity_written_without_pmt(base_wb):
    wb, _ = base_wb
    for sheet, cell, formula in formulas_of(wb):
        assert "PMT(" not in formula and "PV(" not in formula, (sheet, cell)


def test_string_literals_fit_excel_limit(base_wb):
    wb, _ = base_wb
    for sheet, cell, formula in formulas_of(wb):
        for literal in re.findall(r'"((?:[^"]|"")*)"', formula):
            assert len(literal.replace('""', '"')) <= EXCEL_STRING_LIMIT, (sheet, cell)


def test_sheet_names_quoted_in_references(base_wb):
    wb, _ = base_wb
    for sheet, cell, formula in formulas_of(wb):
        unquoted = re.findall(r"(?<!')\b([A-Za-z][A-Za-z ]*)!", formula)
        assert unquoted == [], (sheet, cell, unquoted)


def test_cash_flow_rows_in_order(base_wb):
    wb, cells = base_wb
    ws = wb["Results"]
    steps = ("net_profit", "ebitda", "total_addbacks", "total_deductions", "operator_salary",
             "capex", "cash_available")
    rows = [int(cells[key][1][1:]) for key in steps]
    assert rows == sorted(rows) and rows[-1] - rows[0] == len(steps) - 1
    labels = [str(ws[f"A{row}"].value) for row in rows]
    words = ("Net profit", "EBITDA", "add-backs", "deductions", "operator salary",
             "maintenance capital spending", "Cash available for debt")
    for number, (label, word) in enumerate(zip(labels, words), start=1):
        assert label.startswith(f"{number}. ") and word in label, label


def test_results_layout_order(base_wb):
    _, cells = base_wb

    def row(key: str) -> int:
        return int(cells[key][1][1:])

    blocks = max(row(f"msg.{c}") for c in BLOCK_CODES)
    assert blocks < row("net_profit") < row("cash_available") < row("max_debt_service")
    assert row("supported_price") < row("coverage_at_ask") < row("msg.operator_in_place")
    assert max(row(f"msg.{c}") for c in WARNING_CODES) < row("msg.qoe") < row("msg.loan_limit")


def test_sba_values_block_on_deal_terms(base_wb):
    wb, _ = base_wb
    text = [str(c.value) for row in wb["Deal terms"].iter_rows() for c in row if c.value is not None]
    assert "SBA values" in text
    assert FACTS["sop_version"] in text and FACTS["checked"] in text
    assert any("1.25" == t or t == str(FACTS["coverage_change_of_ownership"]["value"]) for t in text)


def test_no_fill_on_results_formulas(base_wb):
    wb, _ = base_wb
    for sheet, cell, _ in formulas_of(wb):
        assert wb[sheet][cell].fill.fill_type is None, (sheet, cell)
