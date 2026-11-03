# Stage 1: Learn

## Purpose

This stage teaches the owner what a Quality of Earnings (QoE) report is. It then collects the intake answers and the owner's acknowledgement of the disclaimer.

## Steps for the model

1. Start a new state with `progress.new_state()`. If the owner uploads a `progress.json` file, load it with `progress.load` and resume at the stage in `state["stage"]`.
2. Do not repeat the start message. The entry file already showed it.
3. Show the education text in the Owner text section. Keep the order. Answer the owner's questions before you move on.
4. Ask the intake questions one at a time. Read them from `intake.json` in file order and use the `question` text.
5. For a choice question, accept only a value from `choices`. Map the owner's words to a choice and confirm the choice. Use the choice value in the state.
6. Skip `billing_system` unless the `required_when` rule matches the answers so far. Ask `advisor_name` last. It may stay blank.
7. For `fiscal_year_end_month`, store an integer from 1 to 12. For `latest_closed_month`, store `YYYY-MM`.
8. Save each answer in `state["intake"]` under its `id`. Do not guess an answer.
9. If `buyer_financing` is `sba`, or `price_may_reach_3m` is `yes` or `unknown`, say that the SBA text applies to this sale.
10. Show the disclaimer word for word. Ask the owner to confirm. Set `disclaimer_acknowledged` to true only after a clear yes.
11. Show the gate checklist. Run `progress.gate_status(state, 1, data_dir)` and mark each item from the `passed` value.
12. If every item passes, offer the owner a `progress.json` file with `progress.save`. Set `state["stage"]` to 2 and open Stage 2.
13. If an item fails, say which one and ask for the missing answer. Do not open Stage 2. If the owner asks to skip, say that every stage keeps a visible record and a gate.

Code for the gate check:

```python
import sys
sys.path.insert(0, "scripts")
from pathlib import Path
import progress

DATA = Path("data")
for item in progress.gate_status(state, 1, DATA):
    print(("[x] " if item.passed else "[ ] ") + item.text)
```

### SBA source record

- Source: SBA SOP 50 10 8.1, Lender and Development Company Loan Programs, Appendix 15 (7(a) Changes of Ownership), paragraph Quality of Earnings.
- URL: https://www.sba.gov/document/sop-50-10-lender-development-company-loan-programs
- Checked on sba.gov as of 2026-11-02. The SOP shows "Published: September 25, 2026" and "Effective Date: October 1, 2026".
- Use no other source for SBA claims. If the owner asks for more detail, send the owner to the URL.

QoE requirement and the $3 million threshold, word for word from the SOP:

> For Business Expansion and Initial Acquisition transactions where the Purchase Price as defined in Paragraph A.1 is equal to or greater than $3 million, the Lender must also obtain a Quality of Earnings (QoE) in addition to the required Business Valuation. The $3 million threshold is determined before the application of buyer equity, seller debt, or other financing sources. Owner Buyout and ESOP & Cooperative transactions are not subject to the QoE requirement because the existing owner(s) retain operational knowledge of the business and the transaction does not result in a change to the management or operating structure.

The "for the benefit of the lender" wording, word for word from the SOP:

> The QoE must be performed by an independent, experienced financial professional and must be conducted for the benefit of the Lender. As the QoE report is part of the financial due diligence of the transaction, the report must not be prepared by or for the seller.

The use of QoE earnings, word for word from the SOP:

> The Lender must use the earnings from the QoE in the Debt Service Coverage (DSC) determination and retain the QoE report in the credit file.

The Cash Proof wording, word for word from the SOP:

> The QoE must include a Cash Proof. For purposes of this requirement, a Cash Proof is a financial analysis that reconstructs cash receipts and disbursements by reconciling bank statement data to the income statement and tax return for each period under review.

The loan amount, word for word from the SOP (Appendix 15):

> When a change of ownership transaction requires a Quality of Earnings (QoE) report as part of the necessary financial due diligence, the Lender must use the report’s findings to calculate the Debt Service Coverage. If that Debt Service Coverage does not support the business valuation and proposed debt structure, the loan amount must be reduced accordingly.

Buyer-commissioned reports, word for word from the SOP:

> Recognizing that some Applicant buyers may elect to commission their own QoE prior to engaging with the Lender for financing as part of their own due diligence, Lenders may elect to have that report reviewed by one of their approved vendors to help mitigate costs. The findings of that vendor review must be included in the loan file along with the original QoE report. The Lender may not rely upon a QoE report prepared by another party without a review being performed by one of their vendors.

