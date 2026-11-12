"""Local xlsx/csv backend (openpyxl and csv). Writes are atomic (temp file + rename)."""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

MAX_CELLS = 5000
CSV_SHEET = "Sheet1"
Cell = str | int | float | bool | None


class WorkbookError(Exception):
    """A user-facing workbook failure."""


def _is_csv(path: Path) -> bool:
    return path.suffix.lower() == ".csv"


def _check_ext(path: Path) -> None:
    if path.suffix.lower() not in (".xlsx", ".csv"):
        raise WorkbookError("only .xlsx and .csv workbooks are supported")


@contextmanager
def _atomic(path: Path) -> Iterator[Path]:
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        yield tmp
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


class LocalBackend:
    """Read/write one workbook file. Construct per call; holds no open handles."""

    def __init__(self, path: Path) -> None:
        _check_ext(path)
        self.path = path

    # -- loading / saving -------------------------------------------------
    def _load_csv(self) -> list[list[Cell]]:
        with self.path.open(newline="", encoding="utf-8") as fh:
            return [list(row) for row in csv.reader(fh)]

    def _save_csv(self, rows: list[list[Cell]]) -> None:
        with _atomic(self.path) as tmp, tmp.open("w", newline="", encoding="utf-8") as fh:
            csv.writer(fh).writerows(["" if c is None else c for c in row] for row in rows)

    def _load_xlsx(self) -> Any:
        from openpyxl import load_workbook

        return load_workbook(self.path)

    def _save_xlsx(self, wb: Any) -> None:
        with _atomic(self.path) as tmp:
            wb.save(tmp)

    def _require_exists(self) -> None:
        if not self.path.is_file():
            raise WorkbookError(f"workbook file does not exist: {self.path.name}")

    # -- operations -------------------------------------------------------
    def create(self, sheets: list[str] | None = None) -> None:
        if self.path.exists():
            raise WorkbookError(f"workbook file already exists: {self.path.name}")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if _is_csv(self.path):
            self._save_csv([])
            return
        from openpyxl import Workbook

        wb = Workbook()
        names = sheets or ["Sheet1"]
        first = wb.active
        assert first is not None
        first.title = names[0]
        for name in names[1:]:
            wb.create_sheet(name)
        self._save_xlsx(wb)

    def sheets(self) -> list[str]:
        self._require_exists()
        if _is_csv(self.path):
            return [CSV_SHEET]
        wb = self._load_xlsx()
        try:
            return list(wb.sheetnames)
        finally:
            wb.close()

    def _sheet(self, wb: Any, sheet: str | None) -> Any:
        if sheet is None:
            return wb.active
        if sheet not in wb.sheetnames:
            raise WorkbookError(f"no sheet named {sheet!r}")
        return wb[sheet]

    def read(self, sheet: str | None, cell_range: str | None) -> dict[str, Any]:
        """Return rows for ``cell_range`` (A1 notation) or the used range, capped."""
        self._require_exists()
        if _is_csv(self.path):
            rows: list[list[Cell]] = self._load_csv()
            if cell_range:
                raise WorkbookError("cell ranges are not supported for csv; omit range")
            return self._cap(rows)
        wb = self._load_xlsx()
        try:
            ws = self._sheet(wb, sheet)
            try:
                block = ws[cell_range] if cell_range else ws.iter_rows()
            except (ValueError, KeyError) as exc:
                raise WorkbookError(f"invalid range {cell_range!r}") from exc
            if cell_range and not isinstance(block, tuple):
                block = ((block,),)
            elif cell_range and block and not isinstance(block[0], tuple):
                block = (block,)
            rows = [[c.value for c in row] for row in block]
        finally:
            wb.close()
        return self._cap(rows)

    @staticmethod
    def _cap(rows: list[list[Cell]]) -> dict[str, Any]:
        out: list[list[Cell]] = []
        cells = 0
        truncated = False
        for row in rows:
            if cells + len(row) > MAX_CELLS:
                truncated = True
                break
            out.append(row)
            cells += len(row)
        return {"rows": out, "row_count": len(out), "truncated": truncated}

    def write(self, sheet: str | None, start: str, values: list[list[Cell]]) -> int:
        """Write ``values`` with the top-left cell at ``start`` (e.g. ``B2``)."""
        self._require_exists()
        self._validate_values(values)
        if _is_csv(self.path):
            raise WorkbookError("use append for csv workbooks")
        from openpyxl.utils.cell import column_index_from_string, coordinate_from_string

        try:
            col_letter, row0 = coordinate_from_string(start)
            col0 = column_index_from_string(col_letter)
        except Exception as exc:
            raise WorkbookError(f"invalid start cell {start!r}") from exc
        wb = self._load_xlsx()
        try:
            ws = self._sheet(wb, sheet)
            for r, row in enumerate(values):
                for c, value in enumerate(row):
                    ws.cell(row=row0 + r, column=col0 + c, value=value)
            self._save_xlsx(wb)
        finally:
            wb.close()
        return sum(len(r) for r in values)

    def append(self, sheet: str | None, rows: list[list[Cell]]) -> int:
        self._require_exists()
        self._validate_values(rows)
        if _is_csv(self.path):
            self._save_csv([*self._load_csv(), *rows])
            return len(rows)
        wb = self._load_xlsx()
        try:
            ws = self._sheet(wb, sheet)
            for row in rows:
                ws.append(row)
            self._save_xlsx(wb)
        finally:
            wb.close()
        return len(rows)

    @staticmethod
    def _validate_values(values: list[list[Cell]]) -> None:
        if not isinstance(values, list) or not all(isinstance(r, list) for r in values):
            raise WorkbookError("values must be a list of rows (lists)")
        if sum(len(r) for r in values) > MAX_CELLS:
            raise WorkbookError(f"too many cells; limit is {MAX_CELLS} per call")
        for row in values:
            for cell in row:
                if cell is not None and not isinstance(cell, str | int | float | bool):
                    raise WorkbookError("cell values must be string, number, boolean or null")
                if isinstance(cell, str) and cell.startswith("="):
                    raise WorkbookError("formulas are not supported yet; values only")
