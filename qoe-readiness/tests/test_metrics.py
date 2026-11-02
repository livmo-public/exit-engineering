"""Tests for metrics.py. Each expected value has its hand calculation below.

periods
  Data Jul 2024 to Sep 2026, fiscal year ends June (6), latest closed 2026-09.
  FY2025 = Jul 2024..Jun 2025 (12 months). FY2026 = Jul 2025..Jun 2026.
  FY2027 would end Jun 2027, after the data, so it is left out.
  TTM = the 12 months ending Sep 2026 = Oct 2025..Sep 2026.
  Young company: Nov 2024..Dec 2025 (14 months), December year end. FY2025 is
  Jan..Dec 2025 (complete). FY2024 has only Nov and Dec, so it is left out.

ebitda
  revenue 1000 - cogs 200 - opex 300 - depreciation 50 - interest 20 - tax 30
  = net income 400. EBITDA = 400 + interest 20 + tax 30 + depreciation 50 = 500.
  With other income 40 and other expense 15: net income = 400 + 40 - 15 = 425,
  EBITDA = 525 (other income and other expense stay in EBITDA).

adjusted_ebitda
  EBITDA 500. Approved 100 and edited 25 are added; rejected 50 and unanswered 70
  are not. 500 + 100 = 600; 500 + 100 + 25 = 625.
  Amounts keyed by month roll up to a fiscal year label: Jan 10 + Feb 20 = 30.
  The P&L fixture holds Jan only, so Jan..Feb EBITDA = 500 and adjusted = 500 + 30 = 530.
  The Mar amount (99) is outside the months and is not counted.

proof_of_cash (cash account "Checking")
  Jan: GL debits 700 and 300 = in 1000; credits 400 = out 400.
  Bank deposits 1000, withdrawals 400, ending 600. Balance sheet cash 590.
  cash_diff = bank ending - balance sheet cash = 600 - 590 = 10.
  A non-cash GL line (account "Sales") does not count.

proof_of_revenue
  Jan: P&L revenue 1000, sales 950, bank deposits 1100.
  pl_vs_sales_pct = |1000 - 950| / 1000 = 0.05. pl_vs_bank_pct = |1000 - 1100| / 1000 = 0.1.
  Zero P&L revenue with a zero other side = 0.0; with a nonzero other side = None.

concentration
  A 30, B 20, C 50 -> total 100. Top 1 = 50 -> 0.5. Top 5 = all = 1.0. Count 3.
  Eight customers of 10 plus one of 120 -> total 200; top 5 = 120 + 4*10 = 160 -> 0.8.
  "Acme Inc" 40 and "ACME INC " 60 are one customer: 100.

arr_waterfall (monthly plan amount x 12 = ARR; annual plan amount / 12 x 12 = amount)
  A base 100 a month from Jan: Jan new 1200, closing 1200.
  B 50 a month from 10 Feb: Feb new 600, closing 1800.
  A add-on 50 from 1 Mar: A goes 1200 -> 1800, Mar expansion 600, closing 2400.
  A base ends 1 Apr (not active in Apr): A goes 1800 -> 600, contraction -1200.
  B ends 1 Apr: churn -600. Apr closing = 2400 - 1200 - 600 = 600.
  Contraction and churn are negative, so opening + new + expansion + contraction
  + churn = closing.

retention
  Start Jan: A 100 -> 1200, B 100 -> 1200, total 2400 (C starts in May and is ignored).
  End Dec: A 150 -> 1800, B gone -> 0. NRR = 1800 / 2400 = 0.75.
  GRR = (min(1800, 1200) + min(0, 1200)) / 2400 = 1200 / 2400 = 0.5.

opex_by_vendor
  Jan: V1 100 + V2 50 = 150. Feb: V1 100 + V3 25 = 125. Mar is outside the window.
  V1 = 200, V2 = 50, V3 = 25. "v1 " matches "V1"; the first spelling is kept.

nwc_trend
  Jan AR 500, inventory 100 + WIP 20 = 120; AP 200, accrued 50, deferred revenue 70.
  NWC = 500 + 120 - 200 - 50 - 70 = 300. Feb has AR 400 only, so NWC = 400.
  Peg = average over the TTM months present = (300 + 400) / 2 = 350.

deferred_revenue_rollforward
  Annual plan 1200 from 2025-01-01: billed Jan 1200, recognized 1200 / 12 = 100 a month.
  Jan opening 0, closing 1200 - 100 = 1100. Feb opening 1100, closing 1000. Mar closing 900.
  Window Mar..Apr opens at the Feb closing, 1000; Apr closing = 1000 - 200 = 800.
  Jan 2025 bill is recognized in full by Dec 2025 (12 x 100), so Dec 2025 closes at 0.
  Jan 2026 anniversary bills 1200 again: opening 0, recognized 100, closing 1100.
  A plan that ends 15 Dec 2025 is not active in Jan 2026, so it does not rebill.
  Monthly plan 50: billed 50 and recognized 50 each active month, closing 0.
"""
import pytest

