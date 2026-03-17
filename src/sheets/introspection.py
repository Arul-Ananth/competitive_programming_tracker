from __future__ import annotations

import re
from typing import Any, Dict, List, Set

from sheets.detector import SheetLayout


RANGE_REF_PATTERN = re.compile(
    r"^=?'?(?P<sheet>[^'!]+)'?!"
    r"(?P<start_col>[A-Z]+)(?P<start_row>\d+)"
    r"(?::(?P<end_col>[A-Z]+)(?P<end_row>\d+))?$"
)


def _parse_one_of_list(condition: Dict[str, Any]) -> List[str]:
    values = []
    for value in condition.get("values", []):
        text = str(value.get("userEnteredValue", "")).strip()
        if text:
            values.append(text)
    return values


def _parse_range_formula(formula: str) -> str | None:
    raw = formula.strip()
    match = RANGE_REF_PATTERN.match(raw)
    if not match:
        return None
    sheet_name = match.group("sheet")
    start_col = match.group("start_col")
    start_row = match.group("start_row")
    end_col = match.group("end_col")
    end_row = match.group("end_row")
    if end_col and end_row:
        return f"'{sheet_name}'!{start_col}{start_row}:{end_col}{end_row}"
    return f"'{sheet_name}'!{start_col}{start_row}"


def _parse_one_of_range(condition: Dict[str, Any], spreadsheet) -> List[str]:
    values = condition.get("values", [])
    if not values:
        return []
    formula = str(values[0].get("userEnteredValue", "")).strip()
    if not formula:
        return []

    range_ref = _parse_range_formula(formula)
    if not range_ref:
        return []

    result = spreadsheet.values_get(range_ref)
    extracted: List[str] = []
    for row in result.get("values", []):
        for item in row:
            text = str(item).strip()
            if text:
                extracted.append(text)
    return extracted


def _extract_validation_values(validation: Dict[str, Any], spreadsheet) -> List[str]:
    condition = validation.get("condition", {})
    condition_type = condition.get("type")
    if condition_type == "ONE_OF_LIST":
        return _parse_one_of_list(condition)
    if condition_type == "ONE_OF_RANGE":
        return _parse_one_of_range(condition, spreadsheet)
    return []


def extract_allowed_values_for_column(
    spreadsheet, layout: SheetLayout, column_index: int, scan_rows: int = 400
) -> List[str]:
    metadata = spreadsheet.fetch_sheet_metadata(params={"includeGridData": "true"})
    target_sheet_id = int(layout.worksheet.id)
    seen: Set[str] = set()
    values: List[str] = []

    for sheet in metadata.get("sheets", []):
        properties = sheet.get("properties", {})
        if int(properties.get("sheetId", -1)) != target_sheet_id:
            continue

        for data_block in sheet.get("data", []):
            start_row = int(data_block.get("startRow", 0))
            row_data = data_block.get("rowData", [])
            for offset, row in enumerate(row_data):
                absolute_row = start_row + offset + 1
                if absolute_row <= layout.header_row:
                    continue
                if absolute_row > layout.header_row + scan_rows:
                    break

                cells = row.get("values", [])
                cell_idx = column_index - 1
                if cell_idx >= len(cells):
                    continue
                validation = cells[cell_idx].get("dataValidation")
                if not validation:
                    continue

                extracted = _extract_validation_values(validation, spreadsheet)
                for item in extracted:
                    normalized = item.strip().lower()
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        values.append(item.strip())
        break

    return values


def sample_existing_rows(layout: SheetLayout, sample_size: int = 100) -> List[Dict[str, str]]:
    rows = layout.worksheet.get_all_values()
    sampled: List[Dict[str, str]] = []
    for idx, row in enumerate(rows, start=1):
        if idx <= layout.header_row:
            continue
        if not any(str(cell).strip() for cell in row):
            continue
        entry: Dict[str, str] = {}
        for logical_name, col_idx in layout.column_map.items():
            i = col_idx - 1
            entry[logical_name] = str(row[i]).strip() if i < len(row) else ""
        sampled.append(entry)
        if len(sampled) >= sample_size:
            break
    return sampled

