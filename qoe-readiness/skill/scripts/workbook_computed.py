"""Builders for the computed tabs of the QoE readiness workbook.

Standard library and openpyxl only (plus the sibling modules). Every number cell from row 5
down is a formula over the input tabs or other computed tabs. Python decides only the layout:
which months, customers, vendors, and subscription rows get a row or a column.

Each builder writes one tab and returns its CellMap entries. Each tab ends with a row labeled
"Check" whose formulas return 0 when the tie holds.
"""
from dataclasses import dataclass

from openpyxl.worksheet.worksheet import Worksheet

import canonical
import metrics
from workbook_cells import (CHECK_LABEL, COUNT, FIRST_ROW, HEADER_ROW, MONEY, PCT, Book, CellMap,
                            col, criterion, month_span, month_sum, put, put_formula, put_row,
                            basis_rows, ref, row_span, shift, span, widths)

ADDBACK_DECISION_COL = 4
ADDBACK_LABEL_COL = 6
PL_LINES = (("revenue", "Revenue"), ("cogs", "Cost of goods sold"), ("opex", "Operating expenses"),
            ("other_income", "Other income"), ("other_expense", "Other expense"),
            ("depreciation", "Depreciation"), ("amortization", "Amortization"),
            ("interest", "Interest"), ("income_tax", "Income tax"))
# Bridge rows: P&L lines 5 to 13, then these.
NET_INCOME_ROW, EBITDA_ROW = 14, 19
ADD_BACK_ROWS = ((15, "Add back: interest", 12), (16, "Add back: income tax", 13),
                 (17, "Add back: depreciation", 10), (18, "Add back: amortization", 11))
TOP_COUNTS = (1, 5, 10)
ONE_TIME_MONTHS = 1


def _tolerance(book: Book) -> float:
    return book.params.get("K04", {}).get("cash_tolerance", 100)


def _pct_limit(book: Book) -> float:
    return book.params.get("K05", {}).get("pct", 0.05)


def _sum(column: int, first: int, last: int) -> str:
    return f"SUM({span(column, first, last)})" if last >= first else "0"


def _outside(column: int, first: int, last: int, limit: float) -> str:
    """Count of cells in the column outside plus or minus the limit."""
    if last < first:
        return "0"
    r = span(column, first, last)
    return f'COUNTIFS({r},">{limit}")+COUNTIFS({r},"<-{limit}")'


def _gap(base: str, other: str) -> str:
    """Absolute gap relative to base; 0 when both are 0; "n/a" when only base is 0."""
    return f'IF({base}=0,IF({other}=0,0,"n/a"),ABS({base}-{other})/ABS({base}))'


def _check_row(ws: Worksheet, row: int, formulas: dict[int, str]) -> None:
    put(ws, row, 1, CHECK_LABEL, bold=True)
    for column, formula in formulas.items():
        put_formula(ws, row, column, formula, COUNT if "COUNTIFS" in formula else MONEY)


def _pl_extra(book: Book, kind: str) -> tuple[tuple[str, str], ...]:
    extra = (("account_type", criterion(kind)),)
    return extra + ((("basis", criterion(book.basis)),) if book.basis else ())


# ---- Adjusted EBITDA bridge -------------------------------------------------------

def _bridge_monthly(ws: Worksheet, book: Book, header: int) -> tuple[dict[str, int], int]:
    """Monthly P&L by type below the bridge, then the input-tab total with no type criterion.

    Returns the row of each type and the row of the input-tab total.
    """
    put(ws, header, 1, "Monthly P&L by type", bold=True)
    for offset, month in enumerate(book.periods.months):
        put(ws, header, 2 + offset, month, bold=True)
    rows = {}
    for k, (kind, label) in enumerate(PL_LINES):
        row = header + 1 + k
        rows[kind] = row
        put(ws, row, 1, label)
        for offset in range(len(book.periods.months)):
            month_cell = f"{col(2 + offset)}${header}"
            put_formula(ws, row, 2 + offset,
                        month_sum(book, "pl", "amount", "period", month_cell, _pl_extra(book, kind)))
    total = header + 1 + len(PL_LINES)
    put(ws, total, 1, f"Total in {book.inputs.titles['pl']}, all account types")
    basis = (("basis", criterion(book.basis)),) if book.basis else ()
    for offset in range(len(book.periods.months)):
        put_formula(ws, total, 2 + offset,
                    month_sum(book, "pl", "amount", "period", f"{col(2 + offset)}${header}", basis))
    return rows, total