import metrics
from helpers import month_range

JAN = ["2025-01"]


def pl(values, month="2025-01"):
    return [{"period": month, "account": t, "account_type": t, "amount": float(v), "basis": "accrual"}
            for t, v in values.items()]


def adj(aid, amounts, decision):
    return {"id": aid, "name": aid, "source_file": "C1", "amounts": amounts,
            "evidence": "", "decision": decision, "owner_stated": True}


def sub(customer, amount, start, end="", interval="month", plan="p"):
    return {"customer": customer, "plan": plan, "interval": interval, "start_date": start,
            "end_date": end, "amount": float(amount), "currency": "USD"}


PL_500 = pl({"revenue": 1000, "cogs": 200, "opex": 300, "depreciation": 50, "interest": 20,
             "income_tax": 30})


# periods
def test_periods_non_calendar_fiscal_year():
    p = metrics.periods(month_range("2024-07", "2026-09"), 6, "2026-09")
    assert list(p.fiscal_years) == ["FY2025", "FY2026"]
    assert p.fiscal_years["FY2025"][0] == "2024-07" and p.ttm == month_range("2025-10", "2026-09")
    assert p.fiscal_years["FY2025"] == month_range("2024-07", "2025-06")
    assert p.fiscal_years["FY2026"] == month_range("2025-07", "2026-06")
    assert p.months == month_range("2024-07", "2026-09")


def test_periods_young_company_has_ttm_and_one_fiscal_year():
    p = metrics.periods(month_range("2024-11", "2025-12"), 12, "2025-12")
    assert list(p.fiscal_years) == ["FY2025"]
    assert p.ttm == month_range("2025-01", "2025-12")


def test_periods_calendar_year_and_unsorted_input():
    months = month_range("2024-01", "2025-06")
    p = metrics.periods(list(reversed(months)), 12, "2025-06")
    assert list(p.fiscal_years) == ["FY2024"] and p.ttm == month_range("2024-07", "2025-06")


def test_periods_short_history_ttm_holds_available_months_only():
    p = metrics.periods(month_range("2025-04", "2025-09"), 12, "2025-09")
    assert p.ttm == month_range("2025-04", "2025-09") and p.fiscal_years == {}


def test_periods_ignores_months_after_latest_closed():
    p = metrics.periods(month_range("2024-01", "2025-03"), 12, "2024-12")
    assert p.months == month_range("2024-01", "2024-12") and list(p.fiscal_years) == ["FY2024"]


def test_periods_rejects_bad_fiscal_year_end_month():
    with pytest.raises(ValueError, match="fiscal_year_end_month"):
        metrics.periods(["2025-01"], 13, "2025-01")


# P&L
def test_pl_by_type_sums_months_and_skips_others():
    rows = pl({"revenue": 10}) + pl({"revenue": 5}, "2025-02") + pl({"revenue": 99}, "2025-03")
    out = metrics.pl_by_type(rows, ["2025-01", "2025-02"])
    assert out["revenue"] == {"2025-01": 10.0, "2025-02": 5.0}
    assert out["cogs"] == {"2025-01": 0.0, "2025-02": 0.0}


def test_pl_by_type_rejects_unmapped_type():
    rows = [{"period": "2025-01", "account": "X", "account_type": "", "amount": 1.0, "basis": ""}]
    with pytest.raises(ValueError, match="'X'"):
        metrics.pl_by_type(rows, JAN)


def test_ebitda_formula():
    e = metrics.ebitda(PL_500, JAN)
    assert e["net_income"] == 400 and e["ebitda"] == 500
    assert e["revenue"] == 1000 and e["interest"] == 20 and e["income_tax"] == 30
    assert e["depreciation"] == 50 and e["amortization"] == 0


def test_ebitda_keeps_other_income_and_expense():
    e = metrics.ebitda(PL_500 + pl({"other_income": 40, "other_expense": 15}), JAN)
    assert e["net_income"] == 425 and e["ebitda"] == 525


