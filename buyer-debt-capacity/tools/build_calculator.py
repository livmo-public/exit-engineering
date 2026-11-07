"""Build the Buyer Debt Capacity Calculator workbook (Excel and Google Sheets, live formulas).

Copyright (c) 2026 LIVMO. MIT license.
This module writes "Start here" and the 5 input tabs. results_tab.py writes the Results tab
and the SBA values block on Deal terms.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from calc_math import MAX_ADDBACKS, MAX_DEDUCTIONS, Inputs

LIABILITY = (
    "Designed by LIVMO. LIVMO is not responsible for this output. You supply every number, "
    "and the results are yours. This calculator estimates the debt a lender could support. "
    "It is not a loan offer, a lender decision, or a valuation, and it gives no tax, legal, "
    "or accounting advice."
)
TABS = ("Start here", "Profit", "Add-backs", "Owner role", "Deal terms", "Results")
INPUT_FILL = "00FFF2CC"
PROFIT, ADDBACKS, ROLE, DEAL = "Profit", "Add-backs", "Owner role", "Deal terms"

# Scalar input cells: Inputs field name -> (sheet, cell). Column B holds the value, C the marker.
INPUT_CELLS: dict[str, tuple[str, str]] = {
    "period_basis": (PROFIT, "B3"), "period_end": (PROFIT, "B4"), "revenue": (PROFIT, "B5"),
    "net_profit": (PROFIT, "B6"), "interest": (PROFIT, "B7"), "income_taxes": (PROFIT, "B8"),
    "depreciation": (PROFIT, "B9"), "amortization": (PROFIT, "B10"), "owner_pay": (PROFIT, "B12"),
    "operator_salary": (ROLE, "B12"),
    "capex": (DEAL, "B4"), "down_pct": (DEAL, "B5"), "seller_pct": (DEAL, "B6"),
    "seller_standby": (DEAL, "B7"), "seller_rate": (DEAL, "B8"), "seller_years": (DEAL, "B9"),
    "bank_rate": (DEAL, "B10"), "bank_years": (DEAL, "B11"), "coverage_target": (DEAL, "B12"),
    "asking_price": (DEAL, "B13"), "loan_limit": (DEAL, "B14"),
}
EBITDA_CELL = (PROFIT, "B11")
OPERATOR_NOTE_CELL = (ROLE, "B13")
BANK_SHARE_CELL = (DEAL, "B16")
ANSWER_CELLS: tuple[tuple[str, str], ...] = tuple((ROLE, f"B{row}") for row in range(4, 10))

# Add-backs tab. The owner pay row is fixed; ADDBACK_ROWS are the 25 free rows below it.
OWNER_PAY_ROW = 4
ADDBACK_ROWS = (5, 4 + MAX_ADDBACKS)  # (5, 29)
ADDBACK_TOTAL_CELL = (ADDBACKS, f"C{ADDBACK_ROWS[1] + 2}")
PROOF_MISSING_CELL = (ADDBACKS, f"C{ADDBACK_ROWS[1] + 3}")
DEDUCTION_ROWS = (ADDBACK_ROWS[1] + 7, ADDBACK_ROWS[1] + 6 + MAX_DEDUCTIONS)  # (36, 45)
DEDUCTION_TOTAL_CELL = (ADDBACKS, f"C{DEDUCTION_ROWS[1] + 1}")
ADDBACK_COLS = {"category": "A", "description": "B", "amount": "C", "proof": "D", "note": "E"}
DEDUCTION_COLS = {"category": "A", "description": "B", "amount": "C", "note": "D"}

ADDBACK_CATEGORIES = (
    "personal expense", "family member on payroll who does not work in the business",
    "one-time cost", "non-business cost", "other",
)
DEDUCTION_CATEGORIES = ("one-time income", "below-market cost", "other")
PERIOD_BASES = ("Last 12 months", "Last fiscal year")
YES_NO = ("yes", "no")
QUESTIONS = (
    "Does the owner close most sales?",
    "Does the owner hold the main customer relationships?",
    "Does the owner do work that no employee can do?",
    "Would the business stop running if the owner were away for 30 days?",
    "Does a general manager or operator already run daily work, with their pay in the P&L?",
    "Do key licenses, permits, or vendor terms depend on the owner personally?",
)

MONEY, PERCENT, YEARS = '#,##0;-#,##0', "0.0%", "0.0"
BOLD = Font(bold=True)
RED = Font(color="C00000")
WRAP = Alignment(wrap_text=True, vertical="top")


def _fill() -> PatternFill:
    return PatternFill("solid", fgColor=INPUT_FILL)


def _input(ws, cell: str, value=None, fmt: str | None = None) -> None:
    ws[cell].value = value
    ws[cell].fill = _fill()
    if fmt:
        ws[cell].number_format = fmt


def _marker(ws, row: int, condition: str) -> None:
    ws[f"C{row}"] = f'=IF({condition},"Required","")'
    ws[f"C{row}"].font = RED


def _validate(ws, dv: DataValidation, cells: str) -> None:
    dv.error = "Enter a valid value."
    dv.errorTitle = "Check this cell"
    dv.showErrorMessage = True
    for part in cells.split():
        dv.add(part)
    ws.add_data_validation(dv)


def _list(ws, options, cells: str) -> None:
    _validate(ws, DataValidation(type="list", formula1='"' + ",".join(options) + '"', allow_blank=True), cells)


def _decimal(ws, cells: str, minimum: float | None = 0, maximum: float | None = None) -> None:
    if minimum is not None and maximum is None:
        dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1=str(minimum), allow_blank=True)
    else:
        lo = -1e12 if minimum is None else minimum
        hi = 1e12 if maximum is None else maximum
        dv = DataValidation(type="decimal", operator="between", formula1=str(lo), formula2=str(hi), allow_blank=True)
    _validate(ws, dv, cells)


def _widths(ws, widths: dict[str, int]) -> None:
    for col, width in widths.items():
        ws.column_dimensions[col].width = width


def _title(ws, text: str, subtitle: str) -> None:
    ws["A1"] = text
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = subtitle


def write_start_here(ws) -> None:
    rows = [
        (LIABILITY, False),
        ("", False),
        ("What this calculator does", True),
        ("It adds back the costs a buyer does not carry and removes the profit a lender will not count. "
         "It subtracts the pay of a replacement operator and the cost of maintenance equipment. "
         "It then shows the bank loan and price that the cash left over could support.", False),
        ("", False),
        ("Steps", True),
        ("1. Profit tab: enter the profit figures from the P&L for the last 12 months or the last fiscal year.", False),
        ("2. Add-backs tab: list each cost to add back and each profit item to deduct. Mark if you have proof.", False),
        ("3. Owner role tab: answer the six questions and enter the operator salary.", False),
        ("4. Deal terms tab: check the deal terms and enter the maintenance capital spending.", False),
        ("5. Results tab: read the cash available for debt, the supported price, and any warnings.", False),
        ("", False),
        ("Colors", True),
        ("A yellow cell is an input. You type in it.", False),
        ("A cell with no color is a formula. Leave it as it is.", False),
        ("", False),
        ("What this calculator leaves out", True),
        ("A lender looks at these items too. The calculator does not include them:", False),
        ("- the buyer's personal finances", False),
        ("- income taxes of the business entity", False),
        ("- working capital needs", False),
        ("- closing costs", False),
    ]
    for index, (text, heading) in enumerate(rows, start=1):
        cell = ws[f"A{index}"]
        cell.value = text or None
        cell.alignment = WRAP
        if heading or index == 1:
            cell.font = BOLD
    legend = ws["A14"]
    legend.fill = _fill()
    ws.column_dimensions["A"].width = 110
    ws.row_dimensions[1].height = 62


def write_profit(ws) -> None:
    _title(ws, "Profit", "Use the last 12 months or the last full fiscal year. Enter amounts in dollars.")
    labels = {
        3: "Period basis", 4: "Period end date (YYYY-MM-DD)", 5: "Revenue (for context only)",
        6: "Net profit", 7: "Interest expense", 8: "Income taxes paid by the business",
        9: "Depreciation", 10: "Amortization",
        11: "EBITDA (net profit plus interest, income taxes, depreciation, and amortization)",
        12: "Owner pay in the P&L: salary, payroll tax, and benefits, for all owners who work in the business",
    }
    for row, label in labels.items():
        ws[f"A{row}"] = label
        ws[f"A{row}"].alignment = WRAP
    ws[f"A{EBITDA_CELL[1][1:]}"].font = BOLD
    ws[EBITDA_CELL[1]] = "=SUM(B6:B10)"
    ws[EBITDA_CELL[1]].number_format = MONEY
    ws["D12"] = "Required. Enter 0 if no owner draws pay."
    for field in INPUT_CELLS:
        sheet, cell = INPUT_CELLS[field]
        if sheet != PROFIT:
            continue
        _input(ws, cell, fmt=None if field in ("period_basis", "period_end") else MONEY)
        if field != "revenue":
            _marker(ws, int(cell[1:]), f"ISBLANK({cell})")
    _list(ws, PERIOD_BASES, "B3")
    _decimal(ws, "B5 B7 B9 B10 B12")
    _decimal(ws, "B6 B8", minimum=None)
    _widths(ws, {"A": 62, "B": 18, "C": 12, "D": 44})


def write_addbacks(ws) -> None:
    _title(ws, "Add-backs", "Add back costs a buyer does not carry. Enter every amount as a positive number.")
    for col, text in zip("ABCDE", ("Category", "Description", "Amount", "Proof on file?", "Note")):
        ws[f"{col}3"] = text
        ws[f"{col}3"].font = BOLD
    ws[f"A{OWNER_PAY_ROW}"] = "Owner pay"
    ws[f"B{OWNER_PAY_ROW}"] = "Linked to the Profit tab"
    owner_cell = INPUT_CELLS["owner_pay"][1]
    ws[f"C{OWNER_PAY_ROW}"] = f"=IF(ISBLANK('{PROFIT}'!{owner_cell}),0,'{PROFIT}'!{owner_cell})"
    first, last = ADDBACK_ROWS
    for row in range(first, last + 1):
        for key in ("category", "description", "amount", "proof", "note"):
            _input(ws, f"{ADDBACK_COLS[key]}{row}", fmt=MONEY if key == "amount" else None)
    total, proof = ADDBACK_TOTAL_CELL[1], PROOF_MISSING_CELL[1]
    ws[f"A{total[1:]}"] = "Total add-backs, including owner pay"
    ws[total] = f"=SUM(C{OWNER_PAY_ROW}:C{last})"
    ws[f"A{proof[1:]}"] = "Add-backs with no proof on file"
    ws[proof] = f'=COUNTIF(D{first}:D{last},"no")'
    for cell in (total, proof):
        ws[f"A{cell[1:]}"].font = BOLD
    ws[total].number_format = MONEY
    ws[f"A{DEDUCTION_ROWS[0] - 2}"] = ("Deductions: profit that a lender removes, such as one-time income or a below-market cost. "
                       "For a below-market cost, enter the difference to market cost.")
    ws[f"A{DEDUCTION_ROWS[0] - 2}"].font = BOLD
    for col, text in zip("ABCD", ("Category", "Description", "Amount", "Note")):
        ws[f"{col}{DEDUCTION_ROWS[0] - 1}"] = text
        ws[f"{col}{DEDUCTION_ROWS[0] - 1}"].font = BOLD
    d_first, d_last = DEDUCTION_ROWS
    for row in range(d_first, d_last + 1):
        for key in ("category", "description", "amount", "note"):
            _input(ws, f"{DEDUCTION_COLS[key]}{row}", fmt=MONEY if key == "amount" else None)
    d_total = DEDUCTION_TOTAL_CELL[1]
    ws[f"A{d_total[1:]}"] = "Total deductions"
    ws[f"A{d_total[1:]}"].font = BOLD
    ws[d_total] = f"=SUM(C{d_first}:C{d_last})"
    ws[d_total].number_format = MONEY
    _list(ws, ADDBACK_CATEGORIES, f"A{first}:A{last}")
    _list(ws, YES_NO, f"D{first}:D{last}")
    _list(ws, DEDUCTION_CATEGORIES, f"A{d_first}:A{d_last}")
    _decimal(ws, f"C{first}:C{last} C{d_first}:C{d_last}")
    _widths(ws, {"A": 46, "B": 40, "C": 16, "D": 40, "E": 40})


def write_role(ws) -> None:
    _title(ws, "Owner role", "Answer all six questions with yes or no.")
    ws["A3"], ws["B3"] = "Question", "Answer"
    ws["A3"].font = ws["B3"].font = BOLD
    for (_, cell), question in zip(ANSWER_CELLS, QUESTIONS):
        row = int(cell[1:])
        ws[f"A{row}"] = f"{row - 3}. {question}"
        _input(ws, cell)
        _marker(ws, row, f"ISBLANK({cell})")
    ws["A10"] = "Questions 1 to 4 and 6 count a yes as owner dependence. Question 5 counts a no as dependence."
    ws["A11"] = "Operator"
    ws["A11"].font = BOLD
    ws["A12"] = "Operator salary: yearly cost to employ the people who take over all the owners' work, with payroll tax and benefits"
    ws["A12"].alignment = WRAP
    _input(ws, "B12", fmt=MONEY)
    _marker(ws, 12, "ISBLANK(B12)")
    ws["A13"] = "Operator note: the roles that the salary pays for"
    _input(ws, OPERATOR_NOTE_CELL[1])
    for (_, cell) in ANSWER_CELLS:
        _list(ws, YES_NO, cell)
    _decimal(ws, "B12")
    _widths(ws, {"A": 80, "B": 24, "C": 12})


def write_deal(ws) -> None:
    _title(ws, "Deal terms", "The file starts with example terms. Change them to match your deal.")
    rows = {
        4: ("Annual maintenance capital spending (spending to keep equipment and systems running)", "capex", MONEY,
            "Required. Enter 0 if none."),
        5: ("Buyer down payment, % of price", "down_pct", PERCENT, "Enter as a percent, such as 10%."),
        6: ("Seller note, % of price", "seller_pct", PERCENT, "Enter as a percent, such as 10%."),
        7: ("Seller note on full standby?", "seller_standby", None,
            "If yes, seller note payments do not count in debt service."),
        8: ("Seller note rate", "seller_rate", PERCENT, "Example only."),
        9: ("Seller note term, years", "seller_years", YEARS, ""),
        10: ("Bank loan rate", "bank_rate", PERCENT, "Example only. Ask your lender for a current rate."),
        11: ("Bank loan term, years", "bank_years", YEARS, ""),
        12: ("Lender coverage target", "coverage_target", "0.00", "Cash available for debt divided by debt service."),
        13: ("Asking price (optional)", "asking_price", MONEY, "Enter a price to see coverage and status."),
        14: ("Loan limit for the flag", "loan_limit", MONEY, "Results flags a bank loan above this limit."),
    }
    for row, (label, field, fmt, note) in rows.items():
        ws[f"A{row}"] = label
        ws[f"A{row}"].alignment = WRAP
        ws[f"D{row}"] = note or None
        _input(ws, f"B{row}", fmt=fmt)
        if field in ("seller_rate", "seller_years", "seller_standby"):
            _marker(ws, row, f"AND(B6>0,ISBLANK(B{row}))")
        elif field != "asking_price":
            _marker(ws, row, f"ISBLANK(B{row})")
    ws[f"A{BANK_SHARE_CELL[1][1:]}"] = "Bank loan share of price (100% minus down payment minus seller note)"
    ws[f"A{BANK_SHARE_CELL[1][1:]}"].font = BOLD
    ws[BANK_SHARE_CELL[1]] = "=1-B5-B6"
    ws[BANK_SHARE_CELL[1]].number_format = PERCENT
    _list(ws, YES_NO, "B7")
    _decimal(ws, "B4 B13 B14")
    _decimal(ws, "B5:B6 B8 B10", minimum=0, maximum=1)
    _decimal(ws, "B9 B11", minimum=0, maximum=100)
    _decimal(ws, "B12", minimum=0, maximum=100)
    _widths(ws, {"A": 62, "B": 18, "C": 12, "D": 56})


def write_inputs(wb, inputs: Inputs) -> None:
    """Write the input values. None leaves the cell empty."""
    for field, (sheet, cell) in INPUT_CELLS.items():
        wb[sheet][cell].value = getattr(inputs, field)
    for (sheet, cell), answer in zip(ANSWER_CELLS, inputs.answers):
        wb[sheet][cell].value = answer
    ws = wb[ADDBACKS]
    first = ADDBACK_ROWS[0]
    for offset, item in enumerate(inputs.addbacks):
        row = first + offset
        ws[f"{ADDBACK_COLS['category']}{row}"] = item.category
        ws[f"{ADDBACK_COLS['amount']}{row}"] = item.amount
        ws[f"{ADDBACK_COLS['proof']}{row}"] = item.proof
    first = DEDUCTION_ROWS[0]
    for offset, item in enumerate(inputs.deductions):
        row = first + offset
        ws[f"{DEDUCTION_COLS['category']}{row}"] = item.category
        ws[f"{DEDUCTION_COLS['amount']}{row}"] = item.amount


def build(path: Path, inputs: Inputs, facts: dict) -> dict[str, tuple[str, str]]:
    """Write the workbook. Return the Results cell map: key -> (sheet, cell)."""
    import results_tab  # Imported here: results_tab reads the constants of this module.

    wb = Workbook()
    wb.remove(wb.active)
    sheets = {name: wb.create_sheet(name) for name in TABS}
    write_start_here(sheets["Start here"])
    write_profit(sheets[PROFIT])
    write_addbacks(sheets[ADDBACKS])
    write_role(sheets[ROLE])
    write_deal(sheets[DEAL])
    sba = results_tab.write_sba_values(sheets[DEAL], facts)
    cells = results_tab.write_results(sheets["Results"], sba)
    write_inputs(wb, inputs)
    wb.save(path)
    return cells