def _label_cols(book: Book, label: str) -> tuple[int, int]:
    """First and last monthly column of a bridge label."""
    months, label_months = book.periods.months, book.label_months[label]
    return 2 + months.index(label_months[0]), 2 + months.index(label_months[-1])


def _adjustment_line(book: Book, row: int, label: str) -> str:
    title = book.titles["addbacks"]
    decision = ref(title, ADDBACK_DECISION_COL, row)
    amount = ref(title, ADDBACK_LABEL_COL + book.labels.index(label), row)
    return f'IF({decision}="approved",{amount},IF({decision}="edited",{amount},0))'


def _bridge_column(ws: Worksheet, book: Book, column: int, label: str, type_rows: dict,
                   counted: list) -> CellMap:
    first, last = _label_cols(book, label)
    c = col(column)
    for k, (kind, _) in enumerate(PL_LINES):
        put_formula(ws, FIRST_ROW + k, column, f"SUM({row_span(type_rows[kind], first, last)})")
    put_formula(ws, NET_INCOME_ROW, column,
                f"{c}5-{c}6-{c}7+{c}8-{c}9-{c}10-{c}11-{c}12-{c}13")
    for row, _, source in ADD_BACK_ROWS:
        put_formula(ws, row, column, f"{c}{source}")
    put_formula(ws, EBITDA_ROW, column, f"{c}14+{c}15+{c}16+{c}17+{c}18")
    for j, item in enumerate(counted):
        put_formula(ws, EBITDA_ROW + 1 + j, column, _adjustment_line(book, item.row, label))
    adjusted = EBITDA_ROW + 1 + len(counted)
    lines = f"+SUM({c}{EBITDA_ROW + 1}:{c}{adjusted - 1})" if counted else ""
    put_formula(ws, adjusted, column, f"{c}{EBITDA_ROW}{lines}")
    sheet = book.titles["bridge"]
    return {f"bridge.revenue.{label}": (sheet, f"{c}5"),
            f"bridge.net_income.{label}": (sheet, f"{c}{NET_INCOME_ROW}"),
            f"bridge.ebitda.{label}": (sheet, f"{c}{EBITDA_ROW}"),
            f"bridge.adjusted.{label}": (sheet, f"{c}{adjusted}")}


def build_bridge(ws: Worksheet, book: Book) -> CellMap:
    counted = [a for a in book.addbacks if a.counted] if "addbacks" in book.rendered else []
    # The check: P&L lines sum to the input-tab total, so rows of no listed type show up.
    basis = f" ({book.basis} basis)" if book.basis else ""
    put_row(ws, HEADER_ROW, [f"Line{basis}", *book.labels], bold=True)
    labels = [label for _, label in PL_LINES] + ["Net income"] + [t for _, t, _ in ADD_BACK_ROWS]
    labels += ["EBITDA"] + [f"Owner-stated adjustment: {a.adjustment['name']}" for a in counted]
    labels += ["Owner-adjusted EBITDA"]
    for offset, text in enumerate(labels):
        put(ws, FIRST_ROW + offset, 1, text, bold=text in ("EBITDA", "Owner-adjusted EBITDA"))
    monthly_header = FIRST_ROW + len(labels) + 1
    type_rows, file_row = _bridge_monthly(ws, book, monthly_header)
    cells: CellMap = {}
    checks = {}
    for i, label in enumerate(book.labels):
        cells = {**cells, **_bridge_column(ws, book, 2 + i, label, type_rows, counted)}
        c, (first, last) = col(2 + i), _label_cols(book, label)
        lines = f"{c}{FIRST_ROW}:{c}{FIRST_ROW + len(PL_LINES) - 1}"
        checks[2 + i] = f"ROUND(SUM({lines})-SUM({row_span(file_row, first, last)}),2)"
    _check_row(ws, file_row + 2, checks)
    widths(ws, max(len(book.labels), len(book.periods.months)) + 1)
    return cells


# ---- Proof of cash ------------------------------------------------------------------

def _ledger_cash(book: Book, column: str, accounts: list[str], month_cell: str) -> str:
    terms = [month_sum(book, "gl", column, "date", month_cell, (("account", criterion(a)),))
             for a in accounts]
    return "+".join(terms) or "0"