def test_adjusted_ebitda_ignores_rejected_and_unanswered():
    adjs = [adj("A1", {"2025-01": 100}, "approved"), adj("A2", {"2025-01": 50}, "rejected"),
            adj("A3", {"2025-01": 70}, None)]
    assert metrics.adjusted_ebitda(PL_500, adjs, JAN, "2025-01") == 600


def test_adjusted_ebitda_counts_edited_and_null_amounts():
    adjs = [adj("A1", {"2025-01": 100}, "approved"), adj("A2", {"2025-01": 25}, "edited"),
            adj("A3", None, "approved")]
    assert metrics.adjusted_ebitda(PL_500, adjs, JAN, "2025-01") == 625


def test_adjusted_ebitda_rolls_month_amounts_into_year_label():
    adjs = [adj("A1", {"2025-01": 10, "2025-02": 20, "2025-03": 99}, "approved")]
    assert metrics.adjusted_ebitda(PL_500, adjs, ["2025-01", "2025-02"], "FY2025") == 530


def test_adjusted_ebitda_does_not_change_inputs():
    adjs = [adj("A1", {"2025-01": 100}, "approved")]
    snapshot = repr(adjs) + repr(PL_500)
    metrics.adjusted_ebitda(PL_500, adjs, JAN, "2025-01")
    assert repr(adjs) + repr(PL_500) == snapshot


# proof of cash and revenue
def test_proof_of_cash():
    bs = [{"period": "2025-01", "account": "Checking", "account_type": "asset", "subtype": "cash",
           "balance": 590.0},
          {"period": "2025-01", "account": "AR", "account_type": "asset", "subtype": "ar",
           "balance": 999.0}]
    gl = [{"date": "2025-01-05", "txn_id": "1", "account": "Checking", "account_type": "asset",
           "name": "", "memo": "", "debit": 700.0, "credit": 0.0},
          {"date": "2025-01-20", "txn_id": "2", "account": "Checking", "account_type": "asset",
           "name": "", "memo": "", "debit": 300.0, "credit": 0.0},
          {"date": "2025-01-21", "txn_id": "3", "account": "Checking", "account_type": "asset",
           "name": "", "memo": "", "debit": 0.0, "credit": 400.0},
          {"date": "2025-01-22", "txn_id": "4", "account": "Sales", "account_type": "revenue",
           "name": "", "memo": "", "debit": 0.0, "credit": 5000.0}]
    bank = [{"account": "Checking", "month": "2025-01", "beginning_balance": 0.0,
             "deposits": 1000.0, "withdrawals": 400.0, "ending_balance": 600.0}]
    assert metrics.proof_of_cash(gl, bank, bs) == [
        {"month": "2025-01", "gl_cash_in": 1000.0, "bank_deposits": 1000.0, "gl_cash_out": 400.0,
         "bank_withdrawals": 400.0, "bank_ending": 600.0, "bs_cash": 590.0, "cash_diff": 10.0}]


def test_proof_of_revenue():
    sales = [{"period": "2025-01", "customer": "A", "amount": 950.0}]
    bank = [{"account": "B", "month": "2025-01", "beginning_balance": 0.0, "deposits": 1100.0,
             "withdrawals": 0.0, "ending_balance": 0.0}]
    out = metrics.proof_of_revenue(pl({"revenue": 1000}), sales, bank)
    assert out == [{"month": "2025-01", "pl_revenue": 1000.0, "sales_total": 950.0,
                    "bank_deposits": 1100.0, "pl_vs_sales_pct": pytest.approx(0.05),
                    "pl_vs_bank_pct": pytest.approx(0.1)}]


def test_proof_of_revenue_zero_pl_revenue():
    sales = [{"period": "2025-01", "customer": "A", "amount": 10.0},
             {"period": "2025-02", "customer": "A", "amount": 0.0}]
    out = metrics.proof_of_revenue(pl({"revenue": 0}, "2025-02"), sales, [])
    assert out[0]["pl_vs_sales_pct"] is None
    assert out[1]["pl_vs_sales_pct"] == 0.0


# concentration
def sales(values, month="2025-01"):
    return [{"period": month, "customer": c, "amount": float(v)} for c, v in values.items()]


def test_concentration():
    c = metrics.concentration(sales({"A": 30, "B": 20, "C": 50}), JAN)
    assert c["top1_pct"] == 0.5 and c["customer_count"] == 3 and c["top5_pct"] == 1.0
    assert c["top10"] == [("C", 50.0), ("A", 30.0), ("B", 20.0)]


