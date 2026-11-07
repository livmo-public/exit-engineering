from dataclasses import replace

import pytest

from base_inputs import base
from calc_math import (
    MESSAGE_ORDER,
    MESSAGES,
    STATUS_YES,
    Addback,
    Deduction,
    annuity_factor,
    xl_round,
    default_inputs,
    evaluate,
    load_facts,
    message_text,
)

FACTS = load_facts()
BANK = annuity_factor(0.105, 10)
NUMBER_FIELDS = (
    "max_debt_service", "supported_price", "max_bank_loan", "coverage_at_ask",
    "price_gap", "price_used", "bank_loan_at_price",
)


def run(**overrides):
    return evaluate(base(**overrides), FACTS)


def facts_without(*keys):
    return {**FACTS, **{k: None for k in keys}}


def test_annuity_factor_matches_formula():
    expected = 12 * (0.105 / 12) / (1 - (1 + 0.105 / 12) ** -120)
    assert annuity_factor(0.105, 10) == pytest.approx(expected, abs=1e-12)
    assert annuity_factor(0, 10) == 0.1


def test_cash_available_steps():
    r = run()
    assert r.ebitda == 380000
    assert r.total_addbacks == 270000
    assert r.total_deductions == 0
    assert r.cash_available == 380000 + 270000 - 0 - 150000 - 25000 == 475000
    assert r.blocks == ()


@pytest.mark.parametrize("category", ["one-time income", "below-market cost", "other"])
def test_deductions_reduce_cash(category):
    r = run(deductions=(Deduction(category, 50_000.0),))
    assert r.total_deductions == 50000
    assert r.cash_available == 475000 - 50000


def test_supported_price():
    r = run()
    assert r.max_debt_service == pytest.approx(475000 / 1.25)
    assert r.supported_price == pytest.approx(r.max_debt_service / (0.9 * BANK))
    assert r.max_bank_loan == pytest.approx(r.supported_price * 0.9)


def test_seller_note_standby_excluded_and_included():
    standby = run(seller_pct=0.05, seller_standby="yes")
    per_dollar = 0.85 * BANK
    assert standby.supported_price == pytest.approx(standby.max_debt_service / per_dollar)
    paying = run(seller_pct=0.05, seller_standby="no")
    per_dollar = 0.85 * BANK + 0.05 * annuity_factor(0.06, 10)
    assert paying.supported_price == pytest.approx(paying.max_debt_service / per_dollar)


@pytest.mark.parametrize(
    "cov, status",
    [
        (1.24, "Not financeable at these terms"),
        (1.25, "Tight"),
        (1.40, "Tight"),
        (1.41, "Financeable"),
    ],
)
def test_status_bands(cov, status):
    cash = run().cash_available
    ask = cash / (cov * 0.9 * BANK)
    r = run(asking_price=ask)
    assert round(r.coverage_at_ask, 2) == cov
    assert r.status == status


def test_price_gap():
    r = run(asking_price=2_000_000.0)
    assert r.price_gap == pytest.approx(2_000_000 - r.supported_price)
    assert r.price_used == 2_000_000


def test_zero_asking_price_is_blank():
    r = run(asking_price=0.0)
    assert r.coverage_at_ask is None
    assert r.status is None
    assert r.price_gap is None
    assert r.price_used == r.supported_price


def test_no_debt_service_means_no_price_limit():
    r = run(down_pct=0.9, seller_pct=0.1, seller_standby="yes", asking_price=1_000_000.0)
    assert r.blocks == ()
    assert r.supported_price is None
    assert r.max_bank_loan is None
    assert r.coverage_at_ask is None
    assert r.status == "Financeable"


REQUIRED = (
    "period_basis", "period_end", "net_profit", "interest", "income_taxes",
    "depreciation", "amortization", "owner_pay", "capex", "down_pct",
    "seller_pct", "bank_rate", "bank_years", "coverage_target", "loan_limit",
)


@pytest.mark.parametrize("field", REQUIRED)
def test_each_required_blank_blocks(field):
    r = run(**{field: None})
    assert "missing_inputs" in r.blocks
    assert r.status is None
    for name in ("ebitda", "total_addbacks", "total_deductions", "cash_available") + NUMBER_FIELDS:
        assert getattr(r, name) is None


