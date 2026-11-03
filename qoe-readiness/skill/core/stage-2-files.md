# Stage 2: File list

## Purpose

This stage builds the file list that fits the owner's business. It shows why a buyer asks for each file and which workbook tabs the file feeds.

## Steps for the model

1. Load the progress state. Check that the Stage 1 gate passed. If it did not, return to Stage 1.
2. Get the active modules with `progress.active_modules(state["intake"])`. Save the result in `state["modules"]`.
3. Read `files.json`. Keep the records whose `module` is in the active modules. Use `progress.active_files` for this step.
4. Explain the modules to the owner with the Owner text. The core module is always on.
5. The SaaS module is on when `business_type` is `saas`. The product module is on when `business_type` is `product` or `project`.
6. If the owner says the modules are wrong, go back to the `business_type` answer in Stage 1. Change it only on the owner's word.
7. Ask the owner to confirm the modules. Set `modules_confirmed` to true only after a clear yes.
8. Show the full list of active files in two groups: critical files first, then recommended files. Mark each critical file.
9. For each file, show `name`, `period`, `why_buyers_ask`, and the workbook tabs in `feeds_tabs`. Show the tab titles from `workbook.json`, not the tab ids.
10. If `accounting_basis` is `both`, say that C1 needs a P&L on each basis.
11. If `accounting_basis` is `cash`, say that C1 is one cash basis P&L. Stage 4 explains the single accrual finding, check K21.
12. Set `file_list_shown` to true after the owner has seen the whole list. Do not set it for a partial list.
13. Show the gate checklist with `progress.gate_status(state, 2, data_dir)`. If every item passes, offer a `progress.json` file and open Stage 3.
14. Save the state with `progress.save` after each change. Do not change the state in place; build a new dict and save it.

## Owner text

### How the file list works

A QoE firm asks for a long list of files. This skill builds the same list for your business.
Your answers in Stage 1 turn parts of the list on or off. Each part is a module.

- The core module is always on. It covers the books, the bank, and the tax returns.
- The SaaS module is on when you run a SaaS business. It adds the billing and subscription files.
- The product module is on when you sell products or run projects. It adds inventory and work in progress.

Please check the modules for your business. Tell me if one is wrong.

### Reading the list

Each file shows four things.

- What the file is.
- Which period it must cover.
- Why a buyer asks for it.
- Which workbook tabs use it.

A critical file is a file the workbook needs. A recommended file helps, but its absence does not stop the work.
The hard floor needs three files: a monthly P&L, a monthly balance sheet, and either the ledger or the bank statements.
The P&L and the balance sheet must cover the 12 months that end at your latest closed month.

### Your books

If you keep both cash and accrual books, send the P&L on each basis.
If you keep cash books only, send the cash P&L. The skill then records one finding: accrual books are needed. A buyer's QoE converts cash books to accrual.

Next, Stage 3 asks about each file.

## Gate

- [ ] The owner confirms the modules.
- [ ] The owner sees the full list with critical files marked.
