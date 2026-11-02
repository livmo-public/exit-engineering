"""Shared builders for progress tests."""
from pathlib import Path

import canonical

FULL_INTAKE = {
    "business_type": "services",
    "revenue_range": "1m_to_5m",
    "accounting_system": "qbo",
    "accounting_basis": "accrual",
    "fiscal_year_end_month": 12,
    "latest_closed_month": "2026-09",
    "sale_timeline": "3_to_12_months",
    "buyer_financing": "sba",
    "price_may_reach_3m": "no",
}

CRITICAL_CORE = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9"]

READY_STATE = {
    "version": 1,
    "stage": 4,
    "intake": FULL_INTAKE,
    "disclaimer_acknowledged": True,
    "modules": ["core"],
    "modules_confirmed": True,
    "file_list_shown": True,
    "files": {fid: {"status": "uploaded"} for fid in CRITICAL_CORE},
    "account_map": {},
    "account_map_confirmed": True,
    "findings": [],
    "responses": {},
    "adjustments": [],
}


def month_range(start: str, end: str) -> list[str]:
    """Return every YYYY-MM from start to end, inclusive."""
    year, month = map(int, start.split("-"))
    end_year, end_month = map(int, end.split("-"))
    out = []
    while (year, month) <= (end_year, end_month):
        out.append(f"{year:04d}-{month:02d}")
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return out


def state_with_pl_bs(tmp_path: Path, months: list[str], latest: str, gl: bool,
                     pl_status: str = "uploaded") -> dict:
    """Build a state whose C1 and C2 canonical files cover the given months.

    gl=True marks C3 uploaded; gl=False leaves C3 and C4 missing.
    """
    pl_path = tmp_path / "pl.csv"
    bs_path = tmp_path / "bs.csv"
    canonical.write("pl", [{"period": m, "account": "Sales", "account_type": "revenue",
                            "amount": 100.0, "basis": "accrual"} for m in months], pl_path)
    canonical.write("bs", [{"period": m, "account": "Cash", "account_type": "asset",
                            "subtype": "cash", "balance": 50.0} for m in months], bs_path)
    files = {
        "C1": {"status": pl_status, "canonical_path": str(pl_path)},
        "C2": {"status": "uploaded", "canonical_path": str(bs_path)},
        "C3": {"status": "uploaded" if gl else "missing"},
        "C4": {"status": "missing"},
    }
    return {**READY_STATE, "intake": {**FULL_INTAKE, "latest_closed_month": latest}, "files": files}


# ---- value check (Task 8) ------------------------------------------------------

def _shift_month(month: str, delta: int) -> str:
    year, number = (int(p) for p in month.split("-"))
    index = year * 12 + number - 1 + delta
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


class _Python:
    """The figures of one workbook, computed with metrics from the canonical files."""

    def __init__(self, state: dict, canonical_dir: Path, data_dir: Path):
        import json

        import metrics
        import run_checks
        self.metrics, self.state = metrics, state
        files = json.loads((Path(data_dir) / "files.json").read_text(encoding="utf-8"))
        self.rows = run_checks.read_canonical(state, canonical_dir, files)
        intake = state["intake"]
        months = sorted({r["period"] for kind in ("pl", "bs") for r in self.rows.get(kind, [])})
        self.periods = metrics.periods(months, int(intake["fiscal_year_end_month"]),
                                       intake["latest_closed_month"])
        self.latest = intake["latest_closed_month"]
        self.labels = {**self.periods.fiscal_years, "TTM": self.periods.ttm}
        wanted = "cash" if intake.get("accounting_basis") == "cash" else "accrual"
        pl = self.rows.get("pl", [])
        self.pl = [r for r in pl if r["basis"] == wanted] or pl
        self._cache: dict = {}

    def once(self, name, build):
        if name not in self._cache:
            self._cache[name] = build()
        return self._cache[name]

    def by_month(self, name, build, key="month"):
        return {r[key]: r for r in self.once(name, build)}

    def value(self, key: str) -> float:
        m, rows = self.metrics, self.rows
        parts = key.split(".")
        group, field = parts[0], parts[1]
        label = ".".join(parts[2:])
        if group == "bridge" and field == "adjusted":
            return m.adjusted_ebitda(self.pl, self.state["adjustments"], self.labels[label], label)
        if group == "bridge":
            return m.ebitda(self.pl, self.labels[label])[field]
        if group == "proof_cash":
            return self.by_month("cash", lambda: m.proof_of_cash(
                rows["gl"], rows["bank"], rows["bs"]))[label]["cash_diff"]
        if group == "proof_revenue":
            return self.by_month("rev", lambda: m.proof_of_revenue(
                self.pl, rows["sales"], rows["bank"]))[label][field]
        if group == "revenue" and field == "arr_closing":
            return self.by_month("arr", lambda: m.arr_waterfall(
                rows["subs"], self._arr_months()))[label]["closing_arr"]
        if group == "revenue" and field in ("grr", "nrr"):
            return self.once("ret", lambda: m.retention(
                rows["subs"], _shift_month(self.latest, -12), self.latest))[field]
        if group == "revenue":
            return self._concentration(field)
        if group == "opex":
            return m.opex_by_vendor(rows["vendor"], self.periods.months)["monthly_total"][label]
        if group == "nwc" and field == "peg":
            return m.indicative_peg(self._nwc(), self.periods.ttm)
        if group == "nwc":
            return self.by_month("nwc", self._nwc)[label]["nwc"]
        if group == "deferred":
            return self.by_month("def", lambda: m.deferred_revenue_rollforward(
                rows["subs"], self.periods.months))[label][field]
        raise KeyError(f"no Python value for cell map key '{key}'")

    def _arr_months(self):
        return [_shift_month(self.latest, d) for d in range(-12, 1)]

    def _nwc(self):
        return self.once("nwc_rows", lambda: self.metrics.nwc_trend(self.rows["bs"], self.periods.months))

    def _concentration(self, field: str) -> float:
        ttm = self.periods.ttm
        result = self.metrics.concentration(self.rows["sales"], ttm)
        if field in ("customer_count", "top1_pct", "top5_pct"):
            return result[field]
        total = sum(r["amount"] for r in self.rows["sales"] if r["period"] in set(ttm))
        return sum(amount for _, amount in result["top10"]) / total


def python_values(state: dict, canonical_dir: Path, data_dir: Path, cell_map: dict) -> dict:
    """The Python figure for every key of the cell map, from metrics on the canonical files."""
    figures = _Python(state, canonical_dir, data_dir)
    return {key: figures.value(key) for key in cell_map}


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
