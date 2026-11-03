"""Progress state and stage gates for the QoE readiness skill.

Standard library only. The state is a plain dict saved as progress.json.
Functions never change the state they receive; they return new values.
"""
import json
import os
from dataclasses import dataclass
from pathlib import Path

import canonical

VERSION = 1
FLOOR_MONTHS = 12
FILE_STATUSES = ("uploaded", "partial", "missing", "not_applicable")
RESPONSE_TYPES = ("fix", "explain", "accept")
DECISIONS = ("approved", "edited", "rejected")
COUNTED_DECISIONS = ("approved", "edited")
BLOCKING_SEVERITIES = ("critical", "high")
REVIEW_STATUS = "review"

TEXT_INTAKE_COMPLETE = "Every intake question has an answer."
TEXT_DISCLAIMER = "The owner acknowledges the disclaimer."
TEXT_MODULES = "The owner confirms the modules."
TEXT_LIST_SHOWN = "The owner sees the full list with critical files marked."
TEXT_CRITICAL_STATUS = "Every critical file has a status."
TEXT_FLOOR = 'The hard floor and minimum history are met (see "Gate rule").'
TEXT_ACCOUNT_MAP = "The owner confirms the account map."
TEXT_FINDINGS = "Every critical and high finding has a response."
TEXT_ADJUSTMENTS = "Every candidate adjustment has a response."


@dataclass(frozen=True)
class GateItem:
    text: str
    passed: bool


def new_state() -> dict:
    """Return a fresh progress state."""
    return {
        "version": VERSION,
        "stage": 1,
        "intake": {},
        "disclaimer_acknowledged": False,
        "modules": [],
        "modules_confirmed": False,
        "file_list_shown": False,
        "files": {},
        "account_map": {},
        "account_map_confirmed": False,
        "findings": [],
        "responses": {},
        "adjustments": [],
    }


