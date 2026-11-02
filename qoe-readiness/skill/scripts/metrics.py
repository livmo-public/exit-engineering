"""QoE readiness figures computed in Python from canonical rows.

Standard library only (plus the canonical module in this folder). Every function is pure:
it reads its inputs and returns new values.

Conventions:
- P&L amounts are positive for revenue and for expenses, as exported.
- Balance sheet liabilities are positive, as exported.
- A ratio is a fraction (0.05 is 5%). A ratio with a zero denominator is None, except
  concentration, which returns 0.0 for an empty sales set.
- Customers and vendors match on canonical.name_key; the first spelling seen is displayed.
- ARR flows: contraction and churn are negative, so opening + new + expansion
  + contraction + churn = closing.
"""
import calendar
from dataclasses import dataclass
from typing import Callable, NamedTuple

import canonical

TOP_LIST_SIZE = 10
TOP_GROUP_SIZE = 5
MONTHS_PER_YEAR = 12
COUNTED_DECISIONS = ("approved", "edited")
# Balance sheet subtype to NWC column. Work in progress counts with inventory.
_NWC_COLUMNS = {"ar": "ar", "inventory": "inventory", "wip": "inventory", "ap": "ap",
                "accrued": "accrued", "deferred_revenue": "deferred_revenue"}


@dataclass(frozen=True)
class Periods:
    months: list[str]
    fiscal_years: dict[str, list[str]]
    ttm: list[str]


# ---- month arithmetic -------------------------------------------------------

def _idx(month: str) -> int:
    year, number = month.split("-")
    return int(year) * MONTHS_PER_YEAR + int(number) - 1


def _month(idx: int) -> str:
    return f"{idx // MONTHS_PER_YEAR:04d}-{idx % MONTHS_PER_YEAR + 1:02d}"


def _bounds(month: str) -> tuple[str, str]:
    """First and last ISO date of a YYYY-MM month."""
    year, number = (int(p) for p in month.split("-"))
    return f"{month}-01", f"{month}-{calendar.monthrange(year, number)[1]:02d}"


def periods(available_months: list[str], fiscal_year_end_month: int,
            latest_closed_month: str) -> Periods:
    """Months, complete fiscal years, and TTM.

    Months after latest_closed_month are dropped. A fiscal year is labeled FY plus the
    calendar year in which it ends, and counts only when all 12 of its months are present.
    TTM is the 12 months ending at latest_closed_month, limited to months present in the data.
    """
    if not 1 <= fiscal_year_end_month <= MONTHS_PER_YEAR:
        raise ValueError(f"fiscal_year_end_month must be 1 to 12: {fiscal_year_end_month}")
    months = sorted({m for m in available_months if m <= latest_closed_month})
    have = set(months)
    latest = _idx(latest_closed_month)
    ttm = [m for m in (_month(i) for i in range(latest - 11, latest + 1)) if m in have]
    fiscal_years: dict[str, list[str]] = {}
    if months:
        for year in range(int(months[0][:4]), int(months[-1][:4]) + 2):
            end = year * MONTHS_PER_YEAR + fiscal_year_end_month - 1
            span = [_month(i) for i in range(end - 11, end + 1)]
            if all(m in have for m in span):
                fiscal_years[f"FY{year}"] = span
    return Periods(months=months, fiscal_years=fiscal_years, ttm=ttm)


# ---- shared helpers ---------------------------------------------------------

def _group(rows: list[dict], key: Callable, value: Callable,
           keep: Callable = lambda row: True) -> dict:
    out: dict = {}
    for row in rows:
        if keep(row):
            out[key(row)] = out.get(key(row), 0.0) + value(row)
    return out


def _rank(rows: list[dict], name_col: str, months: list[str]) -> list[tuple[str, float]]:
    """Total per name over the months, largest first. Zero totals are dropped."""
    wanted = set(months)
    totals: dict[str, float] = {}
    display: dict[str, str] = {}
    for row in rows:
        if row["period"] in wanted:
            key = canonical.name_key(row[name_col])
            display.setdefault(key, row[name_col])
            totals[key] = totals.get(key, 0.0) + row["amount"]
    ranked = [(display[k], v) for k, v in totals.items() if v != 0]
    return sorted(ranked, key=lambda item: (-item[1], item[0]))


