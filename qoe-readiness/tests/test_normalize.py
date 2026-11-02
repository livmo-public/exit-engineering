import json
from pathlib import Path

import openpyxl
import pytest

import canonical
import normalize

PRESETS = json.loads(
    (Path(__file__).resolve().parent.parent / "skill" / "data" / "export_presets.json")
    .read_text(encoding="utf-8"))

GL_MAP = {k: v for k, v in PRESETS["qbo"]["general_ledger"]["columns"].items()}
GENERIC_MAP = {"customer": "Client", "plan": "Product", "interval": "Billing cycle",
               "start_date": "Started", "end_date": "Cancelled", "amount": "Monthly price",
               "currency": "Cur"}


def pick(rows, *keys):
    return [{k: r[k] for k in keys} for r in rows]


# --- parse_amount ---

@pytest.mark.parametrize("text,expected", [
    ("1234.56", 1234.56),
    ("$1,234.56", 1234.56),
    ("(500.00)", -500.0),
    ("($1,200.50)", -1200.5),
    ("-500", -500.0),
    ("$-500.00", -500.0),
    ("-$500.00", -500.0),
    ("", 0.0),
    ("   ", 0.0),
    ("-", 0.0),
    ("(0.00)", 0.0),
    (" 42 ", 42.0),
])
def test_parse_amount(text, expected):
    assert normalize.parse_amount(text) == expected


@pytest.mark.parametrize("text", ["abc", "1.2.3", "nan", "inf", "1e5", "12 USD"])
def test_parse_amount_rejects_text(text):
    with pytest.raises(normalize.NormalizeError):
        normalize.parse_amount(text)


def test_parse_amount_zero_is_not_negative_zero():
    assert repr(normalize.parse_amount("(0.00)")) == "0.0"


# --- parse_month_label ---

@pytest.mark.parametrize("text,expected", [
    ("Jan 2025", "2025-01"),
    ("January 2025", "2025-01"),
    ("Jan-25", "2025-01"),
    ("2025-01", "2025-01"),
    ("01/2025", "2025-01"),
    ("Sept 2025", "2025-09"),
    ("Dec 2024", "2024-12"),
    ("Jan 31, 2025", "2025-01"),
    ("31 Jan 2025", "2025-01"),
    ("Jan 25", "2025-01"),
    ("Jan 31, 25", "2025-01"),
    ("2025-01-31", "2025-01"),
    ("  Feb 2025  ", "2025-02"),
])
def test_parse_month_label(text, expected):
    assert normalize.parse_month_label(text) == expected


@pytest.mark.parametrize("text", ["Total", "TOTAL", "", "Account", "Foo 2025", "2025-13",
                                  "13/2025", "January - March 2025"])
def test_parse_month_label_none(text):
    assert normalize.parse_month_label(text) is None


def test_every_preset_period_example_parses():
    examples = [(s, r, e["period_header_example"])
                for s, reports in PRESETS.items() for r, e in reports.items()
                if "period_header_example" in e]
    assert examples
    for system, report, example in examples:
        assert normalize.parse_month_label(example) is not None, (system, report, example)


# --- pivot ---

def test_pivot_pl_qbo(fixtures):
    rows = normalize.parse_pivot(fixtures / "qbo_pl_by_month.csv", "pl", "account")
    assert {"period": "2025-01", "account": "Subscription revenue", "amount": 41000.0} in pick(
        rows, "period", "account", "amount")
    assert not any(r["account"].lower().startswith("total") for r in rows)


def test_pivot_pl_skips_subtotals_and_section_headers(fixtures):
    rows = normalize.parse_pivot(fixtures / "qbo_pl_by_month.csv", "pl", "account")
    accounts = {r["account"] for r in rows}
    assert accounts == {"Subscription revenue", "Hosting", "Payroll", "Software",
                        "Depreciation expense", "Interest expense", "Interest income"}
    assert len(rows) == 7 * 3
    assert {r["period"] for r in rows} == {"2025-01", "2025-02", "2025-03"}


