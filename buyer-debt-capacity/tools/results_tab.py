"""Write the Results tab and the SBA values block of the Buyer Debt Capacity Calculator.

Copyright (c) 2026 LIVMO. MIT license.
Every Results cell is a live formula that gives the same value as calc_math.evaluate.
"""
from __future__ import annotations

import re

from openpyxl.styles import Alignment, Font

import build_calculator as bc
from calc_math import (
    BLOCK_CODES, FLAG_CODES, HEAVY_SCORE, MAX_COVERAGE_TARGET, MAX_RATE, MAX_TERM_YEARS, MESSAGES,
    OPERATOR_LOW_SHARE, STATUS_NO, STATUS_TIGHT, STATUS_YES, TIGHT_BAND, WARNING_CODES, ZERO_RATE,
    fact_value,
)

RESULTS = "Results"
EXCEL_TEXT_CHUNK = 200  # Excel allows at most 255 characters in one formula text value.
FACTOR, RATIO, COUNT = "0.000000", "0.00", "0"
BOLD = Font(bold=True)
WRAP = Alignment(wrap_text=True, vertical="top")

BLOCK_LABELS = {
    "missing_inputs": "Required inputs", "negative_inputs": "Amounts not negative",
    "missing_answers": "Owner role answers",
    "operator_blank": "Operator salary entered", "operator_zero": "Operator salary above zero",
    "bad_terms": "Deal terms in range", "no_cash": "Cash available for debt",
}
WARNING_LABELS = {
    "operator_in_place": "Operator in place", "operator_low": "Operator salary level",
    "heavy": "Owner dependence", "proof": "Proof of add-backs",
    "sba_down": "SBA down payment", "sba_term": "SBA loan term",
    "sba_coverage": "SBA coverage", "sba_standby": "SBA standby seller note",
}
FLAG_LABELS = {"qoe": "Quality of Earnings report", "loan_limit": "Loan limit"}

# SBA values block on Deal terms: key -> (label, number format).
SBA_ROWS = {
    "min_equity_injection": ("Minimum equity injection, share of total project cost (Results compares it "
                             "to the price)", bc.PERCENT),
    "coverage_change_of_ownership": ("Minimum debt service coverage when a new owner buys the business", RATIO),
    "max_term_years_no_real_estate": ("Maximum 7(a) loan term with no real estate, years", bc.YEARS),
    "max_loan": ("Maximum 7(a) loan amount", bc.MONEY),
    "standby_note_max_share_of_injection": ("Most of the equity injection a standby seller note can cover",
                                            bc.PERCENT),
    "qoe_amount": ("Quality of Earnings report required at this amount or above", bc.MONEY),
    "qoe_basis": ("Quality of Earnings amount compares to (price or loan)", None),
    "qoe_flag_text": ("Quality of Earnings flag text", None),
}


def ref(location: tuple[str, str]) -> str:
    sheet, cell = location
    return f"'{sheet}'!{cell}"


def lit(text: str) -> str:
    """Return a formula text value. Split long text into joined parts under the Excel limit."""
    parts = [text[i:i + EXCEL_TEXT_CHUNK] for i in range(0, len(text), EXCEL_TEXT_CHUNK)] or [""]
    return "&".join('"' + part.replace('"', '""') + '"' for part in parts)


def fill_template(code: str, values: dict[str, str]) -> str:
    """Return a formula for a message template. Each {name} becomes the formula in values."""
    pieces = re.split(r"\{(\w+)\}", MESSAGES[code])
    out = [lit(p) if n % 2 == 0 else values[p] for n, p in enumerate(pieces) if n % 2 or p]
    return "&".join(out)


def not_blank(cell: str) -> str:
    return f"ISBLANK({cell})=FALSE"


def any_blank(cells) -> str:
    return "OR(" + ",".join(f"ISBLANK({c})" for c in cells) + ")"


def is_word(cell: str) -> str:
    """True when the cell holds yes or no, in any case."""
    return f'OR({cell}="yes",{cell}="no")'


def hide_if(gate: str):
    """Return a function that wraps a value formula so the cell shows "" while gate is true."""
    def wrap(value: str) -> str:
        return f'=IF({gate},"",{value})'
    return wrap


def message(condition: str, text: str) -> str:
    return f'=IF({condition},{text},"")'


