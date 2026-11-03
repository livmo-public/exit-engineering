# Stage 4: Spot check

## Purpose

This stage runs the spot checks, collects the owner's response to each serious finding, and runs the adjustment review. The owner states every adjustment amount.

## Steps for the model

1. Load the state. Check that the Stage 3 gate passed. Set `state["stage"]` to 4.
2. Tell the owner what a spot check is, using the Owner text. Then run the computed checks.
3. Run `python scripts/run_checks.py --state progress.json --canonical work`. It reads the state, runs every computed check whose files are `uploaded`, and saves the findings in the state.
4. Each finding has `id`, `check_id`, `name`, `category`, `severity`, `detail`, `owner_message`, `fix`, and `evidence`. Show the `owner_message` and the `fix`. Show `evidence` when the owner asks.
5. Say the category. Hygiene means the books hold an error to fix. Risk means the books are correct and a buyer will discount for the fact.

### Review items

6. Call `run_checks.review_items(state, canonical_dir, data_dir)`. It returns the `model_review` checks that can run, with a monthly `series`.
7. Look at each `series` and name candidates for the owner. For K02, compare `monthly_revenue` with `annual_billings`. For K15, read `large_entries`.
8. Present every candidate as "for review." A review item has a severity of medium or lower. It has no gate effect and needs no response.
9. Save the candidates you showed. Write a JSON file that maps each `check_id` to the list of candidates you showed, one line each.
10. Run `python scripts/run_checks.py --state progress.json --canonical work --reviews reviews.json`. It saves one finding per check with status `review`.
11. This call replaces all review findings in the state. Put every candidate you showed in the file each time. Leave out a check with no candidates.
12. If the owner finds a real error in a review item, treat it as a fix. Ask for the corrected file in the normal way.

### Owner questions

13. Call `run_checks.questions(state, data_dir)`. It returns one question for each `owner_question` check that applies. Ask each question in the owner's words. Show `candidates` when K11 has any.
14. Ask every question before the adjustment review. The answers to K12, K13, and K14 name candidates for it.
15. Decide for each question whether the owner's answer confirms the condition of the check. If the answer shows a problem, the condition holds. If the answer shows no problem, leave it out.
16. Write a JSON file that maps `check_id` to the owner's statement. Include only the answers to questions you actually asked. Never add an answer the owner did not give.
17. Run `python scripts/run_checks.py --state progress.json --canonical work --answers answers.json`. This call replaces all owner-question findings in the state. Put every confirmed answer in the file each time.
18. An owner-question finding carries the note "Owner statement, no document." Tell the owner that this note goes into the workbook.

### Adjustment review

19. Name each candidate adjustment. Take them from R1, R3, R4, R5, R6, and from the owner-question answers you saved above. Typical candidates are owner pay against replacement cost, rent to an owner entity, a one-time legal fee, and personal costs the business paid.
20. The owner states every amount. You never propose an amount. Never fill an amount from the books, a document, or an example. Never suggest a range.
21. If the owner asks to see ledger entries, show them. The owner then types the amount. If the owner says "use the ledger amount," ask the owner to state the number.
22. Get the period labels with `metrics.periods`: one label for each complete fiscal year, such as `FY2025`, and `TTM`. A single month uses its `YYYY-MM` key.
23. Ask for a separate amount for each label that applies. An amount that falls in a fiscal year and in the TTM goes under both labels.
24. For each candidate, ask the owner to approve, edit, or reject it. Approve means the owner states the amount and confirms it. Edit means the owner changes a stated amount. Reject means no amount counts.
25. Ask what document supports each amount. Save the answer as `evidence`, or `None` if the owner has no document.
26. Save each candidate in `state["adjustments"]` as shown in the code. Only approved and edited adjustments enter adjusted EBITDA.
27. Record `approved` or `edited` only after the owner states at least one amount. A candidate with no stated amount gets `decision` `rejected`.
After the review, ask K13 again if any adjustment has no `evidence`. Run `--answers` again with every confirmed answer.

### Responses

