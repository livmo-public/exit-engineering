# Export steps by system

## Purpose

This file gives the exact report name and export settings for each file the skill reads. Use the section that matches the owner's system.

## Steps for the model

- Read `accounting_system` and `billing_system` from the intake in the progress state.
- Show only the section for the owner's system. Show the report name and menu path first, then the settings.
- Use the report names in `export_presets.json` as the source. This file repeats them in plain words.
- For an owner on another system, ask for the closest report. Then use `normalize_generic` with a column map that the owner confirms.
- Run the converter with the report id shown in each entry. Stage 3 gives the call.

## Owner text

### Before you export

The column layouts in this file are not yet confirmed against real exports. They follow each system's standard report layout.
If your export has a different layout, or a column is missing, tell the skill. The skill will ask you to map the columns.
Use the latest closed month as the end of every report period.
Export the P&L on each basis you keep. Choose CSV when the system offers it.

### QuickBooks Online

The QuickBooks help page confirms the Reports menu, Standard reports, the option to show columns by month, and the export to Excel or CSV.

The page does not name every report below. The report names follow the standard report list.

#### Profit and Loss (file C1, report id pl_by_month)

- Report name: Profit and Loss
- Menu path: Reports > Standard reports > Business overview > Profit and Loss
- Settings:
  - Report period: first day of the first month to last day of the latest closed month
  - Display columns by: Months
  - Accounting method: Accrual or Cash, one export per basis
  - Export/Print > Export to Excel, or Export as CSV
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/report-management/run-reports-quickbooks-online/L7aILHhbl_US_en_US on 2026-11-02

#### Balance Sheet (file C2, report id bs_by_month)

- Report name: Balance Sheet
- Menu path: Reports > Standard reports > Business overview > Balance Sheet
- Settings:
  - Report period: first day of the first month to last day of the latest closed month
  - Display columns by: Months
  - Export/Print > Export to Excel, or Export as CSV
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/report-management/run-reports-quickbooks-online/L7aILHhbl_US_en_US on 2026-11-02

#### General Ledger (file C3, report id general_ledger)

- Report name: General Ledger
- Menu path: Reports > Standard reports > For my accountant > General Ledger
- Settings:
  - Report period: same range as the P&L
  - Accounting method: Accrual or Cash
  - Export/Print > Export to Excel, or Export as CSV
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Date, Num, Name, Memo/Description, Amount
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/report-management/run-reports-quickbooks-online/L7aILHhbl_US_en_US on 2026-11-02

#### Sales by Customer Summary (file C6, report id sales_by_customer)

- Report name: Sales by Customer Summary
- Menu path: Reports > Standard reports > Sales and customers > Sales by Customer Summary
- Settings:
  - Report period: same range as the P&L
  - Display columns by: Months
  - Export/Print > Export to Excel, or Export as CSV
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/report-management/use-reports-see-sales-inventory-status/L7ocoLmqP_US_en_US on 2026-11-02

#### Expenses by Vendor Summary (file C7, report id expenses_by_vendor)

- Report name: Expenses by Vendor Summary
- Menu path: Reports > Standard reports > Expenses and vendors > Expenses by Vendor Summary
- Settings:
  - Report period: same range as the P&L
  - Display > Display columns by > Date > Months
  - Export/Print > Export to Excel, or Export as CSV
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/receive-payments/run-save-monthly-expense-report-vendor/L7ZOCfJmT_US_en_US on 2026-11-02

#### A/R Aging Detail (file C8, report id ar_aging)

- Report name: A/R Aging Detail
- Menu path: Reports > Standard reports > Who owes you > A/R Aging Detail
- Settings:
  - Report date: last day of the latest closed month
  - Export/Print > Export to Excel, or Export as CSV
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Customer, Date, Due date, Open balance
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/report-management/run-reports-quickbooks-online/L7aILHhbl_US_en_US on 2026-11-02

#### A/P Aging Detail (file C8, report id ap_aging)

- Report name: A/P Aging Detail
- Menu path: Reports > Standard reports > What you owe > A/P Aging Detail
- Settings:
  - Report date: last day of the latest closed month
  - Export/Print > Export to Excel, or Export as CSV
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Vendor, Date, Due date, Open balance
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/report-management/run-reports-quickbooks-online/L7aILHhbl_US_en_US on 2026-11-02

### QuickBooks Desktop

The QuickBooks help page confirms that QuickBooks Desktop exports reports to Excel and to CSV.

The page lists no CSV steps. The steps below follow the standard export window.

