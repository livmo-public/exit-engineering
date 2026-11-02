"""Write the owner-prepared QoE readiness workbook (xlsx) and the chat summary.

Standard library and openpyxl only (plus the sibling modules). The computed tabs live in
workbook_computed.py; the cell and reference helpers live in workbook_cells.py.

Rules:
- Tabs follow data/workbook.json. Tabs of inactive modules are left out.
- A tab renders when every critical input of an active module in its "inputs" is uploaded.
  A tab whose inputs hold no critical file renders when at least one input is uploaded.
  A tab that does not render shows "not available: file missing" in A4.
- Row 1 of every tab holds the full header text; row 2 the advisor line when set. Data starts
  at row 4. Input tabs hold values; computed tabs hold formulas.
- The P&L basis follows run_checks: the intake basis rows (cash, else accrual); all rows when
  no row has that basis.
- chat_summary figures come from metrics in Python, never from the workbook.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import openpyxl
from openpyxl.worksheet.worksheet import Worksheet

import canonical
import metrics
import progress
import run_checks
from workbook_cells import (FIRST_ROW, HEADER_ROW, MONEY, NOT_AVAILABLE, PCT, COUNT, AddbackRow,
                            Book, CellMap, Inputs, basis_rows, criterion, put, put_formula, put_row,
                            put_table, quote, span, widths)
from workbook_computed import ADDBACK_DECISION_COL, ADDBACK_LABEL_COL, BUILDERS

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"
HEADER = ("Owner-prepared QoE readiness workbook. Designed by LIVMO. LIVMO is not responsible for "
          "this output. This is not an independent Quality of Earnings report, an audit, a review, "
          "or a compilation. The owner supplied the source files, and no one verified them. Do not "
          "give this workbook to a lender or buyer as a QoE.")
ADVISOR_LINE = "Facilitated by {advisor_name}, LIVMO. Facilitator only."
OWNER_STATEMENT = "owner statement, no document"
SEVERITIES = ("critical", "high", "medium", "low")
MAX_TOP_FINDINGS = 5
MAX_GAPS = 5
NEXT_STEP_GAPS = "Book a LIVMO exit assessment. It helps you close these gaps before a buyer orders a QoE."
NEXT_STEP_READY = "Commission an independent sell-side QoE. Your files and answers are ready for one."
FINDINGS_HEADER = ["Finding", "Check", "Name", "Category", "Severity", "Method", "Status",
                   "Response", "Owner answer", "Detail", "Fix", "Evidence"]
INVENTORY_HEADER = ["File", "Name", "Module", "Critical", "Status", "Reason", "Source system",
                    "Feeds tabs"]
FINDINGS_SEVERITY_COL = FINDINGS_HEADER.index("Severity") + 1
INVENTORY_CRITICAL_COL = INVENTORY_HEADER.index("Critical") + 1
INVENTORY_STATUS_COL = INVENTORY_HEADER.index("Status") + 1


@dataclass(frozen=True)
class Availability:
    rendered: bool
    blocking: tuple[str, ...]
    thin: tuple[str, ...]


@dataclass(frozen=True)
class Plan:
    book: Book
    tabs: tuple[dict, ...]
    available: dict[str, Availability]
    files: tuple[dict, ...]
    checks: tuple[dict, ...]


# ---- plan ---------------------------------------------------------------------------

def _load(data_dir: Path, name: str) -> list:
    with open(Path(data_dir) / name, encoding="utf-8") as handle:
        return json.load(handle)


def _uploaded(state: dict, file_id: str) -> bool:
    return state.get("files", {}).get(file_id, {}).get("status") == "uploaded"


def availability(tab: dict, state: dict, files: dict[str, dict], modules: list[str]) -> Availability:
    """Whether the tab renders, the files that stop it, and the optional files it lacks."""
    inputs = [i for i in tab["inputs"] if files[i]["module"] in modules]
    missing = tuple(i for i in inputs if not _uploaded(state, i))
    critical = [i for i in inputs if files[i]["critical"]]
    if not inputs:
        return Availability(True, (), ())
    if critical:
        blocking = tuple(i for i in missing if i in critical)
        thin = () if blocking else tuple(i for i in missing if i not in critical)
        return Availability(not blocking, blocking, thin)
    rendered = len(missing) < len(inputs)
    return Availability(rendered, () if rendered else missing, missing if rendered else ())


def _basis(state: dict, pl_rows: list[dict]) -> str | None:
    wanted = "cash" if state.get("intake", {}).get("accounting_basis") == "cash" else "accrual"
    return wanted if any(r["basis"] == wanted for r in pl_rows) else None


def _addback_layout(state: dict) -> tuple[AddbackRow, ...]:
    """Counted adjustments first, then rejected, then undecided; rows from row 5."""
    def rank(item: tuple[int, dict]) -> tuple[int, int]:
        decision = item[1].get("decision")
        return (0 if decision in metrics.COUNTED_DECISIONS else 1 if decision == "rejected" else 2,
                item[0])
    ordered = sorted(enumerate(state.get("adjustments", [])), key=rank)
    return tuple(AddbackRow(a, FIRST_ROW + n, a.get("decision") in metrics.COUNTED_DECISIONS)
                 for n, (_, a) in enumerate(ordered))


def _plan(state: dict, canonical_dir: Path, data_dir: Path) -> Plan:
    files, checks = _load(data_dir, "files.json"), _load(data_dir, "checks.json")
    modules = progress.active_modules(state.get("intake", {}))
    tabs = tuple(t for t in _load(data_dir, "workbook.json") if t["module"] in modules)
    by_id = {f["id"]: f for f in files}
    available = {t["id"]: availability(t, state, by_id, modules) for t in tabs}
    rows = run_checks._read_canonical(state, canonical_dir, files)
    periods = run_checks.build_context(state, rows).periods
    label_months = {**periods.fiscal_years, **({"TTM": periods.ttm} if periods.ttm else {})}
    book = Book(
        state=state, rows=rows, periods=periods, labels=tuple(label_months),
        label_months=label_months, basis=_basis(state, rows.get("pl", [])),
        latest=state.get("intake", {}).get("latest_closed_month") or (periods.months or [None])[-1],
        inputs=Inputs({t["canonical_kind"]: t["title"] for t in tabs if t["kind"] == "input"},
                      {k: len(v) for k, v in rows.items()}),
        titles={t["id"]: t["title"] for t in tabs},
        rendered=frozenset(t for t, a in available.items() if a.rendered),
        addbacks=_addback_layout(state), params={c["id"]: c["params"] for c in checks},
        modules=tuple(modules))
    return Plan(book, tabs, available, tuple(f for f in files if f["module"] in modules), tuple(checks))


# ---- register and input tabs ----------------------------------------------------------

def _input_tab(ws: Worksheet, plan: Plan, tab: dict) -> CellMap:
    kind = tab["canonical_kind"]
    columns = canonical.KINDS[kind]
    rows = [[None if r[c] == "" else r[c] for c in columns] for r in plan.book.rows.get(kind, [])]
    put_table(ws, columns, rows)
    return {}


def _sorted_findings(state: dict) -> list[dict]:
    order = {s: n for n, s in enumerate(SEVERITIES)}
    return sorted(state.get("findings", []),
                  key=lambda f: (order.get(f.get("severity"), len(SEVERITIES)),
                                 f.get("category", ""), f.get("id", "")))


def _findings_tab(ws: Worksheet, plan: Plan, tab: dict) -> CellMap:
    responses = plan.book.state.get("responses", {})
    rows = []
    for f in _sorted_findings(plan.book.state):
        response = responses.get(f.get("id"), {})
        rows.append([f.get("id"), f.get("check_id"), f.get("name"), f.get("category"),
                     f.get("severity"), f.get("method"), f.get("status"),
                     response.get("type", "none"), response.get("text"), f.get("detail"),
                     f.get("fix"), "; ".join(f.get("evidence", []))])
    put_table(ws, FINDINGS_HEADER, rows)
    return {}


def _inventory_tab(ws: Worksheet, plan: Plan, tab: dict) -> CellMap:
    states = plan.book.state.get("files", {})
    rows = []
    for f in plan.files:
        entry = states.get(f["id"], {})
        rows.append([f["id"], f["name"], f["module"], "yes" if f["critical"] else "no",
                     entry.get("status", "no status"), entry.get("reason"),
                     entry.get("source_system"), ", ".join(f["feeds_tabs"])])
    put_table(ws, INVENTORY_HEADER, rows)
    return {}


def _addbacks_tab(ws: Worksheet, plan: Plan, tab: dict) -> CellMap:
    book = plan.book
    header = ["Adjustment", "Name", "Source file", "Decision", "Owner stated", *book.labels, "Evidence"]
    assert header.index("Decision") + 1 == ADDBACK_DECISION_COL
    assert len(header) == ADDBACK_LABEL_COL + len(book.labels)
    rows = []
    for item in book.addbacks:
        a = item.adjustment
        amounts = [None if a.get("amounts") is None
                   else metrics._adjustment_amount(a, book.label_months[label], label)
                   for label in book.labels]
        rows.append([a.get("id"), a.get("name"), a.get("source_file"),
                     a.get("decision") or "no decision", "yes" if a.get("owner_stated") else "no",
                     *amounts, a.get("evidence")])
    last = put_table(ws, header, rows)
    for item in book.addbacks:
        for offset in range(len(book.labels)):
            ws.cell(item.row, ADDBACK_LABEL_COL + offset).number_format = MONEY
    put(ws, last + 2, 1, "Every amount is an owner statement. Only approved or edited "
                         "adjustments enter owner-adjusted EBITDA.")
    return {}


# ---- scope and limitations ------------------------------------------------------------

def _not_run_reason(state: dict, check: dict) -> str:
    if (state.get("intake", {}).get("accounting_basis") == "cash"
            and check["id"] in run_checks.CASH_SKIPPED_CHECKS):
        return "skipped for cash-basis books"
    absent = run_checks.ABSENCE_INPUTS.get(check["id"], ())
    needed = [i for i in check["inputs"] if i not in absent and not _uploaded(state, i)]
    any_of = check["params"].get("any_of") or []
    if any_of and not any(_uploaded(state, i) for i in any_of):
        needed.append(" or ".join(any_of))
    return "needs " + ", ".join(needed)


def _file_lines(plan: Plan) -> list[tuple[str, str]]:
    states = plan.book.state.get("files", {})
    lines = []
    for f in plan.files:
        status = states.get(f["id"], {}).get("status", "no status")
        if status != "uploaded":
            lines.append(("Missing file", f"{f['id']} {f['name']}: {status.replace('_', ' ')}"))
    for tab in plan.tabs:
        a = plan.available[tab["id"]]
        if not a.rendered:
            lines.append(("Tab not available", f"{tab['title']}: not available, file missing: "
                                               f"{', '.join(a.blocking)}"))
        elif a.thin:
            lines.append(("Tab built without a file", f"{tab['title']}: built without {', '.join(a.thin)}"))
    if "bridge" in plan.book.rendered and "addbacks" not in plan.book.rendered:
        lines.append(("Adjustments", "Adjusted EBITDA bridge: no owner-stated adjustments, "
                                     "because the Add-backs tab is not available."))
    return lines


def _scope_lines(plan: Plan) -> list[tuple[str, str]]:
    state = plan.book.state
    lines = _file_lines(plan)
    responses = state.get("responses", {})
    for f in _sorted_findings(state):
        response = responses.get(f.get("id"), {})
        if response.get("type") == "explain":
            lines.append(("Owner statement", f"{f['id']} {f.get('name')}: {response.get('text')} "
                                             f"({OWNER_STATEMENT})"))
    for check in plan.checks:
        if (check["method"] in ("computed", "model_review") and check["module"] in plan.book.modules
                and not run_checks._should_run(state, check)):
            lines.append(("Check not run", f"{check['id']} {check['name']}: not run, "
                                           f"{_not_run_reason(state, check)}"))
    basis = plan.book.basis
    lines.append(("P&L basis", f"The workbook uses the {basis}-basis P&L rows." if basis
                  else "The P&L rows carry no matching basis, so the workbook uses all rows."))
    return lines


def _scope_tab(ws: Worksheet, plan: Plan, tab: dict) -> CellMap:
    put_table(ws, ["Item", "Detail"], [list(line) for line in _scope_lines(plan)])
    ws.column_dimensions["B"].width = 100
    return {}


REGISTERS = {"scope": _scope_tab, "findings": _findings_tab, "inventory": _inventory_tab,
             "addbacks": _addbacks_tab}


# ---- summary -------------------------------------------------------------------------

def _summary_figures(ws: Worksheet, plan: Plan, cell_map: CellMap) -> None:
    labels = plan.book.labels
    put_row(ws, HEADER_ROW, ["Figure", *labels], bold=True)
    for offset, (key, text) in enumerate((("revenue", "Revenue"), ("ebitda", "Reported EBITDA"),
                                          ("adjusted", "Owner-adjusted EBITDA"))):
        row = FIRST_ROW + offset
        put(ws, row, 1, text)
        if f"bridge.{key}.{labels[0] if labels else ''}" not in cell_map:
            put(ws, row, 2, NOT_AVAILABLE)
            continue
        for i, label in enumerate(labels):
            sheet, cell = cell_map[f"bridge.{key}.{label}"]
            put_formula(ws, row, 2 + i, f"{quote(sheet)}!{cell}")


def _summary_counts(ws: Worksheet, plan: Plan, top: int) -> int:
    titles, state = plan.book.titles, plan.book.state
    findings_last = max(FIRST_ROW, HEADER_ROW + len(state.get("findings", [])))
    severity = f"{quote(titles['findings'])}!{span(FINDINGS_SEVERITY_COL, FIRST_ROW, findings_last)}"
    put(ws, top, 1, "Findings by severity", bold=True)
    for offset, level in enumerate(SEVERITIES, start=1):
        put(ws, top + offset, 1, f"Findings: {level}")
        put_formula(ws, top + offset, 2, f"COUNTIFS({severity},{criterion(level)})", COUNT)
    files_last = max(FIRST_ROW, HEADER_ROW + len(plan.files))
    inventory = quote(titles["inventory"])
    critical = f"{inventory}!{span(INVENTORY_CRITICAL_COL, FIRST_ROW, files_last)}"
    status = f"{inventory}!{span(INVENTORY_STATUS_COL, FIRST_ROW, files_last)}"
    row = top + len(SEVERITIES) + 2
    put(ws, row, 1, "Critical files uploaded")
    put_formula(ws, row, 2, f'COUNTIFS({critical},"yes",{status},"uploaded")', COUNT)
    put(ws, row + 1, 1, "Critical files in the list")
    put_formula(ws, row + 1, 2, f'COUNTIFS({critical},"yes")', COUNT)
    put(ws, row + 2, 1, "Share of critical files uploaded")
    put_formula(ws, row + 2, 2, f"IFERROR(B{row}/B{row + 1},0)", PCT)
    return row + 4


def _summary_tab(ws: Worksheet, plan: Plan, cell_map: CellMap) -> None:
    _summary_figures(ws, plan, cell_map)
    top = _summary_counts(ws, plan, FIRST_ROW + 4)
    put_row(ws, top, ["Top findings", "Name", "Severity", "Response"], bold=True)
    responses = plan.book.state.get("responses", {})
    for offset, f in enumerate(_sorted_findings(plan.book.state)[:MAX_TOP_FINDINGS], start=1):
        put_row(ws, top + offset, [f.get("id"), f.get("name"), f.get("severity"),
                                   responses.get(f.get("id"), {}).get("type", "none")])
    put(ws, top + MAX_TOP_FINDINGS + 2, 1, "Adjustments are owner statements. The owner supplied "
                                           "every file, and no one verified them.")
    widths(ws, max(4, len(plan.book.labels) + 1))


# ---- build ---------------------------------------------------------------------------

def _write_header(ws: Worksheet, state: dict) -> None:
    put(ws, 1, 1, HEADER, bold=True)
    advisor = (state.get("intake", {}).get("advisor_name") or "").strip()
    if advisor:
        put(ws, 2, 1, ADVISOR_LINE.format(advisor_name=advisor))


def _fill(ws: Worksheet, plan: Plan, tab: dict) -> CellMap:
    if not plan.available[tab["id"]].rendered:
        put(ws, HEADER_ROW, 1, NOT_AVAILABLE)
        return {}
    if tab["kind"] == "input":
        return _input_tab(ws, plan, tab)
    if tab["id"] in BUILDERS:
        return BUILDERS[tab["id"]](ws, plan.book)
    return REGISTERS[tab["id"]](ws, plan, tab)


def build(state: dict, canonical_dir: Path, data_dir: Path, out_path: Path) -> CellMap:
    """Write the workbook and return the map of metric keys to (sheet title, cell)."""
    plan = _plan(state, canonical_dir, data_dir)
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    sheets = {t["id"]: wb.create_sheet(t["title"]) for t in plan.tabs}
    cell_map: CellMap = {}
    for tab in plan.tabs:
        _write_header(sheets[tab["id"]], state)
        if tab["id"] != "summary":
            cell_map = {**cell_map, **_fill(sheets[tab["id"]], plan, tab)}
    if "summary" in sheets:
        _summary_tab(sheets["summary"], plan, cell_map)
    wb.calculation.fullCalcOnLoad = True
    wb.save(out_path)
    return cell_map


# ---- chat summary --------------------------------------------------------------------

def _gaps(plan: Plan) -> list[dict]:
    """Missing files by the number of tabs they stop, then open critical and high findings."""
    state, files = plan.book.state, []
    for f in plan.files:
        if _uploaded(state, f["id"]):
            continue
        blocks = [t["title"] for t in plan.tabs if f["id"] in plan.available[t["id"]].blocking]
        thins = [t["title"] for t in plan.tabs if f["id"] in plan.available[t["id"]].thin]
        if f["critical"] or blocks or thins:
            files.append({"type": "file", "id": f["id"], "name": f["name"], "critical": f["critical"],
                          "blocks_tabs": blocks, "thins_tabs": thins})
    files.sort(key=lambda g: (-len(g["blocks_tabs"]), not g["critical"], -len(g["thins_tabs"]), g["id"]))
    responses = state.get("responses", {})
    open_findings = [{"type": "finding", "id": f["id"], "name": f.get("name"),
                      "severity": f.get("severity"), "fix": f.get("fix")}
                     for f in _sorted_findings(state)
                     if f.get("severity") in progress.BLOCKING_SEVERITIES
                     and responses.get(f["id"], {}).get("type") != "fix"]
    return (files + open_findings)[:MAX_GAPS]


def chat_summary(state: dict, canonical_dir: Path, data_dir: Path) -> dict:
    """Top findings, reported and owner-adjusted EBITDA, gaps, and the next step."""
    plan = _plan(state, canonical_dir, data_dir)
    book = plan.book
    fiscal = list(book.periods.fiscal_years)
    labels = fiscal[-1:] + (["TTM"] if "TTM" in book.label_months else [])
    pl, adjustments = basis_rows(book), state.get("adjustments", [])
    responses = state.get("responses", {})
    gaps = _gaps(plan)
    has_gaps = any(g["type"] == "finding" or g["critical"] for g in gaps)
    return {
        "top_findings": [{"id": f.get("id"), "name": f.get("name"), "severity": f.get("severity"),
                          "category": f.get("category"), "detail": f.get("detail"),
                          "response": responses.get(f.get("id"), {}).get("type", "none")}
                         for f in _sorted_findings(state)[:MAX_TOP_FINDINGS]],
        "reported_ebitda": {label: metrics.ebitda(pl, book.label_months[label])["ebitda"]
                            for label in labels},
        "adjusted_ebitda": {label: metrics.adjusted_ebitda(pl, adjustments, book.label_months[label],
                                                           label) for label in labels},
        "basis": book.basis or "all rows",
        "gaps": gaps,
        "next_step": NEXT_STEP_GAPS if has_gaps else NEXT_STEP_READY,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the owner-prepared QoE readiness workbook.")
    parser.add_argument("--state", required=True, type=Path, help="progress.json to read")
    parser.add_argument("--canonical", required=True, type=Path, help="folder of canonical CSVs")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_DIR, help="folder of catalog JSON")
    parser.add_argument("--out", required=True, type=Path, help="xlsx file to write")
    args = parser.parse_args(argv)
    try:
        state = progress.load(args.state)
        build(state, args.canonical, args.data, args.out)
        summary = chat_summary(state, args.canonical, args.data)
    except (run_checks.RunChecksError, canonical.CanonicalError, ValueError, OSError) as err:
        print(f"build_workbook: {err}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