def build_proof_cash(ws: Worksheet, book: Book) -> CellMap:
    rows = metrics.proof_of_cash(book.rows.get("gl", []), book.rows.get("bank", []),
                                 book.rows.get("bs", []))
    accounts = sorted({r["account"] for r in book.rows.get("bs", []) if r["subtype"] == "cash"})
    put_row(ws, HEADER_ROW, ["Month", "Ledger cash in", "Bank deposits", "Difference in",
                             "Ledger cash out", "Bank withdrawals", "Difference out",
                             "Bank ending balance", "Balance sheet cash", "Cash difference"], bold=True)
    sheet, cells = book.titles["proof_cash"], {}
    for offset, item in enumerate(rows):
        r, m = FIRST_ROW + offset, f"$A{FIRST_ROW + offset}"
        put(ws, r, 1, item["month"])
        put_formula(ws, r, 2, _ledger_cash(book, "debit", accounts, m))
        put_formula(ws, r, 3, month_sum(book, "bank", "deposits", "month", m))
        put_formula(ws, r, 4, f"B{r}-C{r}")
        put_formula(ws, r, 5, _ledger_cash(book, "credit", accounts, m))
        put_formula(ws, r, 6, month_sum(book, "bank", "withdrawals", "month", m))
        put_formula(ws, r, 7, f"E{r}-F{r}")
        put_formula(ws, r, 8, month_sum(book, "bank", "ending_balance", "month", m))
        put_formula(ws, r, 9, month_sum(book, "bs", "balance", "period", m,
                                        (("subtype", criterion("cash")),)))
        put_formula(ws, r, 10, f"H{r}-I{r}")
        cells[f"proof_cash.diff.{item['month']}"] = (sheet, f"J{r}")
    last = FIRST_ROW + len(rows) - 1
    _check_row(ws, last + 2, {10: _outside(10, FIRST_ROW, last, _tolerance(book))})
    widths(ws, 10)
    return cells


# ---- Proof of revenue ---------------------------------------------------------------

def build_proof_revenue(ws: Worksheet, book: Book) -> CellMap:
    rows = metrics.proof_of_revenue(basis_rows(book), book.rows.get("sales", []),
                                    book.rows.get("bank", []))
    put_row(ws, HEADER_ROW, ["Month", "P&L revenue", "Sales by customer", "Bank deposits",
                             "P&L vs sales", "P&L vs bank"], bold=True)
    sheet, cells = book.titles["proof_revenue"], {}
    for offset, item in enumerate(rows):
        r, m = FIRST_ROW + offset, f"$A{FIRST_ROW + offset}"
        put(ws, r, 1, item["month"])
        put_formula(ws, r, 2, month_sum(book, "pl", "amount", "period", m, _pl_extra(book, "revenue")))
        put_formula(ws, r, 3, month_sum(book, "sales", "amount", "period", m))
        put_formula(ws, r, 4, month_sum(book, "bank", "deposits", "month", m))
        put_formula(ws, r, 5, _gap(f"B{r}", f"C{r}"), PCT)
        put_formula(ws, r, 6, _gap(f"B{r}", f"D{r}"), PCT)
        cells[f"proof_revenue.pl_revenue.{item['month']}"] = (sheet, f"B{r}")
        cells[f"proof_revenue.sales_total.{item['month']}"] = (sheet, f"C{r}")
        cells[f"proof_revenue.bank_deposits.{item['month']}"] = (sheet, f"D{r}")
    last, limit = FIRST_ROW + len(rows) - 1, _pct_limit(book)
    checks = {5: f'COUNTIFS({span(5, FIRST_ROW, last)},">{limit}")' if rows else "0",
              6: f'COUNTIFS({span(6, FIRST_ROW, last)},">{limit}")' if rows else "0"}
    _check_row(ws, last + 2, checks)
    widths(ws, 6)
    return cells


# ---- customer and vendor grids ------------------------------------------------------

@dataclass(frozen=True)
class Grid:
    names: tuple[str, ...]
    first_row: int
    total_row: int
    file_row: int
    ttm_col: int
    last_month_col: int

    @property
    def ranked_col(self) -> int:
        """TTM total, blank when zero: metrics ranks only names with a non-zero total."""
        return self.ttm_col + 3


