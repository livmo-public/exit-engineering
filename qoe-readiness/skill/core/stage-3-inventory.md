# Stage 3: Inventory

## Purpose

This stage records the status of every file, converts each uploaded export to a canonical CSV, and helps the owner close gaps. It ends with the owner's confirmed account map.

## Steps for the model

1. Load the state. Check that the Stage 2 gate passed. Make a working folder `work/` and use its absolute path as `WORK`.
2. Take the active files from `files.json` with `progress.active_files`. Ask about the critical files first, then the recommended files. Ask about one file at a time.
3. For each file, ask the owner to upload it or pick a status: `uploaded`, `partial`, `missing`, or `not_applicable`.
4. Save the status in `state["files"][file_id]`. Save the state with `progress.save` after each file.
5. Never invent a status. Never mark a file `uploaded` before you have read it. A file with fewer months than the floor needs is `partial`.

### Gaps and help

6. For a `missing` file, ask why. Save one reason code in `reason`: `not_produced`, `never_kept`, `held_by_other`, or `unknown`.
7. Then give the help. Say what the buyer loses without the file, using `why_buyers_ask` from `files.json`.
8. Give the exact report name and menu path from `exports.md` for the owner's system. Say who usually holds the file, using the Owner text.
9. If the owner can get the file later, keep the status `missing` and move on. Return to it before the gate.

### Convert an export

10. Choose the system from `state["intake"]["accounting_system"]` for books, and from `billing_system` for subscriptions. Use the report ids in `files.json` under `export_ref`.
11. Convert with `normalize.normalize(system, report_id, path, WORK, basis=...)`. It writes `WORK/{kind}.csv`. Use `basis` `accrual` or `cash` for the P&L.
12. C8 has two reports: `ar_aging` and `ap_aging`. Run both. The second call keeps the rows of the first.
13. A P&L on two bases, or a Xero export in two date ranges, writes the same file twice. Convert each into its own folder, then join the rows and write once with `canonical.write`.
14. For Xero sales and vendor reports, ask for one export per month. Convert them with `normalize.normalize_runs`, using a dict of `YYYY-MM` to file path.
15. For any other system, read the column headers of the owner's file. Propose a column map to the canonical columns. Run `normalize.normalize_generic` only after the owner confirms the map.
16. If the headers or the layout differ from the preset, tell the owner what differs. Do not guess. Use the generic path with a confirmed column map.
17. Store the result as an absolute path. Save `state["files"][file_id]` with `status`, `source_system`, and `canonical_path`, where `canonical_path` is `str(Path(path).resolve())`.
18. Files with no canonical kind need only a status. These are C5, R1 to R11, and S2 to S6.

### Read PDFs and paper

19. For bank statements (C4), in PDF or CSV form, read the 4 monthly totals for each account and each month: `beginning_balance`, `deposits`, `withdrawals`, `ending_balance`. Use positive numbers for withdrawals.
20. Ask for 13 months of statements. Thirteen months give both ends of a 12-month window.
21. For tax returns (C9), read the gross receipts or sales line for each year. Write one row per year with `year` and `gross_receipts`.
22. For inventory and WIP (P1, P2), read the period-end amount. Write one row per period with `item_type` `inventory` or `wip`. P1 and P2 share one file; join their rows.
23. Show every value you read to the owner in a plain list. Write the canonical CSV only after the owner confirms the values. Fix each value the owner corrects.
24. If a PDF does not parse, or the scan is unclear, ask the owner to type the values. A typed value is an owner statement.

### Account map

25. After C1 and C2 are converted, and C3 if present, collect the distinct `account` names from the P&L, balance sheet, and ledger rows.
26. Run `normalize.propose_account_map(accounts)`. Show the proposal to the owner. Mark each blank `account_type` as "needs your answer."
27. Ask the owner to confirm or correct every entry. Do not decide an unclear account yourself. A balance sheet entry also needs a `subtype`.
28. Save the confirmed map in `state["account_map"]`. Apply it with `canonical.apply_account_map` to the P&L, balance sheet, and ledger rows. Write each file back.
29. Set `account_map_confirmed` to true only after the owner confirms the full map. A later fix to the map needs a new confirmation.

### Hard floor and gate

30. Check the hard floor with `progress.meets_floor(state, data_dir)`. It needs C1 and C2 to cover the 12 months that end at `latest_closed_month`. It also needs C3 or C4 with status `uploaded`.
31. If the floor fails, find the cause. Read the months with `progress.months_covered` on the canonical rows. Tell the owner which months are missing.
32. If `accounting_basis` is `cash`, tell the owner about the single accrual finding (check K21) and that the workbook says "cash basis." Ask if the bookkeeper can produce an accrual P&L and balance sheet.
33. Show the gate checklist with `progress.gate_status(state, 3, data_dir)`. If every item passes, offer a `progress.json` file and open Stage 4.
34. If an item fails, say which one and what closes it. Do not open Stage 4. A missing file that is not part of the floor does not block the gate.