def test_pivot_handles_export_quirks(tmp_path):
    p = tmp_path / "q.csv"
    p.write_text('Acme Co\nProfit and Loss\n\n,Jan-25,February 2025,2025-03,Total\nIncome\nSales,"$1,234.56",(500.00),,"$734.56"\nTotal Income,1234.56,-500,0,734.56\n')
    rows = normalize.parse_pivot(p, "pl", "account")
    assert [(r["period"], r["amount"]) for r in rows] == [("2025-01", 1234.56), ("2025-02", -500.0), ("2025-03", 0.0)]


def test_pivot_month_labels_with_day_and_comma(fixtures):
    rows = normalize.parse_pivot(fixtures / "qbo_bs_by_month.csv", "bs", "account")
    assert {r["period"] for r in rows} == {"2025-01", "2025-02", "2025-03"}


def test_pivot_bs_uses_balance_and_keeps_net_income(fixtures):
    rows = normalize.parse_pivot(fixtures / "qbo_bs_by_month.csv", "bs", "account")
    assert {"period": "2025-03", "account": "Checking", "balance": 80200.0} in pick(
        rows, "period", "account", "balance")
    assert "amount" not in rows[0]
    accounts = {r["account"] for r in rows}
    assert "Net Income" in accounts
    assert not any(a.lower().startswith("total") for a in accounts)


def test_pivot_bs_balances(fixtures):
    rows = normalize.parse_pivot(fixtures / "qbo_bs_by_month.csv", "bs", "account")
    assets = {"Checking", "Accounts Receivable (A/R)"}
    for period in ("2025-01", "2025-02", "2025-03"):
        a = sum(r["balance"] for r in rows if r["period"] == period and r["account"] in assets)
        other = sum(r["balance"] for r in rows if r["period"] == period and r["account"] not in assets)
        assert a == other


def test_pivot_other_systems(fixtures):
    xero = normalize.parse_pivot(fixtures / "xero_pl_by_month.csv", "pl", "account")
    refunds = [r["amount"] for r in xero if r["account"] == "Refunds"]
    assert refunds == [-100.0, 0.0, -50.0]
    assert not any(r["account"] in ("Gross Profit", "Net Profit") for r in xero)
    qbd = normalize.parse_pivot(fixtures / "qbd_pl_by_month.csv", "pl", "account")
    assert {r["period"] for r in qbd} == {"2025-01", "2025-02", "2025-03"}
    accounts = {r["account"] for r in qbd}
    assert "Net Ordinary Income" not in accounts and "Net Other Income" not in accounts
    assert "Net Income" not in accounts


def test_pivot_sales_and_vendor_row_fields(fixtures):
    sales = normalize.parse_pivot(fixtures / "qbo_sales_by_customer.csv", "sales", "customer")
    assert sum(r["amount"] for r in sales if r["period"] == "2025-01") == 41000.0
    assert "TOTAL" not in {r["customer"] for r in sales}
    vendor = normalize.parse_pivot(fixtures / "qbo_vendor_expenses.csv", "vendor", "vendor")
    assert {r["vendor"] for r in vendor} == {"Hosting Provider A", "Office Landlord D",
                                              "Payroll Services C", "Software Vendor B"}


def test_pivot_rejects_wrong_row_field(fixtures):
    with pytest.raises(normalize.NormalizeError, match="row_field"):
        normalize.parse_pivot(fixtures / "qbo_sales_by_customer.csv", "sales", "account")