def test_concentration_top5_share():
    values = {f"S{i}": 10 for i in range(8)} | {"Big": 120}
    c = metrics.concentration(sales(values), JAN)
    assert c["top5_pct"] == pytest.approx(0.8) and c["customer_count"] == 9


def test_concentration_merges_name_forms_and_keeps_first():
    rows = sales({"Acme Inc": 40, "Other": 10}) + sales({"ACME INC ": 60}, "2025-02")
    c = metrics.concentration(rows, ["2025-01", "2025-02"])
    assert c["top10"][0] == ("Acme Inc", 100.0) and c["customer_count"] == 2


def test_concentration_empty_is_zero():
    c = metrics.concentration([], JAN)
    assert c == {"top1_pct": 0.0, "top5_pct": 0.0, "top10": [], "customer_count": 0}


# ARR waterfall and retention
def test_arr_waterfall_new_expansion_contraction_churn():
    subs = [sub("A", 100, "2025-01-01", "2025-04-01", plan="base"),
            sub("A", 50, "2025-03-01", plan="addon"),
            sub("B", 50, "2025-02-10", "2025-04-01")]
    wf = metrics.arr_waterfall(subs, month_range("2025-01", "2025-04"))
    rows = {r["month"]: r for r in wf}
    assert rows["2025-01"] == {"month": "2025-01", "opening_arr": 0.0, "new": 1200.0,
                               "expansion": 0.0, "contraction": 0.0, "churn": 0.0,
                               "closing_arr": 1200.0}
    assert rows["2025-02"]["new"] == 600.0 and rows["2025-02"]["closing_arr"] == 1800.0
    assert rows["2025-03"]["expansion"] == 600.0 and rows["2025-03"]["closing_arr"] == 2400.0
    assert rows["2025-04"]["contraction"] == -1200.0 and rows["2025-04"]["churn"] == -600.0
    assert rows["2025-04"]["closing_arr"] == 600.0


def test_arr_waterfall_columns_sum_to_closing():
    subs = [sub("A", 100, "2025-01-01", "2025-03-01"), sub("B", 10, "2025-02-01")]
    for r in metrics.arr_waterfall(subs, month_range("2025-01", "2025-05")):
        total = r["opening_arr"] + r["new"] + r["expansion"] + r["contraction"] + r["churn"]
        assert total == pytest.approx(r["closing_arr"])


def test_arr_waterfall_opening_uses_month_before_window():
    wf = metrics.arr_waterfall([sub("A", 100, "2024-06-01")], ["2025-01"])
    assert wf[0]["opening_arr"] == 1200.0 and wf[0]["new"] == 0.0


def test_arr_waterfall_annual_plan_is_amount_over_twelve_times_twelve():
    wf = metrics.arr_waterfall([sub("A", 1200, "2025-01-01", interval="year")], JAN)
    assert wf[0]["closing_arr"] == 1200.0


def test_arr_waterfall_matches_customers_across_name_forms():
    subs = [sub("Acme Inc", 100, "2025-01-01"), sub("ACME INC ", 50, "2025-02-01")]
    wf = metrics.arr_waterfall(subs, ["2025-01", "2025-02"])
    assert wf[1]["new"] == 0.0 and wf[1]["expansion"] == 600.0


def test_arr_waterfall_rejects_unknown_interval():
    with pytest.raises(ValueError, match="Acme.*quarter"):
        metrics.arr_waterfall([sub("Acme", 100, "2025-01-01", interval="quarter")], JAN)


def subs_two_customers_one_expands_one_churns():
    return [sub("A", 100, "2025-01-01", "2025-06-01"), sub("A", 150, "2025-06-01"),
            sub("B", 100, "2025-01-01", "2025-07-01"), sub("C", 100, "2025-05-01")]


def test_retention_caps_expansion_for_grr():
    r = metrics.retention(subs_two_customers_one_expands_one_churns(), "2025-01", "2025-12")
    assert r["grr"] == 0.5 and r["nrr"] == 0.75


def test_retention_none_when_no_starting_arr():
    assert metrics.retention([], "2025-01", "2025-12") == {"grr": None, "nrr": None}