class Refs:
    """Formula references to the input and total cells."""

    def __init__(self, sba: dict[str, str]) -> None:
        self.i = {field: ref(loc) for field, loc in bc.INPUT_CELLS.items()}
        self.answers = [ref(loc) for loc in bc.ANSWER_CELLS]
        sheet, first = bc.ANSWER_CELLS[0]
        self.answer_range = f"'{sheet}'!{first}:{bc.ANSWER_CELLS[-1][1]}"
        self.ebitda = ref(bc.EBITDA_CELL)
        self.addbacks = ref(bc.ADDBACK_TOTAL_CELL)
        self.deductions = ref(bc.DEDUCTION_TOTAL_CELL)
        self.proof = ref(bc.PROOF_MISSING_CELL)
        self.share = ref(bc.BANK_SHARE_CELL)
        self.amount_ranges = [amount_range(bc.ADDBACK_COLS["amount"], bc.ADDBACK_ROWS),
                              amount_range(bc.DEDUCTION_COLS["amount"], bc.DEDUCTION_ROWS)]
        self.sba = sba


def amount_range(col: str, rows: tuple[int, int]) -> str:
    return f"'{bc.ADDBACKS}'!{col}{rows[0]}:{col}{rows[1]}"


def write_sba_values(ws, facts: dict) -> dict[str, str]:
    """Write the SBA values block below the deal terms. Return key -> formula reference."""
    start = int(bc.BANK_SHARE_CELL[1][1:]) + 2
    ws[f"A{start}"] = "SBA values"
    ws[f"A{start}"].font = BOLD
    header = (("SOP version", facts.get("sop_version")), ("Date checked", facts.get("checked")),
              ("Source page on sba.gov", facts.get("url")))
    for offset, (label, value) in enumerate(header, start=1):
        ws[f"A{start + offset}"], ws[f"B{start + offset}"] = label, value
        ws[f"B{start + offset}"].alignment = WRAP
    note_row = start + len(header) + 1
    ws[f"A{note_row}"] = ("These values come from the SBA SOP. Results uses them for the SBA warnings "
                          "and the Quality of Earnings flag. Change them only when the SOP changes.")
    ws[f"A{note_row}"].alignment = WRAP
    qoe = fact_value(facts, "qoe")
    values = {key: fact_value(facts, key) for key in SBA_ROWS}
    values["qoe_amount"] = None if qoe is None else qoe["amount"]
    values["qoe_basis"] = None if qoe is None else qoe["basis"]
    values["qoe_flag_text"] = None if qoe is None else facts["qoe"]["flag_text"]
    out = {}
    for offset, (key, (label, fmt)) in enumerate(SBA_ROWS.items(), start=note_row + 1):
        ws[f"A{offset}"], ws[f"B{offset}"] = label, values[key]
        ws[f"D{offset}"] = sop_section(key, facts)
        if fmt:
            ws[f"B{offset}"].number_format = fmt
        out[key] = f"'{bc.DEAL}'!B{offset}"
    return out


def sop_section(key: str, facts: dict) -> str | None:
    """Return the SOP section of a fact. The 3 QoE rows share the qoe fact."""
    entry = facts.get("qoe" if key.startswith("qoe_") else key)
    return entry.get("section") if isinstance(entry, dict) else None


