"""Spot checks for the QoE readiness skill.

Standard library only (plus the sibling modules). Every check function is pure: it reads a
Context and returns new findings.

Conventions:
- COMPUTED holds one function per computed check in checks.json. A function returns [] when the
  books pass, and one failing finding otherwise. run() numbers the ids "<check_id>-<n>".
- A ratio that metrics returns as None never produces a failing finding.
- A month with a missing side is "not available" and is not compared.
- The P&L figures use the rows of the intake accounting basis (cash, else accrual). When no row
  has that basis, all rows count.
"""
import argparse
import calendar
import copy
import json
import sys
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Callable

import canonical
import metrics
import progress

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
MONTHS_PER_YEAR = 12
MAX_EVIDENCE = 12
MAX_LARGE_ENTRIES = 25
# K01 and K07 compare two bases or need accrual books. A cash-basis owner gets K21 instead.
CASH_SKIPPED_CHECKS = ("K01", "K07")
# Inputs whose absence is the finding: K16 fires when the policy file (S5) is not uploaded.
ABSENCE_INPUTS = {"K16": ("S5",)}


class RunChecksError(ValueError):
    """The state or the canonical files cannot support the checks."""


@dataclass(frozen=True)
class Context:
    state: dict
    canonical: dict[str, list[dict]]
    periods: metrics.Periods
    # Check records by id, from the catalog the run uses. Empty means the bundled catalog.
    checks: dict[str, dict] = field(default_factory=dict)


# ---- catalog and finding helpers ---------------------------------------------

@lru_cache(maxsize=None)
def _load_json(path: str) -> list:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _catalog(data_dir: Path, name: str) -> list[dict]:
    """A deep copy of the catalog file, so callers cannot change the cached data."""
    return copy.deepcopy(_load_json(str(Path(data_dir) / name)))


def _record(ctx: "Context", check_id: str) -> dict:
    """The check record from the run's catalog; else from the bundled catalog."""
    if check_id in ctx.checks:
        return ctx.checks[check_id]
    return next(c for c in _catalog(DEFAULT_DATA_DIR, "checks.json") if c["id"] == check_id)


def _cap(items: list[str]) -> list[str]:
    if len(items) <= MAX_EVIDENCE:
        return list(items)
    return items[:MAX_EVIDENCE] + [f"and {len(items) - MAX_EVIDENCE} more"]


def _finding(ctx: "Context", check_id: str, detail: str, evidence: list[str] = (),
             owner_message: str | None = None) -> dict:
    record = _record(ctx, check_id)
    return {"id": f"{check_id}-1", "check_id": check_id, "name": record["name"],
            "category": record["category"], "severity": record["severity"],
            "method": record["method"], "status": "fail", "detail": detail,
            "owner_message": owner_message or record["owner_message"], "fix": record["fix"],
            "evidence": _cap(list(evidence))}


def _money(value: float) -> str:
    return f"{value:,.2f}"


def _gap(base: float, other: float) -> float | None:
    """Absolute difference relative to base. None when base is zero and other is not."""
    if base == 0:
        return 0.0 if other == 0 else None
    return abs(base - other) / abs(base)


# ---- context helpers ---------------------------------------------------------

def _idx(month: str) -> int:
    year, number = month.split("-")
    return int(year) * MONTHS_PER_YEAR + int(number) - 1


def _shift(month: str, delta: int) -> str:
    index = _idx(month) + delta
    return f"{index // MONTHS_PER_YEAR:04d}-{index % MONTHS_PER_YEAR + 1:02d}"


def _rows(ctx: Context, kind: str) -> list[dict]:
    return ctx.canonical.get(kind, [])


def _latest(ctx: Context) -> str | None:
    latest = ctx.state.get("intake", {}).get("latest_closed_month")
    if latest:
        return latest
    return ctx.periods.months[-1] if ctx.periods.months else None


