"""Export tabellare: CSV con intestazioni italiane e XLSX a un foglio."""

from __future__ import annotations

import csv
import io
from typing import Iterable, Sequence

from openpyxl import Workbook
from openpyxl.styles import Font


def csv_bytes(headers: Sequence[str], rows: Iterable[Sequence[object]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(headers)
    for row in rows:
        writer.writerow(["" if value is None else value for value in row])
    return buffer.getvalue().encode("utf-8-sig")


def xlsx_bytes(
    sheet: str, headers: Sequence[str], rows: Iterable[Sequence[object]]
) -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = sheet[:31] or "export"
    worksheet.append(list(headers))
    for cell in worksheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        worksheet.append([None if value is None else value for value in row])
    worksheet.freeze_panes = "A2"
    for column in worksheet.columns:
        values = [str(cell.value or "") for cell in column]
        width = max((len(value) for value in values), default=8)
        worksheet.column_dimensions[column[0].column_letter].width = min(
            max(width + 2, 10), 48
        )
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