def block_formulas(r: Refs) -> dict[str, str]:
    i = r.i
    required = [i[f] for f in ("period_basis", "period_end", "net_profit", "interest", "income_taxes",
                               "depreciation", "amortization", "owner_pay", "capex", "down_pct",
                               "seller_pct", "bank_rate", "bank_years", "coverage_target", "loan_limit")]
    seller_gap = (f"IF({i['seller_pct']}>0,OR(ISBLANK({i['seller_rate']}),ISBLANK({i['seller_years']}),"
                  f"{is_word(i['seller_standby'])}=FALSE),FALSE)")
    core = [i[f] for f in ("down_pct", "seller_pct", "bank_rate", "bank_years", "coverage_target")]
    down, seller, rate, years, cover = core
    s_rate, s_years = i["seller_rate"], i["seller_years"]
    seller_bad = (f"IF(AND({seller}>0,{not_blank(s_rate)},{not_blank(s_years)}),OR({s_rate}<0,"
                  f"{s_rate}>{MAX_RATE:g},{s_years}<=0,{s_years}>{MAX_TERM_YEARS}),FALSE)")
    bad = (f"IF({any_blank(core)},FALSE,OR({down}<0,{down}>1,{seller}<0,{seller}>1,{down}+{seller}>1,"
           f"{years}<=0,{cover}<=0,{rate}<0,{rate}>{MAX_RATE:g},{cover}>{MAX_COVERAGE_TARGET},"
           f"{years}>{MAX_TERM_YEARS},{seller_bad}))")
    cash_inputs = [i[f] for f in ("net_profit", "interest", "income_taxes", "depreciation", "amortization",
                                  "owner_pay", "operator_salary", "capex")]
    raw_cash = f"{r.ebitda}+{r.addbacks}-{r.deductions}-{i['operator_salary']}-{i['capex']}"
    op, q5 = i["operator_salary"], r.answers[4]
    negative = ",".join([f"{i[f]}<0" for f in ("owner_pay", "operator_salary", "capex")]
                        + [f'COUNTIF({rng},"<0")>0' for rng in r.amount_ranges])
    conditions = {
        "missing_inputs": f"OR({','.join(f'ISBLANK({c})' for c in required)},{seller_gap})",
        "negative_inputs": f"OR({negative})",
        "missing_answers": f'COUNTIF({r.answer_range},"yes")+COUNTIF({r.answer_range},"no")<{len(r.answers)}',
        "operator_blank": f"ISBLANK({op})",
        "operator_zero": f'IF(ISBLANK({op}),FALSE,AND({op}=0,{q5}="no"))',
        "bad_terms": bad,
        "no_cash": f"IF({any_blank(cash_inputs)},FALSE,{raw_cash}<=0)",
    }
    return {code: message(conditions[code], lit(MESSAGES[code])) for code in BLOCK_CODES}


def annuity(rate: str, years: str) -> str:
    """Annual payment per $1 of a monthly-payment loan, written with arithmetic only."""
    return (f"IF(ABS({rate})<{ZERO_RATE:.0E},1/{years},"
            f"12*({rate}/12)/(1-(1+{rate}/12)^(-12*{years})))")


def write_rows(ws, start: int, rows: list[tuple[str, str, str, str | None]], cells: dict) -> int:
    """Write (key, label, formula, format) rows from start. Return the next free row."""
    for offset, (key, label, formula, fmt) in enumerate(rows):
        row = start + offset
        ws[f"A{row}"], ws[f"B{row}"] = label, formula
        ws[f"A{row}"].alignment = ws[f"B{row}"].alignment = WRAP
        if fmt:
            ws[f"B{row}"].number_format = fmt
        cells[key] = (RESULTS, f"B{row}")
    return start + len(rows)


def heading(ws, row: int, text: str) -> int:
    ws[f"A{row}"] = text
    ws[f"A{row}"].font = BOLD
    return row + 1


def write_results(ws, sba: dict[str, str]) -> dict[str, tuple[str, str]]:
    """Write the Results tab. Return the cell map: key -> (sheet, cell)."""
    r = Refs(sba)
    cells: dict[str, tuple[str, str]] = {}
    ws["A1"] = RESULTS
    ws["A1"].font = Font(bold=True, size=14)
    ws["A2"] = "Read from top to bottom. A message cell is blank when its check passes."
    row = heading(ws, 4, "Checks that block the results")
    blocks = block_formulas(r)
    row = write_rows(ws, row, [(f"msg.{c}", BLOCK_LABELS[c], blocks[c], None) for c in BLOCK_CODES], cells)
    msg = {c: cells[f"msg.{c}"][1] for c in BLOCK_CODES}
    blocked_cell = f"B{row}"
    any_block = ",".join(f'{msg[c]}<>""' for c in BLOCK_CODES)
    row = write_rows(ws, row, [("blocked", "Results blocked?", f'=IF(OR({any_block}),"yes","no")', None)], cells)
    row = write_cash_flow(ws, heading(ws, row + 1, "Cash flow"), r, msg, cells)
    blocked = f'{blocked_cell}="yes"'
    row = write_debt_capacity(ws, heading(ws, row + 1, "Debt capacity"), r, blocked, cells)
    row = write_asking(ws, heading(ws, row + 1, "Asking price"), r, blocked, cells)
    row = write_warnings(ws, heading(ws, row + 1, "Warnings"), r, blocked, cells)
    write_flags(ws, heading(ws, row + 1, "Flags"), r, blocked, cells)
    bc._widths(ws, {"A": 52, "B": 90})
    return cells


