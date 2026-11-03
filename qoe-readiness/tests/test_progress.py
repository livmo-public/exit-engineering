import json

import pytest

import progress
from helpers import CRITICAL_CORE, FULL_INTAKE, READY_STATE, month_range, state_with_pl_bs

LATEST = "2026-09"
YEAR = month_range("2025-10", "2026-09")


def test_stage1_gate_needs_intake_and_disclaimer(data_dir):
    s = progress.new_state()
    assert not progress.gate_passed(s, 1, data_dir)
    s = {**s, "intake": FULL_INTAKE, "disclaimer_acknowledged": True}
    assert progress.gate_passed(s, 1, data_dir)


def test_stage1_blank_answer_fails(data_dir):
    s = {**progress.new_state(), "intake": {**FULL_INTAKE, "revenue_range": " "},
         "disclaimer_acknowledged": True}
    assert not progress.gate_passed(s, 1, data_dir)


def test_stage1_billing_system_required_only_for_saas(data_dir):
    base = {**progress.new_state(), "disclaimer_acknowledged": True}
    saas = {**base, "intake": {**FULL_INTAKE, "business_type": "saas"}}
    assert not progress.gate_passed(saas, 1, data_dir)
    saas_done = {**saas, "intake": {**saas["intake"], "billing_system": "stripe"}}
    assert progress.gate_passed(saas_done, 1, data_dir)
    assert progress.gate_passed({**base, "intake": FULL_INTAKE}, 1, data_dir)


def test_stage2_gate(data_dir):
    s = progress.new_state()
    assert not progress.gate_passed(s, 2, data_dir)
    s = {**s, "modules_confirmed": True}
    assert not progress.gate_passed(s, 2, data_dir)
    assert progress.gate_passed({**s, "file_list_shown": True}, 2, data_dir)


def test_floor_needs_12_consecutive_months_to_latest(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=True)
    assert progress.meets_floor(s, data_dir).passed
    s = state_with_pl_bs(tmp_path, month_range("2025-09", "2026-08"), LATEST, gl=True)
    assert not progress.meets_floor(s, data_dir).passed


def test_floor_rejects_gap(tmp_path, data_dir):
    months = [m for m in YEAR if m != "2026-03"]
    assert not progress.meets_floor(state_with_pl_bs(tmp_path, months, LATEST, gl=True), data_dir).passed


def test_floor_needs_gl_or_bank(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=False)
    assert not progress.meets_floor(s, data_dir).passed
    bank = {**s, "files": {**s["files"], "C4": {"status": "uploaded"}}}
    assert progress.meets_floor(bank, data_dir).passed


def test_partial_file_never_meets_floor(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=True, pl_status="partial")
    assert not progress.meets_floor(s, data_dir).passed
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=False)
    partial_gl = {**s, "files": {**s["files"], "C3": {"status": "partial"}}}
    assert not progress.meets_floor(partial_gl, data_dir).passed


def test_floor_fails_on_missing_or_bad_canonical_file(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=True)
    gone = {**s, "files": {**s["files"], "C1": {"status": "uploaded", "canonical_path": str(tmp_path / "no.csv")}}}
    assert not progress.meets_floor(gone, data_dir).passed
    no_path = {**s, "files": {**s["files"], "C2": {"status": "uploaded"}}}
    assert not progress.meets_floor(no_path, data_dir).passed
    bad = tmp_path / "bad.csv"
    bad.write_text("period,account\n2026-09,Sales\n", encoding="utf-8")
    broken = {**s, "files": {**s["files"], "C1": {"status": "uploaded", "canonical_path": str(bad)}}}
    assert not progress.meets_floor(broken, data_dir).passed


def test_floor_fails_without_latest_closed_month(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=True)
    assert not progress.meets_floor({**s, "intake": {}}, data_dir).passed


def test_months_covered_sorted_distinct():
    rows = [{"period": "2026-02"}, {"period": "2026-01"}, {"period": "2026-02"}]
    assert progress.months_covered(rows) == ["2026-01", "2026-02"]


def test_stage3_gate(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=True)
    assert not progress.gate_passed(s, 3, data_dir)  # C5 to C9 have no status
    full = {**s, "files": {**{f: {"status": "missing", "reason": "unknown"} for f in CRITICAL_CORE},
                           **s["files"]}}
    assert progress.gate_passed(full, 3, data_dir)
    assert not progress.gate_passed({**full, "account_map_confirmed": False}, 3, data_dir)


def test_stage3_requires_status_for_active_module_critical_files(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=True)
    files = {**{f: {"status": "not_applicable"} for f in CRITICAL_CORE}, **s["files"]}
    saas = {**s, "files": files, "intake": {**s["intake"], "business_type": "saas"}}
    assert not progress.gate_passed(saas, 3, data_dir)  # S1 is critical and has no status
    saas_done = {**saas, "files": {**files, "S1": {"status": "missing", "reason": "never_kept"}}}
    assert progress.gate_passed(saas_done, 3, data_dir)