def _names(rows: list[dict], name_col: str, months: list[str], ttm: list[str]):
    """Display names in TTM order, and the spellings of each. SUMIFS ignores case only."""
    wanted, in_ttm = set(months), set(ttm)
    display, spellings, totals = {}, {}, {}
    for row in rows:
        if row["period"] not in wanted:
            continue
        key = canonical.name_key(row[name_col])
        display.setdefault(key, row[name_col])
        spellings.setdefault(key, {}).setdefault(row[name_col].lower(), row[name_col])
        totals[key] = totals.get(key, 0.0) + (row["amount"] if row["period"] in in_ttm else 0.0)
    order = sorted(display, key=lambda k: (-totals[k], display[k]))
    return [display[k] for k in order], [list(spellings[k].values()) for k in order]


def _name_grid(ws: Worksheet, book: Book, kind: str, name_col: str, label: str) -> Grid:
    """Name by month grid from row 4, with TTM total, share, rank, and ranked TTM columns."""
    months, ttm = book.periods.months, book.periods.ttm
    names, spellings = _names(book.rows.get(kind, []), name_col, months, ttm)
    ttm_col = 2 + len(months)
    put_row(ws, HEADER_ROW, [label, *months, "TTM total", "Share of TTM", "Rank",
                             "TTM total, blank when zero"], bold=True)
    first, last = FIRST_ROW, FIRST_ROW + len(names) - 1
    t0 = 2 + months.index(ttm[0]) if ttm else ttm_col
    for i, (name, variants) in enumerate(zip(names, spellings)):
        r = FIRST_ROW + i
        put(ws, r, 1, name)
        for offset in range(len(months)):
            m = f"{col(2 + offset)}${HEADER_ROW}"
            terms = [month_sum(book, kind, "amount", "period", m, ((name_col, criterion(v)),))
                     for v in variants]
            put_formula(ws, r, 2 + offset, "+".join(terms))
        put_formula(ws, r, ttm_col, f"SUM({row_span(r, t0, ttm_col - 1)})" if ttm else "0")
        totals = span(ttm_col, first, last)
        put_formula(ws, r, ttm_col + 1, f"IFERROR({col(ttm_col)}{r}/SUM({totals}),0)", PCT)
        put_formula(ws, r, ttm_col + 2, f"RANK({col(ttm_col)}{r},{totals})", COUNT)
        put_formula(ws, r, ttm_col + 3, f'IF({col(ttm_col)}{r}=0,"",{col(ttm_col)}{r})')
    total, file_row = last + 1, last + 2
    put(ws, total, 1, "Total", bold=True)
    put(ws, file_row, 1, f"Total in {book.inputs.titles[kind]}")
    for c in range(2, ttm_col + 1):
        put_formula(ws, total, c, _sum(c, first, last))
    for offset in range(len(months)):
        put_formula(ws, file_row, 2 + offset,
                    month_sum(book, kind, "amount", "period", f"{col(2 + offset)}${HEADER_ROW}"))
    return Grid(tuple(names), first, total, file_row, ttm_col, ttm_col - 1)


def _grid_check(grid: Grid) -> dict[int, str]:
    return {c: f"ROUND({col(c)}{grid.total_row}-{col(c)}{grid.file_row},2)"
            for c in range(2, grid.last_month_col + 1)}


def _top_share(r: str, count: int) -> str:
    terms = "+".join(f"IFERROR(LARGE({r},{k}),0)" for k in range(1, count + 1))
    return f"IFERROR(({terms})/SUM({r}),0)"


def _concentration(ws: Worksheet, book: Book, grid: Grid, top: int) -> CellMap:
    sheet = book.titles["revenue"]
    if not grid.names:
        put(ws, top, 1, "No sales fall in the months of the P&L.")
        return {}
    # LARGE skips the blank cells, so zero-total customers never take a top-N place.
    r = span(grid.ranked_col, grid.first_row, grid.total_row - 1)
    ttm = span(grid.ttm_col, grid.first_row, grid.total_row - 1)
    put(ws, top, 1, "Customers with TTM sales")
    put_formula(ws, top, 2, f'COUNTIFS({ttm},"<>0")', COUNT)
    cells = {"revenue.customer_count": (sheet, f"B{top}")}
    for offset, count in enumerate(TOP_COUNTS, start=1):
        put(ws, top + offset, 1, "Top customer share of TTM" if count == 1
            else f"Top {count} customers share of TTM")
        put_formula(ws, top + offset, 2, _top_share(r, count), PCT)
        cells[f"revenue.top{count}_pct"] = (sheet, f"B{top + offset}")
    return cells


