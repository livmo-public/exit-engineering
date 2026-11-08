"""Made-up sample company for the Buyer Debt Capacity Calculator.

Copyright (c) 2026 LIVMO. MIT license.
Sample Services Co. is not a real business. Every number is invented.
"""
from __future__ import annotations

from calc_math import Addback, Inputs

COMPANY_NAME = "Sample Services Co."
SAMPLE_NOTE = f"Sample file: {COMPANY_NAME} is a made-up company. Every number is invented."

SAMPLE = Inputs(
    period_basis="Last fiscal year",
    period_end="2025-12-31",
    revenue=3_400_000.0,
    net_profit=300_000.0,
    interest=25_000.0,
    income_taxes=15_000.0,
    depreciation=35_000.0,
    amortization=5_000.0,
    owner_pay=240_000.0,
    addbacks=(
        Addback("personal expense", 18_000.0, "yes"),
        Addback("family member on payroll who does not work in the business", 24_000.0, "yes"),
        Addback("one-time cost", 15_000.0, "no"),
        Addback("non-business cost", 9_000.0, "yes"),
        Addback("other", 6_000.0, "yes"),
    ),
    deductions=(),
    # Dependence score 4: questions 1, 2, and 6 answer yes, and question 5 answers no.
    answers=("yes", "yes", "no", "no", "no", "yes"),
    operator_salary=130_000.0,
    capex=30_000.0,
    down_pct=0.10,
    seller_pct=0.0,
    seller_standby="yes",
    seller_rate=0.06,
    seller_years=10.0,
    bank_rate=0.105,
    bank_years=10.0,
    coverage_target=1.25,
    asking_price=3_400_000.0,
    loan_limit=5_000_000.0,
)

# One description for each add-back above, in the same order.
SAMPLE_DESCRIPTIONS = (
    "Owner vehicle lease",
    "Spouse on payroll",
    "Legal fees for a one-time dispute",
    "Home office costs paid by the company",
    "Owner conference travel",
)
