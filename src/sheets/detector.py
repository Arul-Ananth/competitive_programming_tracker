from dataclasses import dataclass
from typing import Dict, Iterable


ALIASES = {
    "title": {"title", "problem", "question", "program title"},
    "link": {"link", "url", "problem link"},
    "date": {"date", "solved on"},
    "platform": {"platform", "site", "oj"},
    "difficulty": {"difficulty", "level"},
    "contest": {"contest"},
    "language": {"language"},
    "tags": {"tags"},
    "notes": {"notes"},
}


class SheetDetectionError(Exception):
    pass


@dataclass
class SheetLayout:
    worksheet: object
    worksheet_title: str
    header_row: int
    headers: list[str]
    column_map: Dict[str, int]
    max_column: int


def _normalize(value: object) -> str:
    return str(value).strip().lower()


def _build_alias_lookup() -> Dict[str, str]:
    lookup: Dict[str, str] = {}
    for canonical, names in ALIASES.items():
        for alias in names:
            lookup[alias] = canonical
    return lookup


ALIAS_LOOKUP = _build_alias_lookup()


def _map_row_to_columns(row: Iterable[object]) -> Dict[str, int]:
    mapping: Dict[str, int] = {}
    for index, value in enumerate(row, start=1):
        normalized = _normalize(value)
        if not normalized:
            continue
        canonical = ALIAS_LOOKUP.get(normalized)
        if canonical and canonical not in mapping:
            mapping[canonical] = index
    return mapping


def detect_log_sheet(spreadsheet, scan_rows: int = 50) -> SheetLayout:
    best_layout: SheetLayout | None = None
    best_score = -1

    for worksheet in spreadsheet.worksheets():
        values = worksheet.get(f"A1:ZZ{scan_rows}")
        for row_index, row in enumerate(values, start=1):
            mapping = _map_row_to_columns(row)
            has_required = {"title", "link"}.issubset(mapping.keys())
            if not has_required:
                continue

            score = len(mapping)
            if score > best_score:
                best_score = score
                best_layout = SheetLayout(
                    worksheet=worksheet,
                    worksheet_title=worksheet.title,
                    header_row=row_index,
                    headers=[str(value).strip() for value in row],
                    column_map=mapping,
                    max_column=max(len(row), max(mapping.values())),
                )

    if not best_layout:
        raise SheetDetectionError(
            "No valid log sheet detected. Required columns 'title' and 'link' were not found in the first 50 rows of any tab."
        )

    return best_layout