# ---- subscriptions: ARR -------------------------------------------------------------

def _sub_names(book: Book) -> list[str]:
    """Display name of each subscription row: the first spelling of its customer."""
    display: dict[str, str] = {}
    out = []
    for row in book.rows.get("subs", []):
        out.append(display.setdefault(canonical.name_key(row["customer"]), row["customer"]))
    return out


def _active(book: Book, index: int, month_cell: str) -> str:
    """1 when the subscription row is active in the month, else 0. ISO dates compare as text."""
    start = book.inputs.cell("subs", "start_date", index)
    end = book.inputs.cell("subs", "end_date", index)
    return (f'IF({start}<={month_cell}&"-31",IF({end}="",1,'
            f'IF({end}>{month_cell}&"-01",1,0)),0)')


def _month_header(ws: Worksheet, row: int, title: str, months: list[str], first_col: int) -> None:
    put(ws, row, 1, title, bold=True)
    for offset, month in enumerate(months):
        put(ws, row, first_col + offset, month, bold=True)


def _arr_rows(ws: Worksheet, book: Book, header: int, months: list[str]) -> tuple[int, int]:
    """ARR by subscription row. Monthly plans count 12 times. Returns the first and last row."""
    _month_header(ws, header, "ARR by subscription row", months, 2)
    names = _sub_names(book)
    for i, name in enumerate(names):
        r = header + 1 + i
        put(ws, r, 1, name)
        amount = book.inputs.cell("subs", "amount", i)
        interval = book.inputs.cell("subs", "interval", i)
        for offset in range(len(months)):
            m = f"{col(2 + offset)}${header}"
            put_formula(ws, r, 2 + offset,
                        f'IF({_active(book, i, m)},IF({interval}="year",{amount},{amount}*12),0)')
    return header + 1, header + len(names)


def _arr_customers(ws: Worksheet, header: int, months: list[str], subs: tuple[int, int],
                   names: list[str]) -> tuple[int, int]:
    """ARR by customer, the change by month, and the GRR column (lesser of start and end)."""
    _month_header(ws, header, "ARR by customer", months, 2)
    kept_col = 2 + len(months)
    put(ws, header, kept_col, "Kept for GRR", bold=True)
    first, last = header + 1, header + len(names)
    for i, name in enumerate(names):
        r = first + i
        put(ws, r, 1, name)
        for offset in range(len(months)):
            c = 2 + offset
            put_formula(ws, r, c, f"SUMIFS({span(c, *subs)},{span(1, *subs)},{criterion(name)})")
        put_formula(ws, r, kept_col, f"MIN(B{r},{col(kept_col - 1)}{r})")
    change = last + 2
    _month_header(ws, change, "ARR change by customer", months[1:], 3)
    for i in range(len(names)):
        for c in range(3, 2 + len(months)):
            put_formula(ws, change + 1 + i, c, f"{col(c)}{first + i}-{col(c - 1)}{first + i}")
        put(ws, change + 1 + i, 1, names[i])
    return first, last


def _arr_waterfall(ws: Worksheet, book: Book, header: int, months: list[str],
                   cust: tuple[int, int], delta_first: int) -> CellMap:
    _month_header(ws, header, "ARR waterfall", months[1:], 3)
    names = ("Opening ARR", "New", "Expansion", "Contraction", "Churn", "Closing ARR", "ARR check")
    for k, text in enumerate(names):
        put(ws, header + 1 + k, 1, text)
    sheet, cells = book.titles["revenue"], {}
    delta_last = delta_first + cust[1] - cust[0]
    for c in range(3, 2 + len(months)):
        cur, prev, delta = span(c, *cust), span(c - 1, *cust), span(c, delta_first, delta_last)
        L, r = col(c), header + 1
        formulas = [f"SUM({prev})", f"SUMIFS({cur},{prev},0)",
                    f'SUMIFS({delta},{prev},"<>0",{cur},"<>0",{delta},">0")',
                    f'SUMIFS({delta},{prev},"<>0",{cur},"<>0",{delta},"<0")',
                    f"-SUMIFS({prev},{cur},0)", f"SUM({cur})",
                    f"ROUND({L}{r}+{L}{r + 1}+{L}{r + 2}+{L}{r + 3}+{L}{r + 4}-{L}{r + 5},2)"]
        for k, formula in enumerate(formulas):
            put_formula(ws, r + k, c, formula)
        cells[f"revenue.arr_closing.{months[c - 2]}"] = (sheet, f"{L}{r + 5}")
    return cells


