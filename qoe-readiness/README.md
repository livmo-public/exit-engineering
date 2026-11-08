# QoE Readiness

A skill for Claude and ChatGPT that helps a business owner prepare for a Quality of Earnings (QoE) report. It guides the owner through five gated stages: learn, file list, file inventory, spot check, and workbook. The owner supplies accounting exports and approves every number. The skill builds an owner-prepared QoE readiness workbook in Excel.

A buyer or lender still orders an independent QoE. This workbook is your own preparation for that report.

For SaaS companies, 6 of the 21 spot checks look at subscription revenue and costs:

- no deferred revenue on annual billing
- revenue spikes in annual billing months
- deferred revenue that does not match subscriptions
- capitalized software without a policy
- mixed treatment of sales commissions
- low gross revenue retention

The workbook has a deferred revenue tab, and the skill reads Stripe subscription exports.

Last updated: November 8, 2026.

## Start text

The skill instructions tell the model to show this text first, word for word.

> This skill was designed by LIVMO. LIVMO is not responsible for its output. You supply the files and approve every number, and the results are yours. The skill helps you prepare for a Quality of Earnings report. It does not replace one, and it gives no tax, legal, or accounting advice.

## Files

| File | What it is |
|---|---|
| [qoe-readiness-guidebook.pdf](guidebook/qoe-readiness-guidebook.pdf) | The guidebook. It explains what a QoE is, what a buyer looks for, and how to prepare. |
| [qoe-readiness-skill.zip](dist/qoe-readiness-skill.zip) | The skill package for Claude.ai and Claude Code. |
| [qoe-readiness-workbook.xlsx](examples/sample-saas-co/qoe-readiness-workbook.xlsx) | A sample workbook built from the synthetic company "Sample SaaS Co." |

The guidebook is also available as [HTML](guidebook/qoe-readiness-guidebook.html).

## Install

### Claude.ai

1. Download `dist/qoe-readiness-skill.zip` from the repository.
2. Open Settings in Claude.ai. Find the Skills section and upload the zip file.
3. Switch the QoE readiness skill on.
4. Start a new chat and write: "Help me prepare for a QoE." The skill instructions tell the model to show the start text first.

### Claude Code

1. Download `dist/qoe-readiness-skill.zip` from the repository and unzip it. The archive holds one folder named `qoe-readiness`.
2. Copy that folder into `~/.claude/skills/`. The result is `~/.claude/skills/qoe-readiness/SKILL.md`.
3. Start Claude Code and write: "Help me prepare for a QoE." The skill instructions tell the model to show the start text first.

### ChatGPT custom GPT

1. In ChatGPT, create a new GPT.
2. Open `skill/gpt-instructions.md` in the repository. Paste its full text into the Instructions field.
3. Upload the 19 knowledge files from the `core`, `data`, and `scripts` folders inside the `skill` folder. The instructions file lists each one.
4. Turn on Code Interpreter. The GPT needs it to run the scripts and to build the Excel workbook.
5. Save the GPT, start a chat, and write: "Help me prepare for a QoE." The GPT instructions tell the model to show the start text first.

## Sample company

The folder `examples/sample-saas-co/` holds a synthetic company, "Sample SaaS Co." Every name and figure is invented. The folder has the canonical CSV files, the finished workbook, and `progress.json`.

The file `progress.json` stores file paths relative to the `qoe-readiness/` folder. Run the sample commands from there.

To rebuild the sample workbook under a new name, run this command from `qoe-readiness/`:

```
python skill/scripts/build_workbook.py --state examples/sample-saas-co/progress.json --canonical examples/sample-saas-co --out my-sample.xlsx
```

The scripts need Python 3 and the `openpyxl` package.

## Before you rely on it

Do these checks first. The skill is new, and these items are not yet confirmed.

1. Open the sample workbook in Google Sheets. Confirm that the figures calculate and that no cell shows an error.
2. Run one real export from each accounting system you use. Column layouts are not yet confirmed against real exports.
3. Confirm the Claude.ai Skills upload location. Check that the Settings and Skills section exists in your plan.
4. Run one full session before you rely on the skill. No live run in Claude.ai or ChatGPT has been done yet. The only test so far is a scripted dry run of the scripts.

## Next step

Book a 30-minute exit assessment: https://calendly.com/khaledazar/exit-builder

## License

The guidebook (PDF and HTML) is licensed under CC BY-NC-ND 4.0. The skill in `skill/`, the tools in `tools/`, and the sample workbook (.xlsx) are licensed under the MIT License. See `skill/LICENSE`, `tools/LICENSE`, and the root `LICENSE`.
