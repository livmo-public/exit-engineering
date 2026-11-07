from dataclasses import replace

import pytest

from base_inputs import base
from calc_math import (
    MESSAGE_ORDER,
    MESSAGES,
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
    r = run(addbacks=(Addback("other", 1.0, "no"), Addback("other", 2.0, "NO"),
                      Addback("other", 3.0, "yes"), Addback("other", 4.0, None)))
    assert r.proof_missing == 2
    assert "proof" in r.warnings


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
    limit = f["standby_note_max_share_of_injection"]["value"] * down
    assert "sba_standby" in run(seller_pct=limit + 0.01).warnings
    assert "sba_standby" not in run(seller_pct=limit).warnings
    assert "sba_standby" not in run(seller_pct=limit + 0.01, seller_standby="no").warnings


@pytest.mark.parametrize(
    "key, overrides, code",
    [
        ("min_equity_injection", {"down_pct": 0.01}, "sba_down"),
        ("max_term_years_no_real_estate", {"bank_years": 30.0}, "sba_term"),
        ("coverage_change_of_ownership", {"coverage_target": 0.5}, "sba_coverage"),
        ("standby_note_max_share_of_injection", {"seller_pct": 0.3}, "sba_standby"),
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
    assert "10%" in down and down.endswith("for an SBA 7(a) loan.")
    assert message_text("qoe", i, r, FACTS).endswith(
        "See the QoE Readiness skill in this repo to prepare.")
    for code in ("sba_term", "sba_coverage", "sba_standby"):
        assert message_text(code, i, r, FACTS).endswith("for an SBA 7(a) loan.")
