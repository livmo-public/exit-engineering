"""Workbook test helpers: recalculate with the formulas library and read cell values."""
from pathlib import Path

import pytest

from calc_math import MESSAGE_ORDER, annuity_factor, evaluate, message_text

NUMBER_KEYS = ("ebitda", "total_addbacks", "total_deductions", "cash_available", "max_debt_service",
               "supported_price", "max_bank_loan", "coverage_at_ask", "price_gap", "price_used",
               "bank_loan_at_price", "dependence_score")
CASH_STEP_INPUTS = ("net_profit", "operator_salary", "capex")



def recalculate(path: Path) -> dict:
    """Recalculate an xlsx with the formulas library. Keys are upper-cased, as cell_value expects."""
    import formulas
    solution = formulas.ExcelModel().loads(str(path)).finish().calculate()
    return {k.upper(): v.value[0][0] for k, v in solution.items() if hasattr(v, "value")}


def cell_value(values: dict, path: Path, sheet: str, cell: str):
    return values[f"'[{path.name.upper()}]{sheet.upper()}'!{cell}"]


def error_cells(values: dict, sheets: list[str]) -> list[str]:
    """Cells of the given sheets whose recalculated value is an Excel error."""
    from formulas.functions import XlError
    prefixes = tuple(f"{s.upper()}'!" for s in sheets)
    return [k for k, v in values.items()
            if k.split("]", 1)[-1].startswith(prefixes) and isinstance(v, XlError)]


def blank(value) -> bool:
    return value is None or value == ""


def assert_number(got, expected, where: str) -> None:
    if expected is None:
        assert blank(got), f"{where}: expected blank, got {got!r}"
    else:
        assert not blank(got) and got == pytest.approx(expected, abs=0.01), f"{where}: {got!r} != {expected!r}"


def compare(inputs, name: str, path, cells: dict, values: dict, facts: dict) -> None:
    """Assert every Results cell of a recalculated workbook equals the Python reference."""
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