28. For every finding with severity `critical` or `high`, collect one response: fix, explain, or accept.
29. Fix now: the owner uploads a corrected file. Convert it as in Stage 3, then run `run_checks.py` again. Record `{"type": "fix"}` only after the rerun. If the finding stays, ask for a new response.
30. Explain: the owner types an answer. Record `{"type": "explain", "text": ...}` with the owner's words. The text must not be blank. The workbook marks it "owner statement, no document."
31. Accept: the finding stays open in the workbook. Record `{"type": "accept"}`.
32. Save responses in `state["responses"]` under the finding id. After a rerun, remove each response whose finding no longer exists.
33. Findings of medium or low severity need no response. Show them, and ask if the owner wants to respond.
34. If the books are on a cash basis, the single accrual finding K21 appears. Checks K01 and K07 do not run. Explain K21 to the owner: a buyer's QoE converts cash books to accrual, and the workbook says "cash basis."

### Gate

35. Show the gate checklist with `progress.gate_status(state, 4, data_dir)`. If every item passes, offer a `progress.json` file and open Stage 5.
36. If an item fails, say which finding or adjustment has no response. Do not open Stage 5.

Code for the answers file, the reviews file, and the adjustments:

```python
import json
import sys
sys.path.insert(0, "scripts")
from pathlib import Path
import canonical, metrics, progress

# Only the questions you asked, and only the answers that confirm the condition.
answers = {"K06": "No. We reconcile the main account only."}
Path("answers.json").write_text(json.dumps(answers), encoding="utf-8")

# Only the review candidates you showed the owner, one line each.
reviews = {"K15": ["2025-11: Computer purchase 4,200.00 in Software and tools"]}
Path("reviews.json").write_text(json.dumps(reviews), encoding="utf-8")

rows = canonical.read("pl", Path(state["files"]["C1"]["canonical_path"]))
intake = state["intake"]
p = metrics.periods(progress.months_covered(rows), intake["fiscal_year_end_month"], intake["latest_closed_month"])
labels = list(p.fiscal_years) + ["TTM"]

# owner_amounts maps each label to the number the owner gave. Never fill it yourself.
adjustment = {
    "id": "A1", "name": "Rent to an owner entity", "source_file": "R5",
    "amounts": owner_amounts,  # Label to amount, exactly as the owner typed it.
    "evidence": None, "decision": "approved", "owner_stated": True,
}
assert owner_amounts, "approved or edited needs at least one amount that the owner stated"
state = {**state, "adjustments": [*state["adjustments"], adjustment]}
progress.save(state, Path("progress.json"))
```

## Owner text

### What a spot check is

A spot check tests your files for errors that a buyer's QoE will find. I run a list of checks. Each check gives a result in plain words and a fix.
Findings fall into two groups.

- Hygiene: your books hold an error to fix. An example is a bank balance that does not match the books.
- Risk: your books are correct, and a buyer will still discount for the fact. An example is one customer paying for a large share of revenue.

Some checks need your answer. I ask you a question, and your answer decides the result.
Some items are for review. I point at a pattern, and you tell me if it is a real error. These items never block you.
The workbook lists each review item as a finding with the status "review."

### Your response to each serious finding

For each critical or high finding, you pick one response.

- Fix now: you upload a corrected file, and I run the checks again.
- Explain: you type your answer. It goes into the workbook as "owner statement, no document."
- Accept: the finding stays open in the workbook.

A buyer will find an open finding in diligence. A fix before the sale is a change you made. A finding a buyer discovers is a reason to cut the price.

### Cash basis books

If you keep cash books only, I record one finding: accrual books are needed. A buyer's QoE converts cash books to accrual.
Two checks do not run for you, because they compare cash and accrual. The workbook says "cash basis" on every computed tab.

### The adjustment review

An adjustment changes your earnings to show what the business earns for a new owner. Examples are:

- Your pay is above or below what a replacement manager would cost.
- You pay rent to a company you own, at a rate above or below market.
- A one-time legal fee.
- A personal cost that the business paid.

I name each candidate. You tell me the amount. I never suggest an amount, and I never fill one in.
For each candidate you approve it, edit it, or reject it. An approved or edited item needs an amount from you. Only approved and edited adjustments count in adjusted EBITDA.
Each amount is your statement. A buyer will ask for a document behind each one.

## Gate

- [ ] Every critical and high finding has a response.
- [ ] Every candidate adjustment has a response.
