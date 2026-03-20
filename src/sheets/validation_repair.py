from __future__ import annotations

from dataclasses import dataclass

from sheets.detector import SheetLayout
from sheets.introspection import ColumnValidationInfo, inspect_column_validation


@dataclass(frozen=True)
class ValidationRepairResult:
    info: ColumnValidationInfo
    next_append_row: int
    repaired: bool
    warning: str | None
    expanded_row_count: int | None

    def coverage_description(self) -> str:
        if not self.info.validated_ranges:
            return "none"
        return ", ".join(
            f"{item.start_row}-{item.end_row}" for item in self.info.validated_ranges
        )


def get_next_append_row(layout: SheetLayout) -> int:
    rows = layout.worksheet.get_all_values()
    return max(len(rows) + 1, layout.header_row + 1)


def _build_expand_request(sheet_id: int, new_row_count: int) -> dict:
    return {
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"rowCount": new_row_count},
            },
            "fields": "gridProperties.rowCount",
        }
    }


def _build_validation_repeat_request(
    sheet_id: int, header_row: int, target_row_count: int, column_index: int, validation: dict
) -> dict:
    return {
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": header_row,
                "endRowIndex": target_row_count,
                "startColumnIndex": column_index - 1,
                "endColumnIndex": column_index,
            },
            "cell": {"dataValidation": validation},
            "fields": "dataValidation",
        }
    }


def ensure_validation_coverage(
    spreadsheet,
    layout: SheetLayout,
    column_index: int,
    next_append_row: int,
    expansion_buffer: int = 1000,
    near_end_buffer: int = 50,
) -> ValidationRepairResult:
    info = inspect_column_validation(spreadsheet, layout, column_index=column_index)
    if info.is_row_validated(next_append_row):
        return ValidationRepairResult(
            info=info,
            next_append_row=next_append_row,
            repaired=False,
            warning=None,
            expanded_row_count=None,
        )

    if info.source_validation is None:
        return ValidationRepairResult(
            info=info,
            next_append_row=next_append_row,
            repaired=False,
            warning=(
                f"No validation rule found for column {column_index}. "
                "Append will proceed outside dropdown validation coverage."
            ),
            expanded_row_count=None,
        )

    target_row_count = info.row_count
    expanded_row_count: int | None = None
    requests: list[dict] = []

    if next_append_row > target_row_count - near_end_buffer:
        target_row_count = target_row_count + expansion_buffer
        expanded_row_count = target_row_count
        requests.append(_build_expand_request(info.sheet_id, target_row_count))

    requests.append(
        _build_validation_repeat_request(
            sheet_id=info.sheet_id,
            header_row=layout.header_row,
            target_row_count=target_row_count,
            column_index=column_index,
            validation=info.source_validation,
        )
    )
    spreadsheet.batch_update({"requests": requests})

    refreshed = inspect_column_validation(spreadsheet, layout, column_index=column_index)
    warning = None
    if not refreshed.is_row_validated(next_append_row):
        warning = (
            f"Platform validation still does not cover append row {next_append_row} "
            f"after repair attempt. Coverage: {ValidationRepairResult(refreshed, next_append_row, False, None, expanded_row_count).coverage_description()}"
        )

    return ValidationRepairResult(
        info=refreshed,
        next_append_row=next_append_row,
        repaired=True,
        warning=warning,
        expanded_row_count=expanded_row_count,
    )