def test_pivot_without_month_header_raises(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Account,Amount\nSales,10\n")
    with pytest.raises(normalize.NormalizeError, match="month"):
        normalize.parse_pivot(p, "pl", "account")


def test_pivot_duplicate_month_raises(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(",Jan 2025,Jan-25\nSales,1,2\n")
    with pytest.raises(normalize.NormalizeError, match="2025-01"):
        normalize.parse_pivot(p, "pl", "account")


def test_pivot_bad_amount_names_row(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text(",Jan 2025\nSales,10\nRent,oops\n")
    with pytest.raises(normalize.NormalizeError, match="row 3"):
        normalize.parse_pivot(p, "pl", "account")


def test_pivot_reads_cp1252_file(tmp_path):
    p = tmp_path / "x.csv"
    p.write_bytes("Account,Jan 2025\nCaf\xe9 sales,10\n".encode("cp1252"))
    rows = normalize.parse_pivot(p, "pl", "account")
    assert rows[0]["account"] == "Caf\xe9 sales"


def test_pivot_reads_xlsx(tmp_path):
    p = tmp_path / "x.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Sample"])
    ws.append([None, "Jan 2025", "Feb 2025", "Total"])
    ws.append(["Income"])
    ws.append(["Sales", 100.5, "(20.00)", 80.5])
    ws.append(["Total Income", 100.5, -20, 80.5])
    wb.save(p)
    rows = normalize.parse_pivot(p, "pl", "account")
    assert [(r["period"], r["amount"]) for r in rows] == [("2025-01", 100.5), ("2025-02", -20.0)]


# --- name key ---

def test_name_key_matches_case_and_space(fixtures, tmp_path):
    sales = normalize.parse_pivot(fixtures / "qbo_sales_by_customer.csv", "sales", "customer")
    subs = normalize.parse_flat(fixtures / "stripe_subscriptions.csv", "subs", PRESETS["stripe"]["subscriptions"]["columns"])
    assert {canonical.name_key(r["customer"]) for r in subs} <= {canonical.name_key(r["customer"]) for r in sales}
    # The raw names differ in case or spacing, so the match depends on name_key.
    assert not {r["customer"] for r in subs} <= {r["customer"] for r in sales}


# --- flat ---

def test_flat_stripe_subscriptions(fixtures):
    rows = normalize.parse_flat(fixtures / "stripe_subscriptions.csv", "subs",
                                PRESETS["stripe"]["subscriptions"]["columns"])
    assert len(rows) == 4
    first = rows[0]
    assert first["customer"] == "ACME INC"
    assert first["start_date"] == "2024-03-01"
    assert first["end_date"] == ""
    assert first["amount"] == 15000.0
    assert rows[2]["end_date"] == "2025-03-10"
    assert set(first) == set(PRESETS["stripe"]["subscriptions"]["columns"])


def test_flat_missing_header_raises(fixtures):
    with pytest.raises(normalize.NormalizeError, match="Nope"):
        normalize.parse_flat(fixtures / "stripe_subscriptions.csv", "subs",
                             {"customer": "Nope", "amount": "Amount"})


def test_flat_finds_header_below_title_rows(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Income and Expenses by Contact\nSample\n\nContact,Income,Expenses\nAcme Inc,\"$1,000.00\",\nTotal,\"$1,000.00\",\n")
    rows = normalize.parse_flat(p, "sales", {"customer": "Contact", "amount": "Income"})
    assert rows == [{"customer": "Acme Inc", "amount": 1000.0}]


def test_flat_bad_date_names_row(tmp_path):
    p = tmp_path / "x.csv"
    p.write_text("Client,Started,Price\nA,not a date,5\n")
    with pytest.raises(normalize.NormalizeError, match="row 2"):
        normalize.parse_flat(p, "subs", {"customer": "Client", "start_date": "Started", "amount": "Price"})


# --- grouped ---

def test_grouped_ledger_carries_account(fixtures):
    rows = normalize.parse_grouped(fixtures / "qbo_general_ledger.csv", "gl", GL_MAP, "")
    assert all(r["account"] for r in rows)


def test_grouped_ledger_lines_and_signed_split(fixtures):
    rows = normalize.parse_grouped(fixtures / "qbo_general_ledger.csv", "gl", GL_MAP, "")
    assert len(rows) == 4
    assert {r["account"] for r in rows} == {"Checking", "Subscription revenue", "Hosting"}
    deposit = rows[0]
    assert (deposit["date"], deposit["txn_id"], deposit["name"], deposit["memo"]) == (
        "2025-01-05", "1001", "Acme Inc", "January invoice paid")
    assert (deposit["debit"], deposit["credit"]) == (15000.0, 0.0)
    expense = rows[1]
    assert (expense["debit"], expense["credit"]) == (0.0, 6000.0)
    assert "amount_signed" not in deposit
    assert sum(r["debit"] for r in rows) == sum(r["credit"] for r in rows)


def test_grouped_named_group_column(tmp_path):
    p = tmp_path / "gl.csv"
    p.write_text("Account,Date,Debit,Credit\nCash,2025-01-02,10,\n,2025-01-03,,4\nTotal Cash,,10,4\nSales,2025-01-02,,10\n")
    rows = normalize.parse_grouped(
        p, "gl", {"date": "Date", "debit": "Debit", "credit": "Credit"}, "Account")
    assert [(r["account"], r["debit"], r["credit"]) for r in rows] == [
        ("Cash", 10.0, 0.0), ("Cash", 0.0, 4.0), ("Sales", 0.0, 10.0)]


def test_grouped_heading_in_date_column(tmp_path):
    p = tmp_path / "gl.csv"
    p.write_text("Account Transactions\n\nDate,Description,Debit,Credit\nSales\n02 Jan 2025,Invoice,,10\nTotal Sales,,,10\nBank\n02 Jan 2025,Receipt,10,\n")
    rows = normalize.parse_grouped(
        p, "gl", {"date": "Date", "memo": "Description", "debit": "Debit", "credit": "Credit"}, "")
    assert [(r["account"], r["date"], r["credit"], r["debit"]) for r in rows] == [
        ("Sales", "2025-01-02", 10.0, 0.0), ("Bank", "2025-01-02", 0.0, 10.0)]


def test_grouped_line_before_heading_raises(tmp_path):
    p = tmp_path / "gl.csv"
    p.write_text(",Date,Amount\n,2025-01-02,5\n")
    with pytest.raises(normalize.NormalizeError, match="heading"):
        normalize.parse_grouped(p, "gl", {"date": "Date", "amount_signed": "Amount"}, "")


def test_grouped_aging_skips_bucket_headings(fixtures):
    columns = PRESETS["qbo"]["ar_aging"]["columns"]
    rows = normalize.parse_grouped(fixtures / "qbo_ar_aging.csv", "aging", columns, "",
                                   group_provides=None)
    assert [(r["name"], r["invoice_date"], r["due_date"], r["amount"]) for r in rows] == [
        ("Acme Inc", "2025-03-20", "2025-04-19", 16000.0),
        ("Delta Partners LLC", "2025-03-25", "2025-04-24", 5500.0),
        ("Beta Holdings Inc", "2025-02-25", "2025-03-27", 12000.0),
        ("Gamma Services LLC", "2024-11-15", "2024-12-15", 7000.0)]


def test_grouped_aging_group_is_name(tmp_path):
    p = tmp_path / "ar.csv"
    p.write_text("Aged Receivables Detail\nDate,Due Date,Due\nAcme Inc\n10 Mar 2025,09 Apr 2025,100.00\nTotal Acme Inc,,100.00\nBeta Holdings Inc\n01 Feb 2025,,50.00\n")
    columns = PRESETS["xero"]["ar_aging"]["columns"]
    rows = normalize.parse_grouped(p, "aging", columns, "", group_provides="name")
    assert [(r["name"], r["due_date"], r["amount"]) for r in rows] == [
        ("Acme Inc", "2025-04-09", 100.0), ("Beta Holdings Inc", "", 50.0)]


def test_grouped_rejects_other_kinds(fixtures):
    with pytest.raises(normalize.NormalizeError, match="grouped"):
        normalize.parse_grouped(fixtures / "qbo_general_ledger.csv", "pl", GL_MAP, "")


# --- normalize (preset path) ---

CASES = [
    ("qbo", "pl_by_month", "qbo_pl_by_month.csv", "pl"),
    ("qbo", "bs_by_month", "qbo_bs_by_month.csv", "bs"),
    ("qbo", "sales_by_customer", "qbo_sales_by_customer.csv", "sales"),
    ("qbo", "expenses_by_vendor", "qbo_vendor_expenses.csv", "vendor"),
    ("qbo", "general_ledger", "qbo_general_ledger.csv", "gl"),
    ("qbo", "ar_aging", "qbo_ar_aging.csv", "aging"),
    ("xero", "pl_by_month", "xero_pl_by_month.csv", "pl"),
    ("qbd", "pl_by_month", "qbd_pl_by_month.csv", "pl"),
    ("stripe", "subscriptions", "stripe_subscriptions.csv", "subs"),
]


@pytest.mark.parametrize("system,report,name,kind", CASES)
def test_normalize_writes_readable_canonical_file(system, report, name, kind, fixtures, tmp_path):
    out = normalize.normalize(system, report, fixtures / name, tmp_path / "out")
    assert out == tmp_path / "out" / f"{kind}.csv"
    assert PRESETS[system][report]["kind"] == kind
    assert canonical.read(kind, out)


def test_normalize_pl_defaults(fixtures, tmp_path):
    out = normalize.normalize("qbo", "pl_by_month", fixtures / "qbo_pl_by_month.csv", tmp_path)
    rows = canonical.read("pl", out)
    assert all(r["account_type"] == "" and r["basis"] == "accrual" for r in rows)
    cash = normalize.normalize("qbo", "pl_by_month", fixtures / "qbo_pl_by_month.csv", tmp_path,
                               basis="cash")
    assert {r["basis"] for r in canonical.read("pl", cash)} == {"cash"}


def test_normalize_bs_leaves_types_blank(fixtures, tmp_path):
    out = normalize.normalize("qbo", "bs_by_month", fixtures / "qbo_bs_by_month.csv", tmp_path)
    rows = canonical.read("bs", out)
    assert all(r["account_type"] == "" and r["subtype"] == "" for r in rows)


def test_normalize_vendor_adds_constant_account(fixtures, tmp_path):
    out = normalize.normalize("qbo", "expenses_by_vendor", fixtures / "qbo_vendor_expenses.csv", tmp_path)
    rows = canonical.read("vendor", out)
    assert {r["account"] for r in rows} == {"All expense accounts"}


def test_normalize_aging_adds_type(fixtures, tmp_path):
    out = normalize.normalize("qbo", "ar_aging", fixtures / "qbo_ar_aging.csv", tmp_path)
    rows = canonical.read("aging", out)
    assert {r["type"] for r in rows} == {"AR"}
    assert len(rows) == 4


def test_normalize_gl_account_map_round_trip(fixtures, tmp_path):
    out = normalize.normalize("qbo", "general_ledger", fixtures / "qbo_general_ledger.csv", tmp_path)
    rows = canonical.read("gl", out)
    mapped = canonical.apply_account_map(rows, {
        "Checking": {"account_type": "asset"},
        "Subscription revenue": {"account_type": "revenue"},
        "Hosting": {"account_type": "cogs"}})
    assert {r["account_type"] for r in mapped} == {"asset", "revenue", "cogs"}


def test_normalize_does_not_change_input(fixtures, tmp_path):
    src = tmp_path / "in.csv"
    src.write_bytes((fixtures / "qbo_pl_by_month.csv").read_bytes())
    before = src.read_bytes()
    normalize.normalize("qbo", "pl_by_month", src, tmp_path / "out")
    assert src.read_bytes() == before


def test_normalize_unknown_system_or_report(fixtures, tmp_path):
    with pytest.raises(normalize.NormalizeError, match="system"):
        normalize.normalize("nope", "pl_by_month", fixtures / "qbo_pl_by_month.csv", tmp_path)
    with pytest.raises(normalize.NormalizeError, match="report"):
        normalize.normalize("qbo", "nope", fixtures / "qbo_pl_by_month.csv", tmp_path)


def test_normalize_bad_layout_reports_input_path(fixtures, tmp_path):
    with pytest.raises(normalize.NormalizeError, match="qbo_ar_aging.csv"):
        normalize.normalize("qbo", "pl_by_month", fixtures / "qbo_ar_aging.csv", tmp_path)


# --- per_run reports ---

XERO_RUN = ("Income and Expenses by Contact\nSample\nContact,Income,Expenses\n"
            "Acme Inc,\"1,000.00\",0.00\nHosting Provider A,0.00,\"400.00\"\nTotal,\"1,000.00\",\"400.00\"\n")


def test_per_run_requires_period(tmp_path):
    p = tmp_path / "run.csv"
    p.write_text(XERO_RUN)
    with pytest.raises(normalize.NormalizeError, match="period"):
        normalize.normalize("xero", "sales_by_customer", p, tmp_path / "out")


def test_per_run_period_and_zero_rows(tmp_path):
    p = tmp_path / "run.csv"
    p.write_text(XERO_RUN)
    out = normalize.normalize("xero", "sales_by_customer", p, tmp_path / "out", period="2025-01")
    assert canonical.read("sales", out) == [{"period": "2025-01", "customer": "Acme Inc", "amount": 1000.0}]
    out = normalize.normalize("xero", "expenses_by_vendor", p, tmp_path / "out2", period="2025-01")
    assert canonical.read("vendor", out) == [{
        "period": "2025-01", "vendor": "Hosting Provider A", "account": "All expense accounts", "amount": 400.0}]


def test_per_run_rejects_bad_period(tmp_path):
    p = tmp_path / "run.csv"
    p.write_text(XERO_RUN)
    with pytest.raises(normalize.NormalizeError, match="period"):
        normalize.normalize("xero", "sales_by_customer", p, tmp_path / "out", period="Jan")


def test_normalize_runs_merges_months(tmp_path):
    jan = tmp_path / "jan.csv"
    feb = tmp_path / "feb.csv"
    jan.write_text(XERO_RUN)
    feb.write_text(XERO_RUN.replace("1,000.00", "1,500.00"))
    out = normalize.normalize_runs("xero", "sales_by_customer",
                                   {"2025-02": feb, "2025-01": jan}, tmp_path / "out")
    assert [(r["period"], r["amount"]) for r in canonical.read("sales", out)] == [
        ("2025-01", 1000.0), ("2025-02", 1500.0)]


def test_normalize_runs_rejects_non_per_run_report(fixtures, tmp_path):
    with pytest.raises(normalize.NormalizeError, match="per_run"):
        normalize.normalize_runs("qbo", "pl_by_month", {"2025-01": fixtures / "qbo_pl_by_month.csv"}, tmp_path)


# --- generic path ---

def test_generic_path_writes_canonical(fixtures, tmp_path):
    out = normalize.normalize_generic(fixtures / "generic_subs.csv", "subs", GENERIC_MAP, tmp_path)
    assert canonical.read("subs", out)


def test_generic_path_values(fixtures, tmp_path):
    out = normalize.normalize_generic(fixtures / "generic_subs.csv", "subs", GENERIC_MAP, tmp_path)
    rows = canonical.read("subs", out)
    assert [(r["customer"], r["start_date"], r["end_date"], r["amount"]) for r in rows] == [
        ("Acme Inc", "2024-03-01", "", 15000.0),
        ("Beta Holdings Inc", "2024-06-15", "", 12000.0),
        ("Gamma Services LLC", "2024-01-10", "2025-03-10", 9000.0)]


def test_generic_path_missing_required_column(fixtures, tmp_path):
    bad = {k: v for k, v in GENERIC_MAP.items() if k != "amount"}
    with pytest.raises(normalize.NormalizeError, match="amount"):
        normalize.normalize_generic(fixtures / "generic_subs.csv", "subs", bad, tmp_path)


def test_generic_path_unknown_canonical_column(fixtures, tmp_path):
    with pytest.raises(normalize.NormalizeError, match="colour"):
        normalize.normalize_generic(fixtures / "generic_subs.csv", "subs",
                                    {**GENERIC_MAP, "colour": "Cur"}, tmp_path)


def test_generic_path_unknown_kind(fixtures, tmp_path):
    with pytest.raises(normalize.NormalizeError, match="kind"):
        normalize.normalize_generic(fixtures / "generic_subs.csv", "nope", GENERIC_MAP, tmp_path)


def test_generic_path_pl_flat_with_default_basis(tmp_path):
    p = tmp_path / "pl.csv"
    p.write_text("Month,Line,Total\nJan 2025,Sales,\"$1,000.00\"\n2025-02,Sales,(50)\n")
    out = normalize.normalize_generic(
        p, "pl", {"period": "Month", "account": "Line", "amount": "Total"}, tmp_path / "out")
    rows = canonical.read("pl", out)
    assert [(r["period"], r["amount"], r["basis"]) for r in rows] == [
        ("2025-01", 1000.0, "accrual"), ("2025-02", -50.0, "accrual")]


# --- propose_account_map ---

def test_propose_account_map_leaves_unknown_blank():
    m = normalize.propose_account_map(["Depreciation expense", "Widgets"])
    assert m["Depreciation expense"]["account_type"] == "depreciation" and m["Widgets"]["account_type"] == ""


@pytest.mark.parametrize("account,entry", [
    ("Depreciation expense", {"account_type": "depreciation"}),
    ("Amortization of capitalized software", {"account_type": "amortization"}),
    ("Interest expense", {"account_type": "interest"}),
    ("Interest income", {"account_type": "other_income"}),
    ("Income tax expense", {"account_type": "income_tax"}),
    ("Cost of Goods Sold", {"account_type": "cogs"}),
    ("Subscription revenue", {"account_type": "revenue"}),
    ("Accumulated depreciation", {"account_type": "asset", "subtype": "other_asset"}),
    ("Checking", {"account_type": "asset", "subtype": "cash"}),
    ("Business Savings", {"account_type": "asset", "subtype": "cash"}),
    ("Accounts Receivable (A/R)", {"account_type": "asset", "subtype": "ar"}),
    ("Inventory Asset", {"account_type": "asset", "subtype": "inventory"}),
    ("Work in Progress", {"account_type": "asset", "subtype": "wip"}),
    ("WIP - Projects", {"account_type": "asset", "subtype": "wip"}),
    ("Capitalized software", {"account_type": "asset", "subtype": "capitalized_software"}),
    ("Deferred revenue", {"account_type": "liability", "subtype": "deferred_revenue"}),
    ("Unearned Revenue", {"account_type": "liability", "subtype": "deferred_revenue"}),
    ("Accounts Payable (A/P)", {"account_type": "liability", "subtype": "ap"}),
    ("Accrued expenses", {"account_type": "liability", "subtype": "accrued"}),
    ("Bank Loan", {"account_type": "liability", "subtype": "debt"}),
    ("Notes Payable", {"account_type": "liability", "subtype": "debt"}),
    ("Line of Credit", {"account_type": "liability", "subtype": "debt"}),
    ("Retained Earnings", {"account_type": "equity", "subtype": "equity"}),
    ("Owner's Draw", {"account_type": "equity", "subtype": "equity"}),
    ("Opening Balance Equity", {"account_type": "equity", "subtype": "equity"}),
    ("Bank service charges", {"account_type": ""}),
    ("Prepaid expenses", {"account_type": ""}),
])
def test_propose_account_map_keywords(account, entry):
    assert normalize.propose_account_map([account])[account] == entry


def test_propose_account_map_bs_entries_are_valid_for_apply():
    accounts = ["Checking", "Accounts Receivable (A/R)", "Deferred revenue", "Retained Earnings"]
    proposed = normalize.propose_account_map(accounts)
    rows = [{"period": "2025-01", "account": a, "account_type": "", "subtype": "", "balance": 1.0}
            for a in accounts]
    mapped = canonical.apply_account_map(rows, proposed)
    assert [r["subtype"] for r in mapped] == ["cash", "ar", "deferred_revenue", "equity"]


def test_propose_account_map_pl_entries_are_valid_for_apply(fixtures):
    rows = normalize.parse_pivot(fixtures / "qbo_pl_by_month.csv", "pl", "account")
    accounts = sorted({r["account"] for r in rows})
    proposed = normalize.propose_account_map(accounts)
    for entry in proposed.values():
        if entry["account_type"] == "":
            continue
        canonical.apply_account_map(
            [{"period": "2025-01", "account": "x", "account_type": "", "amount": 1.0, "basis": "accrual"}],
            {"x": entry})


def test_propose_account_map_returns_new_dicts():
    a = normalize.propose_account_map(["Checking"])
    b = normalize.propose_account_map(["Checking"])
    a["Checking"]["account_type"] = "changed"
    assert b["Checking"]["account_type"] == "asset"
