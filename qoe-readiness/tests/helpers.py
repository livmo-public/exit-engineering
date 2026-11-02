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
