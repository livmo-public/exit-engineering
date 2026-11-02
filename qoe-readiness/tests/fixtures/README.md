# Test fixtures

These files are synthetic exports for the tests of `normalize.py`.

The fixtures follow `skill/data/export_presets.json`. That file is unverified: every entry has `verified: false`, because no vendor page states the export headers. No fixture comes from a real export.

Re-check each fixture against a real export of the same system and report before the skill ships. Replace the fixture where the headers or the layout differ.

All names in the fixtures are fictional.

## Canonical sets for the workbook tests

`canonical/` holds one small synthetic company in canonical CSV form, for `test_build_workbook.py`. It covers 2025-01 to 2026-03 with a December year end. Monthly amounts are constant within a year, so each test value has a short hand calculation (see the comments in `tests/conftest.py`). Planted facts: one bank month (2025-08) differs from balance sheet cash by 500, cash-basis P&L rows sit beside the accrual rows, and one customer name has a second spelling (`ACME  INC`).
