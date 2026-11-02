"""Generate the synthetic company "Sample SaaS Co." for the QoE readiness skill.

Usage, from qoe-readiness/:  python tools/make_sample.py examples/sample-saas-co [--seed 7]

The company is a SaaS business with a December year end and 27 months of books, 2024-07 to
2026-09. It has 40 customers on monthly and annual plans, a rent paid to an owner entity, a
suspense balance, and annual billing booked as revenue with no deferred revenue account.
The books come from one double-entry simulation, so the P&L, balance sheet, ledger, bank,
sales, vendor, and aging files tie. All names are invented.

Output folder: the canonical CSVs, progress.json, and qoe-readiness-workbook.xlsx.
canonical_path in progress.json is the CSV path as given to make_sample: absolute, or relative
to the current directory. The scripts read a relative path from the current directory too.
Findings come from run_checks, not from hand-written values.
"""
import argparse
import random
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "skill" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import build_workbook  # noqa: E402
import canonical  # noqa: E402
import progress  # noqa: E402
import run_checks  # noqa: E402

COMPANY = "Sample SaaS Co."
WORKBOOK_NAME = "qoe-readiness-workbook.xlsx"
DATA_DIR = SCRIPTS.parent / "data"
RELATED_PARTY = "Owner Property LLC"
K12_STATEMENT = ("We rent our office from a company the owner controls. "
                 "We keep no schedule of the rent terms.")
OPENING = "2024-06"
FIRST, LAST = "2024-07", "2026-09"
CUSTOMERS = 40
ANNUAL_CUSTOMERS = 12
SUSPENSE_MONTH, SUSPENSE_AMOUNT = "2025-11", 3150.0
LEGAL_MONTH, LEGAL_FEE = "2025-11", 12500.0
RENT, MARKET_RENT = 4500.0, 3250.0

INTAKE = {
    "business_type": "saas", "revenue_range": "1m_to_5m", "accounting_system": "qbo",
    "billing_system": "stripe", "accounting_basis": "accrual", "fiscal_year_end_month": 12,
    "latest_closed_month": LAST, "sale_timeline": "3_to_12_months", "buyer_financing": "sba",
    "price_may_reach_3m": "no", "advisor_name": "",
}
FILE_KINDS = {"C1": "pl", "C2": "bs", "C3": "gl", "C4": "bank", "C6": "sales", "C7": "vendor",
              "C8": "aging", "C9": "tax", "S1": "subs"}
SOURCE_SYSTEMS = {"C1": "qbo", "C2": "qbo", "C3": "qbo", "C4": "qbo", "C6": "qbo", "C7": "qbo",
                  "C8": "qbo", "C9": "qbo", "S1": "stripe"}
# Files with no canonical CSV carry no canonical_path.
DOCUMENT_FILES = {
    "C5": {"status": "uploaded"}, "R1": {"status": "uploaded"}, "R3": {"status": "uploaded"},
    "R2": {"status": "missing", "reason": "never_kept"},
    "R4": {"status": "missing", "reason": "never_kept"},
    "R5": {"status": "missing", "reason": "never_kept"},
    "R6": {"status": "missing", "reason": "unknown"},
    "S2": {"status": "missing", "reason": "unknown"},
    "S3": {"status": "missing", "reason": "never_kept"},
    "S4": {"status": "missing", "reason": "never_kept"},
    "S5": {"status": "not_applicable"}, "S6": {"status": "not_applicable"},
}
# Owner-stated amounts. A3 gives month keys; the others give period labels.
# A1 and A3 are approved, A2 is edited (the owner lowered it), A4 is rejected.
ADJUSTMENTS = [
    {"id": "A1", "name": "Owner salary above replacement cost", "source_file": "R1",
     "amounts": {"FY2025": 36000.0, "TTM": 36000.0}, "evidence": "Payroll summary 2025",
     "decision": "approved", "owner_stated": True},
    {"id": "A2", "name": "Rent to owner entity above market",  "source_file": "R6",
     "amounts": {"FY2025": 15000.0, "TTM": 15000.0}, "evidence": None,
     "decision": "edited", "owner_stated": True},
    {"id": "A3", "name": "One-time legal fee for a contract dispute", "source_file": "R3",
     "amounts": {LEGAL_MONTH: LEGAL_FEE}, "evidence": "Law firm invoice",
     "decision": "approved", "owner_stated": True},
    {"id": "A4", "name": "Personal travel booked to the company", "source_file": "R3",
     "amounts": {"FY2025": 4800.0, "TTM": 6200.0}, "evidence": None,
     "decision": "rejected", "owner_stated": True},
]
RESPONSES = {
    "K01-1": {"type": "explain", "text": "We book each annual invoice as revenue when we send it. "
                                         "We have not set up deferred revenue."},
    "K03-1": {"type": "accept"},
    "K08-1": {"type": "fix"},
}

