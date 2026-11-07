"""Results tab: recalculate scenario workbooks and compare every Results cell to calc_math."""
from __future__ import annotations

import re

import pytest
from openpyxl import load_workbook

import build_calculator as bc
from calc_math import MESSAGE_ORDER, annuity_factor, evaluate, message_text
from helpers import cell_value, error_cells, recalculate
from scenarios import FACTS, NULL_FACTS, SCENARIOS

ALLOWED = {"SUM", "IF", "AND", "OR", "COUNTIF", "COUNTA", "COUNTBLANK", "ISBLANK", "IFERROR",
           "MIN", "MAX", "ROUND", "ABS"}
NUMBER_KEYS = ("ebitda", "total_addbacks", "total_deductions", "cash_available", "max_debt_service",
               "supported_price", "max_bank_loan", "coverage_at_ask", "price_gap", "price_used",
               "bank_loan_at_price", "dependence_score")
BRIEF_KEYS = ("ebitda", "total_addbacks", "total_deductions", "cash_available", "max_debt_service",
              "supported_price", "max_bank_loan", "coverage_at_ask", "status", "price_gap",
              "dependence_score")
CASH_STEP_INPUTS = ("net_profit", "operator_salary", "capex")
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


def blank(value) -> bool:
    return value is None or value == ""


def assert_number(got, expected, where: str) -> None:
    if expected is None:
        assert blank(got), f"{where}: expected blank, got {got!r}"
    else:
        assert not blank(got) and got == pytest.approx(expected, abs=0.01), f"{where}: {got!r} != {expected!r}"


def compare(name: str, path, cells: dict, values: dict, facts: dict) -> None:
    inputs = SCENARIOS[name]
    result = evaluate(inputs, facts)

    def got(key: str):
        return cell_value(values, path, *cells[key])

    for key in NUMBER_KEYS:
        assert_number(got(key), getattr(result, key), f"{name}.{key}")
    assert got("status") == (result.status or ""), f"{name}.status"
    for key in CASH_STEP_INPUTS:
        expected = None if result.ebitda is None else getattr(inputs, key)
        assert_number(got(key), expected, f"{name}.{key}")
    if result.blocks:
        expected_factors = dict.fromkeys(("bank_factor", "seller_factor", "service_per_dollar"))
    else:
        bank = annuity_factor(inputs.bank_rate, inputs.bank_years)
        paid = inputs.seller_pct > 0 and inputs.seller_standby.lower() == "no"
        seller = annuity_factor(inputs.seller_rate, inputs.seller_years) if paid else 0.0
        share = 1 - inputs.down_pct - inputs.seller_pct
        expected_factors = dict(bank_factor=bank, seller_factor=seller,
                                service_per_dollar=share * bank + inputs.seller_pct * seller)
    for key, expected in expected_factors.items():
        if expected is None:
            assert blank(got(key)), f"{name}.{key}"
        else:
            assert got(key) == pytest.approx(expected, rel=1e-9), f"{name}.{key}"
    shown = set(result.blocks) | set(result.warnings) | set(result.flags)
    for code in MESSAGE_ORDER:
        expected = message_text(code, inputs, result, facts) if code in shown else ""
        assert (got(f"msg.{code}") or "") == expected, f"{name}.msg.{code}"


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_results_match_python(name, solved):
    path, cells, values = solved(name)
    compare(name, path, cells, values, FACTS)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_no_error_values(name, solved):
    _, _, values = solved(name)
    assert error_cells(values, ["Results", "Deal terms"]) == []


def test_null_facts_never_fire(solved):
    path, cells, values = solved("sba_all", NULL_FACTS, label="sba_all_null_facts")
    compare("sba_all", path, cells, values, NULL_FACTS)
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

    blocks = max(row(f"msg.{c}") for c in MESSAGE_ORDER[:6])
    assert blocks < row("net_profit") < row("cash_available") < row("max_debt_service")
    assert row("supported_price") < row("coverage_at_ask") < row("msg.operator_in_place")
    assert max(row(f"msg.{c}") for c in MESSAGE_ORDER[6:14]) < row("msg.qoe") < row("msg.loan_limit")


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