def write_cash_flow(ws, row: int, r: Refs, msg: dict[str, str], cells: dict) -> int:
    gate = "OR(" + ",".join(f'{msg[c]}<>""' for c in BLOCK_CODES if c != "no_cash") + ")"
    show = hide_if(gate)
    first = row
    steps = [
        ("net_profit", "1. Net profit", show(r.i["net_profit"])),
        ("ebitda", "2. Plus interest, income taxes, depreciation, and amortization, which gives EBITDA",
         show(r.ebitda)),
        ("total_addbacks", "3. Plus total add-backs, including owner pay", show(r.addbacks)),
        ("total_deductions", "4. Minus total deductions", show(r.deductions)),
        ("operator_salary", "5. Minus the operator salary", show(r.i["operator_salary"])),
        ("capex", "6. Minus maintenance capital spending", show(r.i["capex"])),
        ("cash_available", "7. Cash available for debt",
         show(f"B{first + 1}+B{first + 2}-B{first + 3}-B{first + 4}-B{first + 5}")),
    ]
    return write_rows(ws, row, [(k, label, f, bc.MONEY) for k, label, f in steps], cells)


def write_debt_capacity(ws, row: int, r: Refs, blocked: str, cells: dict) -> int:
    i = r.i
    cash = cells["cash_available"][1]
    show = hide_if(blocked)
    bank, seller, service, max_service, supported = (f"B{row + n}" for n in range(5))
    paid = f'AND({i["seller_pct"]}>0,{i["seller_standby"]}="no")'
    rows = [
        ("bank_factor", "Bank annual payment per $1 of loan", show(annuity(i["bank_rate"], i["bank_years"])),
         FACTOR),
        ("seller_factor", "Seller note annual payment per $1 of note (0 on full standby)",
         show(f"IF({paid},{annuity(i['seller_rate'], i['seller_years'])},0)"), FACTOR),
        ("service_per_dollar", "Annual debt service per $1 of price",
         show(f"{r.share}*{bank}+{i['seller_pct']}*{seller}"), FACTOR),
        ("max_debt_service", "Maximum annual debt service (cash available for debt / coverage target)",
         show(f"{cash}/{i['coverage_target']}"), bc.MONEY),
        ("supported_price", "Supported price", show(f'IF({service}>0,{max_service}/{service},"")'), bc.MONEY),
        ("max_bank_loan", "Maximum bank loan", f'=IF({supported}="","",{supported}*{r.share})', bc.MONEY),
    ]
    return write_rows(ws, row, rows, cells)


def write_asking(ws, row: int, r: Refs, blocked: str, cells: dict) -> int:
    i = r.i
    ask, target = i["asking_price"], i["coverage_target"]
    cash, service, supported = (cells[k][1] for k in ("cash_available", "service_per_dollar", "supported_price"))
    show = hide_if(blocked)
    coverage, used = f"B{row}", f"B{row + 3}"
    shown = f"ROUND({coverage},2)"
    status = (f'IF({ask}>0,IF({service}>0,IF({shown}<ROUND({target},2),{lit(STATUS_NO)},'
              f'IF({shown}<=ROUND({target}+{TIGHT_BAND:g},2),{lit(STATUS_TIGHT)},{lit(STATUS_YES)})),'
              f'{lit(STATUS_YES)}),"")')
    rows = [
        ("coverage_at_ask", "Debt coverage at the asking price",
         show(f'IF(AND({ask}>0,{service}>0),{cash}/({ask}*{service}),"")'), RATIO),
        ("status", "Status at the asking price", show(status), None),
        ("price_gap", "Price gap (asking price minus supported price)",
         show(f'IF(AND({ask}>0,{supported}<>""),{ask}-{supported},"")'), bc.MONEY),
        ("price_used", "Price used for the flags (the asking price, or the supported price if none)",
         show(f"IF({ask}>0,{ask},{supported})"), bc.MONEY),
        ("bank_loan_at_price", "Bank loan at the price used", f'=IF({used}="","",{used}*{r.share})', bc.MONEY),
    ]
    return write_rows(ws, row, rows, cells)