MONTHLY_PRICES = (1000.0, 1500.0, 2000.0, 3000.0, 3500.0, 4500.0)
ANNUAL_PRICES = (12000.0, 18000.0, 24000.0, 30000.0, 40000.0)
UNPAID_INVOICES = 3
LOAN_RATE, LOAN_PRINCIPAL, OPENING_LOAN = 0.08, 2000.0, 150000.0
OPENING_CASH, OPENING_EQUIPMENT, OPENING_DEPRECIATION = 260000.0, 24000.0, -9000.0
OPENING_CAPITAL, MONTHLY_DEPRECIATION, DISTRIBUTION = 100000.0, 600.0, 10000.0
CASH, AR, EQUIPMENT, ACCUM, AP, ACCRUED, LOAN, SUSPENSE = (
    "Operating Checking", "Accounts Receivable", "Computer Equipment", "Accumulated Depreciation",
    "Accounts Payable", "Accrued Expenses", "Bank Loan", "Suspense")
CAPITAL, RETAINED, DISTRIBUTIONS, NET_INCOME = (
    "Owner's Capital", "Retained Earnings", "Owner Distributions", "Net Income")
REV_MONTHLY, REV_ANNUAL = "Subscription revenue - monthly plans", "Subscription revenue - annual plans"
DEPRECIATION, INTEREST = "Depreciation expense", "Interest expense"

# account -> (account_type, balance sheet subtype or None)
ACCOUNTS = {
    REV_MONTHLY: ("revenue", None), REV_ANNUAL: ("revenue", None),
    "Hosting and infrastructure": ("cogs", None), "Customer support payroll": ("cogs", None),
    "Salaries and wages": ("opex", None), "Payroll taxes and benefits": ("opex", None),
    "Contractors": ("opex", None), "Software and tools": ("opex", None),
    "Advertising and marketing": ("opex", None), "Rent": ("opex", None),
    "Professional fees": ("opex", None), "Legal fees": ("opex", None),
    "Insurance": ("opex", None), "Travel": ("opex", None),
    DEPRECIATION: ("depreciation", None), INTEREST: ("interest", None),
    CASH: ("asset", "cash"), AR: ("asset", "ar"), EQUIPMENT: ("asset", "other_asset"),
    ACCUM: ("asset", "other_asset"), AP: ("liability", "ap"), ACCRUED: ("liability", "accrued"),
    LOAN: ("liability", "debt"), SUSPENSE: ("liability", "other_liability"),
    CAPITAL: ("equity", "equity"), RETAINED: ("equity", "equity"),
    DISTRIBUTIONS: ("equity", "equity"), NET_INCOME: ("equity", "equity"),
}
PL_ACCOUNTS = [a for a, (t, s) in ACCOUNTS.items() if s is None]
BS_ACCOUNTS = [a for a, (t, s) in ACCOUNTS.items() if s is not None]
# vendor, account, how the bill is paid: cash in the month, or in the next month from AP / accrued
VENDORS = (
    ("Hosting Provider", "Hosting and infrastructure", AP),
    ("Payroll Processor", "Customer support payroll", CASH),
    ("Payroll Processor", "Salaries and wages", CASH),
    ("Payroll Tax Agency", "Payroll taxes and benefits", ACCRUED),
    ("Contract Developer 1", "Contractors", CASH), ("Contract Developer 2", "Contractors", CASH),
    ("Software Tools Vendor", "Software and tools", CASH),
    ("Ad Platform", "Advertising and marketing", CASH),
    (RELATED_PARTY, "Rent", CASH), ("Accounting Service", "Professional fees", CASH),
    ("Law Firm", "Legal fees", CASH), ("Insurance Carrier", "Insurance", CASH),
    ("Travel Vendor", "Travel", CASH),
)


