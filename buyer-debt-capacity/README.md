# Buyer Debt Capacity Calculator

Designed by LIVMO. LIVMO is not responsible for this output. You supply every number, and the results are yours. This calculator estimates the debt a lender could support. It is not a loan offer, a lender decision, or a valuation, and it gives no tax, legal, or accounting advice.

The calculator finds the cash that a buyer's lender sees in your business after the costs of running it. It then turns that cash into the largest loan a lender could support and the price that loan supports.

## How to use

1. Download `buyer-debt-capacity-calculator.xlsx`.
2. Open it in Excel, or upload it to Google Sheets. The file has no script or macro.
3. Fill in the tabs in this order: Profit, Add-backs, Owner role, Deal terms.
4. Read the Results tab.

Input cells have a fill color. Formula cells have no fill. The Start here tab shows the color legend.

Use the numbers for the last 12 months or the last full fiscal year. A P&L or a tax return has everything you need. Most owners finish in 20 minutes.

The folder `examples/` holds `sample-buyer-debt-capacity.xlsx`. It uses a made-up company, "Sample Services Co.", with about $3.4M revenue and these results:

- Cash available for debt: $532,000.
- Supported price: about $2.92M.
- Asking price: $3.4M.
- Coverage at the asking price: 1.07.
- Status: "Not financeable at these terms".
- Flag: the lender requires a Quality of Earnings report at this price.

If a required input is blank, Results shows a message and no loan or price. Each blank required cell shows "Required".

## Cash flow steps

Results shows these steps from top to bottom. A lender takes each step for a reason.

1. **Net profit.** The profit on your P&L.
2. **Plus interest, income taxes, depreciation, and amortization.** The sum is EBITDA. The lender judges the business before its own debt, taxes, and non-cash charges. The buyer's loan replaces your interest.
3. **Plus add-backs, including owner pay.** An add-back is a cost that a new owner would not pay. Examples are personal expenses and one-time costs. A lender accepts an add-back only with proof. Results warns when a row has no proof on file.
4. **Minus deductions.** A deduction is profit that a new owner would not get. Examples are one-time income and below-market costs, such as rent to a related party below market rent.
5. **Minus the operator salary.** A buyer must pay someone to run the business. The lender counts that cost.
6. **Minus maintenance capital spending.** The business must replace equipment and systems to keep running.
7. **Cash available for debt.** This is the cash that can pay a loan.

Then Results finds the debt capacity:

1. It divides the cash available by the lender coverage target. The result is the maximum yearly debt payment.
2. It finds the yearly payment for each $1 of price. It uses the bank loan rate and term, and the bank share of the price. A seller note adds to this payment, unless the note is on full standby.
3. It divides the maximum yearly payment by the payment per $1 of price. The result is the supported price.
4. It multiplies the supported price by the bank share. The result is the maximum bank loan.

If you enter an asking price, Results also shows these items:

- The coverage at the asking price.
- A status: "Not financeable at these terms" when coverage is below the target, "Tight" when coverage is within 0.15 above the target, and "Financeable" above that.
- The gap between the asking price and the supported price.

An asking price of 0 counts as blank. If no cash is available for debt, Results says so and shows no price.

## Operator salary

The calculator adds back all owner pay. A buyer must then pay someone to do the owner's work. A result that adds back the owner's pay and replaces it with nothing misleads you, and it fails at the lender. So the operator salary is required.

Enter the total yearly cost to employ the people who take over all the work of the owners. Include payroll tax and benefits. If two owners work in the business, one figure covers both roles.

The rules:

- Blank: Results blocks.
- 0, with no general manager or operator in place: Results blocks.
- 0, with an operator already in place: Results calculates and shows a note. Make sure the operator's pay is in the P&L.
- Above 0 but below half of the owner pay: Results warns that the salary may not cover all of the owners' work.
- Heavy owner dependence (3 or more of 6 answers): Results warns that buyers usually ask for a transition period.

## SBA rules

These facts come from the SBA's Standard Operating Procedure text. Secondary sources are not used.

- Source: https://www.sba.gov/document/sop-50-10-lender-development-company-loan-programs
- Version: SOP 50 10 8.1 (Lender and Development Company Loan Programs with Technical Policy Updates), published 2026-09-25, effective 2026-10-01
- Date checked: 2026-11-07

The facts for a 7(a) loan that finances a change of ownership:

- The minimum equity injection is 10% of the price.
- The debt service coverage ratio must be at least 1.25.
- The loan term must not exceed 10 years.
- The maximum loan is $5,000,000.
- A seller note on full standby may count as equity. It may supply up to 50% of the required equity injection.
- At a purchase price of $3M or more, the lender must get a Quality of Earnings report. An independent professional does it for the lender. The seller cannot prepare it or have it prepared.

The SBA can change these rules. Check the current SOP before you rely on them.

Results shows a warning when an input breaks one of these rules. The warning says "for an SBA 7(a) loan". A warning does not block Results, because a buyer can also use a lender outside the SBA program.

## What the calculator leaves out

A lender looks at these items too. The calculator does not include them:

- the buyer's personal finances
- income taxes of the business entity
- working capital needs
- closing costs

## QoE Readiness

At a price of $3M or more, an SBA lender requires an independent Quality of Earnings report. Results shows a flag when the price reaches that amount. The `qoe-readiness/` folder in this repository holds the QoE Readiness skill. It helps you prepare for that review.

## Files

- `buyer-debt-capacity-calculator.xlsx`: the blank calculator, with default deal terms.
- `examples/sample-buyer-debt-capacity.xlsx`: the sample company.
- `tools/build_calculator.py`: generates both files.
- `tests/`: the tests. Run `python -m pytest -q` from this folder. They need the packages in `requirements-dev.txt`.

## Next step

Book a 30-minute exit assessment: https://calendly.com/khaledazar/exit-builder

## License

The spreadsheet files (.xlsx) and the tools in `tools/` are licensed under the MIT License. See `tools/LICENSE` and the root `LICENSE`.
