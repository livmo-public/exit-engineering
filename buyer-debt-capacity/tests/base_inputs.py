"""Shared test helper: the sample-like Inputs that Tasks 1 to 4 start from."""
from dataclasses import replace

from calc_math import Addback, Inputs


def base(**overrides) -> Inputs:
    """Return a complete, valid Inputs. Pass field names to override them."""
    inputs = Inputs(
        period_basis="Last fiscal year",
        period_end="2025-12-31",
        revenue=3_400_000.0,
        net_profit=300_000.0,
        interest=40_000.0,
        income_taxes=10_000.0,
        depreciation=30_000.0,
        amortization=0.0,
        owner_pay=250_000.0,
        addbacks=(Addback("other", 20_000.0, "yes"),),
        deductions=(),
        answers=("no", "no", "no", "no", "yes", "no"),
        operator_salary=150_000.0,
        capex=25_000.0,
        down_pct=0.10,
        seller_pct=0.0,
        seller_standby="yes",
        seller_rate=0.06,
        seller_years=10.0,
        bank_rate=0.105,
        bank_years=10.0,
        coverage_target=1.25,
        asking_price=None,
        loan_limit=5_000_000.0,
    )
    return replace(inputs, **overrides)
