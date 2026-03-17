from __future__ import annotations

from typing import Dict, Iterable, List, Set

from sheets.detector import SheetLayout
from utils.fingerprint import build_fallback_key, normalize_link


class SheetWriteError(Exception):
    pass


def _canonical_platform_key(value: str) -> str:
    lowered = value.strip().lower()
    if "leetcode" in lowered:
        return "leetcode"
    if "codeforces" in lowered:
        return "codeforces"
    if "atcoder" in lowered:
        return "atcoder"
    return lowered


def _safe_cell(row: list[str], column_index: int) -> str:
    idx = column_index - 1
    if idx < 0 or idx >= len(row):
        return ""
    return str(row[idx]).strip()


def read_existing_keys(
    layout: SheetLayout, platform_usernames: Dict[str, str]
) -> Set[str]:
    existing_keys: Set[str] = set()
    rows = layout.worksheet.get_all_values()
    link_col = layout.column_map.get("link")
    platform_col = layout.column_map.get("platform")
    title_col = layout.column_map.get("title")
    date_col = layout.column_map.get("date")

    for index, row in enumerate(rows, start=1):
        if index <= layout.header_row:
            continue
        if not any(cell.strip() for cell in row):
            continue

        link_value = _safe_cell(row, link_col) if link_col else ""
        if link_value:
            existing_keys.add(normalize_link(link_value))
            continue

        if platform_col and title_col and date_col:
            platform = _canonical_platform_key(_safe_cell(row, platform_col))
            title = _safe_cell(row, title_col)
            solved_date = _safe_cell(row, date_col)
            username = platform_usernames.get(platform, "")
            if platform and title and solved_date:
                existing_keys.add(
                    build_fallback_key(platform, title, solved_date, username)
                )

    return existing_keys


def _entry_value(entry: dict, column_name: str) -> str:
    value = entry.get(column_name, "")
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _entry_to_row(layout: SheetLayout, entry: dict) -> List[str]:
    row = [""] * max(layout.max_column, max(layout.column_map.values()))
    for column_name, column_index in layout.column_map.items():
        row[column_index - 1] = _entry_value(entry, column_name)
    return row


def append_entries(layout: SheetLayout, entries: Iterable[dict]) -> int:
    rows = [_entry_to_row(layout, entry) for entry in entries]
    if not rows:
        return 0

    try:
        layout.worksheet.append_rows(rows, value_input_option="USER_ENTERED")
    except Exception as exc:
        raise SheetWriteError("Failed to append rows to Google Sheet.") from exc

    return len(rows)