def _gap_pct(base: float, other: float) -> float | None:
    if base == 0:
        return 0.0 if other == 0 else None
    return abs(base - other) / abs(base)


# ---- P&L --------------------------------------------------------------------

def pl_by_type(pl_rows: list[dict], months: list[str]) -> dict[str, dict[str, float]]:
    """Account type to month to amount. Every P&L type and every month is present."""
    wanted = set(months)
    out = {t: {m: 0.0 for m in months} for t in canonical.PL_TYPES}
    for row in pl_rows:
        if row["period"] not in wanted:
            continue
        if row["account_type"] not in out:
            raise ValueError(f"P&L account '{row['account']}' has account_type "
                             f"'{row['account_type']}'; map every account before computing")
        out[row["account_type"]][row["period"]] += row["amount"]
    return out


def ebitda(pl_rows: list[dict], months: list[str]) -> dict[str, float]:
    """Net income and EBITDA over the months. Other income and expense stay in EBITDA."""
    t = {k: sum(v.values()) for k, v in pl_by_type(pl_rows, months).items()}
    net_income = (t["revenue"] - t["cogs"] - t["opex"] - t["depreciation"] - t["amortization"]
                  - t["interest"] - t["income_tax"] + t["other_income"] - t["other_expense"])
    return {
        "revenue": t["revenue"],
        "net_income": net_income,
        "interest": t["interest"],
        "income_tax": t["income_tax"],
        "depreciation": t["depreciation"],
        "amortization": t["amortization"],
        "ebitda": net_income + t["interest"] + t["income_tax"] + t["depreciation"]
        + t["amortization"],
    }


def adjustment_amount(adjustment: dict, months: list[str], label: str) -> float:
    """The amount under the label; else the sum of its month keys that fall in months."""
    amounts = adjustment.get("amounts") or {}
    if label in amounts:
        return float(amounts[label])
    wanted = set(months)
    return sum(float(v) for k, v in amounts.items() if k in wanted)


def adjusted_ebitda(pl_rows: list[dict], adjustments: list[dict], months: list[str],
                    label: str) -> float:
    """EBITDA plus every approved or edited adjustment amount for the label."""
    added = sum(adjustment_amount(a, months, label) for a in adjustments
                if a.get("decision") in COUNTED_DECISIONS)
    return ebitda(pl_rows, months)["ebitda"] + added


# ---- proofs -----------------------------------------------------------------

def proof_of_cash(gl_rows: list[dict], bank_rows: list[dict], bs_rows: list[dict]) -> list[dict]:
    """Monthly ledger cash flow against the bank. cash_diff is bank ending minus balance sheet cash.

    Cash accounts are the balance sheet accounts with subtype cash. Their ledger debits are
    cash in and their credits are cash out.
    """
    cash = {r["account"] for r in bs_rows if r["subtype"] == "cash"}
    is_cash = lambda r: r["account"] in cash  # noqa: E731
    month_of = lambda r: r["date"][:7]  # noqa: E731
    gl_in = _group(gl_rows, month_of, lambda r: r["debit"], is_cash)
    gl_out = _group(gl_rows, month_of, lambda r: r["credit"], is_cash)
    deposits = _group(bank_rows, lambda r: r["month"], lambda r: r["deposits"])
    withdrawals = _group(bank_rows, lambda r: r["month"], lambda r: r["withdrawals"])
    ending = _group(bank_rows, lambda r: r["month"], lambda r: r["ending_balance"])
    bs_cash = _group(bs_rows, lambda r: r["period"], lambda r: r["balance"],
                     lambda r: r["subtype"] == "cash")
    out = []
    for month in sorted(set(gl_in) | set(gl_out) | set(deposits) | set(ending) | set(bs_cash)):
        bank_end, book_cash = ending.get(month, 0.0), bs_cash.get(month, 0.0)
        out.append({"month": month, "gl_cash_in": gl_in.get(month, 0.0),
                    "bank_deposits": deposits.get(month, 0.0),
                    "gl_cash_out": gl_out.get(month, 0.0),
                    "bank_withdrawals": withdrawals.get(month, 0.0),
                    "bank_ending": bank_end, "bs_cash": book_cash,
                    "cash_diff": bank_end - book_cash})
    return out


