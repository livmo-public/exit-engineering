# Stage 5: Workbook

## Purpose

This stage builds the owner-prepared QoE readiness workbook and gives the owner a chat summary. The workbook is an Excel file that also opens in Google Sheets.

## Steps for the model

1. Load the state. Run `progress.gate_passed(state, stage, data_dir)` for stages 1, 2, 3, and 4. If any stage fails, return to that stage. Do not build the workbook.
2. The Stage 3 gate holds the hard floor. Without the P&L, the balance sheet, and the ledger or bank statements, the workbook has no base.
3. Set `state["stage"]` to 5. Save the state with `progress.save`.
4. Run `python scripts/build_workbook.py --state progress.json --canonical work --out qoe-readiness-workbook.xlsx`.
5. If the command prints an error, tell the owner in plain words and name the stage that closes it. Do not retry in a loop.
6. The command prints the chat summary as JSON. It has the keys `top_findings`, `reported_ebitda`, `adjusted_ebitda`, `basis`, `gaps`, and `next_step`.
7. Give the owner the xlsx file. Then show the chat summary from the Owner text.
8. Show the findings from `top_findings`, in the order given. For each one, show `name`, `severity`, `detail`, and the owner's `response`.
9. Show `reported_ebitda` and `adjusted_ebitda` for the last fiscal year and for the TTM. Use the labels in the JSON, such as `FY2025` and `TTM`.
10. Say that every adjustment is an owner statement. Never call the adjusted figure verified.
11. If `basis` is `cash`, say "cash basis" next to each figure. Explain that the single accrual finding (check K21) stays open until accrual books exist.
12. Show `gaps`. For a gap with `type` `file`, name the file and the tabs it stops (`blocks_tabs`) or thins (`thins_tabs`). For a gap with `type` `finding`, name the finding and its `fix`.
13. Show `next_step` word for word.
14. Then say that a QoE the seller orders does not meet the SBA lender requirement. The SOP says the report must not be prepared by or for the seller.
15. Tell the owner that a tab without its input file shows "not available: file missing." Those tabs also appear in the scope and limitations tab.
16. Offer a final `progress.json` file so the owner can resume later.
17. Never call the output a QoE, an audit, a review, or a compilation. Give no valuation and no tax, legal, or accounting advice.
18. If `advisor_name` is set, the workbook names the advisor as facilitator only. The label stays "owner-prepared."
19. If the owner adds a file or changes an answer, return to the stage the change affects. Run the later stages again.

Code for the last gate check:

```python
import sys
sys.path.insert(0, "scripts")
from pathlib import Path
import progress

DATA = Path("data")
ready = all(progress.gate_passed(state, stage, DATA) for stage in (1, 2, 3, 4))
```

## Owner text

### What you get

You get one Excel workbook. It opens in Excel. To use Google Sheets, upload the file to Google Drive and open it with Google Sheets.
Every computed cell is a live formula. Each formula points to an input tab, so you can trace any number back to your files.
Each computed tab has a check row. The check row shows whether the tab ties to its source.

### The notice on every tab

Every tab starts with this notice.

Owner-prepared QoE readiness workbook. Designed by LIVMO. LIVMO is not responsible for this output. This is not an independent Quality of Earnings report, an audit, a review, or a compilation. The owner supplied the source files, and no one verified them. Do not give this workbook to a lender or buyer as a QoE.

### What is in the workbook

- Summary: reported and adjusted EBITDA, the top findings, and the share of critical files you gave.
- Scope and limitations: missing files, owner statements with no document, and checks that did not run.
- Findings: every finding with its severity, your response, and the fix.
- File inventory: every file and its status.
- Adjusted EBITDA bridge and Add-backs: how reported earnings become adjusted earnings.
- Proof of cash, Proof of revenue, and Revenue analysis.
- Opex by vendor and NWC trend.
- Deferred revenue for SaaS, and Inventory and WIP for product and project businesses.
- Input tabs: your files in canonical form.

### Your chat summary

I show you four items.

- The five most important findings.
- Reported EBITDA and owner-adjusted EBITDA for the last fiscal year and the trailing 12 months (TTM).
- The files and fixes that would close the largest gaps.
- The next step.

Every adjustment in the summary is your own statement. No one has verified it.

### Cash basis books

If you keep cash books only, every figure is on a cash basis, and each computed tab says "cash basis."
The accrual finding stays open until you have accrual books. A buyer's QoE converts to accrual, and the result can differ from your figures.

### What this workbook is not

This workbook is your own preparation for a QoE. It is not a QoE, and it gives no valuation.
It gives no tax, legal, or accounting advice. A buyer or lender will commission an independent QoE.
A QoE that the seller orders does not meet the SBA lender requirement.

## Gate

- [ ] The workbook file exists.
- [ ] The owner has the chat summary.
- [ ] The owner has the final progress file.