def percent_text(value: str) -> str:
    return f'ROUND({value}*100,6)&"%"'


def write_warnings(ws, row: int, r: Refs, blocked: str, cells: dict) -> int:
    i, sba, a = r.i, r.sba, r.answers
    score_cell = f"B{row}"
    points = [f'IF({c}="{"no" if n == 4 else "yes"}",1,0)' for n, c in enumerate(a)]
    valid = f'COUNTIF({r.answer_range},"yes")+COUNTIF({r.answer_range},"no")={len(a)}'
    op, down, share = i["operator_salary"], sba["min_equity_injection"], sba["standby_note_max_share_of_injection"]
    term, cover = sba["max_term_years_no_real_estate"], sba["coverage_change_of_ownership"]
    sba_text = {"down": percent_text(down), "term": term, "coverage": cover, "share": percent_text(share),
                "cash_min": percent_text(f"{down}*(1-{share})")}
    def unblocked(condition: str, code: str) -> str:
        return hide_if(blocked)(f'IF({condition},{fill_template(code, sba_text)},"")')

    n = r.proof
    proof = fill_template("proof", {"n": n, "noun": f'IF({n}=1,"add-back has","add-backs have")'})
    # Same rule as calc_math._sba_warnings: a standby note counts as equity up to share x min.
    d, s, on_standby = i["down_pct"], i["seller_pct"], f'{i["seller_standby"]}="yes"'
    counted = f"IF(AND({on_standby},{not_blank(share)}),MIN({s},{share}*{down}),0)"
    below_min = f"IF(ISBLANK({down}),FALSE,{d}+{counted}<{down})"
    standby = (f'IF(OR(ISBLANK({share}),ISBLANK({down})),FALSE,AND({on_standby},'
               f'{d}<{down}*(1-{share}),{d}+{s}>={down}))')
    formulas = {
        "operator_in_place": unblocked(f"{op}=0", "operator_in_place"),
        "operator_low": unblocked(f"IF({op}=0,FALSE,{op}<{OPERATOR_LOW_SHARE:g}*{i['owner_pay']})", "operator_low"),
        "heavy": f'=IF({score_cell}="","",IF({score_cell}>={HEAVY_SCORE},{lit(MESSAGES["heavy"])},""))',
        "proof": message(f"{n}>0", proof),
        "sba_down": unblocked(below_min, "sba_down"),
        "sba_term": unblocked(f"IF(ISBLANK({term}),FALSE,{i['bank_years']}>{term})", "sba_term"),
        "sba_coverage": unblocked(f"IF(ISBLANK({cover}),FALSE,{i['coverage_target']}<{cover})", "sba_coverage"),
        "sba_standby": unblocked(standby, "sba_standby"),
    }
    rows = [("dependence_score", "Owner dependence score (0 to 6, heavy at 3 or more)",
             f'=IF({valid},{"+".join(points)},"")', COUNT)]
    rows += [(f"msg.{c}", WARNING_LABELS[c], formulas[c], None) for c in WARNING_CODES]
    return write_rows(ws, row, rows, cells)


def write_flags(ws, row: int, r: Refs, blocked: str, cells: dict) -> int:
    sba = r.sba
    used, loan = cells["price_used"][1], cells["bank_loan_at_price"][1]
    amount, basis = sba["qoe_amount"], sba["qoe_basis"]
    qoe = (f'IF(OR(ISBLANK({amount}),{used}=""),FALSE,IF({basis}="price",{used},{loan})>={amount})')
    qoe_text = fill_template("qoe", {"flag_text": sba["qoe_flag_text"]})
    limit = f'IF({loan}="",FALSE,{loan}>{r.i["loan_limit"]})'
    formulas = {
        "qoe": f'=IF({blocked},"",IF({qoe},{qoe_text},""))',
        "loan_limit": f'=IF({blocked},"",IF({limit},{lit(MESSAGES["loan_limit"])},""))',
    }
    return write_rows(ws, row, [(f"msg.{c}", FLAG_LABELS[c], formulas[c], None) for c in FLAG_CODES], cells)