def proof_of_revenue(pl_rows: list[dict], sales_rows: list[dict],
                     bank_rows: list[dict]) -> list[dict]:
    """Monthly P&L revenue against sales by customer and bank deposits.

    The percentages are absolute differences relative to P&L revenue.
    """
    revenue = _group(pl_rows, lambda r: r["period"], lambda r: r["amount"],
                     lambda r: r["account_type"] == "revenue")
    sales = _group(sales_rows, lambda r: r["period"], lambda r: r["amount"])
    deposits = _group(bank_rows, lambda r: r["month"], lambda r: r["deposits"])
    pl_months = {r["period"] for r in pl_rows if r["account_type"] == "revenue"}
    out = []
    for month in sorted(pl_months | set(sales) | set(deposits)):
        pl_rev, sales_total, bank = revenue.get(month, 0.0), sales.get(month, 0.0), \
            deposits.get(month, 0.0)
        out.append({"month": month, "pl_revenue": pl_rev, "sales_total": sales_total,
                    "bank_deposits": bank, "pl_vs_sales_pct": _gap_pct(pl_rev, sales_total),
                    "pl_vs_bank_pct": _gap_pct(pl_rev, bank)})
    return out


# ---- customers and vendors --------------------------------------------------

def concentration(sales_rows: list[dict], months: list[str]) -> dict:
    """Customer concentration over the months."""
    ranked = _rank(sales_rows, "customer", months)
    total = sum(amount for _, amount in ranked)

    def share(count: int) -> float:
        return sum(a for _, a in ranked[:count]) / total if total else 0.0

    return {"top1_pct": share(1), "top5_pct": share(TOP_GROUP_SIZE),
            "top10": ranked[:TOP_LIST_SIZE], "customer_count": len(ranked)}


def opex_by_vendor(vendor_rows: list[dict], months: list[str]) -> dict:
    """Monthly vendor spend and the top 10 vendors over the months."""
    monthly = {m: 0.0 for m in months}
    for row in vendor_rows:
        if row["period"] in monthly:
            monthly[row["period"]] += row["amount"]
    return {"monthly_total": monthly,
            "top_vendors": _rank(vendor_rows, "vendor", months)[:TOP_LIST_SIZE]}


# ---- subscriptions ----------------------------------------------------------

class _Sub(NamedTuple):
    key: str
    interval: str
    amount: float
    start: str
    end: str


def _prepare(subs_rows: list[dict]) -> list[_Sub]:
    """Validate intervals and reduce rows to what the subscription metrics use."""
    out = []
    for row in subs_rows:
        interval = str(row["interval"]).strip().lower()
        if interval not in ("month", "year"):
            raise ValueError(f"subscription row for '{row['customer']}' (plan '{row['plan']}') "
                             f"has interval '{row['interval']}'; expected 'month' or 'year'")
        out.append(_Sub(canonical.name_key(row["customer"]), interval, row["amount"],
                        row["start_date"], row["end_date"]))
    return out


def _is_active(sub: _Sub, month: str) -> bool:
    first, last = _bounds(month)
    return sub.start <= last and (sub.end == "" or sub.end > first)


def _arr_by_customer(subs: list[_Sub], month: str) -> dict[str, float]:
    """ARR per customer in a month. Monthly plans count 12 times; annual plans count once."""
    out: dict[str, float] = {}
    for sub in subs:
        if _is_active(sub, month):
            arr = sub.amount * MONTHS_PER_YEAR if sub.interval == "month" else sub.amount
            out[sub.key] = out.get(sub.key, 0.0) + arr
    return out


def _waterfall_row(month: str, before: dict[str, float], after: dict[str, float]) -> dict:
    new = expansion = contraction = churn = 0.0
    for key in sorted(set(before) | set(after)):
        was, now = before.get(key, 0.0), after.get(key, 0.0)
        if was == 0:
            new += now
        elif now == 0:
            churn -= was
        elif now > was:
            expansion += now - was
        else:
            contraction -= was - now
    return {"month": month, "opening_arr": float(sum(before.values())), "new": new,
            "expansion": expansion, "contraction": contraction, "churn": churn,
            "closing_arr": float(sum(after.values()))}


