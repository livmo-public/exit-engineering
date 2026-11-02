"""Tests for the five JSON data catalogs in skill/data."""
import datetime
import json
import re

import pytest

import canonical

SYSTEMS_ACCOUNTING = ("qbo", "qbd", "xero")
REPORT_IDS = (
    "pl_by_month", "bs_by_month", "general_ledger", "sales_by_customer",
    "expenses_by_vendor", "ar_aging", "ap_aging",
)

def _load(data_dir, name):
    return json.loads((data_dir / name).read_text(encoding="utf-8"))


@pytest.fixture
def intake(data_dir):
    return _load(data_dir, "intake.json")


@pytest.fixture
def files(data_dir):
    return _load(data_dir, "files.json")


@pytest.fixture
def checks(data_dir):
    return _load(data_dir, "checks.json")


@pytest.fixture
def tabs(data_dir):
    return _load(data_dir, "workbook.json")


@pytest.fixture
def presets(data_dir):
    return _load(data_dir, "export_presets.json")


def _walk_strings(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk_strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_strings(item)
    elif isinstance(node, str):
        yield node


# ---------------------------------------------------------------- intake

def test_intake_ids_and_types(intake):
    by_id = {q["id"]: q for q in intake}
    assert [q["id"] for q in intake] == [
        "business_type", "revenue_range", "accounting_system", "billing_system",
        "accounting_basis", "fiscal_year_end_month", "latest_closed_month",
        "sale_timeline", "buyer_financing", "price_may_reach_3m", "advisor_name",
    ]
    assert by_id["business_type"]["choices"] == ["saas", "services", "product", "project"]
    assert by_id["accounting_system"]["choices"] == ["qbo", "qbd", "xero", "other"]
    assert by_id["billing_system"]["choices"] == ["stripe", "other", "none"]
    assert by_id["accounting_basis"]["choices"] == ["cash", "accrual", "both"]
    assert by_id["buyer_financing"]["choices"] == ["sba", "conventional", "cash", "unknown"]
    assert by_id["price_may_reach_3m"]["choices"] == ["yes", "no", "unknown"]
    assert by_id["fiscal_year_end_month"]["type"] == "int"
    assert by_id["latest_closed_month"]["type"] == "month"
    assert by_id["advisor_name"]["required"] is False
    assert by_id["billing_system"]["required"] is False
    assert by_id["billing_system"]["required_when"] == {"business_type": "saas"}
    assert by_id["fiscal_year_end_month"]["min"] == 1 and by_id["fiscal_year_end_month"]["max"] == 12
    for q in intake:
        assert q["type"] in ("choice", "text", "month", "int")
        assert (q["type"] == "choice") == ("choices" in q)
        assert q["question"].strip()


# ---------------------------------------------------------------- files

def test_file_ids_and_critical_set(files):
    assert {f["id"] for f in files if f["critical"]} == {f"C{i}" for i in range(1, 10)} | {"S1"}


def test_file_ids_complete(files):
    expected = (
        [f"C{i}" for i in range(1, 10)] + [f"R{i}" for i in range(1, 12)]
        + [f"S{i}" for i in range(1, 7)] + ["P1", "P2"]
    )
    assert [f["id"] for f in files] == expected
    for f in files:
        prefix = f["id"][0]
        assert f["module"] == {"C": "core", "R": "core", "S": "saas", "P": "product"}[prefix]


def test_feeds_tabs_exist(files, tabs):
    tab_ids = {t["id"] for t in tabs}
    assert all(set(f["feeds_tabs"]) <= tab_ids for f in files)


def test_files_canonical_kind(files):
    expected = {
        "C1": "pl", "C2": "bs", "C3": "gl", "C4": "bank", "C6": "sales",
        "C7": "vendor", "C8": "aging", "C9": "tax", "S1": "subs",
        "P1": "inventory", "P2": "inventory",
    }
    for f in files:
        assert f["canonical_kind"] == expected.get(f["id"]), f["id"]
        if f["canonical_kind"] is not None:
            assert f["canonical_kind"] in canonical.KINDS


def test_files_text_fields(files):
    for f in files:
        assert f["name"].strip() and f["period"].strip() and f["why_buyers_ask"].strip()
        assert isinstance(f["feeds_tabs"], list) and isinstance(f["critical"], bool)
        assert isinstance(f["export_ref"], list)


def test_export_refs_resolve_to_presets(files, presets):
    for f in files:
        for ref in f["export_ref"]:
            systems = ["stripe"] if f["module"] == "saas" else list(SYSTEMS_ACCOUNTING)
            for system in systems:
                assert ref in presets[system], (f["id"], ref, system)
    refs = {r for f in files for r in f["export_ref"]}
    assert set(REPORT_IDS) | {"subscriptions"} == refs


# ---------------------------------------------------------------- checks

def test_checks_complete_and_valid(checks, files):
    assert [c["id"] for c in checks] == [f"K{i:02d}" for i in range(1, 22)]
    file_ids = {f["id"] for f in files}
    for c in checks:
        assert set(c["inputs"]) <= file_ids
        if c["method"] == "model_review":
            assert c["severity"] in ("medium", "low")
        assert (c["owner_question"] is not None) == (c["method"] == "owner_question")


def test_check_methods(checks):
    by_method = {}
    for c in checks:
        by_method.setdefault(c["method"], set()).add(c["id"])
    ids = lambda *n: {f"K{i:02d}" for i in n}  # noqa: E731
    assert by_method["computed"] == ids(1, 3, 4, 5, 7, 8, 9, 10, 16, 18, 19, 20, 21)
    assert by_method["owner_question"] == ids(6, 11, 12, 13, 14, 17)
    assert by_method["model_review"] == ids(2, 15)


def test_check_fields_and_enums(checks):
    for c in checks:
        assert c["category"] in ("hygiene", "risk")
        assert c["severity"] in ("critical", "high", "medium", "low")
        assert c["module"] in ("core", "saas")
        assert isinstance(c["params"], dict)
        for field in ("name", "condition", "owner_message", "fix"):
            assert c[field].strip(), (c["id"], field)
    by_id = {c["id"]: c for c in checks}
    k21 = by_id["K21"]
    assert (k21["name"], k21["module"], k21["category"], k21["severity"], k21["method"]) == (
        "Cash-basis books only", "core", "hygiene", "high", "computed")
    assert k21["inputs"] == ["C1"]
    assert by_id["K19"]["category"] == "risk" and by_id["K20"]["category"] == "risk"


def test_thresholds_match_spec(checks):
    p = {c["id"]: c["params"] for c in checks}
    assert p["K04"]["cash_tolerance"] == 100
    assert p["K05"]["pct"] == 0.05 and p["K07"]["pct"] == 0.05 and p["K10"]["pct"] == 0.05 and p["K03"]["pct"] == 0.05
    assert p["K18"]["days"] == 90
    assert p["K19"] == {"top1_pct": 0.20, "top5_pct": 0.50}
    assert p["K20"]["grr_min"] == 0.70


def test_k11_threshold_by_year(checks):
    k11 = next(c for c in checks if c["id"] == "K11")["params"]
    assert k11["threshold_by_year"] == {"2023": 600, "2024": 600, "2025": 600, "2026": 2000}
    assert k11["source"].startswith("https://www.irs.gov/")
    assert datetime.date.fromisoformat(k11["checked"])


# ---------------------------------------------------------------- workbook

def test_tab_titles_short(tabs):
    assert all(len(t["title"]) <= 31 for t in tabs)


def test_tab_ids_and_titles(tabs):
    titles = {t["id"]: t["title"] for t in tabs}
    assert titles == {
        "summary": "Summary", "scope": "Scope and limitations", "findings": "Findings",
        "inventory": "File inventory", "bridge": "Adjusted EBITDA bridge",
        "addbacks": "Add-backs", "proof_cash": "Proof of cash",
        "proof_revenue": "Proof of revenue", "revenue": "Revenue analysis",
        "opex": "Opex by vendor", "nwc": "NWC trend",
        "deferred_revenue": "Deferred revenue", "inventory_wip": "Inventory and WIP",
        "input_pl": "Inputs - P&L", "input_bs": "Inputs - Balance sheet",
        "input_gl": "Inputs - General ledger", "input_bank": "Inputs - Bank",
        "input_sales": "Inputs - Sales", "input_vendor": "Inputs - Vendors",
        "input_subs": "Inputs - Subscriptions", "input_aging": "Inputs - Aging",
        "input_tax": "Inputs - Tax", "input_inventory": "Inputs - Inventory",
    }
    assert [t["id"] for t in tabs][:3] == ["summary", "scope", "findings"]
    assert len({t["title"] for t in tabs}) == len(tabs)


def test_input_tabs_cover_every_canonical_kind(tabs, files):
    inputs = {t["id"]: t for t in tabs if t["kind"] == "input"}
    assert {t["canonical_kind"] for t in inputs.values()} == set(canonical.KINDS)
    assert len(inputs) == len(canonical.KINDS)
    assert all(t["id"] == f"input_{t['canonical_kind']}" for t in inputs.values())
    for t in tabs:
        if t["kind"] != "input":
            assert t.get("canonical_kind") is None
    file_ids = {f["id"] for f in files}
    assert all(set(t["inputs"]) <= file_ids for t in tabs)


def test_tab_modules_and_kinds(tabs):
    by_id = {t["id"]: t for t in tabs}
    assert by_id["deferred_revenue"]["module"] == "saas" and by_id["input_subs"]["module"] == "saas"
    assert by_id["inventory_wip"]["module"] == "product" and by_id["input_inventory"]["module"] == "product"
    assert by_id["summary"]["kind"] == "summary"
    assert by_id["proof_cash"]["kind"] == "computed"
    assert {by_id[i]["kind"] for i in ("scope", "findings", "inventory", "addbacks")} == {"register"}
    assert all(t["kind"] in ("summary", "computed", "input", "register") for t in tabs)


# ---------------------------------------------------------------- export presets

def test_presets_systems_and_reports(presets):
    assert set(presets) == {"qbo", "qbd", "xero", "stripe"}
    for system in SYSTEMS_ACCOUNTING:
        assert set(presets[system]) == set(REPORT_IDS)
    assert set(presets["stripe"]) == {"subscriptions"}


def _all_reports(presets):
    for system, reports in presets.items():
        for report_id, report in reports.items():
            yield system, report_id, report


def test_presets_every_report_is_complete(presets):
    for system, report_id, r in _all_reports(presets):
        where = (system, report_id)
        assert r["kind"] in canonical.KINDS, where
        assert r["layout"] in ("pivot", "flat", "grouped"), where
        assert r["report_name"].strip(), where
        assert r["menu_path"].strip(), where
        assert isinstance(r["columns"], dict) and r["columns"], where
        assert r["source_url"].startswith("https://"), where
        assert datetime.date.fromisoformat(r["checked"]), where
        assert isinstance(r["verified"], bool), where
        assert isinstance(r["notes"], str) and r["notes"].strip(), where
        if r["layout"] == "grouped":
            assert "group_header_column" in r and isinstance(r["group_header_column"], str), where
            assert r["group_provides"] is None or r["group_provides"] in canonical.KINDS[r["kind"]], where
        else:
            assert "group_header_column" not in r and "group_provides" not in r, where


def test_presets_layout_by_report(presets):
    for system in SYSTEMS_ACCOUNTING:
        reports = presets[system]
        for rid in ("pl_by_month", "bs_by_month"):
            assert reports[rid]["layout"] == "pivot", (system, rid)
        assert reports["general_ledger"]["layout"] == "grouped", system
    for rid in ("sales_by_customer", "expenses_by_vendor"):
        assert presets["qbo"][rid]["layout"] == "pivot"
        assert presets["qbd"][rid]["layout"] == "pivot"
    assert presets["stripe"]["subscriptions"]["layout"] == "flat"


def test_presets_columns_cover_canonical_kind(presets):
    always_derived = {"basis", "account_type", "subtype"}
    for system, report_id, r in _all_reports(presets):
        kind_cols = set(canonical.KINDS[r["kind"]])
        columns = set(r["columns"])
        constants = set(r.get("constants", {}))
        extra = columns - kind_cols - {"amount_signed"}
        assert not extra, (system, report_id, extra)
        assert all(isinstance(v, str) for v in r["columns"].values())
        covered = columns | constants | always_derived
        if r["layout"] == "pivot":
            # period and amount come from the month columns.
            covered |= {"period", "amount", "balance"}
        if r["layout"] == "grouped":
            covered |= {r["group_provides"]} if r["group_provides"] else set()
        if r.get("period_mode") == "per_run":
            # The owner runs the report once per month, so the run gives the period.
            covered |= {"period"}
        if "amount_signed" in columns:
            covered |= {"debit", "credit"}
        missing = kind_cols - covered
        assert not missing, (system, report_id, missing)


def test_catalog_text_names_no_outside_person_or_company(presets, intake, files, checks, tabs, denylist):
    if not denylist:
        pytest.skip("denylist file not found; it lives outside the repo on purpose")
    for catalog in (presets, intake, files, checks, tabs):
        for text in _walk_strings(catalog):
            low = text.lower()
            for term in denylist:
                assert term not in low, (term, text)


def test_denylist_loader_reads_env_path(tmp_path, monkeypatch):
    from conftest import load_denylist

    path = tmp_path / "deny.txt"
    path.write_text("Alpha Corp\n\n# comment\nbeta\n", encoding="utf-8")
    monkeypatch.setenv("QOE_DENYLIST", str(path))
    assert load_denylist() == ["alpha corp", "beta"]
    monkeypatch.setenv("QOE_DENYLIST", str(tmp_path / "missing.txt"))
    assert load_denylist() == []


def test_workbook_inputs_are_files_that_feed_the_tab(files, tabs):
    feeds = {f["id"]: set(f["feeds_tabs"]) for f in files}
    for tab in tabs:
        for file_id in tab["inputs"]:
            assert tab["id"] in feeds[file_id], (tab["id"], file_id)