def test_stage4_gate_needs_responses_and_adjustment_decisions(data_dir):
    s = {**READY_STATE, "findings": [{"id": "K04-1", "severity": "critical"}], "responses": {}}
    assert not progress.gate_passed(s, 4, data_dir)
    s = {**s, "responses": {"K04-1": {"type": "accept"}}, "adjustments": [{"id": "A1", "decision": None}]}
    assert not progress.gate_passed(s, 4, data_dir)
    s = {**s, "adjustments": [{"id": "A1", "decision": "approved", "amounts": {"TTM": 12000.0}}]}
    assert progress.gate_passed(s, 4, data_dir)


@pytest.mark.parametrize("decision", ["approved", "edited"])
@pytest.mark.parametrize("amounts", [None, {}])
def test_stage4_counted_adjustment_needs_an_owner_stated_amount(data_dir, decision, amounts):
    adjustment = {"id": "A1", "decision": decision, "amounts": amounts}
    s = {**READY_STATE, "adjustments": [adjustment]}
    assert not progress.gate_passed(s, 4, data_dir)
    stated = {**adjustment, "amounts": {"TTM": 500.0}}
    assert progress.gate_passed({**READY_STATE, "adjustments": [stated]}, 4, data_dir)


def test_stage4_rejected_adjustment_needs_no_amount(data_dir):
    s = {**READY_STATE, "adjustments": [{"id": "A1", "decision": "rejected", "amounts": {}}]}
    assert progress.gate_passed(s, 4, data_dir)


def test_stage4_ignores_medium_and_low_findings(data_dir):
    s = {**READY_STATE, "findings": [{"id": "K02-1", "severity": "medium"}, {"id": "K09-1", "severity": "low"}]}
    assert progress.gate_passed(s, 4, data_dir)


def test_stage4_ignores_review_findings_at_any_severity(data_dir):
    review = {"id": "K02-1", "severity": "high", "method": "model_review", "status": "review"}
    assert progress.gate_passed({**READY_STATE, "findings": [review]}, 4, data_dir)
    assert not progress.is_blocking(review)
    assert progress.is_blocking({**review, "status": "fail"})


def test_stage4_high_needs_response_and_explain_needs_text(data_dir):
    s = {**READY_STATE, "findings": [{"id": "K05-1", "severity": "high"}]}
    assert not progress.gate_passed(s, 4, data_dir)
    s = {**s, "responses": {"K05-1": {"type": "explain"}}}
    assert not progress.gate_passed(s, 4, data_dir)
    s = {**s, "responses": {"K05-1": {"type": "explain", "text": "One-time event."}}}
    assert progress.gate_passed(s, 4, data_dir)
    s = {**s, "responses": {"K05-1": {"type": "bogus"}}}
    assert not progress.gate_passed(s, 4, data_dir)


def test_gate_texts_are_static_strings(tmp_path, data_dir):
    s = state_with_pl_bs(tmp_path, YEAR, LATEST, gl=True)
    for stage in (1, 2, 3, 4):
        for state in (progress.new_state(), s):
            items = progress.gate_status(state, stage, data_dir)
            assert items and all(isinstance(i.text, str) and i.text.endswith(".") for i in items)
        assert [i.text for i in progress.gate_status(progress.new_state(), stage, data_dir)] == \
               [i.text for i in progress.gate_status(s, stage, data_dir)]


def test_gate_status_rejects_unknown_stage(data_dir):
    with pytest.raises(ValueError):
        progress.gate_status(progress.new_state(), 5, data_dir)


def test_saas_module_on():
    assert progress.active_modules({"business_type": "saas"}) == ["core", "saas"]


def test_modules_for_other_business_types():
    assert progress.active_modules({"business_type": "services"}) == ["core"]
    assert progress.active_modules({"business_type": "product"}) == ["core", "product"]
    assert progress.active_modules({"business_type": "project"}) == ["core", "product"]
    assert progress.active_modules({}) == ["core"]


def test_active_files_filters_by_module():
    catalog = [{"id": "C1", "module": "core"}, {"id": "S1", "module": "saas"}, {"id": "P1", "module": "product"}]
    ids = lambda t: [f["id"] for f in progress.active_files({"intake": {"business_type": t}}, catalog)]
    assert ids("saas") == ["C1", "S1"]
    assert ids("product") == ["C1", "P1"]
    assert ids("services") == ["C1"]


def test_save_load_round_trip(tmp_path):
    s = {**progress.new_state(), "intake": FULL_INTAKE}
    path = tmp_path / "progress.json"
    progress.save(s, path)
    assert progress.load(path) == s
    assert not (tmp_path / "progress.json.tmp").exists()


def test_load_fills_defaults_and_rejects_bad_version(tmp_path):
    path = tmp_path / "progress.json"
    path.write_text(json.dumps({"version": 1, "stage": 2}), encoding="utf-8")
    loaded = progress.load(path)
    assert loaded["stage"] == 2 and loaded["files"] == {} and loaded["file_list_shown"] is False
    path.write_text(json.dumps({"version": 2}), encoding="utf-8")
    with pytest.raises(ValueError):
        progress.load(path)


def test_new_state_does_not_share_mutable_values():
    a, b = progress.new_state(), progress.new_state()
    a["files"]["C1"] = {"status": "uploaded"}
    assert b["files"] == {}