def test_blank_revenue_does_not_block():
    assert run(revenue=None).blocks == ()


def test_seller_details_required_only_with_note():
    assert "missing_inputs" not in run(seller_rate=None, seller_pct=0.0).blocks
    assert "missing_inputs" in run(seller_rate=None, seller_pct=0.05).blocks
    assert "missing_inputs" in run(seller_years=None, seller_pct=0.05).blocks
    assert "missing_inputs" in run(seller_standby=None, seller_pct=0.05).blocks


def test_blank_answer_blocks():
    r = run(answers=("no", "no", None, "no", "yes", "no"))
    assert "missing_answers" in r.blocks
    assert r.dependence_score is None
    assert r.heavy is None


def test_answer_case_is_ignored():
    plain = run(answers=("yes", "yes", "yes", "no", "yes", "no"))
    for word in ("Yes", "YES"):
        r = run(answers=(word, word, word, "no", "yes", "no"))
        assert r.dependence_score == plain.dependence_score == 3
        assert r.blocks == ()
    r = run(answers=("y", "no", "no", "no", "yes", "no"))
    assert "missing_answers" in r.blocks


def test_operator_blank_blocks():
    assert "operator_blank" in run(operator_salary=None).blocks


def test_operator_zero_without_operator_blocks():
    r = run(operator_salary=0.0, answers=("no",) * 6)
    assert "operator_zero" in r.blocks
    assert r.cash_available is None


def test_operator_zero_with_operator_in_place():
    r = run(operator_salary=0.0)
    assert r.blocks == ()
    assert r.cash_available == 625000
    assert "operator_in_place" in r.warnings


def test_operator_low_warning():
    assert "operator_low" in run(operator_salary=100_000.0).warnings
    assert "operator_low" not in run(operator_salary=125_000.0).warnings


def test_dependence_score_and_heavy():
    r = run(answers=("yes", "yes", "yes", "no", "yes", "no"))
    assert r.dependence_score == 3
    assert r.heavy is True
    assert "heavy" in r.warnings
    r = run(answers=("no", "no", "no", "no", "yes", "no"))
    assert r.dependence_score == 0
    assert r.heavy is False
    r = run(answers=("no", "no", "no", "no", "no", "no"))
    assert r.dependence_score == 1


def test_proof_missing_counted():
    """A row counts when its amount is above 0 and its proof is not "yes": blank, "no", or other text."""
    r = run(addbacks=(Addback("other", 1.0, "no"), Addback("other", 2.0, "NO"),
                      Addback("other", 3.0, "yes"), Addback("other", 4.0, None),
                      Addback("other", 5.0, "YES"), Addback("other", 6.0, "maybe")))
    assert r.proof_missing == 4
    assert "proof" in r.warnings


def test_proof_ignores_rows_without_an_amount():
    r = run(addbacks=(Addback("other", 0.0, None), Addback("other", None, "no"),
                      Addback("other", 0.0, "no"), Addback("other", 10.0, "yes")))
    assert r.proof_missing == 0
    assert "proof" not in r.warnings


def test_percent_typed_as_whole_number_blocks():
    r = run(down_pct=10.0)
    assert "bad_terms" in r.blocks
    assert r.supported_price is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"bank_years": 0.0},
        {"coverage_target": 0.0},
        {"bank_rate": -0.01},
        {"down_pct": 0.8, "seller_pct": 0.3},
        {"seller_pct": 0.05, "seller_years": 0.0},
        {"seller_pct": 0.05, "seller_rate": -0.01},
        {"bank_rate": 10.5},
        {"bank_rate": 1.01},
        {"seller_pct": 0.05, "seller_rate": 6.0},
        {"coverage_target": 5.01},
        {"coverage_target": 125.0},
        {"bank_years": 41.0},
        {"seller_pct": 0.05, "seller_years": 41.0},
    ],
)
def test_bad_terms(overrides):
    assert "bad_terms" in run(**overrides).blocks


def test_upper_limits_do_not_block():
    r = run(bank_rate=0.25, coverage_target=5.0, bank_years=40.0,
            seller_pct=0.05, seller_rate=1.0, seller_years=40.0)
    assert "bad_terms" not in r.blocks


def test_seller_limits_ignored_without_note():
    assert "bad_terms" not in run(seller_pct=0.0, seller_rate=6.0, seller_years=99.0).blocks