def _retention(ws: Worksheet, book: Book, row: int, months: list[str], cust: tuple[int, int]) -> CellMap:
    start, end, kept = span(2, *cust), span(1 + len(months), *cust), span(2 + len(months), *cust)
    put(ws, row, 1, f"Gross revenue retention {months[0]} to {months[-1]}")
    put_formula(ws, row, 2, f'IF(SUM({start})<=0,"n/a",SUM({kept})/SUM({start}))', PCT)
    put(ws, row + 1, 1, f"Net revenue retention {months[0]} to {months[-1]}")
    put_formula(ws, row + 1, 2, f'IF(SUM({start})<=0,"n/a",SUMIFS({end},{start},"<>0")/SUM({start}))', PCT)
    retained = metrics.retention(book.rows.get("subs", []), months[0], months[-1])
    sheet = book.titles["revenue"]
    return {f"revenue.{k}": (sheet, f"B{row + i}") for i, k in enumerate(("grr", "nrr"))
            if retained[k] is not None}


def _arr_section(ws: Worksheet, book: Book, top: int) -> tuple[CellMap, int]:
    """ARR waterfall, GRR, and NRR over the 12 months that end at the latest closed month."""
    if not book.rows.get("subs") or not book.latest:
        return {}, top
    months = month_span(shift(book.latest, -12), book.latest)
    subs = _arr_rows(ws, book, top, months)
    names = list(dict.fromkeys(_sub_names(book)))
    cust = _arr_customers(ws, subs[1] + 2, months, subs, names)
    delta_first = cust[1] + 3
    waterfall = delta_first + len(names) + 1
    cells = _arr_waterfall(ws, book, waterfall, months, cust, delta_first)
    cells = {**cells, **_retention(ws, book, waterfall + 9, months, cust)}
    return cells, waterfall + 10


def build_revenue(ws: Worksheet, book: Book) -> CellMap:
    grid = _name_grid(ws, book, "sales", "customer", "Customer")
    cells = _concentration(ws, book, grid, grid.file_row + 2)
    end = grid.file_row + 2 + len(TOP_COUNTS)
    if "saas" in book.modules:
        arr, end = _arr_section(ws, book, end + 2)
        cells = {**cells, **arr}
    _check_row(ws, end + 2, _grid_check(grid))
    widths(ws, grid.ranked_col)
    return cells


# ---- Opex by vendor -----------------------------------------------------------------

def build_opex(ws: Worksheet, book: Book) -> CellMap:
    grid = _name_grid(ws, book, "vendor", "vendor", "Vendor")
    months_col, flag_col = grid.ranked_col + 1, grid.ranked_col + 2
    put(ws, HEADER_ROW, months_col, "Months with spend", bold=True)
    put(ws, HEADER_ROW, flag_col, "One-time candidate", bold=True)
    for i in range(len(grid.names)):
        r = grid.first_row + i
        put_formula(ws, r, months_col, f'COUNTIFS({row_span(r, 2, grid.last_month_col)},"<>0")', COUNT)
        put_formula(ws, r, flag_col, f'IF({col(months_col)}{r}={ONE_TIME_MONTHS},"yes","")')
    sheet = book.titles["opex"]
    cells = {f"opex.monthly_total.{m}": (sheet, f"{col(2 + i)}{grid.total_row}")
             for i, m in enumerate(book.periods.months)}
    _check_row(ws, grid.file_row + 2, _grid_check(grid))
    widths(ws, flag_col)
    return cells


# ---- NWC trend ----------------------------------------------------------------------

NWC_COLUMNS = (("ar", "Receivables (AR)"), ("inventory", "Inventory and WIP"),
               ("ap", "Payables (AP)"), ("accrued", "Accrued liabilities"),
               ("deferred_revenue", "Deferred revenue"))


def _bs_sum(book: Book, subtype: str, month_cell: str) -> str:
    return month_sum(book, "bs", "balance", "period", month_cell, (("subtype", criterion(subtype)),))


