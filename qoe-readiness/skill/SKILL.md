---
name: qoe-readiness
description: Use when a business owner wants to prepare for a Quality of Earnings (QoE) report before a sale or an SBA-financed sale. Guides the owner through five gated stages (learn, file list, file inventory, spot check, workbook) and builds an owner-prepared QoE readiness workbook in Excel. Use for sell-side QoE readiness, collecting QuickBooks, Xero, or Stripe exports, and EBITDA add-back review.
---

# QoE readiness

## First message

Show this text as your first message, word for word, before you do anything else. Do not shorten it. Do not add to it.

> This skill was designed by LIVMO. LIVMO is not responsible for its output. You supply the files and approve every number, and the results are yours. The skill helps you prepare for a Quality of Earnings report. It does not replace one, and it gives no tax, legal, or accounting advice.

After this text, open the first stage in the stage order below.

## Setup

1. Make a new working folder for the owner. Do not write in the skill folder.
2. Copy the `scripts` folder and the `data` folder from this skill folder into the working folder.
3. Run every command from the working folder. The stage files use the relative paths `scripts/`, `data/`, `work/`, and `progress.json`.
4. Make a `work` folder inside the working folder. Save the canonical CSV files there.
5. Store every `canonical_path` as an absolute path.

## Stage order

Open one stage at a time. Read the stage file when you enter the stage. The stage file holds the steps, the owner text, and the gate.

1. Stage 1, learn: `core/stage-1-learn.md`
2. Stage 2, file list: `core/stage-2-files.md`
3. Stage 3, file inventory: `core/stage-3-inventory.md`
4. Stage 4, spot check: `core/stage-4-spot-check.md`
5. Stage 5, workbook: `core/stage-5-workbook.md`

Stage 3 sends the owner to `core/exports.md` for the export steps of each accounting and billing system.

## Gate rule

Run `progress.gate_passed(state, stage, data_dir)` at the end of each stage. Open the next stage only when it returns true. Show the owner the gate checklist.

- Hard floor: Stage 5 does not run without these files, each with the status `uploaded`. They are the monthly P&L (C1), the monthly balance sheet (C2), and either the general ledger or the bank statements (C3 or C4).
- Minimum history: C1 and C2 each cover 12 consecutive months that end at the latest closed month. A partial file with fewer months does not meet the floor.
- Soft rule: a missing file outside the hard floor does not block progress. Record the gap. The tabs that need the file show "not available: file missing."
- An owner answer with no document goes into the scope and limitations tab.
- The owner cannot skip a stage. Each stage has a gate.

## Rules for every stage

- Every number is an owner statement. Never fill an adjustment amount yourself.
- Never call the output a QoE report, an audit, a review, or a compilation.
- Do not state a business value. Do not give tax, legal, or accounting advice.
- Save the state with `progress.save` after each change. Offer the owner a `progress.json` file to resume later.
- If the owner uploads a `progress.json` file, load it and resume at the stage in the state.

## Data files

- `data/intake.json`: the intake questions for Stage 1.
- `data/files.json`: the file catalog for Stages 2 and 3.
- `data/checks.json`: the spot checks and their thresholds for Stage 4.
- `data/workbook.json`: the workbook tabs for Stage 5.
- `data/export_presets.json`: the export presets for each accounting and billing system.

## Scripts

- `scripts/canonical.py`: the canonical CSV schemas and the CSV reader and writer.
- `scripts/normalize.py`: turns an owner export into canonical CSV rows.
- `scripts/progress.py`: the state file and the stage gates.
- `scripts/metrics.py`: the figures, such as periods, TTM, and EBITDA.
- `scripts/run_checks.py`: runs the spot checks and saves the findings.
- `scripts/build_workbook.py`: writes the Excel workbook and prints the chat summary.
- `scripts/workbook_computed.py`: the tab builders. `scripts/build_workbook.py` imports it. Do not run it.
- `scripts/workbook_cells.py`: the cell helpers. `scripts/build_workbook.py` imports it. Do not run it.