No help page names the reports or the menu groups below. They follow the standard report layout.

Choose CSV over Excel output. A CSV file keeps the columns and rows in a plain form.

#### Profit & Loss Standard (file C1, report id pl_by_month)

- Report name: Profit & Loss Standard
- Menu path: Reports > Company & Financial > Profit & Loss Standard
- Settings:
  - Dates: custom range ending at the latest closed month
  - Customize Report > Display tab > Columns: Month
  - Report Basis: Accrual or Cash, one export per basis
  - Excel > Create New Worksheet > Create a comma separated values (.csv) file > Export
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/export-reports-excel-workbooks-quickbooks-desktop/L4cLJEeXt_US_en_US on 2026-11-02

#### Balance Sheet Standard (file C2, report id bs_by_month)

- Report name: Balance Sheet Standard
- Menu path: Reports > Company & Financial > Balance Sheet Standard
- Settings:
  - Dates: custom range ending at the latest closed month
  - Customize Report > Display tab > Columns: Month
  - Excel > Create New Worksheet > Create a comma separated values (.csv) file > Export
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/export-reports-excel-workbooks-quickbooks-desktop/L4cLJEeXt_US_en_US on 2026-11-02

#### General Ledger (file C3, report id general_ledger)

- Report name: General Ledger
- Menu path: Reports > Accountant & Taxes > General Ledger
- Settings:
  - Dates: same range as the P&L
  - Report Basis: Accrual or Cash
  - Excel > Create New Worksheet > Create a comma separated values (.csv) file > Export
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Date, Num, Name, Memo, Debit, Credit
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/export-reports-excel-workbooks-quickbooks-desktop/L4cLJEeXt_US_en_US on 2026-11-02

#### Sales by Customer Summary (file C6, report id sales_by_customer)

- Report name: Sales by Customer Summary
- Menu path: Reports > Sales > Sales by Customer Summary
- Settings:
  - Dates: same range as the P&L
  - Customize Report > Display tab > Columns: Month
  - Excel > Create New Worksheet > Create a comma separated values (.csv) file > Export
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/export-reports-excel-workbooks-quickbooks-desktop/L4cLJEeXt_US_en_US on 2026-11-02

#### Expenses by Vendor Summary (file C7, report id expenses_by_vendor)

- Report name: Expenses by Vendor Summary
- Menu path: Reports > Company & Financial > Expenses by Vendor Summary
- Settings:
  - Dates: same range as the P&L
  - Customize Report > Display tab > Columns: Month
  - Excel > Create New Worksheet > Create a comma separated values (.csv) file > Export
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/export-reports-excel-workbooks-quickbooks-desktop/L4cLJEeXt_US_en_US on 2026-11-02

#### A/R Aging Detail (file C8, report id ar_aging)

- Report name: A/R Aging Detail
- Menu path: Reports > Customers & Receivables > A/R Aging Detail
- Settings:
  - Date: last day of the latest closed month
  - Excel > Create New Worksheet > Create a comma separated values (.csv) file > Export
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Name, Date, Due Date, Open Balance
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/export-reports-excel-workbooks-quickbooks-desktop/L4cLJEeXt_US_en_US on 2026-11-02

#### A/P Aging Detail (file C8, report id ap_aging)

- Report name: A/P Aging Detail
- Menu path: Reports > Vendors & Payables > A/P Aging Detail
- Settings:
  - Date: last day of the latest closed month
  - Excel > Create New Worksheet > Create a comma separated values (.csv) file > Export
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Name, Date, Due Date, Open Balance
- Help page checked: https://quickbooks.intuit.com/learn-support/en-us/help-article/export-reports/export-reports-excel-workbooks-quickbooks-desktop/L4cLJEeXt_US_en_US on 2026-11-02

### Xero

The Xero help page confirms that reports export as PDF, Excel, or Google Sheets.

The report names and menu paths below follow the standard report layout. Save the Excel file as CSV if needed.

Xero runs a P&L or balance sheet for about 12 months at a time. Run a second export for earlier months.

#### Profit and Loss (file C1, report id pl_by_month)

- Report name: Profit and Loss
- Menu path: Reporting > All reports > Profit and Loss
- Settings:
  - Date range: the 12 months ending at the latest closed month
  - Compare with: 11 previous Months
  - Accounting basis: Accrual or Cash, one export per basis
  - Export > Excel
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Headers the skill expects, not yet confirmed: Account
- Help page checked: https://central.xero.com/0/article/Export-or-print-a-report on 2026-11-02

#### Balance Sheet (file C2, report id bs_by_month)

