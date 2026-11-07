"""Reference math for the Buyer Debt Capacity Calculator.

The spreadsheet formulas must give the same results as `evaluate`. Tests compare them.
None means a blank cell.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

FACTS_PATH = Path(__file__).with_name("sba_facts.json")
MAX_ADDBACKS = 25
MAX_DEDUCTIONS = 10
QUESTION_COUNT = 6
HEAVY_SCORE = 3
OPERATOR_LOW_SHARE = 0.5
TIGHT_BAND = 0.15
SBA_SUFFIX = "for an SBA 7(a) loan."
MAX_RATE = 1.0
MAX_COVERAGE_TARGET = 5
MAX_TERM_YEARS = 40
ZERO_RATE = 1e-12
BANK_SHARE_DIGITS = 9  # Rounding removes the float residual of 1 - down - seller (Excel shows 0).

STATUS_NO = "Not financeable at these terms"
STATUS_TIGHT = "Tight"
STATUS_YES = "Financeable"

MESSAGES: dict[str, str] = {
    # Blocks
    "missing_inputs": 'Fill in every required input. Each blank required cell shows "Required" next to it.',
    "missing_answers": "Answer all six questions on the Owner role tab.",
    "operator_blank": "Enter an operator salary on the Owner role tab.",
    "operator_zero": (
        "Enter an operator salary above zero. With no general manager or operator in place, "
        "a buyer must pay someone to run the business."
    ),
    "bad_terms": (
        "Check the deal terms. The down payment and seller note must add up to 100% or less. "
        "Enter percents as percents (10%, not 10). Enter terms in years. "
        "Terms and the coverage target must be above zero, and rates cannot be negative. "
        "A rate above 100%, a coverage target above 5, or a term above 40 years is probably a typing slip."
    ),
    "no_cash": "No cash is available for debt at these numbers.",
    # Warnings
    "operator_in_place": (
        "No operator salary, because an operator is already in place. Make sure their pay is in the P&L."
    ),
    "operator_low": (
        "The operator salary is less than half of the owner pay that it replaces. "
        "Check that it covers all of the owners' work."
    ),
    "heavy": "Heavy owner dependence. Buyers and lenders usually ask for a transition period with the seller.",
    "proof": "{n} {noun} no proof on file. A lender asks for proof of each add-back.",
    "sba_down": "The down payment is below the {down} minimum equity injection " + SBA_SUFFIX,
    "sba_term": "The bank loan term is longer than the {term}-year maximum term " + SBA_SUFFIX,
    "sba_coverage": "The coverage target is below the {coverage} minimum debt service coverage " + SBA_SUFFIX,
    "sba_standby": (
        "The standby seller note is above {limit} of the price. "
        "A standby note can cover at most {share} of the required equity injection " + SBA_SUFFIX
    ),
    # Flags
    "qoe": "{flag_text} See the QoE Readiness skill in this repo to prepare.",
    "loan_limit": "The bank loan at this price is above the loan limit on the Deal terms tab.",
}
BLOCK_CODES = ("missing_inputs", "missing_answers", "operator_blank", "operator_zero", "bad_terms", "no_cash")
WARNING_CODES = (
    "operator_in_place", "operator_low", "heavy", "proof",
    "sba_down", "sba_term", "sba_coverage", "sba_standby",
)
FLAG_CODES = ("qoe", "loan_limit")
MESSAGE_ORDER: tuple[str, ...] = BLOCK_CODES + WARNING_CODES + FLAG_CODES


@dataclass(frozen=True)
class Addback:
    category: str
    amount: float | None
    proof: str | None  # "yes", "no", or None


@dataclass(frozen=True)
class Deduction:
    category: str
    amount: float | None


@dataclass(frozen=True)
class Inputs:
    period_basis: str | None
    period_end: str | None
    revenue: float | None
    net_profit: float | None
    interest: float | None
    income_taxes: float | None
    depreciation: float | None
    amortization: float | None
    owner_pay: float | None
    addbacks: tuple[Addback, ...]
    deductions: tuple[Deduction, ...]
    answers: tuple[str | None, ...]
    operator_salary: float | None
    capex: float | None
    down_pct: float | None
    seller_pct: float | None
    seller_standby: str | None
    seller_rate: float | None
    seller_years: float | None
    bank_rate: float | None
    bank_years: float | None
    coverage_target: float | None
    asking_price: float | None
    loan_limit: float | None

    def __post_init__(self) -> None:
        if len(self.addbacks) > MAX_ADDBACKS:
            raise ValueError(f"At most {MAX_ADDBACKS} add-backs.")
        if len(self.deductions) > MAX_DEDUCTIONS:
            raise ValueError(f"At most {MAX_DEDUCTIONS} deductions.")
        if len(self.answers) != QUESTION_COUNT:
            raise ValueError(f"Exactly {QUESTION_COUNT} answers.")


@dataclass(frozen=True)
class Result:
    ebitda: float | None
    total_addbacks: float | None
    total_deductions: float | None
    cash_available: float | None
    max_debt_service: float | None
    supported_price: float | None
    max_bank_loan: float | None
    coverage_at_ask: float | None
    price_gap: float | None
    price_used: float | None
    bank_loan_at_price: float | None
    status: str | None
    dependence_score: int | None
    heavy: bool | None
    proof_missing: int
    blocks: tuple[str, ...]
    warnings: tuple[str, ...]
    flags: tuple[str, ...]


def load_facts(path: Path | None = None) -> dict:
    return json.loads((path or FACTS_PATH).read_text(encoding="utf-8"))


def annuity_factor(rate: float, years: float) -> float:
    """Annual payment per $1 of a monthly-payment loan."""
    if abs(rate) < ZERO_RATE:
        return 1 / years
    monthly = rate / 12
    return 12 * monthly / (1 - (1 + monthly) ** (-12 * years))


def xl_round(value: float, digits: int) -> float:
    """Round half away from zero, like the spreadsheet ROUND."""
    quantum = Decimal(1).scaleb(-digits)
    return float(Decimal(repr(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def fact_value(facts: dict, key: str):
    entry = facts.get(key)
    return None if entry is None else entry.get("value")


def default_inputs(facts: dict) -> Inputs:
    return Inputs(
        period_basis=None, period_end=None, revenue=None, net_profit=None, interest=None,
        income_taxes=None, depreciation=None, amortization=None, owner_pay=None,
        addbacks=(), deductions=(), answers=(None,) * QUESTION_COUNT, operator_salary=None,
        capex=None,
        down_pct=_or(fact_value(facts, "min_equity_injection"), 0.10),
        seller_pct=0.0,
        seller_standby="yes",
        seller_rate=0.06,
        seller_years=10,
        bank_rate=0.105,
        bank_years=_or(fact_value(facts, "max_term_years_no_real_estate"), 10),
        coverage_target=_or(fact_value(facts, "coverage_change_of_ownership"), 1.25),
        asking_price=None,
        loan_limit=_or(fact_value(facts, "max_loan"), 5_000_000),
    )


def _or(value, fallback):
    return fallback if value is None else value


def _word(text: str | None) -> str | None:
    """Return "yes" or "no" for those answers in any case. Any other text is blank.

    Surrounding spaces are not removed, because the sheet cannot remove them (no TRIM).
    """
    word = (text or "").lower()
    return word if word in ("yes", "no") else None


def _sum_amounts(rows) -> float:
    return sum(row.amount or 0 for row in rows)


def _blank_result(**kept) -> dict:
    values = dict.fromkeys(
        ("ebitda", "total_addbacks", "total_deductions", "cash_available", "max_debt_service",
         "supported_price", "max_bank_loan", "coverage_at_ask", "price_gap", "price_used",
         "bank_loan_at_price", "status"),
    )
    values.update(kept)
    return values


def _cash_inputs_complete(i: Inputs) -> bool:
    fields = (i.net_profit, i.interest, i.income_taxes, i.depreciation, i.amortization,
              i.owner_pay, i.operator_salary, i.capex)
    return all(f is not None for f in fields)


def _missing_inputs(i: Inputs) -> bool:
    required = (i.period_basis, i.period_end, i.net_profit, i.interest, i.income_taxes,
                i.depreciation, i.amortization, i.owner_pay, i.capex, i.down_pct, i.seller_pct,
                i.bank_rate, i.bank_years, i.coverage_target, i.loan_limit)
    if any(f is None or f == "" for f in required):
        return True
    if i.seller_pct > 0:
        return (i.seller_rate is None or i.seller_years is None
                or _word(i.seller_standby) is None)
    return False


def _bad_terms(i: Inputs) -> bool:
    if None in (i.down_pct, i.seller_pct, i.bank_rate, i.bank_years, i.coverage_target):
        return False
    bad = (
        not 0 <= i.down_pct <= 1
        or not 0 <= i.seller_pct <= 1
        or i.down_pct + i.seller_pct > 1
        or i.bank_years <= 0
        or i.coverage_target <= 0
        or i.bank_rate < 0
        or i.bank_rate > MAX_RATE
        or i.coverage_target > MAX_COVERAGE_TARGET
        or i.bank_years > MAX_TERM_YEARS
    )
    if i.seller_pct > 0 and i.seller_rate is not None and i.seller_years is not None:
        bad = (bad or i.seller_rate < 0 or i.seller_rate > MAX_RATE
               or i.seller_years <= 0 or i.seller_years > MAX_TERM_YEARS)
    return bad


def _ordered(codes: set[str]) -> tuple[str, ...]:
    return tuple(code for code in MESSAGE_ORDER if code in codes)


def _sba_warnings(i: Inputs, facts: dict) -> set[str]:
    codes: set[str] = set()
    min_down = fact_value(facts, "min_equity_injection")
    max_term = fact_value(facts, "max_term_years_no_real_estate")
    coverage = fact_value(facts, "coverage_change_of_ownership")
    share = fact_value(facts, "standby_note_max_share_of_injection")
    if min_down is not None and i.down_pct < min_down:
        codes.add("sba_down")
    if max_term is not None and i.bank_years > max_term:
        codes.add("sba_term")
    if coverage is not None and i.coverage_target < coverage:
        codes.add("sba_coverage")
    if (share is not None and min_down is not None and _word(i.seller_standby) == "yes"
            and i.seller_pct > share * min_down):
        codes.add("sba_standby")
    return codes


def _flags(i: Inputs, facts: dict, price_used: float | None, bank_loan: float | None) -> set[str]:
    codes: set[str] = set()
    qoe = fact_value(facts, "qoe")
    if qoe is not None:
        basis = price_used if qoe["basis"] == "price" else bank_loan
        if basis is not None and basis >= qoe["amount"]:
            codes.add("qoe")
    if bank_loan is not None and bank_loan > i.loan_limit:
        codes.add("loan_limit")
    return codes


def evaluate(inputs: Inputs, facts: dict) -> Result:
    i = inputs
    answers = tuple(_word(a) for a in i.answers)
    answers_complete = None not in answers
    score = heavy = None
    if answers_complete:
        score = sum(1 for n, a in enumerate(answers, start=1)
                    if (a == "no" if n == 5 else a == "yes"))
        heavy = score >= HEAVY_SCORE
    proof_missing = sum(1 for row in i.addbacks if _word(row.proof) == "no")

    blocks: set[str] = set()
    if _missing_inputs(i):
        blocks.add("missing_inputs")
    if not answers_complete:
        blocks.add("missing_answers")
    if i.operator_salary is None:
        blocks.add("operator_blank")
    elif i.operator_salary == 0 and answers[4] == "no":
        blocks.add("operator_zero")
    if _bad_terms(i):
        blocks.add("bad_terms")

    numbers = _blank_result()
    if _cash_inputs_complete(i):
        ebitda = i.net_profit + i.interest + i.income_taxes + i.depreciation + i.amortization
        total_addbacks = i.owner_pay + _sum_amounts(i.addbacks)
        total_deductions = _sum_amounts(i.deductions)
        cash = ebitda + total_addbacks - total_deductions - i.operator_salary - i.capex
        kept = dict(ebitda=ebitda, total_addbacks=total_addbacks,
                    total_deductions=total_deductions, cash_available=cash)
        if cash <= 0:
            blocks.add("no_cash")
        if blocks <= {"no_cash"}:
            numbers.update(kept)

    warnings: set[str] = set()
    flags: set[str] = set()
    if heavy:
        warnings.add("heavy")
    if proof_missing:
        warnings.add("proof")

    if not blocks:
        numbers.update(_debt_capacity(i, numbers["cash_available"]))
        if i.operator_salary == 0:
            warnings.add("operator_in_place")
        elif i.operator_salary < OPERATOR_LOW_SHARE * i.owner_pay:
            warnings.add("operator_low")
        warnings |= _sba_warnings(i, facts)
        flags = _flags(i, facts, numbers["price_used"], numbers["bank_loan_at_price"])

    return Result(
        **numbers,
        dependence_score=score, heavy=heavy, proof_missing=proof_missing,
        blocks=_ordered(blocks), warnings=_ordered(warnings), flags=_ordered(flags),
    )


def bank_share_of(i: Inputs) -> float:
    """Bank loan share of price, rounded like the sheet cell =ROUND(1-down-seller, 9)."""
    return xl_round(1 - i.down_pct - i.seller_pct, BANK_SHARE_DIGITS)


def _debt_capacity(i: Inputs, cash: float) -> dict:
    bank_share = bank_share_of(i)
    seller_factor = 0.0
    if i.seller_pct > 0 and _word(i.seller_standby) == "no":
        seller_factor = annuity_factor(i.seller_rate, i.seller_years)
    service = bank_share * annuity_factor(i.bank_rate, i.bank_years) + i.seller_pct * seller_factor
    max_service = cash / i.coverage_target
    asking = i.asking_price if i.asking_price and i.asking_price > 0 else None

    supported = max_service / service if service > 0 else None
    out = dict(
        max_debt_service=max_service,
        supported_price=supported,
        max_bank_loan=None if supported is None else supported * bank_share,
        coverage_at_ask=None, price_gap=None, status=None,
    )
    price_used = asking if asking is not None else supported
    out["price_used"] = price_used
    out["bank_loan_at_price"] = None if price_used is None else price_used * bank_share
    if asking is not None:
        out["price_gap"] = None if supported is None else asking - supported
        if service > 0:
            coverage = cash / (asking * service)
            out["coverage_at_ask"] = coverage
            out["status"] = _status(coverage, i.coverage_target)
        else:
            out["status"] = STATUS_YES
    return out


def _status(coverage: float, target: float) -> str:
    shown = xl_round(coverage, 2)
    if shown < xl_round(target, 2):
        return STATUS_NO
    if shown <= xl_round(target + TIGHT_BAND, 2):
        return STATUS_TIGHT
    return STATUS_YES


def _percent(value: float) -> str:
    return f"{value * 100:g}%"


def message_text(code: str, inputs: Inputs, result: Result, facts: dict) -> str:
    """Return the text for one message code, with the proof count and SOP values filled in."""
    template = MESSAGES[code]
    if code == "proof":
        n = result.proof_missing
        return template.format(n=n, noun="add-back has" if n == 1 else "add-backs have")
    if code == "qoe":
        return template.format(flag_text=facts["qoe"]["flag_text"])
    if code.startswith("sba_"):
        down = fact_value(facts, "min_equity_injection")
        share = fact_value(facts, "standby_note_max_share_of_injection")
        term = fact_value(facts, "max_term_years_no_real_estate")
        coverage = fact_value(facts, "coverage_change_of_ownership")
        return template.format(
            down="" if down is None else _percent(down),
            term="" if term is None else f"{term:g}",
            coverage="" if coverage is None else f"{coverage:g}",
            share="" if share is None else _percent(share),
            limit="" if None in (share, down) else _percent(share * down),
        )
    return template
