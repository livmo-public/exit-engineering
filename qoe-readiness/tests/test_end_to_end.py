"""End-to-end session (Task 8): stages 1 to 5 with scripted owner answers on the sample company.

The helper does what the skill does: it saves progress.json after each stage, sets canonical_path
to the absolute path of each canonical CSV it writes, and calls the script entry points.
"""
import json
from pathlib import Path

import pytest

import build_workbook
import canonical
import make_sample
import metrics
import progress
import run_checks

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "skill" / "data"
CANONICAL_FILES = {"C1": "pl", "C2": "bs", "C3": "gl", "C4": "bank", "C6": "sales", "C7": "vendor",
                   "C8": "aging", "C9": "tax", "S1": "subs"}
UNMAPPED_KINDS = ("pl", "bs", "gl")


def passed(state, stage):
    return progress.gate_passed(state, stage, DATA)


def checkpoint(state, path):
    """Save the state and read it back, as the skill does between stages."""
    progress.save(state, path)
    return progress.load(path)


def write_normalized_files(company, folder):
    """Write the canonical CSVs and return {file id: path}. Account types come from the map."""
    folder.mkdir(parents=True, exist_ok=True)
    paths = {}
    for file_id, kind in CANONICAL_FILES.items():
        rows = company["rows"][kind]
        if kind in UNMAPPED_KINDS:
            blank = [{**r, "account_type": "", **({"subtype": ""} if kind == "bs" else {})} for r in rows]
            rows = canonical.apply_account_map(blank, company["account_map"])
            assert rows == company["rows"][kind]
        paths[file_id] = folder / f"{kind}.csv"
        canonical.write(kind, rows, paths[file_id])
    return paths


def stage_1(tmp_path, state_path):
    state = progress.new_state()
    assert not passed(state, 1)
    state = {**state, "intake": dict(make_sample.INTAKE)}
    assert not passed(state, 1)  # the disclaimer is not acknowledged yet
    state = checkpoint({**state, "disclaimer_acknowledged": True, "stage": 2}, state_path)
    assert passed(state, 1)
    return state


def stage_2(state, state_path):
    assert not passed(state, 2)
    state = {**state, "modules": progress.active_modules(state["intake"]), "modules_confirmed": True}
    assert not passed(state, 2)  # the owner has not seen the full list yet
    state = checkpoint({**state, "file_list_shown": True, "stage": 3}, state_path)
    assert passed(state, 2)
    assert state["modules"] == ["core", "saas"]
    return state


def stage_3(company, state, state_path, folder):
    paths = write_normalized_files(company, folder)
    files = {**make_sample.DOCUMENT_FILES}
    for file_id, path in paths.items():
        files[file_id] = {"status": "uploaded", "source_system": make_sample.SOURCE_SYSTEMS[file_id],
                          "canonical_path": str(path)}
    only_pl = {k: v for k, v in files.items() if k not in ("C2", "C3", "C4")}
    assert not passed({**state, "files": only_pl}, 3)  # no hard floor, no account map
    with_files = {**state, "files": files, "account_map": company["account_map"]}
    assert not passed(with_files, 3)  # the owner has not confirmed the account map
    state = checkpoint({**with_files, "account_map_confirmed": True, "stage": 4}, state_path)
    assert passed(state, 3)
    return state


def stage_4(company, state, state_path, folder):
    answers = folder / "owner-answers.json"
    answers.write_text(json.dumps({"K12": make_sample.K12_STATEMENT}), encoding="utf-8")
    argv = ["--state", str(state_path), "--canonical", str(folder), "--data", str(DATA)]
    assert run_checks.main(argv + ["--answers", str(answers)]) == 0
    state = progress.load(state_path)
    found = {f["check_id"] for f in state["findings"]}
    assert {"K01", "K03", "K08", "K12"} <= found
    questions = {q["check_id"]: q for q in run_checks.questions(state, DATA)}
    assert questions["K11"]["candidates"]  # reads the vendor file through canonical_path
    assert not passed(state, 4)  # critical and high findings have no response yet
    state = {**state, "responses": dict(make_sample.RESPONSES)}
    owner_stated = [{**a, "decision": None} for a in make_sample.ADJUSTMENTS]
    state = {**state, "adjustments": owner_stated}
    assert not passed(state, 4)  # no adjustment has a decision yet
    decided = [{**a} for a in make_sample.ADJUSTMENTS]
    return checkpoint({**state, "adjustments": decided, "stage": 5}, state_path)


def stage_5(state, folder, tmp_path):
    out = tmp_path / "qoe-readiness-workbook.xlsx"
    state_path = tmp_path / "progress.json"
    argv = ["--state", str(state_path), "--canonical", str(folder), "--data", str(DATA),
            "--out", str(out)]
    assert build_workbook.main(argv) == 0
    return out


def run_session_through_gates(tmp_path):
    """Drive stages 1 to 5 with scripted owner answers; return the final state."""
    state_path = tmp_path / "progress.json"
    folder = tmp_path / "canonical"
    company = make_sample.build_company(seed=7)
    state = stage_1(tmp_path, state_path)
    state = stage_2(state, state_path)
    state = stage_3(company, state, state_path, folder)
    state = stage_4(company, state, state_path, folder)
    stage_5(state, folder, tmp_path)
    return state


def test_end_to_end_gates(tmp_path):
    state = run_session_through_gates(tmp_path)
    assert all(progress.gate_passed(state, s, DATA) for s in (1, 2, 3, 4))
    assert (tmp_path / "qoe-readiness-workbook.xlsx").exists()


def test_end_to_end_summary_excludes_rejected_adjustments(tmp_path):
    state = run_session_through_gates(tmp_path)
    summary = build_workbook.chat_summary(state, tmp_path / "canonical", DATA)
    ttm = ["2025-10", "2025-11", "2025-12"] + [f"2026-{m:02d}" for m in range(1, 10)]
    counted = sum(metrics.adjustment_amount(a, ttm, "TTM") for a in state["adjustments"]
                  if a["decision"] in ("approved", "edited"))
    rejected = sum(metrics.adjustment_amount(a, ttm, "TTM") for a in state["adjustments"]
                   if a["decision"] == "rejected")
    gap = summary["adjusted_ebitda"]["TTM"] - summary["reported_ebitda"]["TTM"]
    assert rejected > 0 and gap == pytest.approx(counted, abs=0.01)
    assert summary["top_findings"][0]["severity"] == "critical"
    assert summary["gaps"] and summary["next_step"]


def test_end_to_end_workbook_has_the_header_on_every_tab(tmp_path):
    import openpyxl
    run_session_through_gates(tmp_path)
    wb = openpyxl.load_workbook(tmp_path / "qoe-readiness-workbook.xlsx")
    assert all(ws["A1"].value.startswith("Owner-prepared QoE readiness workbook.") for ws in wb.worksheets)
