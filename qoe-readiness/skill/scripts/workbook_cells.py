"""Cell writing and formula reference helpers for the QoE readiness workbook.

Standard library and openpyxl only (plus the sibling modules). build_workbook.py and
workbook_computed.py share these helpers and the Book context.

Formula rules:
- Every reference to another sheet quotes the sheet name: 'Inputs - P&L'!$D$5.
- Ranges are bounded: rows 5 to the last data row of the input tab (at least row 5).
- A month criterion is the month text plus "*": the wildcard forces a text match in Excel and
  Google Sheets (a bare "2025-01" parses as a date), and it also buckets ISO dates by month.
"""
from dataclasses import dataclass

from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

import canonical
import metrics

HEADER_ROW = 4
FIRST_ROW = 5
MONEY = "#,##0.00"
PCT = "0.0%"
COUNT = "0"
NOT_AVAILABLE = "not available: file missing"
CHECK_LABEL = "Check"
FIRST_COL_WIDTH = 44
COL_WIDTH = 14
MONTHS_PER_YEAR = 12
_BOLD = Font(bold=True)

CellMap = dict[str, tuple[str, str]]


# ---- context ------------------------------------------------------------------

@dataclass(frozen=True)
class Inputs:
    """Input tab titles and row counts by canonical kind."""
    titles: dict[str, str]
    counts: dict[str, int]

    def last_row(self, kind: str) -> int:
        return max(FIRST_ROW, HEADER_ROW + self.counts.get(kind, 0))

    def _letter(self, kind: str, column: str) -> str:
        return get_column_letter(canonical.KINDS[kind].index(column) + 1)

    def column(self, kind: str, column: str) -> str:
        """Bounded range of one canonical column, for example 'Inputs - P&L'!$D$5:$D$140."""
        c = self._letter(kind, column)
        return f"{quote(self.titles[kind])}!${c}${FIRST_ROW}:${c}${self.last_row(kind)}"

    def cell(self, kind: str, column: str, index: int) -> str:
        """One input cell; index 0 is the first data row."""
        return f"{quote(self.titles[kind])}!${self._letter(kind, column)}${FIRST_ROW + index}"


@dataclass(frozen=True)
class AddbackRow:
    adjustment: dict
    row: int
    counted: bool


@dataclass(frozen=True)
class Book:
    """Everything a tab builder reads. Builders never change it."""
    state: dict
    rows: dict[str, list[dict]]
    periods: metrics.Periods
    labels: tuple[str, ...]
    label_months: dict[str, list[str]]
    basis: str | None
    latest: str | None
    inputs: Inputs
    titles: dict[str, str]
    rendered: frozenset[str]
    addbacks: tuple[AddbackRow, ...]
    params: dict[str, dict]
    modules: tuple[str, ...]


def basis_rows(book: Book) -> list[dict]:
    """P&L rows of the chosen basis; all rows when no basis applies."""
    rows = book.rows.get("pl", [])
    return [r for r in rows if book.basis is None or r["basis"] == book.basis]


# ---- references and criteria ----------------------------------------------------

def quote(title: str) -> str:
    return "'" + title.replace("'", "''") + "'"


def col(index: int) -> str:
    return get_column_letter(index)


def ref(sheet: str, column: int, row: int) -> str:
    """Absolute reference to a cell of another sheet, with the sheet name quoted."""
    return f"{quote(sheet)}!${col(column)}${row}"


def span(column: int, first: int, last: int) -> str:
    """Same-sheet column range, absolute: $B$5:$B$9."""
    return f"${col(column)}${first}:${col(column)}${last}"


def row_span(row: int, first_col: int, last_col: int) -> str:
    return f"{col(first_col)}{row}:{col(last_col)}{row}"


def criterion(text: str) -> str:
    """Excel string literal that matches the text exactly in SUMIFS or COUNTIFS."""
    escaped = text.replace("~", "~~").replace("*", "~*").replace("?", "~?")
    if escaped[:1] in ("=", "<", ">"):
        escaped = "=" + escaped
    return '"' + escaped.replace('"', '""') + '"'


def month_match(cell: str) -> str:
    """Criterion for a month cell: the month text plus a wildcard."""
    return f'{cell}&"*"'


def month_sum(book: Book, kind: str, value: str, period: str, month_cell: str,
              extra: tuple[tuple[str, str], ...] = ()) -> str:
    """SUMIFS of an input column over one month, with extra (column, criterion) pairs."""
    parts = [book.inputs.column(kind, value), book.inputs.column(kind, period), month_match(month_cell)]
    for column, crit in extra:
        parts += [book.inputs.column(kind, column), crit]
    return f"SUMIFS({','.join(parts)})"


# ---- months ---------------------------------------------------------------------

def _idx(month: str) -> int:
    year, number = month.split("-")
    return int(year) * MONTHS_PER_YEAR + int(number) - 1


def shift(month: str, delta: int) -> str:
    index = _idx(month) + delta
    return f"{index // MONTHS_PER_YEAR:04d}-{index % MONTHS_PER_YEAR + 1:02d}"


def month_span(first: str, last: str) -> list[str]:
    return [shift(first, i) for i in range(_idx(last) - _idx(first) + 1)]


# ---- writing --------------------------------------------------------------------

def put(ws: Worksheet, row: int, column: int, value, fmt: str | None = None,
        bold: bool = False) -> None:
    """Write a value or a label. Text that starts with '=' stays text."""
    cell = ws.cell(row=row, column=column)
    if isinstance(value, str):
        cell.value = ILLEGAL_CHARACTERS_RE.sub("", value)
        if cell.value.startswith("="):
            cell.data_type = "s"
    else:
        cell.value = value
    if fmt:
        cell.number_format = fmt
    if bold:
        cell.font = _BOLD


def put_formula(ws: Worksheet, row: int, column: int, formula: str, fmt: str = MONEY) -> str:
    """Write a formula and return its cell address."""
    if not formula.startswith("="):
        formula = "=" + formula
    cell = ws.cell(row=row, column=column, value=formula)
    cell.number_format = fmt
    return cell.coordinate


def put_row(ws: Worksheet, row: int, values: list, bold: bool = False, start: int = 1) -> None:
    for offset, value in enumerate(values):
        put(ws, row, start + offset, value, bold=bold)


def widths(ws: Worksheet, count: int) -> None:
    ws.column_dimensions["A"].width = FIRST_COL_WIDTH
    for index in range(2, count + 1):
        ws.column_dimensions[col(index)].width = COL_WIDTH


def put_table(ws: Worksheet, header: list[str], rows: list[list]) -> int:
    """Header at row 4 and data from row 5. Returns the last row written."""
    put_row(ws, HEADER_ROW, header, bold=True)
    for offset, values in enumerate(rows):
        put_row(ws, FIRST_ROW + offset, values)
    widths(ws, len(header))
    return HEADER_ROW + len(rows)
