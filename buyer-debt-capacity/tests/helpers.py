"""Workbook test helpers: recalculate with the formulas library and read cell values."""
from pathlib import Path


def recalculate(path: Path) -> dict:
    """Recalculate an xlsx with the formulas library. Keys are upper-cased, as cell_value expects."""
    import formulas
    solution = formulas.ExcelModel().loads(str(path)).finish().calculate()
    return {k.upper(): v.value[0][0] for k, v in solution.items() if hasattr(v, "value")}


def cell_value(values: dict, path: Path, sheet: str, cell: str):
    return values[f"'[{path.name.upper()}]{sheet.upper()}'!{cell}"]


def error_cells(values: dict, sheets: list[str]) -> list[str]:
    """Cells of the given sheets whose recalculated value is an Excel error."""
    from formulas.functions import XlError
    prefixes = tuple(f"{s.upper()}'!" for s in sheets)
    return [k for k, v in values.items()
            if k.split("]", 1)[-1].startswith(prefixes) and isinstance(v, XlError)]