def test_tiny_rate_is_zero_rate():
    assert annuity_factor(1e-20, 10) == pytest.approx(0.1)
    assert annuity_factor(1e-13, 10) == pytest.approx(0.1)


def test_status_rounds_half_up():
    assert xl_round(1.245, 2) == 1.25
    assert xl_round(-1.245, 2) == -1.25
    cash_only = dict(net_profit=1245.0, interest=0.0, income_taxes=0.0, depreciation=0.0,
                     amortization=0.0, owner_pay=0.0, addbacks=(), operator_salary=0.0,
                     capex=0.0, down_pct=0.0, seller_pct=0.0, bank_rate=0.0, bank_years=1.0)
    r = run(asking_price=1000.0, **cash_only)
    assert r.blocks == ()
    assert r.coverage_at_ask == 1.245
    assert r.status == "Tight"


def test_no_cash_blocks():
    r = run(operator_salary=900_000.0)
    assert r.blocks == ("no_cash",)
    assert r.cash_available == 380000 + 270000 - 900000 - 25000
    assert r.ebitda == 380000
    assert r.total_addbacks == 270000
    assert r.total_deductions == 0
    assert r.supported_price is None
    assert r.status is None


def test_qoe_flag_threshold():
    assert "qoe" in run(asking_price=3_000_000.0).flags
    assert "qoe" not in run(asking_price=2_999_999.0).flags
    big = run(net_profit=2_000_000.0)
    assert big.supported_price >= 3_000_000
    assert "qoe" in big.flags
    assert "qoe" not in evaluate(base(asking_price=3_000_000.0), facts_without("qoe")).flags
    loan_basis = {**FACTS, "qoe": {**FACTS["qoe"], "value": {"amount": 2_000_000, "basis": "loan"}}}
    assert "qoe" in evaluate(base(asking_price=2_300_000.0), loan_basis).flags
    assert "qoe" not in evaluate(base(asking_price=2_200_000.0), loan_basis).flags


def test_loan_limit_flag():
    assert "loan_limit" in run(asking_price=6_000_000.0).flags
    assert "loan_limit" not in run(asking_price=1_000_000.0).flags


def test_flags_blocked_with_blocks():
    assert run(asking_price=6_000_000.0, capex=None).flags == ()


def test_sba_warnings():
    f = FACTS
    down = f["min_equity_injection"]["value"]
    assert "sba_down" in run(down_pct=down - 0.01).warnings
    assert "sba_down" not in run(down_pct=down).warnings
    term = f["max_term_years_no_real_estate"]["value"]
    assert "sba_term" in run(bank_years=term + 1).warnings
    assert "sba_term" not in run(bank_years=term).warnings
    cov = f["coverage_change_of_ownership"]["value"]
    assert "sba_coverage" in run(coverage_target=cov - 0.05).warnings
    assert "sba_coverage" not in run(coverage_target=cov).warnings


SBA_EQUITY = ("sba_down", "sba_standby")


@pytest.mark.parametrize(
    "down, seller, standby, expected",
    [
        # The standby rule limits how much of the note counts as equity, not the note size.
        (0.10, 0.10, "yes", set()),
        (0.90, 0.10, "yes", set()),
        (0.05, 0.05, "yes", set()),
        (0.10, 0.30, "yes", set()),
        # The note is needed for the 10%, but the down payment is below the required half (5%).
        (0.04, 0.10, "yes", {"sba_down", "sba_standby"}),
        (0.01, 0.30, "Yes", {"sba_down", "sba_standby"}),
        (0.03, 0.07, "yes", {"sba_down", "sba_standby"}),
        # The note is too small to reach the 10%, so only the equity warning shows.
        (0.03, 0.03, "yes", {"sba_down"}),
        # A paid seller note does not count as equity.
        (0.05, 0.10, "no", {"sba_down"}),
        (0.05, 0.0, "yes", {"sba_down"}),
        (0.10, 0.0, "yes", set()),
    ],
)
def test_sba_equity_warnings(down, seller, standby, expected):
    r = run(down_pct=down, seller_pct=seller, seller_standby=standby)
    assert r.blocks == ()
    assert {c for c in r.warnings if c in SBA_EQUITY} == expected