# ---- months ---------------------------------------------------------------------

def idx(month: str) -> int:
    year, number = month.split("-")
    return int(year) * 12 + int(number) - 1


def month_of(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


MONTHS = [month_of(i) for i in range(idx(FIRST), idx(LAST) + 1)]


# ---- customers and billing ---------------------------------------------------------

def _plan_rows(i: int, interval: str, start: int, amount: float, end: int | None,
               upgrade: int | None, shout: bool) -> list[dict]:
    """Subscription rows of one customer. An upgrade ends one row and starts the next the same day."""
    name = f"Sample Customer {i + 1:02d}"
    shown = name.upper() if shout else name

    def row(first: int, last: int | None, price: float) -> dict:
        return {"customer": shown, "plan": "Pro" if price > amount else "Standard",
                "interval": interval, "start_date": f"{month_of(first)}-01",
                "end_date": "" if last is None else f"{month_of(last)}-01", "amount": price,
                "currency": "USD"}

    if upgrade is None:
        return [row(start, end, amount)]
    return [row(start, upgrade, amount), row(upgrade, end, round(amount * 1.5, -2))]


def make_subscriptions(rng: random.Random) -> list[dict]:
    """40 customers: 12 on annual plans, 28 on monthly plans; churn and upgrades inside the window."""
    last, quarter = idx(LAST), idx("2025-12")
    annual = {0, *rng.sample(range(2, CUSTOMERS), ANNUAL_CUSTOMERS - 1)}
    starts = {i: idx("2023-10") + rng.randrange(33) for i in range(CUSTOMERS)}
    starts.update({0: idx("2024-03"), 1: idx("2023-12")})
    monthly_pool = [i for i in range(2, CUSTOMERS) if i not in annual and starts[i] <= quarter]
    churn = set(rng.sample(monthly_pool, 4))
    annual_churn = rng.choice([i for i in sorted(annual - {0}) if starts[i] + 12 <= last - 1])
    upgrade = set(rng.sample([i for i in monthly_pool if i not in churn], 4))
    rows = []
    for i in range(CUSTOMERS):
        interval = "year" if i in annual else "month"
        amount = (72000.0 if i == 0 else 7500.0 if i == 1 else
                  rng.choice(ANNUAL_PRICES if i in annual else MONTHLY_PRICES))
        end = None
        if i in churn:
            end = rng.randrange(max(starts[i] + 6, idx("2024-10")), last)
        if i == annual_churn:
            end = starts[i] + 12
        up = starts[i] + rng.randrange(4, 12) if i in upgrade else None
        if up is not None and up >= last:
            up = None
        rows += _plan_rows(i, interval, starts[i], amount, end, up, i in (4, 16))
    return rows


def _active(sub: dict, month: str) -> bool:
    first = f"{month}-01"
    return sub["start_date"][:7] <= month and (sub["end_date"] == "" or sub["end_date"] > first)


def billing(subs: list[dict], month: str) -> dict[str, tuple[str, float]]:
    """Customer to (interval, amount billed in the month). Annual plans bill on each anniversary."""
    out: dict[str, tuple[str, float]] = {}
    for sub in subs:
        if not _active(sub, month):
            continue
        due = sub["interval"] == "month" or (idx(month) - idx(sub["start_date"][:7])) % 12 == 0
        if due:
            key = canonical.name_key(sub["customer"])
            out[key] = (sub["interval"], out.get(key, (sub["interval"], 0.0))[1] + sub["amount"])
    return out


def mrr(subs: list[dict], month: str) -> float:
    return sum(s["amount"] if s["interval"] == "month" else s["amount"] / 12
               for s in subs if _active(s, month))


# ---- vendor amounts -----------------------------------------------------------------

def vendor_amount(seed: int, vendor: str, account: str, month: str, monthly: float) -> float:
    """Monthly bill for a vendor and account. A pure function of its arguments."""
    noise = random.Random(f"{seed}-{vendor}-{account}-{month}")
    step = (idx(month) - idx(OPENING)) // 6
    support, salaries = 5000.0 + 150.0 * step, 34000.0 + 500.0 * step
    amounts = {
        "Hosting and infrastructure": lambda: 0.08 * monthly,
        "Customer support payroll": lambda: support,
        "Salaries and wages": lambda: salaries,
        "Payroll taxes and benefits": lambda: 0.11 * (support + salaries),
        "Contractors": lambda: 4500.0 if vendor.endswith("1") else 3000.0,
        "Software and tools": lambda: 2200.0 + noise.randrange(-150, 150),
        "Advertising and marketing": lambda: 2500.0 + noise.randrange(-600, 600),
        "Rent": lambda: RENT, "Professional fees": lambda: 1200.0, "Insurance": lambda: 700.0,
        "Legal fees": lambda: 500.0 + (LEGAL_FEE if month == LEGAL_MONTH else 0.0),
        "Travel": lambda: 600.0 + noise.randrange(0, 900),
    }
    return float(round(amounts[account]()))


# ---- pass 1: the ledger --------------------------------------------------------------

def _display(key: str) -> str:
    return key.title()


def _post(gl: list[dict], month: str, day: int, txn: str, name: str, memo: str,
          lines: list[tuple[str, float, float]]) -> None:
    for account, debit, credit in lines:
        gl.append({"date": f"{month}-{day:02d}", "txn_id": txn, "account": account,
                   "account_type": ACCOUNTS[account][0], "name": name, "memo": memo,
                   "debit": debit, "credit": credit})


def _unpaid(bills: dict[str, tuple[str, float]]) -> list[tuple[str, float]]:
    """The first monthly-plan invoices by customer name stay unpaid at month end."""
    monthly = sorted((_display(k), amount) for k, (interval, amount) in bills.items()
                     if interval == "month")
    return monthly[:UNPAID_INVOICES]


def _post_revenue(gl, sales, month, bills, carry) -> list[tuple[str, float]]:
    monthly = sum(a for i, a in bills.values() if i == "month")
    annual = sum(a for i, a in bills.values() if i == "year")
    lines = [(AR, monthly + annual, 0.0), (REV_MONTHLY, 0.0, monthly)]
    if annual:
        lines.append((REV_ANNUAL, 0.0, annual))
    _post(gl, month, 1, f"INV-{month}", "Customer invoices", "Subscription invoices", lines)
    unpaid = _unpaid(bills)
    receipts = carry[AR] + monthly + annual - sum(a for _, a in unpaid)
    _post(gl, month, 15, f"RCPT-{month}", "Customer receipts", "Payments received",
          [(CASH, receipts, 0.0), (AR, 0.0, receipts)])
    sales.extend({"period": month, "customer": _display(k), "amount": a}
                 for k, (_, a) in sorted(bills.items()))
    return unpaid


def _post_vendors(seed, gl, vendor_rows, month, monthly, carry) -> None:
    day = 3
    for terms in (AP, ACCRUED):
        payee = next(v for v, a, t in VENDORS if t == terms)
        _post(gl, month, 20, f"PAY-{month}-{terms[:2].upper()}", payee, f"Payment of {terms}",
              [(terms, carry[terms], 0.0), (CASH, 0.0, carry[terms])])
    for vendor, account, terms in VENDORS:
        amount = vendor_amount(seed, vendor, account, month, monthly)
        vendor_rows.append({"period": month, "vendor": vendor, "account": account, "amount": amount})
        _post(gl, month, day, f"BILL-{month}-{day:02d}", vendor, account,
              [(account, amount, 0.0), (terms, 0.0, amount)])
        if terms != CASH:
            carry[terms] = amount
        day += 1


def _post_other(gl, month, loan) -> float:
    _post(gl, month, 28, f"DEP-{month}", "Depreciation", "Monthly depreciation",
          [(DEPRECIATION, MONTHLY_DEPRECIATION, 0.0), (ACCUM, 0.0, MONTHLY_DEPRECIATION)])
    interest = float(round(loan * LOAN_RATE / 12))
    _post(gl, month, 27, f"LOAN-{month}", "Bank Loan Servicing", "Loan payment",
          [(INTEREST, interest, 0.0), (LOAN, LOAN_PRINCIPAL, 0.0),
           (CASH, 0.0, interest + LOAN_PRINCIPAL)])
    _post(gl, month, 26, f"DIST-{month}", "Owner", "Owner distribution",
          [(DISTRIBUTIONS, DISTRIBUTION, 0.0), (CASH, 0.0, DISTRIBUTION)])
    if month == SUSPENSE_MONTH:
        _post(gl, month, 12, f"DEPX-{month}", "Unidentified deposit",
              "Deposit not matched to an invoice",
              [(CASH, SUSPENSE_AMOUNT, 0.0), (SUSPENSE, 0.0, SUSPENSE_AMOUNT)])
    return loan - LOAN_PRINCIPAL


def opening_balances(seed: int, subs: list[dict]) -> dict[str, float]:
    """Debit-positive balances at OPENING. Retained earnings is the plug that balances them."""
    hosting = vendor_amount(seed, "Hosting Provider", "Hosting and infrastructure", OPENING,
                            mrr(subs, OPENING))
    taxes = vendor_amount(seed, "Payroll Tax Agency", "Payroll taxes and benefits", OPENING, 0.0)
    unpaid = sum(a for _, a in _unpaid(billing(subs, OPENING)))
    bal = {CASH: OPENING_CASH, AR: unpaid, EQUIPMENT: OPENING_EQUIPMENT, ACCUM: OPENING_DEPRECIATION,
           AP: -hosting, ACCRUED: -taxes, LOAN: -OPENING_LOAN, SUSPENSE: 0.0, CAPITAL: -OPENING_CAPITAL,
           DISTRIBUTIONS: 0.0, NET_INCOME: 0.0}
    return {**bal, RETAINED: -sum(bal.values())}


def simulate(seed: int, subs: list[dict], opening: dict[str, float]) -> dict:
    """Post 27 months of double entries. Returns the ledger, sales, and vendor rows."""
    gl: list[dict] = []
    sales: list[dict] = []
    vendor_rows: list[dict] = []
    carry = {AR: opening[AR], AP: -opening[AP], ACCRUED: -opening[ACCRUED]}
    loan, unpaid = OPENING_LOAN, []
    for month in MONTHS:
        unpaid = _post_revenue(gl, sales, month, billing(subs, month), carry)
        _post_vendors(seed, gl, vendor_rows, month, mrr(subs, month), carry)
        loan = _post_other(gl, month, loan)
        carry[AR] = sum(a for _, a in unpaid)
    return {"gl": gl, "sales": sales, "vendor": vendor_rows, "unpaid": unpaid,
            "hosting": carry[AP]}


# ---- pass 2: statements from the ledger --------------------------------------------------

def _net_by_month(gl: list[dict]) -> dict[str, dict[str, float]]:
    net = {m: dict.fromkeys(ACCOUNTS, 0.0) for m in MONTHS}
    for line in gl:
        net[line["date"][:7]][line["account"]] += line["debit"] - line["credit"]
    return net


def _pl_rows(net) -> tuple[list[dict], dict[str, float]]:
    rows, income = [], {}
    for month in MONTHS:
        total = 0.0
        for account in PL_ACCOUNTS:
            kind = ACCOUNTS[account][0]
            amount = -net[month][account] if kind == "revenue" else net[month][account]
            total += amount if kind == "revenue" else -amount
            if amount:
                rows.append({"period": month, "account": account, "account_type": kind,
                             "amount": amount, "basis": "accrual"})
        income[month] = total
    return rows, income


def _bs_rows(net, opening, income) -> list[dict]:
    rows, running = [], dict(opening)
    for month in MONTHS:
        for account, amount in net[month].items():
            running[account] = running.get(account, 0.0) + amount
        year = month[:4]
        earlier = sum(v for m, v in income.items() if m[:4] < year)
        this_year = sum(v for m, v in income.items() if m[:4] == year and m <= month)
        special = {RETAINED: -opening[RETAINED] + earlier, NET_INCOME: this_year}
        for account in BS_ACCOUNTS:
            kind, subtype = ACCOUNTS[account]
            balance = special.get(account, running[account] * (1 if kind == "asset" else -1))
            rows.append({"period": month, "account": account, "account_type": kind,
                         "subtype": subtype, "balance": balance})
    return rows


def _bank_rows(gl, opening) -> list[dict]:
    rows, ending = [], opening[CASH]
    for month in MONTHS:
        cash = [ln for ln in gl if ln["account"] == CASH and ln["date"][:7] == month]
        deposits, withdrawals = sum(c["debit"] for c in cash), sum(c["credit"] for c in cash)
        rows.append({"account": CASH, "month": month, "beginning_balance": ending,
                     "deposits": deposits, "withdrawals": withdrawals,
                     "ending_balance": ending + deposits - withdrawals})
        ending += deposits - withdrawals
    return rows


def _aging_rows(sim) -> list[dict]:
    year, month = (int(p) for p in LAST.split("-"))
    rows = [{"type": "AR", "name": name, "invoice_date": f"{LAST}-01", "due_date": f"{LAST}-28",
             "amount": amount} for name, amount in sim["unpaid"]]
    rows.append({"type": "AP", "name": "Hosting Provider", "invoice_date": f"{LAST}-25",
                 "due_date": f"{year + month // 12}-{month % 12 + 1:02d}-25",
                 "amount": sim["hosting"]})
    return rows


def _tax_rows(pl_rows) -> list[dict]:
    def revenue(year: str) -> float:
        return sum(r["amount"] for r in pl_rows
                   if r["account_type"] == "revenue" and r["period"][:4] == year)

    return [{"year": "2024", "gross_receipts": float(round(revenue("2024") * 1.9))},
            {"year": "2025", "gross_receipts": float(round(revenue("2025") * 1.003))}]


def account_map() -> dict[str, dict]:
    return {a: {"account_type": t, **({"subtype": s} if s else {})} for a, (t, s) in ACCOUNTS.items()}


def build_company(seed: int = 7) -> dict:
    """The sample's canonical rows by kind, and its account map."""
    subs = make_subscriptions(random.Random(seed))
    opening = opening_balances(seed, subs)
    sim = simulate(seed, subs, opening)
    net = _net_by_month(sim["gl"])
    pl, income = _pl_rows(net)
    rows = {"pl": pl, "bs": _bs_rows(net, opening, income), "gl": sim["gl"],
            "bank": _bank_rows(sim["gl"], opening), "sales": sim["sales"], "vendor": sim["vendor"],
            "subs": subs, "aging": _aging_rows(sim), "tax": _tax_rows(pl)}
    return {"rows": rows, "account_map": account_map()}


# ---- output ---------------------------------------------------------------------------

def _state(company: dict, out: Path) -> dict:
    files = dict(DOCUMENT_FILES)
    for file_id, kind in FILE_KINDS.items():
        files[file_id] = {"status": "uploaded", "source_system": SOURCE_SYSTEMS[file_id],
                          "canonical_path": (out / f"{kind}.csv").as_posix()}
    return {**progress.new_state(), "company": COMPANY, "stage": 5, "intake": dict(INTAKE),
            "disclaimer_acknowledged": True, "modules": progress.active_modules(INTAKE),
            "modules_confirmed": True, "file_list_shown": True, "files": files,
            "account_map": company["account_map"], "account_map_confirmed": True}


def make_sample(out_dir: Path, seed: int = 7) -> Path:
    """Write the sample company to out_dir and return out_dir."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    company = build_company(seed)
    for kind, rows in company["rows"].items():
        canonical.write(kind, rows, out / f"{kind}.csv")
    state = _state(company, out)
    findings = run_checks.run(state, out, DATA_DIR) + run_checks.owner_findings(
        state, {"K12": K12_STATEMENT}, DATA_DIR)
    missing = set(RESPONSES) - {f["id"] for f in findings}
    if missing:
        raise ValueError(f"responses for findings that do not exist: {sorted(missing)}")
    state = {**state, "findings": findings, "responses": dict(RESPONSES),
             "adjustments": [dict(a) for a in ADJUSTMENTS]}
    progress.save(state, out / "progress.json")
    build_workbook.build(state, out, DATA_DIR, out / WORKBOOK_NAME)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the synthetic Sample SaaS Co.")
    parser.add_argument("out_dir", type=Path, help="folder to write")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args(argv)
    print(make_sample(args.out_dir, args.seed))
    return 0


if __name__ == "__main__":
    sys.exit(main())
