"""Committed files: sample company, freshness, recalculated values, and naming."""
from __future__ import annotations

import pytest
from openpyxl import load_workbook

import build_calculator as bc
from calc_math import evaluate, load_facts
from helpers import blank, cell_value, compare, recalculate
from sample_data import SAMPLE

FACTS = load_facts()


def test_sample_meets_spec():
    r = evaluate(SAMPLE, FACTS)
    assert 3_200_000 <= SAMPLE.revenue <= 3_600_000
    assert r.dependence_score == 4 and r.heavy is True
    assert SAMPLE.owner_pay > 0 and SAMPLE.operator_salary > 0
    assert len(SAMPLE.addbacks) == 5
    assert r.proof_missing == 1
    assert 500_000 <= r.cash_available <= 800_000
    assert r.status == "Not financeable at these terms"
    assert r.price_gap > 0
    assert SAMPLE.asking_price >= 3_000_000
    if FACTS.get("qoe") is not None:
        assert "qoe" in r.flags


def test_sample_company_name():
    wb = load_workbook(bc.SAMPLE_FILE)
    assert "Sample Services Co." in str(wb["Start here"]["A2"].value)


def snapshot(path) -> dict:
    """Normalized workbook content: values, formulas, formats, fills, validations, layout."""
    wb = load_workbook(path)
    out = {"sheets": wb.sheetnames, "props": (wb.properties.creator, wb.properties.created,
                                              wb.properties.modified)}
    for ws in wb:
        cells = {}
        for row in ws.iter_rows():
            for c in row:
                if c.value is not None or c.fill.fill_type or c.number_format != "General":
                    cells[c.coordinate] = (c.value, c.number_format, c.fill.fill_type,
                                           c.fill.fgColor.rgb, c.font.b, c.font.color and c.font.color.rgb)
        validations = sorted(
            (str(dv.sqref), dv.type, dv.operator, dv.formula1, dv.formula2, dv.allow_blank)
            for dv in ws.data_validations.dataValidation)
        out[ws.title] = {
            "cells": cells,
            "validations": validations,
            "merged": sorted(str(m) for m in ws.merged_cells.ranges),
            "freeze": ws.freeze_panes,
            "heights": {k: d.height for k, d in sorted(ws.row_dimensions.items()) if d.height},
            "conditional": sorted(
                (str(rng.sqref), [(r.type, r.operator, r.formula) for r in rules])
                for rng, rules in ws.conditional_formatting._cf_rules.items()),
            "tab_color": ws.sheet_properties.tabColor and ws.sheet_properties.tabColor.rgb,
            "widths": {k: d.width for k, d in sorted(ws.column_dimensions.items())},
        }
    return out


def test_committed_files_are_fresh(tmp_path):
    blank_path, sample_path = tmp_path / "blank.xlsx", tmp_path / "examples" / "sample.xlsx"
    bc.build_both(blank_path, sample_path)
    for built, committed in ((blank_path, bc.BLANK_FILE), (sample_path, bc.SAMPLE_FILE)):
        assert committed.is_file(), f"{committed} is missing. Run python tools/build_calculator.py."
        assert snapshot(built) == snapshot(committed), f"{committed.name} is stale"


def test_rebuild_is_byte_identical(tmp_path):
    first, second = tmp_path / "a.xlsx", tmp_path / "b.xlsx"
    bc.build(first, SAMPLE, FACTS)
    bc.build(second, SAMPLE, FACTS)
    assert first.read_bytes() == second.read_bytes()


@pytest.fixture(scope="module")
def solved_files(tmp_path_factory):
    """Recalculate the committed files from a copy, so that the repo files stay untouched."""
    import shutil
    folder = tmp_path_factory.mktemp("committed")
    cells = bc.build(folder / "cells.xlsx", SAMPLE, FACTS)
    out = {}
    for key, source in (("blank", bc.BLANK_FILE), ("sample", bc.SAMPLE_FILE)):
        copy = folder / f"{key}.xlsx"
        shutil.copyfile(source, copy)
        out[key] = (copy, recalculate(copy))
    return cells, out


def test_sample_results_match_python(solved_files):
    cells, out = solved_files
    path, values = out["sample"]
    compare(SAMPLE, "sample", path, cells, values, FACTS)


def test_blank_file_blocks_until_filled(solved_files):
    cells, out = solved_files
    path, values = out["blank"]

    def got(key):
        return cell_value(values, path, *cells[key])

    assert not blank(got("msg.missing_inputs"))
    for key in ("cash_available", "supported_price", "coverage_at_ask", "status", "price_gap"):
        assert blank(got(key)), key