def _aging_check(book: Book, kind: str, latest: str) -> str:
    total = (f"SUMIFS({book.inputs.column('aging', 'amount')},"
             f"{book.inputs.column('aging', 'type')},{criterion(kind)})")
    return f"ROUND({total}-{latest},2)"


def build_nwc(ws: Worksheet, book: Book) -> CellMap:
    months, ttm = book.periods.months, set(book.periods.ttm)
    put_row(ws, HEADER_ROW, ["Month", *(t for _, t in NWC_COLUMNS), "Net working capital"], bold=True)
    sheet, cells = book.titles["nwc"], {}
    for offset, month in enumerate(months):
        r, m = FIRST_ROW + offset, f"$A{FIRST_ROW + offset}"
        put(ws, r, 1, month)
        for k, (subtype, _) in enumerate(NWC_COLUMNS):
            wip = "+" + _bs_sum(book, "wip", m) if subtype == "inventory" else ""
            put_formula(ws, r, 2 + k, _bs_sum(book, subtype, m) + wip)
        put_formula(ws, r, 7, f"B{r}+C{r}-D{r}-E{r}-F{r}")
        cells[f"nwc.nwc.{month}"] = (sheet, f"G{r}")
    rows = [FIRST_ROW + i for i, m in enumerate(months) if m in ttm]
    peg = FIRST_ROW + len(months) + 1
    put(ws, peg, 1, "Indicative peg: average NWC over the TTM", bold=True)
    if rows:
        put_formula(ws, peg, 7, f"AVERAGE({span(7, rows[0], rows[-1])})")
        cells["nwc.peg"] = (sheet, f"G{peg}")
    else:
        put(ws, peg, 7, "n/a")
    put(ws, peg + 1, 1, "Check: aging totals less latest balance sheet (AR in B, AP in D)")
    last = FIRST_ROW + len(months) - 1
    checks = {2: _aging_check(book, "AR", f"B{last}"), 4: _aging_check(book, "AP", f"D{last}")} \
        if months else {}
    _check_row(ws, peg + 3, checks)
    widths(ws, 7)
    return cells


# ---- Deferred revenue ---------------------------------------------------------------

def _sub_grid(ws: Worksheet, header: int, title: str, months: list[str], names: list[str],
              formula, fmt: str = MONEY, total: bool = True) -> tuple[int, int]:
    """One row per subscription row and one column per month; formula(i, row, column, month).

    Returns the first data row and the total row (the last data row when total is False).
    """
    _month_header(ws, header, title, months, 2)
    for i, name in enumerate(names):
        r = header + 1 + i
        put(ws, r, 1, name)
        for offset in range(len(months)):
            c = 2 + offset
            put_formula(ws, r, c, formula(i, r, c, f"{col(c)}${header}"), fmt)
    last = header + len(names)
    if not total:
        return header + 1, last
    put(ws, last + 1, 1, f"{title}: total", bold=True)
    for offset in range(len(months)):
        put_formula(ws, last + 1, 2 + offset, _sum(2 + offset, header + 1, last))
    return header + 1, last + 1


def _deferred_grids(ws: Worksheet, book: Book, top: int, months: list[str]) -> tuple[int, int]:
    """Billing month flags, billings, and recognized revenue. Returns the two total rows.

    An annual plan bills in its start month and every 12 months after while active, and
    recognizes each billing over 12 months. A monthly plan bills and recognizes each active month.
    """
    names = _sub_names(book)
    cell = book.inputs.cell

    def flag(i: int, r: int, c: int, m: str) -> str:
        start = cell("subs", "start_date", i)
        own = f'IF({start}>={m}&"-01",IF({start}<={m}&"-31",1,0),0)'
        return own + (f"+{col(c - 12)}{r}" if c - 12 >= 2 else "")

    flags = _sub_grid(ws, top, "Billing month flags (1 = annual billing month)", months, names,
                      flag, COUNT, total=False)

    def billing(i: int, r: int, c: int, m: str) -> str:
        amount, interval = cell("subs", "amount", i), cell("subs", "interval", i)
        return (f'IF({_active(book, i, m)},IF({interval}="year",'
                f'{col(c)}{flags[0] + i}*{amount},{amount}),0)')

    bills = _sub_grid(ws, flags[1] + 2, "Billings by subscription row", months, names, billing)

    def recognized(i: int, r: int, c: int, m: str) -> str:
        row = bills[0] + i
        return (f'IF({cell("subs", "interval", i)}="year",'
                f'SUM({row_span(row, max(2, c - 11), c)})/12,{col(c)}{row})')

    recs = _sub_grid(ws, bills[1] + 2, "Recognized revenue by subscription row", months, names,
                     recognized)
    return bills[1], recs[1]