def load(path: Path) -> dict:
    """Read a progress file. Keys the file lacks take their default from new_state()."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: progress file must hold a JSON object")
    if data.get("version") != VERSION:
        raise ValueError(f"{path}: unsupported progress version '{data.get('version')}'; expected {VERSION}")
    return {**new_state(), **data}


def save(state: dict, path: Path) -> None:
    """Write the state to a progress file. The write replaces the file in one step."""
    target = Path(path)
    temp = target.with_name(target.name + ".tmp")
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
        handle.write("\n")
    os.replace(temp, target)


def active_modules(intake: dict) -> list[str]:
    """Core is always on. SaaS is on for saas. Product is on for product and project."""
    business_type = intake.get("business_type")
    modules = ["core"]
    if business_type == "saas":
        modules.append("saas")
    if business_type in ("product", "project"):
        modules.append("product")
    return modules


def active_files(state: dict, files_catalog: list[dict]) -> list[dict]:
    """Return the catalog records that belong to the active modules."""
    modules = active_modules(state.get("intake", {}))
    return [record for record in files_catalog if record["module"] in modules]


def months_covered(rows: list[dict]) -> list[str]:
    """Return the sorted, distinct YYYY-MM periods in canonical P&L or balance sheet rows."""
    return sorted({row["period"] for row in rows if row.get("period")})


def _month_index(period: str) -> int:
    year, month = period.split("-")
    return int(year) * 12 + int(month) - 1


def _covers_floor(rows: list[dict], latest: str) -> bool:
    """True when every month in the 12 months that end at latest appears in rows."""
    covered = {_month_index(p) for p in months_covered(rows)}
    end = _month_index(latest)
    return all(end - offset in covered for offset in range(FLOOR_MONTHS))


def _is_period(value) -> bool:
    return (isinstance(value, str) and len(value) == 7 and value[4] == "-"
            and value[:4].isdigit() and value[5:].isdigit() and 1 <= int(value[5:]) <= 12)


def _file_covers_floor(state: dict, file_id: str, kind: str, latest: str) -> bool:
    entry = state.get("files", {}).get(file_id, {})
    if entry.get("status") != "uploaded" or not entry.get("canonical_path"):
        return False
    try:
        rows = canonical.read(kind, Path(entry["canonical_path"]))
    except (OSError, canonical.CanonicalError):
        return False
    return _covers_floor(rows, latest)


def meets_floor(state: dict, data_dir: Path) -> GateItem:
    """Check the hard floor: C1 and C2 cover 12 months to the latest closed month, plus C3 or C4.

    Only a file with status "uploaded" counts. A "partial" file never counts.
    data_dir is part of the gate interface; the floor rule itself is fixed.
    """
    latest = state.get("intake", {}).get("latest_closed_month")
    if not _is_period(latest):
        return GateItem(TEXT_FLOOR, False)
    ledger_or_bank = any(
        state.get("files", {}).get(file_id, {}).get("status") == "uploaded" for file_id in ("C3", "C4"))
    passed = (ledger_or_bank
              and _file_covers_floor(state, "C1", "pl", latest)
              and _file_covers_floor(state, "C2", "bs", latest))
    return GateItem(TEXT_FLOOR, passed)


def _has_answer(value) -> bool:
    return value is not None and not (isinstance(value, str) and value.strip() == "")


def _question_applies(question: dict, intake: dict) -> bool:
    if question.get("required"):
        return True
    condition = question.get("required_when")
    if not condition:
        return False
    return all(intake.get(key) == value for key, value in condition.items())


def _load_catalog(data_dir: Path, name: str) -> list[dict]:
    with open(Path(data_dir) / name, encoding="utf-8") as handle:
        return json.load(handle)


def _stage1(state: dict, data_dir: Path) -> list[GateItem]:
    intake = state.get("intake", {})
    questions = _load_catalog(data_dir, "intake.json")
    complete = all(_has_answer(intake.get(q["id"])) for q in questions if _question_applies(q, intake))
    return [
        GateItem(TEXT_INTAKE_COMPLETE, complete),
        GateItem(TEXT_DISCLAIMER, state.get("disclaimer_acknowledged") is True),
    ]


def _stage2(state: dict, data_dir: Path) -> list[GateItem]:
    return [
        GateItem(TEXT_MODULES, state.get("modules_confirmed") is True),
        GateItem(TEXT_LIST_SHOWN, state.get("file_list_shown") is True),
    ]


def _stage3(state: dict, data_dir: Path) -> list[GateItem]:
    catalog = _load_catalog(data_dir, "files.json")
    files = state.get("files", {})
    critical = [f for f in active_files(state, catalog) if f.get("critical")]
    all_have_status = all(files.get(f["id"], {}).get("status") in FILE_STATUSES for f in critical)
    return [
        GateItem(TEXT_CRITICAL_STATUS, all_have_status),
        meets_floor(state, data_dir),
        GateItem(TEXT_ACCOUNT_MAP, state.get("account_map_confirmed") is True),
    ]


def _response_is_valid(response) -> bool:
    if not isinstance(response, dict) or response.get("type") not in RESPONSE_TYPES:
        return False
    if response["type"] == "explain":
        return _has_answer(response.get("text"))
    return True


def _adjustment_is_decided(adjustment: dict) -> bool:
    """A decision counts when it is valid. approved and edited also need an amount the owner stated."""
    decision = adjustment.get("decision")
    if decision not in DECISIONS:
        return False
    if decision in COUNTED_DECISIONS:
        return bool(adjustment.get("amounts"))
    return True


def is_blocking(finding: dict) -> bool:
    """A critical or high finding needs a response. A finding for review never blocks a gate."""
    return finding.get("severity") in BLOCKING_SEVERITIES and finding.get("status") != REVIEW_STATUS


def _stage4(state: dict, data_dir: Path) -> list[GateItem]:
    responses = state.get("responses", {})
    blocking = [f for f in state.get("findings", []) if is_blocking(f)]
    findings_done = all(_response_is_valid(responses.get(f["id"])) for f in blocking)
    adjustments_done = all(_adjustment_is_decided(a) for a in state.get("adjustments", []))
    return [
        GateItem(TEXT_FINDINGS, findings_done),
        GateItem(TEXT_ADJUSTMENTS, adjustments_done),
    ]


_STAGES = {1: _stage1, 2: _stage2, 3: _stage3, 4: _stage4}


def gate_status(state: dict, stage: int, data_dir: Path) -> list[GateItem]:
    """Return the gate checklist for a stage (1 to 4)."""
    if stage not in _STAGES:
        raise ValueError(f"stage {stage} has no gate; expected one of {', '.join(map(str, _STAGES))}")
    return _STAGES[stage](state, data_dir)


def gate_passed(state: dict, stage: int, data_dir: Path) -> bool:
    """True when every item of the stage checklist passes."""
    return all(item.passed for item in gate_status(state, stage, data_dir))