@pytest.mark.parametrize(
    "key, overrides, code",
    [
        ("min_equity_injection", {"down_pct": 0.01}, "sba_down"),
        ("max_term_years_no_real_estate", {"bank_years": 30.0}, "sba_term"),
        ("coverage_change_of_ownership", {"coverage_target": 0.5}, "sba_coverage"),
        ("standby_note_max_share_of_injection", {"down_pct": 0.02, "seller_pct": 0.3}, "sba_standby"),
        ("min_equity_injection", {"down_pct": 0.02, "seller_pct": 0.3}, "sba_standby"),
    ],
)
def test_null_fact_gives_no_sba_warning(key, overrides, code):
    r = evaluate(base(**overrides), facts_without(key))
    assert code not in r.warnings


def test_message_order_is_fixed():
    r = run(
        operator_salary=100_000.0,
        answers=("yes", "yes", "yes", "no", "yes", "no"),
        addbacks=(Addback("other", 1.0, "no"),),
        down_pct=0.01, bank_years=30.0, coverage_target=1.0,
        seller_pct=0.3, seller_standby="yes",
        asking_price=9_000_000.0,
    )
    for group in (r.warnings, r.flags):
        assert len(group) >= 2
        assert list(group) == sorted(group, key=MESSAGE_ORDER.index)
    assert r.warnings == ("operator_low", "heavy", "proof", "sba_down", "sba_term",
                          "sba_coverage", "sba_standby")
    blocked = run(net_profit=None, answers=(None,) * 6, operator_salary=None,
                  down_pct=10.0)
    assert blocked.blocks == ("missing_inputs", "missing_answers", "operator_blank", "bad_terms")
    blocked = run(net_profit=None, capex=-1.0, answers=(None,) * 6, down_pct=10.0)
    assert blocked.blocks == ("missing_inputs", "negative_inputs", "missing_answers", "bad_terms")
    assert MESSAGE_ORDER[:2] == ("missing_inputs", "negative_inputs")
    assert set(MESSAGE_ORDER) == set(MESSAGES)


def test_default_inputs_use_facts():
    d = default_inputs(FACTS)
    assert d.coverage_target == FACTS["coverage_change_of_ownership"]["value"]
    assert d.down_pct == FACTS["min_equity_injection"]["value"]
    assert d.bank_years == FACTS["max_term_years_no_real_estate"]["value"]
    assert d.loan_limit == FACTS["max_loan"]["value"]
    nulls = {k: None for k in ("coverage_change_of_ownership", "min_equity_injection",
                               "max_term_years_no_real_estate", "max_loan")}
    d = default_inputs({**FACTS, **nulls})
    assert (d.coverage_target, d.down_pct, d.bank_years, d.loan_limit) == (1.25, 0.10, 10, 5_000_000)
    assert d.net_profit is None and d.capex is None and d.operator_salary is None
    assert d.answers == (None,) * 6
    assert (d.seller_pct, d.seller_standby, d.seller_rate, d.seller_years, d.bank_rate) == (0.0, "yes", 0.06, 10, 0.105)


def test_blank_defaults_block_with_missing_inputs():
    assert "missing_inputs" in evaluate(default_inputs(FACTS), FACTS).blocks


def test_input_size_limits():
    with pytest.raises(ValueError):
        base(addbacks=tuple(Addback("other", 1.0, "yes") for _ in range(26)))
    with pytest.raises(ValueError):
        base(deductions=tuple(Deduction("other", 1.0) for _ in range(11)))
    with pytest.raises(ValueError):
        base(answers=("yes",) * 5)


