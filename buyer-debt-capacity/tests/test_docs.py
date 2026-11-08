"""Docs and license checks: the README, the root README and LICENSE, and no em-dashes."""
from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import load_workbook

import build_calculator as bc
from calc_math import evaluate, load_facts
from sample_data import SAMPLE

BDC_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BDC_ROOT.parent
README = BDC_ROOT / "README.md"
FACTS = load_facts()
BOOKING = "https://calendly.com/khaledazar/exit-builder"
HEADINGS = ("How to use", "Cash flow steps", "Operator salary", "SBA rules", "QoE Readiness", "License")
EM_DASH = "—"


def readme_text() -> str:
    return README.read_text(encoding="utf-8")


def test_readme_starts_with_liability():
    paragraphs = [p for p in readme_text().split("\n\n") if p.strip() and not p.startswith("#")]
    assert bc.LIABILITY in paragraphs[0]


def test_readme_sections():
    text = readme_text()
    for heading in HEADINGS:
        assert f"\n## {heading}\n" in text, heading


def test_readme_sba_source():
    text = readme_text()
    for key in ("url", "sop_version", "checked"):
        assert FACTS[key] in text, key


def test_readme_booking_link_only():
    text = readme_text()
    assert BOOKING in text
    assert "Who LIVMO is" not in text


def test_root_readme_lists_tool():
    assert "`buyer-debt-capacity/`" in (REPO_ROOT / "README.md").read_text(encoding="utf-8")


def test_root_license_mit_for_spreadsheets():
    text = (REPO_ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Spreadsheet files (.xlsx)" in text
    assert "buyer-debt-capacity/tools/LICENSE" in text
    joined = " ".join(text.split())
    assert ("Spreadsheet files (.xlsx) and the folders buyer-debt-capacity/tools/ and "
            "buyer-debt-capacity/tests/ are licensed under the MIT License instead.") in joined
    assert "also licensed" not in joined


def test_readme_license_covers_tests():
    assert "the tests in `tests/` use the MIT License" in readme_text()


def test_qoe_readme_license_line_covers_sample_workbook():
    text = (REPO_ROOT / "qoe-readiness" / "README.md").read_text(encoding="utf-8")
    assert "sample workbook (.xlsx)" in text


def test_no_em_dash():
    assert EM_DASH not in readme_text()
    for path in (bc.BLANK_FILE, bc.SAMPLE_FILE):
        for ws in load_workbook(path):
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str):
                        assert EM_DASH not in cell.value, (path, ws.title, cell.coordinate)


def test_readme_sample_figures_match_the_math():
    r = evaluate(SAMPLE, FACTS)
    text = readme_text()
    assert f"Cash available for debt: ${r.cash_available:,.0f}." in text
    assert f"Supported price: about ${r.supported_price / 1e6:.2f}M." in text
    assert f"Asking price: ${SAMPLE.asking_price / 1e6:.1f}M." in text
    assert f"Coverage at the asking price: {r.coverage_at_ask:.2f}." in text
    assert f'Status: "{r.status}".' in text
    assert "qoe" in r.flags


def test_readme_sba_scope_qualifiers():
    text = readme_text()
    assert "does not finance real estate" in text
    assert "new owner buys the business" in text
    assert "owner buyout" in text.lower()
    assert "loan limit" in text
    assert "has everything you need" not in text
    assert "only with proof" not in text


def test_readme_sba_wording():
    text = readme_text()
    assert "10% of the total project cost" in text and "10% of the price." not in text
    assert "compares the down payment to the price only" in text
    assert "When a new owner buys the business, the debt service coverage ratio must be at least 1.25." in text
    assert "last fiscal year-end or on the average of the last two fiscal year-ends" in text
    assert "Flag: an SBA lender requires a Quality of Earnings report" in text
    assert "payoff period" not in text and "must be paid off over 10 years or less" in text
    assert "Do not include owner draws or distributions." in text


def test_equity_quote_carries_the_basis():
    quote = FACTS["min_equity_injection"]["quote"]
    assert quote.startswith("SBA requires equity injections (Applicant contribution) for change of ownership "
                            "transactions to be based on the total project cost")
    assert quote.endswith("Initial Acquisition: 10%.")