Costs, word for word from the SOP (Appendix 15, uses of proceeds). The SOP lists these among the funds a change of ownership loan may include. It does not say who pays for a QoE.

> Change of ownership transactions may include funds for: Working Capital; Borrower out of pocket expenses (including business valuations and QoE); and Owner-Occupied Commercial Real Estate when structured on a blended basis.

Business Purchase Price, from the same appendix: it excludes owner-occupied commercial real estate in the sale.

## Owner text

### What a QoE is

A Quality of Earnings report, or QoE, is an analysis of a company's earnings. It tests whether the earnings repeat.
A buyer or a lender can rely on it. An independent analyst builds it from your bank, ledger, and tax records.
A QoE does not give an opinion on your financial statements. It asks one question: how much profit will this business keep earning?

### How a QoE differs from other reports

An audit is a full test of your financial statements. The auditor gives an opinion on them.
A review is a lighter check. The accountant asks questions and looks for numbers that seem off.
A compilation has the least work. The accountant formats your numbers into statements and checks nothing.
Accrual bookkeeping records income when you earn it and costs when you incur them. It is a way to keep books. It is not a report on them.
A tax return reports income by tax rules. Those rules can differ from how you keep your books.
A QoE sits on top of these. It starts from your books and tests them against the bank and the tax return.

### What a QoE produces

- Adjusted EBITDA bridge. EBITDA is earnings before interest, taxes, depreciation, and amortization. The bridge starts at net income. It adds or removes one-time and personal items to reach adjusted EBITDA.
- Proof of cash. This tests that the cash in your books matches the bank, month by month.
- Proof of revenue. This tests that the revenue in your books matches your sales records and bank deposits.
- Revenue analysis. This shows revenue trends, customer concentration, and customer counts. For a SaaS business it also shows recurring revenue and retention.
- Net working capital (NWC) and the peg. NWC is receivables, inventory, and other short-term items, minus payables and other short-term debts. The peg is the normal level of NWC. The seller leaves that level in the business.
- Net debt and debt-like items. These are loans and other obligations that reduce what the buyer pays you.

### Sell-side and buy-side QoE

A sell-side QoE is ordered by the seller. It helps you find and fix problems before buyers see them.
A buy-side QoE is ordered by the buyer or the buyer's lender. It tests what the seller claims.
In an SBA deal, the loan can include QoE costs among the borrower's out-of-pocket costs.
A sell-side report does not replace a buy-side report. On an SBA deal at or above the threshold, the lender must obtain a QoE that the seller did not order.
A buyer may commission a QoE first. The lender may then have its own vendor review that report.

### The SBA rule

The SBA has a new rule for 7(a) loans. It is in SOP 50 10 8.1 and it takes effect on October 1, 2026.
For an initial acquisition or a business expansion, the rule applies at a price of $3 million or more.
The SBA sets the $3 million line before buyer equity, seller debt, or other financing. The price does not include owner-occupied real estate.
In that case the lender must obtain a QoE. It must be done for the benefit of the lender.
An independent, experienced financial professional must do the work. The SBA says the report must not be prepared by or for the seller.
The lender uses the QoE earnings to test the loan. If those earnings do not support the valuation and the debt structure, the lender must reduce the loan amount.
The SBA says an owner buyout does not need a QoE.
Source: SBA SOP 50 10 8.1 on sba.gov, as of 2026-11-02.
Link: https://www.sba.gov/document/sop-50-10-lender-development-company-loan-programs

### Why fixing problems first protects your price

A buyer who finds a problem in diligence cuts the price. The industry calls this a retrade.
You can fix many of the same problems before you list the business. A fix you make is a change in how you run the business.
A problem a buyer finds is a reason to pay less.

### What this skill produces

- A list of the files a QoE firm asks for, and why.
- A status for each file, and the exact export steps for each missing file.
- A set of spot checks for errors that a buyer's QoE will find.
- An Excel workbook with live formulas. It also opens in Google Sheets.

This skill does not produce a QoE. It gives no valuation. It does not connect to your accounting system.
It processes your files only inside this chat.

### Disclaimer

A buyer or lender will commission an independent QoE. This workbook is your own preparation for that QoE. LIVMO designed this skill and is not responsible for its output.

Please confirm that you have read this text.

### Questions

Next I ask a few questions about your business. They set the file list for Stage 2.

## Gate

- [ ] Every intake question has an answer.
- [ ] The owner acknowledges the disclaimer.
