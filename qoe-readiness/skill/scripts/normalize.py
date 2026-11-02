"""Convert accounting and billing exports to canonical CSV.

Standard library and openpyxl only. The functions never change an input file.
"""
import csv
import io
import json
import math
import re
from datetime import date
from pathlib import Path

import canonical

PRESETS_PATH = Path(__file__).resolve().parent.parent / "data" / "export_presets.json"

_MONTHS = ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"]
_MONTH_NUMBER = {name[:3]: number for number, name in enumerate(_MONTHS, start=1)}

# Pivot rows that repeat a computed subtotal. Total rows are skipped by prefix.
_PL_SUBTOTALS = {"gross profit", "net operating income", "net other income", "net income",
                 "net ordinary income", "net profit", "operating profit", "net earnings"}
_FOOTER_PREFIXES = ("accrual basis", "cash basis")
_BALANCE_LABELS = {"beginning balance", "ending balance", "opening balance", "closing balance"}
_PIVOT_ROW_FIELDS = {"pl": "account", "bs": "account", "sales": "customer", "vendor": "vendor"}
_PIVOT_VALUE_FIELD = {"pl": "amount", "bs": "balance", "sales": "amount", "vendor": "amount"}
_GROUPED_ANCHOR = {"gl": "date", "aging": "invoice_date"}


class NormalizeError(ValueError):
    """An export cannot be converted to canonical CSV."""


# --- value parsers ---

_NUMBER_RE = re.compile(r"^(\d+\.?\d*|\.\d+)$")


def parse_amount(text: str) -> float:
    """Parse an exported amount: $, commas, (x) negatives. Blank is 0.0."""
    s = str(text).replace(" ", " ").replace("−", "-").strip()
    if s in ("", "-", "--", "–", "—"):
        return 0.0
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1].strip()
    s = s.replace("$", "").replace(",", "").replace(" ", "")
    if s.startswith("-"):
        negative = True
        s = s[1:]
    elif s.startswith("+"):
        s = s[1:]
    if not _NUMBER_RE.match(s):
        raise NormalizeError(f"not a number: '{text}'")
    value = float(s)
    if not math.isfinite(value):
        raise NormalizeError(f"not a finite number: '{text}'")
    return (-value if negative else value) + 0.0


def _month_number(name: str) -> int | None:
    key = name.lower()
    number = _MONTH_NUMBER.get(key[:3])
    if number is None:
        return None
    full = _MONTHS[number - 1]
    return number if (full.startswith(key) or key == "sept") else None


def _year(text: str) -> int:
    return 2000 + int(text) if len(text) == 2 else int(text)


_ISO_MONTH_RE = re.compile(
    r"^(\d{4})-(\d{1,2})(?:-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2}(?:\.\d+)?)?)?)?$")
_SLASH_MONTH_RE = re.compile(r"^(\d{1,2})/(\d{4})$")
_NAME_MONTH_RE = re.compile(
    r"^([A-Za-z]{3,9})\.?[ \-]+(?:(\d{1,2}),?[ \-]+)?(\d{4}|\d{2})$")
_DAY_FIRST_RE = re.compile(r"^(\d{1,2})[ \-]([A-Za-z]{3,9})\.?,?[ \-](\d{4}|\d{2})$")


def parse_month_label(text: str) -> str | None:
    """Return YYYY-MM for a month label, or None when the text is not a month."""
    s = str(text).strip()
    if not s:
        return None
    year = month = None
    if m := _ISO_MONTH_RE.match(s):
        year, month = int(m.group(1)), int(m.group(2))
    elif m := _SLASH_MONTH_RE.match(s):
        year, month = int(m.group(2)), int(m.group(1))
    elif m := _NAME_MONTH_RE.match(s):
        month, year = _month_number(m.group(1)), _year(m.group(3))
    elif m := _DAY_FIRST_RE.match(s):
        month, year = _month_number(m.group(2)), _year(m.group(3))
    if month is None or year is None or not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