# vendors and NWC
def test_opex_by_vendor():
    rows = [{"period": "2025-01", "vendor": "V1", "account": "x", "amount": 100.0},
            {"period": "2025-01", "vendor": "V2", "account": "x", "amount": 50.0},
            {"period": "2025-02", "vendor": "v1 ", "account": "x", "amount": 100.0},
            {"period": "2025-02", "vendor": "V3", "account": "x", "amount": 25.0},
            {"period": "2025-03", "vendor": "V9", "account": "x", "amount": 999.0}]
    out = metrics.opex_by_vendor(rows, ["2025-01", "2025-02"])
    assert out["monthly_total"] == {"2025-01": 150.0, "2025-02": 125.0}
    assert out["top_vendors"] == [("V1", 200.0), ("V2", 50.0), ("V3", 25.0)]


def test_opex_by_vendor_keeps_top_ten():
    rows = [{"period": "2025-01", "vendor": f"V{i}", "account": "x", "amount": float(i)}
            for i in range(1, 13)]
    out = metrics.opex_by_vendor(rows, JAN)
    assert len(out["top_vendors"]) == 10 and out["top_vendors"][0] == ("V12", 12.0)


def bs_row(period, subtype, balance):
    kind = "asset" if subtype in ("ar", "inventory", "wip", "cash") else "liability"
    return {"period": period, "account": subtype, "account_type": kind, "subtype": subtype,
            "balance": float(balance)}


def test_nwc_trend_and_peg():
    jan = [bs_row("2025-01", "ar", 500), bs_row("2025-01", "inventory", 100),
           bs_row("2025-01", "wip", 20), bs_row("2025-01", "ap", 200),
           bs_row("2025-01", "accrued", 50), bs_row("2025-01", "deferred_revenue", 70),
           bs_row("2025-01", "cash", 9999)]
    feb = [bs_row("2025-02", "ar", 400)]
    trend = metrics.nwc_trend(jan + feb, ["2025-01", "2025-02"])
    assert trend[0] == {"month": "2025-01", "ar": 500.0, "inventory": 120.0, "ap": 200.0,
                        "accrued": 50.0, "deferred_revenue": 70.0, "nwc": 300.0}
    assert trend[1]["nwc"] == 400.0
    assert metrics.indicative_peg(trend, ["2025-01", "2025-02", "2025-03"]) == 350.0


def test_indicative_peg_needs_a_month():
    with pytest.raises(ValueError, match="TTM"):
        metrics.indicative_peg([], ["2025-01"])


# deferred revenue
def test_deferred_revenue_annual_plan():
    rf = metrics.deferred_revenue_rollforward([sub("A", 1200, "2025-01-01", interval="year")],
                                              month_range("2025-01", "2025-03"))
    assert [m["recognized"] for m in rf] == [100, 100, 100] and rf[0]["closing"] == 1100
    assert [m["opening"] for m in rf] == [0, 1100, 1000]
    assert [m["billings"] for m in rf] == [1200, 0, 0] and rf[2]["closing"] == 900


def test_deferred_revenue_window_opens_with_prior_balance():
    rf = metrics.deferred_revenue_rollforward([sub("A", 1200, "2025-01-01", interval="year")],
                                              ["2025-03", "2025-04"])
    assert rf[0]["opening"] == 1000 and rf[0]["billings"] == 0 and rf[1]["closing"] == 800


def test_deferred_revenue_anniversary_rebills_while_active():
    s = [sub("A", 1200, "2025-01-01", "2026-06-01", interval="year")]
    rf = {m["month"]: m for m in metrics.deferred_revenue_rollforward(s, ["2025-12", "2026-01"])}
    assert rf["2025-12"]["closing"] == 0 and rf["2026-01"]["billings"] == 1200
    assert rf["2026-01"]["opening"] == 0 and rf["2026-01"]["closing"] == 1100


def test_deferred_revenue_no_rebill_after_end():
    s = [sub("A", 1200, "2025-01-01", "2025-12-15", interval="year")]
    rf = metrics.deferred_revenue_rollforward(s, ["2026-01"])
    assert rf[0]["billings"] == 0


def test_deferred_revenue_monthly_plan_has_no_deferral():
    rf = metrics.deferred_revenue_rollforward([sub("A", 50, "2025-01-01")], ["2025-01", "2025-02"])
    assert [(m["billings"], m["recognized"], m["closing"]) for m in rf] == [(50, 50, 0), (50, 50, 0)]


def test_deferred_revenue_rejects_unknown_interval():
    with pytest.raises(ValueError, match="quarter"):
        metrics.deferred_revenue_rollforward([sub("A", 1, "2025-01-01", interval="quarter")], JAN)
