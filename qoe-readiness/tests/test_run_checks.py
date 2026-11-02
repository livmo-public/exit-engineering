"""Tests for run_checks.py. Each expected value has its hand calculation in a comment.

Window used by most unit tests: latest closed month 2026-03, December year end.
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest

import canonical
import progress
import run_checks
from helpers import month_range

LATEST = "2026-03"
BASE_INTAKE = {"business_type": "saas", "accounting_basis": "accrual",
               "fiscal_year_end_month": 12, "latest_closed_month": LATEST}


@pytest.fixture
def checks(data_dir):
    return json.loads((data_dir / "checks.json").read_text(encoding="utf-8"))


def params_of(checks, check_id):
    return next(c for c in checks if c["id"] == check_id)["params"]


# ---- row builders ------------------------------------------------------------

def pl_row(period, amount, account="Sales", kind="revenue", basis="accrual"):
    return {"period": period, "account": account, "account_type": kind, "amount": amount, "basis": basis}


def bs_row(period, balance, account="Cash", subtype="cash"):
    return {"period": period, "account": account,
            "account_type": "liability" if subtype in ("ap", "deferred_revenue") else "asset",
            "subtype": subtype, "balance": balance}


def bank_row(month, ending, deposits=0.0, account="Checking"):
    return {"account": account, "month": month, "beginning_balance": 0.0, "deposits": deposits,
            "withdrawals": 0.0, "ending_balance": ending}


def sale(period, customer, amount):
    return {"period": period, "customer": customer, "amount": amount}


def sub(customer, interval="month", amount=100.0, start="2025-01-01", end=""):
    return {"customer": customer, "plan": "Basic", "interval": interval, "start_date": start,
            "end_date": end, "amount": amount, "currency": "USD"}


def aging_row(kind, due, amount=500.0, name="Buyer"):
    return {"type": kind, "name": name, "invoice_date": due, "due_date": due, "amount": amount}


@pytest.fixture
def ctx_factory():
    def factory(*, intake=None, files=None, bank_end=None, bs_cash=None, annual_subs=None,
                deferred_account=None, **canon):
        canon = dict(canon)
        if bank_end is not None:
            canon["bank"] = [bank_row(LATEST, bank_end)]
        if bs_cash is not None:
            canon["bs"] = canon.get("bs", []) + [bs_row(LATEST, bs_cash)]
        if annual_subs is not None:
            canon["subs"] = [sub("Acme", "year" if annual_subs else "month", 1200.0, "2025-06-01")]
            canon["bs"] = canon.get("bs", []) + [bs_row(LATEST, 10.0)]
        if deferred_account:
            canon["bs"] = canon["bs"] + [bs_row(LATEST, 0.0, "Deferred Revenue", "deferred_revenue")]
        state = {**progress.new_state(), "intake": {**BASE_INTAKE, **(intake or {})},
                 "files": files or {}}
        return run_checks.build_context(state, canon)
    return factory


# ---- registry ----------------------------------------------------------------

def test_registry_matches_catalog(checks):
    assert set(run_checks.COMPUTED) == {c["id"] for c in checks if c["method"] == "computed"}


def test_finding_has_catalog_fields(ctx_factory):
    f = run_checks.COMPUTED["K21"](ctx_factory(intake={"accounting_basis": "cash"}), {"trigger_basis": "cash"})[0]
    assert set(f) == {"id", "check_id", "name", "category", "severity", "method", "status", "detail",
                      "owner_message", "fix", "evidence"}
    assert (f["check_id"], f["status"], f["method"]) == ("K21", "fail", "computed")


# ---- K01 ---------------------------------------------------------------------

def test_k01_annual_billing_no_deferred(ctx_factory):
    f = run_checks.COMPUTED["K01"](ctx_factory(annual_subs=True, deferred_account=False), {})
    assert f and f[0]["severity"] == "critical"


def test_k01_passes_with_deferred_account(ctx_factory):
    assert not run_checks.COMPUTED["K01"](ctx_factory(annual_subs=True, deferred_account=True), {})


def test_k01_passes_with_monthly_billing_only(ctx_factory):
    assert not run_checks.COMPUTED["K01"](ctx_factory(annual_subs=False, deferred_account=False), {})


def test_k01_sales_only_pattern_of_yearly_payments(ctx_factory):
    # Customer pays in 2025-04 and 2026-03 only: gap 11 months is under 12, so not annual.
    # Customer pays in 2024-12 and 2025-12: gap 12 months, so annual.
    params = {"min_interval_months": 12}
    bs = [bs_row(LATEST, 10.0)]
    annual = ctx_factory(bs=bs, sales=[sale("2024-12", "Acme", 1200.0), sale("2025-12", "Acme", 1200.0)])
    assert run_checks.COMPUTED["K01"](annual, params)
    near = ctx_factory(bs=bs, sales=[sale("2025-04", "Acme", 1200.0), sale("2026-03", "Acme", 1200.0)])
    assert not run_checks.COMPUTED["K01"](near, params)


# ---- K03 ---------------------------------------------------------------------

def deferred_ctx(ctx_factory, balances):
    # Annual plan 1200 from 2026-01: billed 1200 in Jan, recognized 100 a month.
    # Closing: Jan 1100, Feb 1000, Mar 900.
    bs = [bs_row(m, b, "Deferred Revenue", "deferred_revenue") for m, b in balances.items()]
    return ctx_factory(bs=bs, subs=[sub("Acme", "year", 1200.0, "2026-01-15")])


def test_k03_passes_when_schedule_ties(ctx_factory):
    ctx = deferred_ctx(ctx_factory, {"2026-01": 1100.0, "2026-02": 1000.0, "2026-03": 930.0})
    assert not run_checks.COMPUTED["K03"](ctx, {"pct": 0.05})  # March gap 30 / 900 = 3.3%


def test_k03_fails_when_schedule_differs(ctx_factory):
    ctx = deferred_ctx(ctx_factory, {"2026-01": 1100.0, "2026-02": 1000.0, "2026-03": 500.0})
    f = run_checks.COMPUTED["K03"](ctx, {"pct": 0.05})  # March gap 400 / 900 = 44%
    assert f and f[0]["severity"] == "high" and any("2026-03" in e for e in f[0]["evidence"])


def test_k03_zero_schedule_never_fails(ctx_factory):
    ctx = ctx_factory(bs=[bs_row(LATEST, 50.0, "Deferred Revenue", "deferred_revenue")],
                      subs=[sub("Acme", "month")])
    assert not run_checks.COMPUTED["K03"](ctx, {"pct": 0.05})  # ratio is None


# ---- K04 ---------------------------------------------------------------------

def test_k04_cash_tie_tolerance(ctx_factory):
    assert not run_checks.COMPUTED["K04"](ctx_factory(bank_end=1000, bs_cash=1099), {"cash_tolerance": 100})
    assert run_checks.COMPUTED["K04"](ctx_factory(bank_end=1000, bs_cash=1101), {"cash_tolerance": 100})


def test_k04_exactly_at_tolerance_passes(ctx_factory):
    assert not run_checks.COMPUTED["K04"](ctx_factory(bank_end=1000, bs_cash=1100), {"cash_tolerance": 100})


def test_k04_missing_side_is_not_a_failure(ctx_factory):
    bank = [bank_row("2026-02", 1000.0), bank_row("2026-03", 1000.0)]
    bs = [bs_row("2026-03", 5000.0)]  # no balance sheet cash row for 2026-02
    assert not run_checks.COMPUTED["K04"](ctx_factory(bank=bank[:1], bs=bs), {"cash_tolerance": 100})
    ctx = ctx_factory(bank=bank, bs=bs)
    assert run_checks.COMPUTED["K04"](ctx, {"cash_tolerance": 100})  # 2026-03 fails; 2026-02 not compared


def test_k04_month_with_missing_bank_account_is_not_compared(ctx_factory):
    # Two bank accounts in 2026-02, one in 2026-03: the March total is partial, so it is skipped.
    bank = [bank_row("2026-02", 600.0), bank_row("2026-02", 400.0, account="Savings"),
            bank_row("2026-03", 600.0)]
    bs = [bs_row("2026-02", 1000.0), bs_row("2026-03", 1000.0)]
    assert not run_checks.COMPUTED["K04"](ctx_factory(bank=bank, bs=bs), {"cash_tolerance": 100})


# ---- K05 ---------------------------------------------------------------------

def deposits_ctx(ctx_factory, deposits):
    return ctx_factory(pl=[pl_row(LATEST, 1000.0)], bank=[bank_row(LATEST, 0.0, deposits)])


def test_k05_deposits_within_tolerance(ctx_factory):
    assert not run_checks.COMPUTED["K05"](deposits_ctx(ctx_factory, 1049.0), {"pct": 0.05})


def test_k05_deposits_outside_tolerance(ctx_factory):
    f = run_checks.COMPUTED["K05"](deposits_ctx(ctx_factory, 1100.0), {"pct": 0.05})  # 100 / 1000 = 10%
    assert f and f[0]["severity"] == "high"


def test_k05_month_without_bank_row_is_skipped(ctx_factory):
    ctx = ctx_factory(pl=[pl_row("2026-02", 1000.0), pl_row(LATEST, 1000.0)], bank=[bank_row(LATEST, 0.0, 1000.0)])
    assert not run_checks.COMPUTED["K05"](ctx, {"pct": 0.05})


def test_k05_zero_revenue_ratio_never_fails(ctx_factory):
    ctx = ctx_factory(pl=[pl_row(LATEST, 0.0)], bank=[bank_row(LATEST, 0.0, 400.0)])
    assert not run_checks.COMPUTED["K05"](ctx, {"pct": 0.05})


# ---- K07 ---------------------------------------------------------------------

def tie_ctx(ctx_factory, cash_revenue, ar_now=200.0):
    # Accrual 1000, cash X. Accrual minus cash must equal change in AR (200 - 100 = 100) minus change in deferred (0).
    return ctx_factory(
        pl=[pl_row(LATEST, 1000.0, basis="accrual"), pl_row(LATEST, cash_revenue, basis="cash")],
        bs=[bs_row("2026-02", 100.0, "AR", "ar"), bs_row(LATEST, ar_now, "AR", "ar")])


def test_k07_bases_tie(ctx_factory):
    assert not run_checks.COMPUTED["K07"](tie_ctx(ctx_factory, 900.0), {"pct": 0.05})


def test_k07_bases_do_not_tie(ctx_factory):
    f = run_checks.COMPUTED["K07"](tie_ctx(ctx_factory, 700.0), {"pct": 0.05})  # 300 vs 100: 200 > 50
    assert f and f[0]["severity"] == "high"


def test_k07_needs_both_bases(ctx_factory):
    ctx = ctx_factory(pl=[pl_row(LATEST, 1000.0)], bs=[bs_row("2026-02", 100.0, "AR", "ar"),
                                                     bs_row(LATEST, 900.0, "AR", "ar")])
    assert not run_checks.COMPUTED["K07"](ctx, {"pct": 0.05})


# ---- K08 ---------------------------------------------------------------------

def test_k08_suspense_balance_fails(ctx_factory):
    ctx = ctx_factory(bs=[bs_row(LATEST, 250.0, "Uncategorized Asset", "other_asset")], gl=[])
    f = run_checks.COMPUTED["K08"](ctx, {"name_patterns": ["suspense", "uncategorized"], "min_abs_balance": 1})
    assert f and "Uncategorized Asset" in " ".join(f[0]["evidence"])


def test_k08_clean_books_pass(ctx_factory):
    ctx = ctx_factory(bs=[bs_row(LATEST, 0.0, "Uncategorized Asset", "other_asset"), bs_row(LATEST, 50.0)], gl=[])
    assert not run_checks.COMPUTED["K08"](ctx, {"name_patterns": ["uncategorized"], "min_abs_balance": 1})


def test_k08_ledger_balance_on_suspense_account_fails(ctx_factory):
    gl = [{"date": "2026-02-10", "txn_id": "1", "account": "Ask My Accountant", "account_type": "opex",
           "name": "", "memo": "", "debit": 75.0, "credit": 0.0}]
    ctx = ctx_factory(bs=[bs_row(LATEST, 50.0)], gl=gl)
    assert run_checks.COMPUTED["K08"](ctx, {"name_patterns": ["ask my accountant"], "min_abs_balance": 1})


# ---- K09 ---------------------------------------------------------------------

def test_k09_negative_ar_fails(ctx_factory):
    ctx = ctx_factory(bs=[bs_row(LATEST, -40.0, "AR", "ar"), bs_row(LATEST, 10.0, "Stock", "inventory")])
    f = run_checks.COMPUTED["K09"](ctx, {"subtypes": ["ar", "ap", "inventory"]})
    assert f and f[0]["severity"] == "medium"


def test_k09_positive_balances_pass(ctx_factory):
    ctx = ctx_factory(bs=[bs_row(LATEST, 40.0, "AR", "ar"), bs_row(LATEST, -9.0, "Cash")])
    assert not run_checks.COMPUTED["K09"](ctx, {"subtypes": ["ar", "ap", "inventory"]})


# ---- K10 ---------------------------------------------------------------------

def tax_ctx(ctx_factory, gross, year="2025"):
    # Books: 12 months of 1000 in 2025 = 12000.
    pl = [pl_row(m, 1000.0) for m in month_range("2025-01", "2025-12")]
    return ctx_factory(pl=pl, tax=[{"year": year, "gross_receipts": gross}])


def test_k10_tax_matches_books(ctx_factory):
    assert not run_checks.COMPUTED["K10"](tax_ctx(ctx_factory, 12400.0), {"pct": 0.05})  # 400 / 12000 = 3.3%


def test_k10_tax_differs_from_books(ctx_factory):
    f = run_checks.COMPUTED["K10"](tax_ctx(ctx_factory, 9000.0), {"pct": 0.05})  # 3000 / 12000 = 25%
    assert f and f[0]["severity"] == "high" and "2025" in f[0]["evidence"][0]


def test_k10_year_without_complete_books_is_skipped(ctx_factory):
    assert not run_checks.COMPUTED["K10"](tax_ctx(ctx_factory, 1.0, year="2023"), {"pct": 0.05})


# ---- K16 ---------------------------------------------------------------------

def cap_ctx(ctx_factory, balance, s5_status):
    files = {"S5": {"status": s5_status}} if s5_status else {}
    return ctx_factory(files=files, bs=[bs_row(LATEST, balance, "Software Dev", "capitalized_software")])


def test_k16_capitalized_software_without_policy_fails(ctx_factory):
    for status in (None, "missing"):
        assert run_checks.COMPUTED["K16"](cap_ctx(ctx_factory, 5000.0, status), {"subtype": "capitalized_software"})


def test_k16_policy_uploaded_passes(ctx_factory):
    assert not run_checks.COMPUTED["K16"](cap_ctx(ctx_factory, 5000.0, "uploaded"), {"subtype": "capitalized_software"})


def test_k16_zero_balance_passes(ctx_factory):
    assert not run_checks.COMPUTED["K16"](cap_ctx(ctx_factory, 0.0, "missing"), {"subtype": "capitalized_software"})


# ---- K18 ---------------------------------------------------------------------

def test_k18_old_receivable_fails(ctx_factory):
    # As of 2026-03-31, due 2025-11-01 is 150 days past due.
    f = run_checks.COMPUTED["K18"](ctx_factory(aging=[aging_row("AR", "2025-11-01")]), {"days": 90})
    assert f and "note" in f[0]["owner_message"].lower()


def test_k18_recent_receivable_and_old_payable_pass(ctx_factory):
    aging = [aging_row("AR", "2026-03-15"), aging_row("AP", "2025-01-01")]
    assert not run_checks.COMPUTED["K18"](ctx_factory(aging=aging), {"days": 90})


def test_k18_exactly_90_days_passes(ctx_factory):
    # 2026-03-31 minus 90 days = 2025-12-31.
    assert not run_checks.COMPUTED["K18"](ctx_factory(aging=[aging_row("AR", "2025-12-31")]), {"days": 90})
    assert run_checks.COMPUTED["K18"](ctx_factory(aging=[aging_row("AR", "2025-12-30")]), {"days": 90})


# ---- K19 ---------------------------------------------------------------------

PARAMS_K19 = {"top1_pct": 0.20, "top5_pct": 0.50}


def test_k19_top_customer_over_limit(ctx_factory):
    sales = [sale("2026-01", "A", 300.0), sale("2026-01", "B", 100.0), sale("2026-01", "C", 100.0),
             sale("2026-01", "D", 100.0), sale("2026-01", "E", 100.0), sale("2026-01", "F", 100.0),
             sale("2026-01", "G", 100.0), sale("2026-01", "H", 100.0)]  # A is 300 / 1000 = 30%
    f = run_checks.COMPUTED["K19"](ctx_factory(sales=sales), PARAMS_K19)
    assert f and f[0]["severity"] == "high"


def test_k19_spread_customers_pass(ctx_factory):
    sales = [sale("2026-01", f"C{i}", 100.0) for i in range(10)]  # top 1 = 10%, top 5 = 50% (not over)
    assert not run_checks.COMPUTED["K19"](ctx_factory(sales=sales), PARAMS_K19)


def test_k19_top_five_over_limit(ctx_factory):
    sales = [sale("2026-01", f"C{i}", 110.0) for i in range(5)] + [sale("2026-01", f"D{i}", 90.0) for i in range(5)]
    f = run_checks.COMPUTED["K19"](ctx_factory(sales=sales), PARAMS_K19)  # top 5 = 550 / 1000 = 55%
    assert f and any("top 5" in e.lower() for e in f[0]["evidence"])


# ---- K20 ---------------------------------------------------------------------

def grr_ctx(ctx_factory, ended):
    # Four customers at 100 a month from 2025-01. Window start 2025-03, end 2026-03.
    subs = [sub(f"C{i}", end="2025-12-01" if i < ended else "") for i in range(4)]
    return ctx_factory(subs=subs)


def test_k20_low_retention_fails(ctx_factory):
    f = run_checks.COMPUTED["K20"](grr_ctx(ctx_factory, 2), {"grr_min": 0.70})  # 2 of 4 kept: 50%
    assert f and f[0]["severity"] == "high"


def test_k20_good_retention_passes(ctx_factory):
    assert not run_checks.COMPUTED["K20"](grr_ctx(ctx_factory, 1), {"grr_min": 0.70})  # 75%


def test_k20_no_starting_arr_never_fails(ctx_factory):
    ctx = ctx_factory(subs=[sub("C1", start="2025-10-01")])  # nobody active in 2025-03: ratio is None
    assert not run_checks.COMPUTED["K20"](ctx, {"grr_min": 0.70})


# ---- K21 ---------------------------------------------------------------------

def test_k21_cash_basis_fails(ctx_factory):
    assert run_checks.COMPUTED["K21"](ctx_factory(intake={"accounting_basis": "cash"}), {"trigger_basis": "cash"})


def test_k21_accrual_and_both_pass(ctx_factory):
    for basis in ("accrual", "both"):
        assert not run_checks.COMPUTED["K21"](ctx_factory(intake={"accounting_basis": basis}),
                                              {"trigger_basis": "cash"})


# ---- run(), questions(), review_items() --------------------------------------

WORLD_MONTHS = month_range("2025-01", LATEST)


def write_world(tmp_path, *, basis="accrual", business_type="saas", skip=(), with_paths=False,
                vendor_total=0.0, vendor_period="2026-01"):
    """Write canonical CSVs and return a state. Accrual world: K01 and K07 would fail."""
    out = tmp_path / "canonical"
    out.mkdir(exist_ok=True)
    pl = [pl_row(m, 1000.0, basis="accrual") for m in WORLD_MONTHS]
    pl += [pl_row(m, 700.0, basis="cash") for m in WORLD_MONTHS]
    bs = [bs_row(m, 500.0) for m in WORLD_MONTHS] + [bs_row(m, 100.0, "AR", "ar") for m in WORLD_MONTHS]
    data = {
        "pl": pl, "bs": bs,
        "gl": [{"date": "2026-01-05", "txn_id": "1", "account": "Cash", "account_type": "asset", "name": "Buyer",
                "memo": "Deposit", "debit": 10.0, "credit": 0.0}],
        "bank": [bank_row(m, 500.0, 1000.0) for m in WORLD_MONTHS],
        "sales": [sale(m, f"C{i}", 100.0) for m in WORLD_MONTHS for i in range(10)],
        "vendor": [{"period": vendor_period, "vendor": "Printer Co", "account": "Supplies", "amount": vendor_total}],
        "aging": [aging_row("AR", "2026-03-20")],
        "tax": [{"year": "2025", "gross_receipts": 5000.0}],
        "subs": [sub("Acme", "year", 1200.0, "2025-02-01")],
    }
    kinds = {"C1": "pl", "C2": "bs", "C3": "gl", "C4": "bank", "C6": "sales", "C7": "vendor",
             "C8": "aging", "C9": "tax", "S1": "subs"}
    files = {}
    for file_id, kind in kinds.items():
        if file_id in skip:
            continue
        path = out / f"{kind}.csv"
        canonical.write(kind, data[kind], path)
        files[file_id] = {"status": "uploaded", **({"canonical_path": str(path)} if with_paths else {})}
    state = {**progress.new_state(), "files": files,
            "intake": {**BASE_INTAKE, "business_type": business_type, "accounting_basis": basis}}
    return state, out


def ids_of(findings):
    return {f["check_id"] for f in findings}


def test_run_accrual_runs_k01_and_k07(tmp_path, data_dir):
    state, out = write_world(tmp_path)
    assert {"K01", "K07"} <= ids_of(run_checks.run(state, out, data_dir))


def test_cash_basis_runs_k21_not_k07_k01(tmp_path, data_dir):
    state, out = write_world(tmp_path, basis="cash")
    ids = ids_of(run_checks.run(state, out, data_dir))
    assert "K21" in ids and not ids & {"K01", "K07"}


def test_missing_input_skips_check(tmp_path, data_dir):
    state, out = write_world(tmp_path)
    assert "K10" in ids_of(run_checks.run(state, out, data_dir))
    state, out = write_world(tmp_path, skip=("C9",))
    assert "K10" not in ids_of(run_checks.run(state, out, data_dir))


def test_partial_input_skips_check(tmp_path, data_dir):
    state, out = write_world(tmp_path)
    partial = {**state, "files": {**state["files"], "C9": {"status": "partial"}}}
    assert "K10" not in ids_of(run_checks.run(partial, out, data_dir))


def test_inactive_module_skips_saas_checks(tmp_path, data_dir):
    state, out = write_world(tmp_path, business_type="services")
    assert not ids_of(run_checks.run(state, out, data_dir)) & {"K01", "K03", "K16", "K20"}


def test_k01_waits_for_any_of_inputs(tmp_path, data_dir):
    state, out = write_world(tmp_path, skip=("S1", "C6"))
    assert "K01" not in ids_of(run_checks.run(state, out, data_dir))


def test_k16_runs_when_policy_file_is_missing(tmp_path, data_dir):
    state, out = write_world(tmp_path)
    assert "K16" not in ids_of(run_checks.run(state, out, data_dir))  # no capitalized software
    bs = canonical.read("bs", out / "bs.csv") + [bs_row(LATEST, 900.0, "Dev costs", "capitalized_software")]
    canonical.write("bs", bs, out / "bs.csv")
    assert "K16" in ids_of(run_checks.run(state, out, data_dir))
    with_policy = {**state, "files": {**state["files"], "S5": {"status": "uploaded"}}}
    assert "K16" not in ids_of(run_checks.run(with_policy, out, data_dir))


def test_finding_ids_number_per_check(tmp_path, data_dir):
    state, out = write_world(tmp_path)
    findings = run_checks.run(state, out, data_dir)
    assert all(f["id"] == f"{f['check_id']}-1" and f["status"] == "fail" for f in findings)


def test_run_reads_state_path_before_canonical_dir(tmp_path, data_dir):
    state, out = write_world(tmp_path, with_paths=True)
    assert "K10" in ids_of(run_checks.run(state, tmp_path / "elsewhere", data_dir))


def test_uploaded_file_without_canonical_csv_raises(tmp_path, data_dir):
    state, out = write_world(tmp_path)
    (out / "tax.csv").unlink()
    with pytest.raises(run_checks.RunChecksError, match="C9"):
        run_checks.run(state, out, data_dir)


def test_k11_candidates_use_year_threshold(tmp_path, checks, data_dir):
    threshold = params_of(checks, "K11")["threshold_by_year"]["2026"]
    below, out = write_world(tmp_path, with_paths=True, vendor_total=threshold - 500, vendor_period="2026-01")
    assert {q["check_id"]: q for q in run_checks.questions(below, data_dir)}["K11"]["candidates"] == []
    at, out = write_world(tmp_path, with_paths=True, vendor_total=threshold, vendor_period="2026-01")
    candidates = {q["check_id"]: q for q in run_checks.questions(at, data_dir)}["K11"]["candidates"]
    assert [(c["vendor"], c["year"], c["total"]) for c in candidates] == [("Printer Co", "2026", threshold)]


def test_k11_threshold_follows_payment_year(tmp_path, checks, data_dir):
    by_year = params_of(checks, "K11")["threshold_by_year"]
    state, out = write_world(tmp_path, with_paths=True, vendor_total=by_year["2025"], vendor_period="2025-06")
    candidates = {q["check_id"]: q for q in run_checks.questions(state, data_dir)}["K11"]["candidates"]
    assert [c["year"] for c in candidates] == ["2025"]
    state, out = write_world(tmp_path, with_paths=True, vendor_total=by_year["2025"], vendor_period="2026-06")
    if by_year["2026"] > by_year["2025"]:
        assert {q["check_id"]: q for q in run_checks.questions(state, data_dir)}["K11"]["candidates"] == []


def test_questions_one_per_owner_question_check(tmp_path, checks, data_dir):
    state, out = write_world(tmp_path, with_paths=True)
    qs = run_checks.questions(state, data_dir)
    expected = {c["id"] for c in checks if c["method"] == "owner_question" and c["module"] in ("core", "saas")}
    assert [q["check_id"] for q in qs] == [c["id"] for c in checks if c["id"] in expected]
    assert all(q["question"] for q in qs)
    services, out = write_world(tmp_path, business_type="services", with_paths=True)
    assert "K17" not in {q["check_id"] for q in run_checks.questions(services, data_dir)}


def test_k11_without_vendor_file_has_no_candidates(data_dir):
    state = {**progress.new_state(), "intake": BASE_INTAKE}
    assert {q["check_id"]: q for q in run_checks.questions(state, data_dir)}["K11"]["candidates"] == []


def test_review_items_carry_monthly_series(tmp_path, data_dir):
    state, out = write_world(tmp_path)
    items = {i["check_id"]: i for i in run_checks.review_items(state, out, data_dir)}
    assert set(items) == {"K02", "K15"}
    k02 = items["K02"]["series"]
    assert k02["monthly_revenue"]["2025-01"] == 1000.0
    assert k02["annual_billings"]["2025-02"] == 1200.0 and k02["annual_billings"]["2026-02"] == 1200.0
    assert items["K15"]["status"] == "review"


def test_review_items_skip_missing_inputs(tmp_path, data_dir):
    state, out = write_world(tmp_path, skip=("S1",))
    assert {i["check_id"] for i in run_checks.review_items(state, out, data_dir)} == {"K15"}


def test_cli_prints_and_saves_findings(tmp_path, data_dir, scripts_dir):
    state, out = write_world(tmp_path, basis="cash")
    state_path = tmp_path / "progress.json"
    progress.save({**state, "findings": [{"id": "K02-1", "check_id": "K02", "method": "model_review",
                                          "severity": "medium", "status": "review"}]}, state_path)
    done = subprocess.run([sys.executable, str(scripts_dir / "run_checks.py"), "--state", str(state_path),
                           "--canonical", str(out), "--data", str(data_dir)],
                          capture_output=True, text=True, check=True)
    printed = json.loads(done.stdout)
    saved = progress.load(state_path)["findings"]
    assert "K21-1" in {f["id"] for f in printed}
    assert {f["id"] for f in saved} == {f["id"] for f in printed} | {"K02-1"}
    rerun = subprocess.run([sys.executable, str(scripts_dir / "run_checks.py"), "--state", str(state_path),
                            "--canonical", str(out), "--data", str(data_dir)],
                           capture_output=True, text=True, check=True)
    assert len(progress.load(state_path)["findings"]) == len(saved)
    assert json.loads(rerun.stdout) == printed