- Report name: Balance Sheet
- Menu path: Reporting > All reports > Balance Sheet
- Settings:
  - Date: last day of the latest closed month
  - Compare with: 11 previous Months
  - Export > Excel
- Layout: One row for each name and one column for each month, plus a Total column. The skill ignores the Total column.
- Headers the skill expects, not yet confirmed: Account
- Help page checked: https://central.xero.com/0/article/Export-or-print-a-report on 2026-11-02

#### Account Transactions (file C3, report id general_ledger)

- Report name: Account Transactions
- Menu path: Reporting > All reports > Account Transactions
- Settings:
  - Date range: same range as the P&L
  - Accounts: all accounts
  - Export > Excel
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Date, Reference, Description, Debit, Credit
- Help page checked: https://central.xero.com/0/article/Export-or-print-a-report on 2026-11-02

#### Income and Expenses by Contact (file C6, report id sales_by_customer)

- Report name: Income and Expenses by Contact
- Menu path: Reporting > All reports > Income and Expenses by Contact
- Settings:
  - Date range: one calendar month per run
  - Run once for each month in the P&L range
  - Export > Excel
- Layout: One row for each record, with one column for each field.
- Run this report as one export for each month. Name each file by its month.
- Headers the skill expects, not yet confirmed: Contact, Income
- Help page checked: https://central.xero.com/0/article/Export-or-print-a-report on 2026-11-02

#### Income and Expenses by Contact (file C7, report id expenses_by_vendor)

- Report name: Income and Expenses by Contact
- Menu path: Reporting > All reports > Income and Expenses by Contact
- Settings:
  - Date range: one calendar month per run
  - Run once for each month in the P&L range
  - Export > Excel
- Layout: One row for each record, with one column for each field.
- Run this report as one export for each month. Name each file by its month.
- Headers the skill expects, not yet confirmed: Contact, Expenses
- Help page checked: https://central.xero.com/0/article/Export-or-print-a-report on 2026-11-02

#### Aged Receivables Detail (file C8, report id ar_aging)

- Report name: Aged Receivables Detail
- Menu path: Reporting > All reports > Aged Receivables Detail
- Settings:
  - Date: last day of the latest closed month
  - Group by: Invoice Date or Due Date
  - Export > Excel
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Date, Due Date, Due
- Help page checked: https://central.xero.com/0/article/Export-or-print-a-report on 2026-11-02

#### Aged Payables Detail (file C8, report id ap_aging)

- Report name: Aged Payables Detail
- Menu path: Reporting > All reports > Aged Payables Detail
- Settings:
  - Date: last day of the latest closed month
  - Group by: Invoice Date or Due Date
  - Export > Excel
- Layout: Rows sit under a heading row. The skill reads the heading and the rows below it.
- Headers the skill expects, not yet confirmed: Date, Due Date, Due
- Help page checked: https://central.xero.com/0/article/Export-or-print-a-report on 2026-11-02

### Stripe

Stripe help pages describe the Export button on list pages in the Dashboard.

No help page lists the export columns. The headers below follow the standard export.

#### Subscriptions export (file S1, report id subscriptions)

- Report name: Subscriptions export
- Menu path: Billing > Subscriptions > Export
- Settings:
  - Date range: All
  - Columns: All columns
  - Time zone: UTC
- Layout: One row for each record, with one column for each field.
- Headers the skill expects, not yet confirmed: Customer Name, Plan, Interval, Start Date (UTC), Ended At (UTC), Amount, Currency
- Help page checked: https://support.stripe.com/questions/exporting-payment-data on 2026-11-02

### Files with no system report

These files come from other places. The skill still needs each one, or a status for it.

- C4 Bank statements: download each statement from the bank's website. Get the last 13 months for every account.
- C5 Bank reconciliations: ask the bookkeeper for the signed reconciliation of each month.
- C9 Tax returns: ask the tax preparer for the filed returns for the last 3 years. You can also request a tax return transcript from the IRS.
- R1 Payroll summaries: download the payroll register and the year-end forms from the payroll provider.
- R2 Form 1096 and Form 1099 filings: ask the bookkeeper or the tax preparer.
- R3 to R10: these are documents you write or already hold. Gather what exists.
- R11 Statement of cash flows: run it from the accounting system, or ask the bookkeeper.
- S2 to S6: contracts, schedules, and plans from your own records.
- P1 Inventory and P2 Work in progress: use the count or the schedule at each period end.

## Gate

This file has no gate. Stage 3 holds the gate for the inventory.