_ISO_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})(?:[T ].*)?$")
_US_DATE_RE = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})$")
_DAY_NAME_RE = re.compile(r"^(\d{1,2})[ \-]([A-Za-z]{3,9})\.?,?[ \-](\d{4}|\d{2})$")
_NAME_DAY_RE = re.compile(r"^([A-Za-z]{3,9})\.?[ \-](\d{1,2}),?[ \-](\d{4}|\d{2})$")


def parse_date(text: str) -> str:
    """Return an ISO date for an exported date. Blank is ''. Slash dates are month first."""
    s = str(text).strip()
    if not s:
        return ""
    year = month = day = None
    if m := _ISO_DATE_RE.match(s):
        year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := _US_DATE_RE.match(s):
        month, day, year = int(m.group(1)), int(m.group(2)), _year(m.group(3))
    elif m := _DAY_NAME_RE.match(s):
        day, month, year = int(m.group(1)), _month_number(m.group(2)), _year(m.group(3))
    elif m := _NAME_DAY_RE.match(s):
        month, day, year = _month_number(m.group(1)), int(m.group(2)), _year(m.group(3))
    try:
        if None in (year, month, day):
            raise ValueError
        return date(year, month, day).isoformat()
    except ValueError:
        raise NormalizeError(f"not a date: '{text}'") from None


# --- file reading ---

def _cell_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _read_xlsx(path: Path) -> list[list[str]]:
    import openpyxl
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.active
        return [[_cell_text(c) for c in row] for row in sheet.iter_rows(values_only=True)]
    finally:
        workbook.close()