def arr_waterfall(subs_rows: list[dict], months: list[str]) -> list[dict]:
    """Monthly ARR bridge. The first opening comes from the month before months[0]."""
    subs = _prepare(subs_rows)
    return [_waterfall_row(m, _arr_by_customer(subs, _month(_idx(m) - 1)),
                           _arr_by_customer(subs, m)) for m in months]


def retention(subs_rows: list[dict], start_month: str, end_month: str) -> dict:
    """GRR and NRR of the customers active in start_month. None when there is no starting ARR."""
    subs = _prepare(subs_rows)
    start = _arr_by_customer(subs, start_month)
    end = _arr_by_customer(subs, end_month)
    base = sum(start.values())
    if base <= 0:
        return {"grr": None, "nrr": None}
    kept = sum(end.get(k, 0.0) for k in start)
    capped = sum(min(end.get(k, 0.0), v) for k, v in start.items())
    return {"grr": capped / base, "nrr": kept / base}


def _annual_events(sub: _Sub, last: int, billings: dict, recognized: dict) -> None:
    """Bill in the start month and each anniversary while active; recognize over 12 months."""
    idx = _idx(sub.start[:7])
    while idx <= last:
        if _is_active(sub, _month(idx)):
            billings[idx] = billings.get(idx, 0.0) + sub.amount
            for j in range(idx, min(idx + MONTHS_PER_YEAR, last + 1)):
                recognized[j] = recognized.get(j, 0.0) + sub.amount / MONTHS_PER_YEAR
        idx += MONTHS_PER_YEAR


def _monthly_events(sub: _Sub, last: int, billings: dict, recognized: dict) -> None:
    """A monthly plan bills and recognizes the same amount in each active month."""
    for idx in range(_idx(sub.start[:7]), last + 1):
        if _is_active(sub, _month(idx)):
            billings[idx] = billings.get(idx, 0.0) + sub.amount
            recognized[idx] = recognized.get(idx, 0.0) + sub.amount


def deferred_revenue_rollforward(subs_rows: list[dict], months: list[str]) -> list[dict]:
    """Opening, billings, recognized, and closing deferred revenue per month.

    The opening of each month is the closing of the month before, rebuilt from the
    first subscription start, so a window that starts mid-history opens correctly.
    """
    subs = _prepare(subs_rows)
    if not months:
        return []
    last = max(_idx(m) for m in months)
    billings: dict[int, float] = {}
    recognized: dict[int, float] = {}
    for sub in subs:
        build = _annual_events if sub.interval == "year" else _monthly_events
        build(sub, last, billings, recognized)

    def balance(through: int) -> float:
        return (sum(v for i, v in billings.items() if i <= through)
                - sum(v for i, v in recognized.items() if i <= through))

    return [{"month": m, "opening": balance(_idx(m) - 1),
             "billings": billings.get(_idx(m), 0.0), "recognized": recognized.get(_idx(m), 0.0),
             "closing": balance(_idx(m))} for m in months]


# ---- working capital --------------------------------------------------------

def nwc_trend(bs_rows: list[dict], months: list[str]) -> list[dict]:
    """Monthly trade working capital: AR + inventory (with WIP) - AP - accrued - deferred revenue."""
    cols = {m: dict.fromkeys(("ar", "inventory", "ap", "accrued", "deferred_revenue"), 0.0)
            for m in months}
    for row in bs_rows:
        column = _NWC_COLUMNS.get(row["subtype"])
        if column and row["period"] in cols:
            cols[row["period"]][column] += row["balance"]
    return [{"month": m, **v,
             "nwc": v["ar"] + v["inventory"] - v["ap"] - v["accrued"] - v["deferred_revenue"]}
            for m, v in cols.items()]


def indicative_peg(trend: list[dict], ttm: list[str]) -> float:
    """Average NWC over the TTM months present in the trend."""
    wanted = set(ttm)
    values = [r["nwc"] for r in trend if r["month"] in wanted]
    if not values:
        raise ValueError("no NWC months fall in the TTM; cannot compute an indicative peg")
    return sum(values) / len(values)
