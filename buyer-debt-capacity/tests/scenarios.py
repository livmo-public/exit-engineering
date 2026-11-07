"""Scenario inputs for the Results recalculation tests. Each one starts from base()."""
from __future__ import annotations

from calc_math import Addback, Deduction, Inputs, default_inputs, evaluate, load_facts

from base_inputs import base

FACTS = load_facts()
BASE_ANSWERS = ("no", "no", "no", "no", "yes", "no")
NO_OPERATOR = ("no", "no", "no", "no", "no", "no")


def _ask_for_coverage(coverage: float) -> float:
    """Return a whole-dollar asking price that gives this coverage at the base terms.

    Coverage = cash / (price * service), and the supported price gives the target coverage.
    """
    inputs = base()
    supported = evaluate(inputs, FACTS).supported_price
    return float(round(supported * inputs.coverage_target / coverage))


SCENARIOS: dict[str, Inputs] = {
    "base": base(),
    "blank_file": default_inputs(FACTS),
    # Blocks
    "missing_net_profit": base(net_profit=None),
    "missing_net_profit_low_cash": base(net_profit=None, capex=800_000.0),
    "missing_answer": base(answers=("no", "no", None, "no", "yes", "no")),
    "missing_answer_and_no_cash": base(answers=("no", "no", None, "no", "yes", "no"), capex=800_000.0),
    "answer_not_yes_no": base(answers=("no", "maybe", "no", "no", "yes", "no")),
    "answers_mixed_case": base(answers=("No", "NO", "no", "No", "Yes", "nO")),
    "operator_blank": base(operator_salary=None),
    "operator_blank_no_operator": base(operator_salary=None, answers=NO_OPERATOR),
    "operator_zero_no_operator": base(operator_salary=0.0, answers=NO_OPERATOR),
    "operator_zero_in_place": base(operator_salary=0.0),
    "seller_missing_terms": base(seller_pct=0.10, seller_rate=None),
    "seller_missing_standby": base(seller_pct=0.10, seller_standby=None),
    "seller_missing_years": base(seller_pct=0.10, seller_standby="no", seller_years=None),
    "missing_bank_term": base(bank_years=None),
    "pct_as_whole_number": base(down_pct=10.0),
    "shares_over_100": base(down_pct=0.6, seller_pct=0.5),
    "rate_whole_number": base(bank_rate=10.5),
    "seller_rate_whole_number": base(seller_pct=0.10, seller_standby="no", seller_rate=6.0),
    "coverage_too_high": base(coverage_target=6.0),
    "term_in_months": base(bank_years=120.0),
    "seller_term_in_months": base(seller_pct=0.10, seller_standby="no", seller_years=120.0),
    "no_cash": base(capex=800_000.0),
    "missing_and_bad_terms": base(period_end=None, bank_rate=-0.01),
    # Warnings
    "operator_low": base(operator_salary=100_000.0),
    "heavy": base(answers=("yes", "yes", "yes", "no", "yes", "no")),
    "heavy_and_blocked": base(answers=("yes", "yes", "yes", "yes", "no", "yes"), capex=None),
    "proof_missing": base(addbacks=(
        Addback("other", 20_000.0, "no"), Addback("personal expense", 8_000.0, "NO"),
        Addback("one-time cost", 5_000.0, "yes"),
    )),
    "proof_one": base(addbacks=(Addback("other", 20_000.0, "no"), Addback("one-time cost", 5_000.0, None))),
    "deduction_one_time": base(deductions=(Deduction("one-time income", 30_000.0),)),
    "deduction_below_market": base(deductions=(Deduction("below-market cost", 12_000.0),)),
    "sba_down": base(down_pct=0.05),
    "sba_term": base(bank_years=25.0),
    "sba_coverage": base(coverage_target=1.15),
    "sba_standby": base(seller_pct=0.10, seller_standby="yes"),
    "sba_all": base(down_pct=0.05, bank_years=25.0, coverage_target=1.15, seller_pct=0.10,
                    seller_standby="Yes", asking_price=3_500_000.0),
    # Debt capacity
    "seller_standby": base(seller_pct=0.05, seller_standby="yes"),
    "seller_paid": base(seller_pct=0.15, seller_standby="no"),
    "seller_paid_mixed_case": base(seller_pct=0.15, seller_standby="No"),
    "rate_zero": base(bank_rate=0.0),
    "unlimited_price": base(down_pct=0.5, seller_pct=0.5, seller_standby="yes"),
    "unlimited_price_with_ask": base(down_pct=0.5, seller_pct=0.5, seller_standby="yes",
                                     asking_price=1_000_000.0),
    # Asking price
    "ask_zero": base(asking_price=0.0),
    "ask_tight_low_edge": base(asking_price=_ask_for_coverage(1.25)),
    "ask_tight_high_edge": base(asking_price=_ask_for_coverage(1.40)),
    "ask_financeable": base(asking_price=_ask_for_coverage(1.41)),
    "ask_not_financeable": base(asking_price=_ask_for_coverage(1.24)),
    # Flags
    "qoe_at_3m": base(asking_price=3_000_000.0),
    "qoe_below_3m": base(asking_price=2_999_999.0),
    "loan_limit": base(loan_limit=2_000_000.0),
}

# Facts with every value removed: no SBA warning and no QoE flag can fire.
NULL_FACTS = {key: ({**entry, "value": None} if isinstance(entry, dict) else entry)
              for key, entry in FACTS.items()}