Code to record a file and to convert it:

```python
import sys
sys.path.insert(0, "scripts")
from pathlib import Path
import canonical, normalize, progress

WORK = Path("work").resolve()
WORK.mkdir(exist_ok=True)
path = normalize.normalize("qbo", "pl_by_month", Path("pl.csv"), WORK, basis="accrual")
entry = {"status": "uploaded", "source_system": "qbo", "canonical_path": str(path.resolve())}
state = {**state, "files": {**state["files"], "C1": entry}}
progress.save(state, Path("progress.json"))
```

Code for two bases, a one-folder-each conversion, then a join:

```python
accrual = normalize.normalize("qbo", "pl_by_month", Path("pl_accrual.csv"), WORK / "pl_accrual", basis="accrual")
cash = normalize.normalize("qbo", "pl_by_month", Path("pl_cash.csv"), WORK / "pl_cash", basis="cash")
canonical.write("pl", canonical.read("pl", accrual) + canonical.read("pl", cash), WORK / "pl.csv")
```

Code for Xero reports that run one month at a time:

```python
runs = {"2025-01": Path("contact-2025-01.xlsx"), "2025-02": Path("contact-2025-02.xlsx")}
normalize.normalize_runs("xero", "sales_by_customer", runs, WORK)
normalize.normalize_runs("xero", "expenses_by_vendor", runs, WORK)
```

Code for the account map:

```python
rows = canonical.read("pl", WORK / "pl.csv") + canonical.read("bs", WORK / "bs.csv")
proposal = normalize.propose_account_map(sorted({r["account"] for r in rows}))
# Show the proposal. Replace each entry with the owner's answer. Then:
state = {**state, "account_map": confirmed_map, "account_map_confirmed": True}
canonical.write("pl", canonical.apply_account_map(canonical.read("pl", WORK / "pl.csv"), confirmed_map), WORK / "pl.csv")
```

## Owner text

### How this stage works

I ask about each file in turn. For each file you pick one of four answers.

- Uploaded: you give me the file now.
- Partial: you have some of it, such as fewer months than needed.
- Missing: you do not have it.
- Not applicable: the file does not apply to your business.

Critical files come first. A missing file does not stop the work, except for the three files in the hard floor.
I record every gap in the workbook. A buyer will see the same gaps.

### If a file is missing

If a file is missing, I ask why. Pick the closest answer.

- Your system does not produce it.
- You never kept it.
- Your bookkeeper or CPA has it.
- You do not know.

Then I tell you what a buyer loses without the file and how to get it.
I give the exact report name and the menu steps for your system.

### Who usually holds each file

- Bookkeeper or CPA: the ledger, the reconciliations, the agings, and the accounting policies.
- Tax preparer: the tax returns and the 1099 filings.
- Payroll provider: the payroll registers and year-end payroll forms.
- Your bank: the bank statements.
- Your billing system: the subscription export.
- You: the lists of one-time items, the related-party schedule, the leases, and the org chart.

### Files you cannot export as a report

For bank statements, tax returns, inventory, and work in progress, I read the numbers from your files.
I show you every number I read. I save the numbers only after you confirm them.
If I cannot read a file, you can type the numbers. Each typed number is your own statement.

- Bank statements: I read four totals for each month. They are the opening balance, the deposits, the withdrawals, and the closing balance.
- Tax returns: I read the gross receipts for each year.
- Inventory and work in progress: I read the amount at the end of each period.

### Reports that run one month at a time

If you use Xero, the sales and vendor reports cover one date range for each run. Please send one export for each month.
Name each file by its month so I can match them.

### Your chart of accounts

Next I list every account in your books and suggest a type for each one. Examples of types are revenue, cost of goods sold, and operating expense.
You confirm or correct each account. I do not decide an unclear account for you.
Your confirmed map controls how the workbook adds up your books.

### Cash basis books

If you keep cash books only, your numbers show cash in and cash out. The workbook says "cash basis" on every computed tab.
The skill records one finding: accrual books are needed. A buyer's QoE converts cash books to accrual, and the result can differ from your figures.
The skill does not convert your books to accrual. It points to the gap.

### The hard floor

The workbook needs a base. You must give me three things.

- A monthly P&L that covers 12 months in a row, ending at your latest closed month.
- A monthly balance sheet for the same 12 months.
- Either the general ledger or the bank statements.

A partial file does not meet the floor. If a file has fewer than 12 months, ask your bookkeeper for the rest.

## Gate

- [ ] Every critical file has a status.
- [ ] The hard floor and minimum history are met (see "Gate rule").
- [ ] The owner confirms the account map.