def _grid_months(book: Book) -> list[str]:
    """Grid months: from one month before the earliest start (or first month) to the last month."""
    months = book.periods.months
    starts = [r["start_date"][:7] for r in book.rows.get("subs", [])]
    return month_span(shift(min(starts + [months[0]]), -1), months[-1])


def build_deferred_revenue(ws: Worksheet, book: Book) -> CellMap:
    months = book.periods.months
    put_row(ws, HEADER_ROW, ["Month", "Opening", "Billings", "Recognized", "Closing",
                             "Balance sheet deferred revenue", "Difference", "Gap"], bold=True)
    if not months:
        _check_row(ws, FIRST_ROW + 1, {8: "0"})
        return {}
    grid = _grid_months(book)
    bill_total, rec_total = _deferred_grids(ws, book, FIRST_ROW + len(months) + 1, grid)
    sheet, cells = book.titles["deferred_revenue"], {}
    for offset, month in enumerate(months):
        r, g = FIRST_ROW + offset, 2 + grid.index(month)
        put(ws, r, 1, month)
        put_formula(ws, r, 2, f"SUM({row_span(bill_total, 2, g - 1)})-SUM({row_span(rec_total, 2, g - 1)})")
        put_formula(ws, r, 3, f"{col(g)}{bill_total}")
        put_formula(ws, r, 4, f"{col(g)}{rec_total}")
        put_formula(ws, r, 5, f"B{r}+C{r}-D{r}")
        put_formula(ws, r, 6, _bs_sum(book, "deferred_revenue", f"$A{r}"))
        put_formula(ws, r, 7, f"F{r}-E{r}")
        put_formula(ws, r, 8, _gap(f"E{r}", f"F{r}"), PCT)
        for i, key in enumerate(("opening", "billings", "recognized", "closing")):
            cells[f"deferred.{key}.{month}"] = (sheet, f"{col(2 + i)}{r}")
    limit = book.params.get("K03", {}).get("pct", 0.05)
    last = FIRST_ROW + len(months) - 1
    _check_row(ws, ws.max_row + 2, {8: f'COUNTIFS({span(8, FIRST_ROW, last)},">{limit}")'})
    widths(ws, len(grid) + 1)
    return cells


# ---- Inventory and WIP --------------------------------------------------------------

def build_inventory_wip(ws: Worksheet, book: Book) -> CellMap:
    months = book.periods.months
    put_row(ws, HEADER_ROW, ["Month", "Inventory (file)", "WIP (file)", "Total (file)",
                             "Balance sheet inventory and WIP", "Difference"], bold=True)
    sheet, cells = book.titles["inventory_wip"], {}
    for offset, month in enumerate(months):
        r, m = FIRST_ROW + offset, f"$A{FIRST_ROW + offset}"
        put(ws, r, 1, month)
        for k, item in enumerate(("inventory", "wip")):
            put_formula(ws, r, 2 + k, month_sum(book, "inventory", "amount", "period", m,
                                                (("item_type", criterion(item)),)))
        put_formula(ws, r, 4, f"B{r}+C{r}")
        put_formula(ws, r, 5, f"{_bs_sum(book, 'inventory', m)}+{_bs_sum(book, 'wip', m)}")
        put_formula(ws, r, 6, f"D{r}-E{r}")
        cells[f"inventory.diff.{month}"] = (sheet, f"F{r}")
    last = FIRST_ROW + len(months) - 1
    _check_row(ws, last + 2, {6: _outside(6, FIRST_ROW, last, _tolerance(book))})
    widths(ws, 6)
    return cells


BUILDERS = {
    "bridge": build_bridge, "proof_cash": build_proof_cash, "proof_revenue": build_proof_revenue,
    "revenue": build_revenue, "opex": build_opex, "nwc": build_nwc,
    "deferred_revenue": build_deferred_revenue, "inventory_wip": build_inventory_wip,
}
