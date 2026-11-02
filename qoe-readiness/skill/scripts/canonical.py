"""Canonical CSV schemas for the QoE readiness skill.

Standard library only. Every other script reads and writes data through this module.
"""
import csv
import math
import re
from datetime import date
from pathlib import Path

KINDS = {
    "pl": ["period", "account", "account_type", "amount", "basis"],
    "bs": ["period", "account", "account_type", "subtype", "balance"],
    "gl": ["date", "txn_id", "account", "account_type", "name", "memo", "debit", "credit"],
    "bank": ["account", "month", "beginning_balance", "deposits", "withdrawals", "ending_balance"],
    "sales": ["period", "customer", "amount"],
    "vendor": ["period", "vendor", "account", "amount"],
    "subs": ["customer", "plan", "interval", "start_date", "end_date", "amount", "currency"],
    "aging": ["type", "name", "invoice_date", "due_date", "amount"],
    "tax": ["year", "gross_receipts"],
    "inventory": ["period", "item_type", "amount"],
}

PL_TYPES = ("revenue", "cogs", "opex", "depreciation", "amortization", "interest",
            "income_tax", "other_income", "other_expense")
BS_TYPES = ("asset", "liability", "equity")
BS_SUBTYPES = ("cash", "ar", "inventory", "wip", "capitalized_software", "other_asset",
               "deferred_revenue", "ap", "accrued", "debt", "other_liability", "equity")
INVENTORY_ITEM_TYPES = ("inventory", "wip")

# Column typing. Columns not listed here are free text.
PERIOD_COLS = {"period", "month"}
DATE_COLS = {"date", "invoice_date", "due_date", "start_date", "end_date"}
YEAR_COLS = {"year"}
NUMBER_COLS = {"amount", "balance", "debit", "credit", "beginning_balance", "deposits",
               "withdrawals", "ending_balance", "gross_receipts"}
# Columns that may be blank in a file: an open subscription has no end date.
# "" in these columns means a blank optional cell (or, for account_type/subtype, not yet mapped).
OPTIONAL_COLS = {"end_date", "due_date", "account_type", "subtype"}
# Blank debit or credit in a ledger line means zero.
BLANK_ZERO_COLS = {("gl", "debit"), ("gl", "credit")}
# Allowed values, checked only when the cell is not blank.
ENUMS = {
    ("pl", "account_type"): PL_TYPES,
    ("bs", "account_type"): BS_TYPES,
    ("bs", "subtype"): BS_SUBTYPES,
    ("inventory", "item_type"): INVENTORY_ITEM_TYPES,
}

_PERIOD_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_YEAR_RE = re.compile(r"^\d{4}$")


class CanonicalError(ValueError):
    """A canonical file or account map is invalid."""


def name_key(name: str) -> str:
    """Match key for customer and vendor names: stripped, single-spaced, case-folded."""
    return " ".join(name.split()).casefold()


def _columns(kind: str) -> list[str]:
    if kind not in KINDS:
        raise CanonicalError(f"unknown kind '{kind}'; expected one of {', '.join(KINDS)}")
    return KINDS[kind]


def _parse(kind: str, col: str, raw: str):
    text = (raw or "").strip()
    if text == "":
        if (kind, col) in BLANK_ZERO_COLS:
            return 0.0
        if col in OPTIONAL_COLS:
            return ""
        raise ValueError(f"'{col}' is blank")
    if col in NUMBER_COLS:
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f"'{col}' is not a number: '{text}'") from None
        if not math.isfinite(value):
            raise ValueError(f"'{col}' is not a finite number: '{text}'")
        return value
    if col in PERIOD_COLS:
        if not _PERIOD_RE.match(text):
            raise ValueError(f"'{col}' must be YYYY-MM: '{text}'")
        return text
    if col in DATE_COLS:
        try:
            return date.fromisoformat(text).isoformat()
        except ValueError:
            raise ValueError(f"'{col}' must be an ISO date YYYY-MM-DD: '{text}'") from None
    if col in YEAR_COLS:
        if not _YEAR_RE.match(text):
            raise ValueError(f"'{col}' must be a 4-digit year: '{text}'")
        return text
    allowed = ENUMS.get((kind, col))
    if allowed is not None and text not in allowed:
        raise ValueError(f"'{col}' must be one of {', '.join(allowed)}: '{text}'")
    return text


def read(kind: str, path: Path) -> list[dict]:
    """Read a canonical CSV. Row numbers in errors count the header as row 1."""
    columns = _columns(kind)
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise CanonicalError(f"{path}: missing column(s) {', '.join(missing)} for kind '{kind}'")
        rows = []
        for number, raw in enumerate(reader, start=2):
            if not any((v or "").strip() for v in raw.values() if isinstance(v, str)):
                continue
            row = {}
            for col in columns:
                try:
                    row[col] = _parse(kind, col, raw.get(col))
                except ValueError as err:
                    raise CanonicalError(f"{path}: row {number}: {err}") from None
            rows.append(row)
    return rows


def write(kind: str, rows: list[dict], path: Path) -> None:
    """Write rows in canonical column order. Extra keys in a row are dropped."""
    columns = _columns(kind)
    with open(path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([_format(row.get(col, "")) for col in columns])


def _format(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


def _row_types(row: dict) -> tuple[str, tuple]:
    """Pick the allowed account types from the row's columns: bs, gl, or P&L-like."""
    if "subtype" in row:
        return "bs", BS_TYPES
    if "debit" in row or "credit" in row:
        return "gl", PL_TYPES + BS_TYPES
    return "pl", PL_TYPES


def _check_entry(account: str, entry, kind: str, allowed: tuple) -> None:
    if not isinstance(entry, dict) or "account_type" not in entry:
        raise CanonicalError(f"account '{account}': map entry needs an 'account_type'")
    if entry["account_type"] not in allowed:
        raise CanonicalError(
            f"account '{account}': account_type '{entry['account_type']}' is not valid for a "
            f"{kind} row; expected one of {', '.join(allowed)}")
    if kind == "bs":
        if "subtype" not in entry:
            raise CanonicalError(f"account '{account}': map entry needs a 'subtype' for a balance sheet row")
        if entry["subtype"] not in BS_SUBTYPES:
            raise CanonicalError(
                f"account '{account}': subtype '{entry['subtype']}' is not valid; "
                f"expected one of {', '.join(BS_SUBTYPES)}")


def apply_account_map(rows: list[dict], account_map: dict[str, dict]) -> list[dict]:
    """Return new rows with account_type (and subtype on balance sheet rows) filled from the map.

    Raises CanonicalError for unmapped accounts and for map entries that are missing a
    key or hold a value outside the allowed type lists. An unmapped account_type is "" in a row.
    """
    unmapped = []
    for row in rows:
        account = row.get("account", "")
        if account not in account_map and account not in unmapped:
            unmapped.append(account)
    if unmapped:
        raise CanonicalError("unmapped account(s): " + ", ".join(f"'{a}'" for a in unmapped))
    out = []
    for row in rows:
        account = row.get("account", "")
        entry = account_map[account]
        kind, allowed = _row_types(row)
        _check_entry(account, entry, kind, allowed)
        new_row = dict(row)
        new_row["account_type"] = entry["account_type"]
        if kind == "bs":
            new_row["subtype"] = entry["subtype"]
        out.append(new_row)
    return out