def test_message_text_carries_values():
    r = run(addbacks=(Addback("other", 1.0, "no"),), down_pct=0.05)
    i = base(addbacks=(Addback("other", 1.0, "no"),), down_pct=0.05)
    assert message_text("proof", i, r, FACTS).startswith("1 add-back has no proof")
    two = replace(i, addbacks=(Addback("other", 1.0, "no"),) * 2)
    assert message_text("proof", two, evaluate(two, FACTS), FACTS).startswith("2 add-backs have no proof")
    down = message_text("sba_down", i, r, FACTS)
    assert down.startswith("The buyer's equity is below the 10% minimum equity injection for an SBA 7(a) loan.")
    assert "up to 50% of the required injection" in down
    assert "total project cost" in down and down.endswith("This check uses the price only.")
    assert message_text("qoe", i, r, FACTS).endswith(
        "See the QoE Readiness skill in this repo to prepare.")
    coverage = message_text("sba_coverage", i, r, FACTS)
    assert coverage.endswith("When a new owner buys the business, the minimum debt service coverage is "
                             "1.25 for an SBA 7(a) loan.")
    standby = message_text("sba_standby", i, r, FACTS)
    assert standby.startswith("The down payment is below 5% of the price.")
    assert "at most 50% of the required equity injection for an SBA 7(a) loan." in standby
    term = message_text("sba_term", i, r, FACTS)
    assert term == ("The bank loan term is longer than 10 years. An SBA 7(a) loan that does not "
                    "finance real estate must be paid off over 10 years or less.")
    qoe = message_text("qoe", i, r, FACTS)
    assert qoe.startswith("When a new owner buys the business at this price")
    assert "must be done" not in qoe and "An independent professional does the report" in qoe


def test_standby_message_uses_the_cash_floor():
    """The down payment floor is min x (1 - share). It equals share x min only when share is 50%."""
    facts = {**FACTS, "standby_note_max_share_of_injection": {
        **FACTS["standby_note_max_share_of_injection"], "value": 0.25}}
    i = base(down_pct=0.05, seller_pct=0.10)
    r = evaluate(i, facts)
    assert "sba_standby" in r.warnings
    assert message_text("sba_standby", i, r, facts).startswith("The down payment is below 7.5% of the price.")


SHARES_100 = [(0.7, 0.3), (0.18, 0.82), (0.41, 0.59), (0.57, 0.43), (0.69, 0.31), (0.5, 0.5)]


@pytest.mark.parametrize("down, seller", SHARES_100)
def test_shares_adding_to_100_leave_no_bank_loan(down, seller):
    """1 - down - seller leaves a float residual for some pairs. The rounded share is 0."""
    assert down + seller == 1
    r = run(down_pct=down, seller_pct=seller, seller_standby="yes", asking_price=1_000_000.0)
    assert r.blocks == ()
    assert r.supported_price is None and r.max_bank_loan is None
    assert r.coverage_at_ask is None and r.price_gap is None
    assert r.bank_loan_at_price == 0
    assert r.status == STATUS_YES
    assert r.flags == ()
    r = run(down_pct=down, seller_pct=seller, seller_standby="yes")
    assert r.supported_price is None and r.price_used is None and r.bank_loan_at_price is None


def test_surrounding_spaces_are_not_removed():
    """The sheet cannot TRIM, so " yes" and " no" count as blank text, the same as in the sheet."""
    r = run(answers=(" no", "no", "no", "no", "yes", "no"))
    assert "missing_answers" in r.blocks and r.dependence_score is None
    r = run(addbacks=(Addback("other", 20_000.0, " no"), Addback("other", 20_000.0, " yes")))
    assert r.proof_missing == 2 and "proof" in r.warnings
    r = run(seller_pct=0.1, seller_standby="no ")
    assert "missing_inputs" in r.blocks


@pytest.mark.parametrize(
    "overrides",
    [
        {"owner_pay": -10_000.0},
        {"operator_salary": -50_000.0},
        {"capex": -25_000.0},
        {"addbacks": (Addback("other", 20_000.0, "yes"), Addback("other", -1.0, "yes"))},
        {"deductions": (Deduction("one-time income", -12_000.0),)},
    ],
)
def test_negative_amounts_block(overrides):
    r = run(**overrides)
    assert r.blocks == ("negative_inputs",)
    assert r.status is None and r.supported_price is None and r.cash_available is None
    assert r.warnings == () and r.flags == ()


def test_negative_operator_salary_does_not_give_a_price():
    """Without the block, a salary of -50,000 adds cash and gives Financeable."""
    r = run(operator_salary=-50_000.0, asking_price=2_000_000.0)
    assert r.blocks == ("negative_inputs",)
    assert r.status is None


def test_zero_and_blank_amounts_are_not_negative():
    r = run(owner_pay=0.0, capex=0.0, addbacks=(Addback("other", None, None), Addback("other", 0.0, "yes")),
            deductions=(Deduction("other", None),))
    assert "negative_inputs" not in r.blocks
    r = run(net_profit=-10_000.0, income_taxes=-1_000.0)
    assert "negative_inputs" not in r.blocks