def _calendar_ttm(ctx: Context) -> list[str]:
    """The 12 calendar months that end at the latest closed month."""
    latest = _latest(ctx)
    return [] if latest is None else [_shift(latest, i) for i in range(1 - MONTHS_PER_YEAR, 1)]


def _ttm(ctx: Context) -> list[str]:
    """The TTM months present in the P&L and balance sheet; else the 12 calendar months."""
    return ctx.periods.ttm or _calendar_ttm(ctx)


def _pl_rows(ctx: Context) -> list[dict]:
    wanted = "cash" if ctx.state.get("intake", {}).get("accounting_basis") == "cash" else "accrual"
    rows = _rows(ctx, "pl")
    chosen = [r for r in rows if r["basis"] == wanted]
    return chosen or rows


def _revenue_by_month(pl_rows: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in pl_rows:
        if row["account_type"] == "revenue":
            out[row["period"]] = out.get(row["period"], 0.0) + row["amount"]
    return out


def _bs_by_month(bs_rows: list[dict], subtype: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in bs_rows:
        if row["subtype"] == subtype:
            out[row["period"]] = out.get(row["period"], 0.0) + row["balance"]
    return out


def _latest_bs_balances(ctx: Context) -> tuple[str | None, dict[tuple[str, str], float]]:
    """The latest balance sheet period (not after the latest closed month) and its balances."""
    latest = _latest(ctx)
    bs = [r for r in _rows(ctx, "bs") if latest is None or r["period"] <= latest]
    if not bs:
        return None, {}
    period = max(r["period"] for r in bs)
    totals: dict[tuple[str, str], float] = {}
    for row in bs:
        if row["period"] == period:
            key = (row["account"], row["subtype"])
            totals[key] = totals.get(key, 0.0) + row["balance"]
    return period, totals


def build_context(state: dict, canonical_rows: dict[str, list[dict]],
                  checks: list[dict] | None = None) -> Context:
    """Build the check context. Periods come from the P&L and balance sheet months.

    checks is the catalog the run uses; findings take their fields from it.
    """
    intake = state.get("intake", {})
    months = sorted({r["period"] for kind in ("pl", "bs") for r in canonical_rows.get(kind, [])})
    latest = intake.get("latest_closed_month") or (months[-1] if months else None)
    if months and latest:
        periods = metrics.periods(months, int(intake.get("fiscal_year_end_month", 12)), latest)
    else:
        periods = metrics.Periods(months=[], fiscal_years={}, ttm=[])
    return Context(state=state, canonical=canonical_rows, periods=periods,
                   checks={c["id"]: c for c in checks or []})


# ---- computed checks ---------------------------------------------------------

def _annual_from_subs(subs: list[dict], min_months: int) -> list[str]:
    if MONTHS_PER_YEAR < min_months:
        return []
    return sorted({r["customer"] for r in subs if str(r["interval"]).strip().lower() == "year"})


def _annual_from_sales(sales: list[dict], min_months: int) -> list[str]:
    """Customers whose sales months are all at least min_months apart, with two or more months."""
    months: dict[str, set[str]] = {}
    for row in sales:
        if row["amount"] != 0:
            months.setdefault(row["customer"], set()).add(row["period"])
    out = []
    for customer, found in sorted(months.items()):
        idxs = sorted(_idx(m) for m in found)
        if len(idxs) >= 2 and all(b - a >= min_months for a, b in zip(idxs, idxs[1:])):
            out.append(customer)
    return out


def check_k01(ctx: Context, params: dict) -> list[dict]:
    bs = _rows(ctx, "bs")
    if not bs or any(r["subtype"] == params.get("subtype", "deferred_revenue") for r in bs):
        return []
    minimum = params.get("min_interval_months", MONTHS_PER_YEAR)
    customers = sorted(set(_annual_from_subs(_rows(ctx, "subs"), minimum))
                       | set(_annual_from_sales(_rows(ctx, "sales"), minimum)))
    if not customers:
        return []
    evidence = [f"Annual billing: {name}" for name in customers]
    return [_finding(ctx, "K01", f"{len(customers)} customer(s) pay a year or more at once. "
                            "The balance sheet has no deferred revenue account.", evidence)]


def check_k03(ctx: Context, params: dict) -> list[dict]:
    subs, bs = _rows(ctx, "subs"), _rows(ctx, "bs")
    present = {r["period"] for r in bs}
    months = [m for m in _ttm(ctx) if m in present]
    if not months or not subs:
        return []
    booked = _bs_by_month(bs, "deferred_revenue")
    bad = []
    for row in metrics.deferred_revenue_rollforward(subs, months):
        have = booked.get(row["month"], 0.0)
        gap = _gap(row["closing"], have)
        if gap is not None and gap > params["pct"]:
            bad.append(f"{row['month']}: balance sheet {_money(have)}, "
                       f"subscriptions {_money(row['closing'])} ({gap:.1%})")
    if not bad:
        return []
    return [_finding(ctx, "K03", f"{len(bad)} of {len(months)} month(s) differ by more than "
                            f"{params['pct']:.0%}.", bad)]


def check_k04(ctx: Context, params: dict) -> list[dict]:
    accounts = {r["account"] for r in _rows(ctx, "bank")}
    bank: dict[str, dict[str, float]] = {}
    for row in _rows(ctx, "bank"):
        bank.setdefault(row["month"], {})[row["account"]] = row["ending_balance"]
    cash = _bs_by_month(_rows(ctx, "bs"), "cash")
    compared = [m for m in sorted(bank) if set(bank[m]) == accounts and m in cash]
    bad = []
    for month in compared:
        ending, book = sum(bank[month].values()), cash[month]
        if abs(ending - book) > params["cash_tolerance"]:
            bad.append(f"{month}: bank {_money(ending)}, balance sheet {_money(book)}, "
                       f"difference {_money(ending - book)}")
    if not bad:
        return []
    return [_finding(ctx, "K04", f"{len(bad)} of {len(compared)} month end(s) differ by more than "
                            f"${params['cash_tolerance']:,}.", bad)]


def check_k05(ctx: Context, params: dict) -> list[dict]:
    pl, bank = _pl_rows(ctx), _rows(ctx, "bank")
    comparable = (set(_revenue_by_month(pl)) & {r["month"] for r in bank}) & set(ctx.periods.months)
    bad = []
    for row in metrics.proof_of_revenue(pl, [], bank):
        gap = row["pl_vs_bank_pct"]
        if row["month"] in comparable and gap is not None and gap > params["pct"]:
            bad.append(f"{row['month']}: revenue {_money(row['pl_revenue'])}, "
                       f"deposits {_money(row['bank_deposits'])} ({gap:.1%})")
    if not bad:
        return []
    return [_finding(ctx, "K05", f"{len(bad)} of {len(comparable)} month(s) differ by more than "
                            f"{params['pct']:.0%}.", bad)]


def check_k07(ctx: Context, params: dict) -> list[dict]:
    pl, bs = _rows(ctx, "pl"), _rows(ctx, "bs")
    accrual = _revenue_by_month([r for r in pl if r["basis"] == "accrual"])
    cash = _revenue_by_month([r for r in pl if r["basis"] == "cash"])
    ar, deferred = _bs_by_month(bs, "ar"), _bs_by_month(bs, "deferred_revenue")
    present = {r["period"] for r in bs}
    bad = []
    for month in _ttm(ctx):
        prior = _shift(month, -1)
        if month not in accrual or month not in cash or month not in present or prior not in present:
            continue
        difference = accrual[month] - cash[month]
        explained = (ar.get(month, 0.0) - ar.get(prior, 0.0)) \
            - (deferred.get(month, 0.0) - deferred.get(prior, 0.0))
        if accrual[month] != 0 and abs(difference - explained) > params["pct"] * abs(accrual[month]):
            bad.append(f"{month}: accrual minus cash {_money(difference)}, "
                       f"receivables and deferred change {_money(explained)}")
    if not bad:
        return []
    return [_finding(ctx, "K07", f"{len(bad)} month(s) do not tie within {params['pct']:.0%} of "
                            "accrual revenue.", bad)]


def check_k08(ctx: Context, params: dict) -> list[dict]:
    patterns = [p.lower() for p in params["name_patterns"]]
    minimum = params["min_abs_balance"]
    hit = lambda account: any(p in account.lower() for p in patterns)  # noqa: E731
    period, balances = _latest_bs_balances(ctx)
    found = [f"Balance sheet {period}: {account} {_money(amount)}"
             for (account, _), amount in sorted(balances.items()) if hit(account) and abs(amount) >= minimum]
    window = set(_calendar_ttm(ctx))
    net: dict[str, float] = {}
    for row in _rows(ctx, "gl"):
        if hit(row["account"]) and row["date"][:7] in window:
            net[row["account"]] = net.get(row["account"], 0.0) + row["debit"] - row["credit"]
    found += [f"Ledger, last 12 months: {account} net {_money(amount)}"
              for account, amount in sorted(net.items()) if abs(amount) >= minimum]
    if not found:
        return []
    return [_finding(ctx, "K08", f"{len(found)} unsorted-item balance(s) found.", found)]


def check_k09(ctx: Context, params: dict) -> list[dict]:
    latest = _latest(ctx)
    bad = sorted((r["period"], r["account"], r["balance"]) for r in _rows(ctx, "bs")
                 if r["subtype"] in params["subtypes"] and r["balance"] < 0
                 and (latest is None or r["period"] <= latest))
    if not bad:
        return []
    evidence = [f"{period}: {account} {_money(balance)}" for period, account, balance in bad]
    return [_finding(ctx, "K09", f"{len(bad)} negative balance(s) found.", evidence)]


def _fiscal_year_beginning(ctx: Context, year: str) -> tuple[str | None, list[str] | None]:
    """The complete fiscal year that begins in the calendar year. A return carries its begin year."""
    for label, months in ctx.periods.fiscal_years.items():
        if months[0][:4] == year:
            return label, months
    return None, None


def check_k10(ctx: Context, params: dict) -> list[dict]:
    pl = _pl_rows(ctx)
    bad = []
    for tax in sorted(_rows(ctx, "tax"), key=lambda r: r["year"]):
        label, months = _fiscal_year_beginning(ctx, tax["year"])
        if not months:
            continue
        books = metrics.ebitda(pl, months)["revenue"]
        gap = _gap(books, tax["gross_receipts"])
        if gap is not None and gap > params["pct"]:
            bad.append(f"{tax['year']} ({label}): tax return {_money(tax['gross_receipts'])}, "
                       f"books {_money(books)} ({gap:.1%})")
    if not bad:
        return []
    return [_finding(ctx, "K10", f"{len(bad)} year(s) differ by more than {params['pct']:.0%}.", bad)]


def check_k16(ctx: Context, params: dict) -> list[dict]:
    if ctx.state.get("files", {}).get("S5", {}).get("status") == "uploaded":
        return []
    period, balances = _latest_bs_balances(ctx)
    held = [(account, amount) for (account, subtype), amount in sorted(balances.items())
            if subtype == params["subtype"] and amount != 0]
    if not held:
        return []
    evidence = [f"{period}: {account} {_money(amount)}" for account, amount in held]
    return [_finding(ctx, "K16", "Capitalized software sits on the balance sheet. "
                            "No policy file is uploaded.", evidence)]


def _as_of(ctx: Context, aging: list[dict]) -> date:
    latest = ctx.state.get("intake", {}).get("latest_closed_month")
    if latest:
        year, month = (int(p) for p in latest.split("-"))
        return date(year, month, calendar.monthrange(year, month)[1])
    return max(date.fromisoformat(r["due_date"] or r["invoice_date"]) for r in aging)


def check_k18(ctx: Context, params: dict) -> list[dict]:
    aging = [r for r in _rows(ctx, "aging") if r["type"].strip().upper() == "AR" and r["amount"] > 0]
    if not aging:
        return []
    as_of = _as_of(ctx, aging)
    old = []
    for row in aging:
        late = (as_of - date.fromisoformat(row["due_date"] or row["invoice_date"])).days
        if late > params["days"]:
            old.append((row["amount"], f"{row['name']}: {_money(row['amount'])}, "
                                       f"{late} days past due at {as_of.isoformat()}"))
    if not old:
        return []
    total = sum(amount for amount, _ in old)
    message = _record(ctx, "K18")["owner_message"] + " Give a short note for each item."
    return [_finding(ctx, "K18", f"{len(old)} receivable(s), {_money(total)} in total, are more than "
                            f"{params['days']} days past due.",
                     [text for _, text in sorted(old, key=lambda item: -item[0])], message)]


def check_k19(ctx: Context, params: dict) -> list[dict]:
    result = metrics.concentration(_rows(ctx, "sales"), _ttm(ctx))
    if result["customer_count"] == 0:
        return []
    evidence = []
    if result["top1_pct"] > params["top1_pct"]:
        evidence.append(f"Top customer {result['top10'][0][0]}: {result['top1_pct']:.1%} of revenue "
                        f"(limit {params['top1_pct']:.0%})")
    if result["top5_pct"] > params["top5_pct"]:
        evidence.append(f"Top 5 customers: {result['top5_pct']:.1%} of revenue "
                        f"(limit {params['top5_pct']:.0%})")
    if not evidence:
        return []
    return [_finding(ctx, "K19", f"{result['customer_count']} customers in the last 12 months.", evidence)]


def check_k20(ctx: Context, params: dict) -> list[dict]:
    latest, subs = _latest(ctx), _rows(ctx, "subs")
    if latest is None or not subs:
        return []
    start = _shift(latest, -MONTHS_PER_YEAR)
    grr = metrics.retention(subs, start, latest)["grr"]
    if grr is None or grr >= params["grr_min"]:
        return []
    return [_finding(ctx, "K20", f"Gross revenue retention from {start} to {latest} is {grr:.1%}.",
                     [f"Gross revenue retention {grr:.1%}, minimum {params['grr_min']:.0%}"])]


def check_k21(ctx: Context, params: dict) -> list[dict]:
    basis = ctx.state.get("intake", {}).get("accounting_basis")
    if basis != params["trigger_basis"]:
        return []
    return [_finding(ctx, "K21", "The owner keeps books on a cash basis. No accrual books exist.")]


COMPUTED: dict[str, Callable[[Context, dict], list[dict]]] = {
    "K01": check_k01, "K03": check_k03, "K04": check_k04, "K05": check_k05, "K07": check_k07,
    "K08": check_k08, "K09": check_k09, "K10": check_k10, "K16": check_k16, "K18": check_k18,
    "K19": check_k19, "K20": check_k20, "K21": check_k21,
}


# ---- model review series -----------------------------------------------------

def _series_k02(ctx: Context, params: dict) -> dict:
    months = ctx.periods.months
    revenue = metrics.pl_by_type(_pl_rows(ctx), months)["revenue"]
    annual = [r for r in _rows(ctx, "subs") if str(r["interval"]).strip().lower() == "year"]
    billings = {r["month"]: r["billings"] for r in metrics.deferred_revenue_rollforward(annual, months)
                if r["billings"] != 0}
    return {"monthly_revenue": revenue, "annual_billings": billings}


def _series_k15(ctx: Context, params: dict) -> dict:
    months = ctx.periods.months
    limit = params["capitalization_threshold"]
    entries = [{"date": r["date"], "account": r["account"], "name": r["name"], "memo": r["memo"],
                "amount": r["debit"] - r["credit"]}
               for r in _rows(ctx, "gl")
               if r["account_type"] == "opex" and r["debit"] - r["credit"] >= limit]
    entries.sort(key=lambda e: (-e["amount"], e["date"]))
    return {"monthly_opex": metrics.pl_by_type(_pl_rows(ctx), months)["opex"],
            "large_entries": entries[:MAX_LARGE_ENTRIES]}


REVIEW_SERIES: dict[str, Callable[[Context, dict], dict]] = {"K02": _series_k02, "K15": _series_k15}


# ---- state, files, and the three entry points --------------------------------

def _uploaded(state: dict, file_id: str) -> bool:
    return state.get("files", {}).get(file_id, {}).get("status") == "uploaded"


def _canonical_path(state: dict, file_id: str, kind: str, canonical_dir: Path) -> Path:
    given = state.get("files", {}).get(file_id, {}).get("canonical_path")
    return Path(given) if given else Path(canonical_dir) / f"{kind}.csv"


def read_canonical(state: dict, canonical_dir: Path, files_catalog: list[dict]) -> dict:
    """Read the canonical CSV of every uploaded active file. A missing file raises.

    Files of one kind (P1 and P2 are both inventory) merge. A path is read once.
    """
    rows: dict[str, list[dict]] = {}
    read_paths: set[Path] = set()
    for record in progress.active_files(state, files_catalog):
        kind = record["canonical_kind"]
        if not kind or not _uploaded(state, record["id"]):
            continue
        path = _canonical_path(state, record["id"], kind, canonical_dir)
        if not path.is_file():
            raise RunChecksError(f"{record['id']} has status uploaded, but {path} does not exist")
        if path not in read_paths:
            read_paths.add(path)
            rows.setdefault(kind, []).extend(canonical.read(kind, path))
    return rows


def should_run(state: dict, check: dict) -> bool:
    intake = state.get("intake", {})
    if check["module"] not in progress.active_modules(intake):
        return False
    if intake.get("accounting_basis") == "cash" and check["id"] in CASH_SKIPPED_CHECKS:
        return False
    needed = [i for i in check["inputs"] if i not in ABSENCE_INPUTS.get(check["id"], ())]
    if not all(_uploaded(state, i) for i in needed):
        return False
    any_of = check["params"].get("any_of")
    return not any_of or any(_uploaded(state, i) for i in any_of)


def _context(state: dict, canonical_dir: Path, data_dir: Path) -> Context:
    rows = read_canonical(state, canonical_dir, _catalog(data_dir, "files.json"))
    return build_context(state, rows, _catalog(data_dir, "checks.json"))


def run(state: dict, canonical_dir: Path, data_dir: Path) -> list[dict]:
    """Run every computed check whose module is active and whose input files are uploaded."""
    ctx = _context(state, canonical_dir, data_dir)
    findings = []
    for check in _catalog(data_dir, "checks.json"):
        if check["method"] != "computed" or not should_run(state, check):
            continue
        for number, found in enumerate(COMPUTED[check["id"]](ctx, check["params"]), start=1):
            findings.append({**found, "id": f"{check['id']}-{number}"})
    return findings


def owner_findings(state: dict, answers: dict[str, str], data_dir: Path) -> list[dict]:
    """One failing finding per owner_question check whose condition the owner's answer confirms.

    answers maps a check id to the owner's statement. The model passes only the answers that
    confirm the condition. Fields come from the catalog; the statement is the evidence.
    """
    if not isinstance(answers, dict):
        raise RunChecksError("owner answers must be a JSON object of check id to statement")
    records = _catalog(data_dir, "checks.json")
    modules = progress.active_modules(state.get("intake", {}))
    by_id = {c["id"]: c for c in records}
    ctx = build_context(state, {}, records)
    out = []
    for check_id, statement in answers.items():
        check = by_id.get(check_id)
        if not check or check["method"] != "owner_question" or check["module"] not in modules:
            raise RunChecksError(f"{check_id} is not an active owner question")
        if not str(statement).strip():
            raise RunChecksError(f"{check_id}: the owner statement is empty")
        out.append(_finding(ctx, check_id, "The owner's answer confirms the condition.",
                            [f"Owner statement, no document: {str(statement).strip()}"]))
    return out


def _threshold(by_year: dict[str, float], year: str) -> float:
    """The threshold for the year; else the nearest earlier year; else the earliest year."""
    if year in by_year:
        return by_year[year]
    earlier = [y for y in by_year if y < year]
    return by_year[max(earlier)] if earlier else by_year[min(by_year)]


def _k11_candidates(state: dict, params: dict) -> list[dict]:
    """Vendors whose payments in a calendar year reach that year's threshold."""
    entry = state.get("files", {}).get("C7", {})
    if entry.get("status") != "uploaded" or not entry.get("canonical_path"):
        return []
    totals: dict[tuple[str, str], float] = {}
    display: dict[tuple[str, str], str] = {}
    for row in canonical.read("vendor", Path(entry["canonical_path"])):
        key = (canonical.name_key(row["vendor"]), row["period"][:4])
        display.setdefault(key, row["vendor"])
        totals[key] = totals.get(key, 0.0) + row["amount"]
    out = []
    for key, total in totals.items():
        limit = _threshold(params["threshold_by_year"], key[1])
        if total >= limit:
            out.append({"vendor": display[key], "year": key[1], "total": total, "threshold": limit})
    return sorted(out, key=lambda c: (c["year"], -c["total"], c["vendor"]))


def questions(state: dict, data_dir: Path) -> list[dict]:
    """One owner question per active owner_question check, in catalog order.

    K11 candidates come from the vendor file named in the state (canonical_path).
    """
    modules = progress.active_modules(state.get("intake", {}))
    out = []
    for check in _catalog(data_dir, "checks.json"):
        if check["method"] != "owner_question" or check["module"] not in modules:
            continue
        candidates = _k11_candidates(state, check["params"]) if check["id"] == "K11" else []
        out.append({"check_id": check["id"], "question": check["owner_question"],
                    "candidates": candidates, "status": "question"})
    return out


def review_items(state: dict, canonical_dir: Path, data_dir: Path) -> list[dict]:
    """One item per model_review check that can run, with the monthly series the model needs."""
    ctx = _context(state, canonical_dir, data_dir)
    out = []
    for check in _catalog(data_dir, "checks.json"):
        if check["method"] != "model_review" or not should_run(state, check):
            continue
        series = REVIEW_SERIES.get(check["id"], lambda c, p: {})(ctx, check["params"])
        out.append({"check_id": check["id"], "name": check["name"], "category": check["category"],
                    "severity": check["severity"], "status": "review", "condition": check["condition"],
                    "owner_message": check["owner_message"], "fix": check["fix"],
                    "params": check["params"], "series": series})
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the QoE readiness spot checks.")
    parser.add_argument("--state", required=True, type=Path, help="progress.json to read and update")
    parser.add_argument("--canonical", required=True, type=Path, help="folder of canonical CSVs")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="folder of catalog JSON")
    parser.add_argument("--answers", type=Path,
                        help="JSON file of owner statements by owner-question check id; "
                             "replaces the owner-question findings in the state")
    args = parser.parse_args(argv)
    try:
        state = progress.load(args.state)
        findings = run(state, args.canonical, args.data)
        replaced = ["computed"]
        if args.answers:
            with open(args.answers, encoding="utf-8") as handle:
                findings += owner_findings(state, json.load(handle), args.data)
            replaced.append("owner_question")
        kept = [f for f in state["findings"] if f.get("method") not in replaced]
        progress.save({**state, "findings": kept + findings}, args.state)
    except (RunChecksError, canonical.CanonicalError, ValueError, OSError) as err:
        print(f"run_checks: {err}", file=sys.stderr)
        return 1
    print(json.dumps(findings, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