def _read_csv(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError:
            raise NormalizeError("file is not UTF-8 or Windows-1252 text") from None
    return list(csv.reader(io.StringIO(text, newline="")))


def _read_table(path: Path) -> list[list[str]]:
    path = Path(path)
    if not path.is_file():
        raise NormalizeError(f"{path}: file not found")
    if path.suffix.lower() in (".xlsx", ".xlsm"):
        return _read_xlsx(path)
    return _read_csv(path)


def _cell(row: list[str], index: int) -> str:
    return row[index].strip() if index < len(row) else ""


def _fail(path: Path, number: int, message: str) -> NormalizeError:
    return NormalizeError(f"{Path(path).name}: row {number}: {message}")


# --- pivot ---

def parse_pivot(path, kind: str, row_field: str) -> list[dict]:
    """Read a report with one column per month. Return one row per label and month."""
    path = Path(path)
    if kind not in _PIVOT_ROW_FIELDS:
        raise NormalizeError(f"pivot layout does not support kind '{kind}'")
    if row_field != _PIVOT_ROW_FIELDS[kind]:
        raise NormalizeError(
            f"row_field for kind '{kind}' must be '{_PIVOT_ROW_FIELDS[kind]}', not '{row_field}'")
    value_field = _PIVOT_VALUE_FIELD[kind]
    table = _read_table(path)
    header_at, months = _find_month_header(table, path)
    rows = []
    for number, line in enumerate(table[header_at + 1:], start=header_at + 2):
        label = _cell(line, 0)
        if not label:
            continue
        cells = [_cell(line, index) for index in months]
        if not any(cells):
            continue  # section header or footer text
        key = label.casefold()
        if (_is_total_label(key, kind) or key.startswith(_FOOTER_PREFIXES)
                or (kind == "pl" and key in _PL_SUBTOTALS)):
            continue
        for (index, period), text in zip(months.items(), cells):
            try:
                amount = parse_amount(text)
            except NormalizeError as err:
                raise _fail(path, number, f"column '{_cell(table[header_at], index)}': {err}") from None
            rows.append({"period": period, row_field: label, value_field: amount})
    return rows


def _is_total_label(key: str, kind: str) -> bool:
    """Total rows. Sales and vendor names may start with "Total", so only a bare "Total" counts."""
    if kind in ("sales", "vendor"):
        return key == "total"
    return key == "total" or key.startswith("total ")


def _find_month_header(table: list[list[str]], path: Path) -> tuple[int, dict[int, str]]:
    for at, line in enumerate(table):
        months = {}
        for index in range(1, len(line)):
            period = parse_month_label(line[index])
            if period is not None:
                months[index] = period
        if months:
            seen = {}
            for index, period in months.items():
                if period in seen:
                    raise _fail(path, at + 1, f"month {period} appears in two columns")
                seen[period] = index
            return at, months
    raise NormalizeError(f"{Path(path).name}: no header row with month labels found")


# --- flat and grouped ---

def _norm_header(text: str) -> str:
    return " ".join(text.split()).casefold()


def _locate_header(table: list[list[str]], wanted: list[str], path: Path) -> tuple[int, dict[str, int]]:
    """Find the first row that holds every wanted header. Return its index and the column positions."""
    targets = [_norm_header(h) for h in wanted]
    for at, line in enumerate(table):
        heads = [_norm_header(c) for c in line]
        if all(t in heads for t in targets):
            return at, {h: heads.index(_norm_header(h)) for h in wanted}
    missing = ", ".join(f"'{h}'" for h in wanted)
    raise NormalizeError(f"{Path(path).name}: no header row with column(s) {missing}")


def _convert(kind: str, column: str, text: str):
    text = text.strip()
    if column in canonical.NUMBER_COLS:
        return parse_amount(text)
    if column in canonical.DATE_COLS:
        return parse_date(text)
    if column in canonical.PERIOD_COLS:
        period = parse_month_label(text)
        if period is None:
            raise NormalizeError(f"not a month: '{text}'")
        return period
    if column in canonical.YEAR_COLS:
        m = re.match(r"^(\d{4})(\.0+)?$", text)
        if not m:
            raise NormalizeError(f"not a year: '{text}'")
        return m.group(1)
    return text


def _split_signed(value: float) -> dict:
    return {"debit": value if value > 0 else 0.0, "credit": -value if value < 0 else 0.0}


def _build_row(kind: str, line: list[str], positions: dict[str, int], path: Path, number: int) -> dict:
    row = {}
    for column, index in positions.items():
        try:
            if column == "amount_signed":
                row.update(_split_signed(parse_amount(_cell(line, index))))
            else:
                row[column] = _convert(kind, column, _cell(line, index))
        except NormalizeError as err:
            raise _fail(path, number, f"column '{column}': {err}") from None
    return row


def _positions(column_map: dict[str, str], found: dict[str, int]) -> dict[str, int]:
    return {column: found[header] for column, header in column_map.items()}


def parse_flat(path, kind: str, column_map: dict[str, str]) -> list[dict]:
    """Read a table with one record per row. column_map maps canonical column to source header."""
    path = Path(path)
    if any(not header for header in column_map.values()):
        raise NormalizeError("a flat export needs a header name for every mapped column")
    table = _read_table(path)
    at, found = _locate_header(table, list(column_map.values()), path)
    positions = _positions(column_map, found)
    rows = []
    for number, line in enumerate(table[at + 1:], start=at + 2):
        if not any(_cell(line, index) for index in positions.values()):
            continue
        first = _cell(line, next(iter(positions.values())))
        if kind in ("sales", "vendor") and first.casefold() == "total":
            continue
        rows.append(_build_row(kind, line, positions, path, number))
    return rows


def parse_grouped(path, kind: str, column_map: dict[str, str], group_header_column: str,
                  group_provides: str | None = "account") -> list[dict]:
    """Read a report where heading rows name the group and the lines sit below.

    The group heading goes into the canonical column named by group_provides. With
    group_provides None, headings (such as aging buckets) are skipped.
    """
    path = Path(path)
    if kind not in _GROUPED_ANCHOR:
        raise NormalizeError(f"grouped layout supports kinds gl and aging, not '{kind}'")
    anchor = _GROUPED_ANCHOR[kind]
    named = {c: h for c, h in column_map.items() if h}
    if anchor not in named:
        raise NormalizeError(f"grouped export for kind '{kind}' needs a '{anchor}' column")
    wanted = list(named.values()) + ([group_header_column] if group_header_column else [])
    table = _read_table(path)
    at, found = _locate_header(table, wanted, path)
    positions = _positions(named, found)
    group_index = _group_index(table[at], group_header_column, found)
    others = [i for i in positions.values() if i != group_index]
    rows = []
    group = ""
    for number, line in enumerate(table[at + 1:], start=at + 2):
        label = _cell(line, group_index)
        if (label.casefold() in _BALANCE_LABELS
                or _cell(line, positions[anchor]).casefold() in _BALANCE_LABELS):
            continue
        if label.casefold().startswith("total"):
            continue
        if label and not any(_cell(line, i) for i in others):
            group = label
            continue
        if not _cell(line, positions[anchor]):
            continue
        if label and group_index != positions[anchor]:
            group = label
        row = _build_row(kind, line, positions, path, number)
        if group_provides:
            if not group:
                raise _fail(path, number, "line found before any group heading")
            row[group_provides] = group
        rows.append(row)
    return rows


def _group_index(header: list[str], group_header_column: str, found: dict[str, int]) -> int:
    if group_header_column:
        return found[group_header_column]
    for index, text in enumerate(header):
        if not text.strip():
            return index
    return 0


# --- presets ---

def _load_presets() -> dict:
    return json.loads(PRESETS_PATH.read_text(encoding="utf-8"))


def _preset(system: str, report_id: str) -> dict:
    presets = _load_presets()
    if system not in presets:
        raise NormalizeError(f"unknown system '{system}'; expected one of {', '.join(presets)}")
    if report_id not in presets[system]:
        raise NormalizeError(
            f"unknown report '{report_id}' for system '{system}'; expected one of "
            f"{', '.join(presets[system])}")
    return presets[system][report_id]


def _preset_rows(preset: dict, path: Path, basis: str, period: str | None) -> list[dict]:
    kind, layout = preset["kind"], preset["layout"]
    columns = preset["columns"]
    per_run = preset.get("period_mode") == "per_run"
    if layout == "pivot":
        row_field = next(c for c in columns if c in ("account", "customer", "vendor"))
        rows = parse_pivot(path, kind, row_field)
    elif layout == "flat":
        if per_run:
            if not period or parse_month_label(period) != period:
                raise NormalizeError(f"{preset['report_name']} is a per_run report: pass period as YYYY-MM")
        rows = parse_flat(path, kind, columns)
        if per_run:
            rows = [{**r, "period": period} for r in rows if r.get("amount") != 0.0]
    elif layout == "grouped":
        rows = parse_grouped(path, kind, columns, preset.get("group_header_column", ""),
                             group_provides=preset.get("group_provides"))
    else:
        raise NormalizeError(f"unknown layout '{layout}'")
    return [_with_defaults(kind, {**r, **preset.get("constants", {})}, basis) for r in rows]


def _with_defaults(kind: str, row: dict, basis: str) -> dict:
    out = dict(row)
    if kind in ("pl", "bs", "gl"):
        out.setdefault("account_type", "")
    if kind == "bs":
        out.setdefault("subtype", "")
    if kind == "pl":
        out.setdefault("basis", basis)
    return out


# Kinds that two reports feed (A/R and A/P aging). A new run replaces only the rows of its own type.
_MERGE_KEYS = {"aging": "type"}


def _merge_existing(kind: str, rows: list[dict], target: Path) -> list[dict]:
    key = _MERGE_KEYS.get(kind)
    if key is None or not target.is_file():
        return rows
    incoming = {r.get(key) for r in rows}
    kept = [r for r in canonical.read(kind, target) if r[key] not in incoming]
    return kept + rows


def _write(kind: str, rows: list[dict], out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{kind}.csv"
    rows = _merge_existing(kind, rows, target)
    canonical.write(kind, rows, target)
    canonical.read(kind, target)  # fail now if a row is not canonical
    return target


def normalize(system: str, report_id: str, path: Path, out_dir: Path, *,
              basis: str = "accrual", period: str | None = None) -> Path:
    """Convert one export to out_dir/{kind}.csv using the preset for the system and report.

    basis fills the P&L basis column. period (YYYY-MM) is required for per_run reports.
    """
    preset = _preset(system, report_id)
    rows = _preset_rows(preset, Path(path), basis, period)
    return _write(preset["kind"], rows, out_dir)


def normalize_runs(system: str, report_id: str, files: dict[str, Path], out_dir: Path) -> Path:
    """Convert one export per month for a per_run report and merge them into one file."""
    preset = _preset(system, report_id)
    if preset.get("period_mode") != "per_run":
        raise NormalizeError(f"{system} {report_id} is not a per_run report; use normalize()")
    rows = []
    for period in sorted(files):
        rows.extend(_preset_rows(preset, Path(files[period]), "accrual", period))
    return _write(preset["kind"], rows, out_dir)


# --- generic path ---

def normalize_generic(path, kind: str, column_map: dict[str, str], out_dir: Path, *,
                      basis: str = "accrual") -> Path:
    """Convert a flat export from any system. The owner confirms column_map before this call."""
    if kind not in canonical.KINDS:
        raise NormalizeError(f"unknown kind '{kind}'; expected one of {', '.join(canonical.KINDS)}")
    columns = canonical.KINDS[kind]
    unknown = [c for c in column_map if c not in columns and c != "amount_signed"]
    if unknown:
        raise NormalizeError(f"column map names unknown column(s) for kind '{kind}': {', '.join(unknown)}")
    defaulted = canonical.OPTIONAL_COLS | {"basis"} | {c for k, c in canonical.BLANK_ZERO_COLS if k == kind}
    missing = [c for c in columns if c not in column_map and c not in defaulted]
    if missing:
        raise NormalizeError(f"column map for kind '{kind}' lacks: {', '.join(missing)}")
    rows = parse_flat(path, kind, column_map)
    return _write(kind, [_with_defaults(kind, r, basis) for r in rows], out_dir)


# --- account map proposal ---

def _bs(subtype: str) -> dict:
    account_type = {"cash": "asset", "ar": "asset", "inventory": "asset", "wip": "asset",
                    "capitalized_software": "asset", "other_asset": "asset", "equity": "equity"
                    }.get(subtype, "liability")
    return {"account_type": account_type, "subtype": subtype}


# First match wins. Order matters: specific rules sit above general ones.
_RULES = [
    (r"accumulated (depreciation|amortization)", _bs("other_asset")),
    # Balance sheet words come first, so "Income taxes payable" is not a P&L tax account.
    (r"^(?!.*(receivable|interest|expense|fee)).*(\bloans?\b|notes? payable|line of credit)", _bs("debt")),
    (r"receivable", _bs("ar")),
    (r"accrued", _bs("accrued")),
    (r"payable", _bs("ap")),
    (r"depreciation", {"account_type": "depreciation"}),
    (r"amortization", {"account_type": "amortization"}),
    (r"income tax|provision for tax", {"account_type": "income_tax"}),
    (r"interest income", {"account_type": "other_income"}),
    (r"interest", {"account_type": "interest"}),
    (r"cost of (goods|sales|revenue)|\bcogs\b", {"account_type": "cogs"}),
    (r"capitalized software", _bs("capitalized_software")),
    (r"deferred revenue|unearned revenue", _bs("deferred_revenue")),
    (r"inventory", _bs("inventory")),
    (r"work in progress|\bwip\b", _bs("wip")),
    (r"equity|retained earnings|owner'?s?\s+(draw|distribution)", _bs("equity")),
    (r"\bcash\b|checking|savings|\bbank\b(?!\s+(fee|charge|service))", _bs("cash")),
    # Names with a cost word stay blank: "Sales and marketing" is not revenue.
    (r"^(?!.*(marketing|commission|tax|expense|cost|software|advertis)).*(\brevenues?\b|\bsales\b)",
     {"account_type": "revenue"}),
]
_COMPILED_RULES = [(re.compile(pattern, re.IGNORECASE), entry) for pattern, entry in _RULES]


def propose_account_map(accounts: list[str]) -> dict[str, dict]:
    """Propose account types by keyword. Unknown accounts map to {"account_type": ""}.

    A balance sheet match also carries a subtype. The owner confirms every entry.
    """
    proposal = {}
    for account in accounts:
        entry = {"account_type": ""}
        for pattern, rule in _COMPILED_RULES:
            if pattern.search(account):
                entry = dict(rule)
                break
        proposal[account] = entry
    return proposal
