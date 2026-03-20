import sys
import unittest
from dataclasses import dataclass

sys.path.insert(0, "src")

from sheets.validation_repair import (  # noqa: E402
    _build_expand_request,
    _build_validation_repeat_request,
    ensure_validation_coverage,
)


class FakeSpreadsheet:
    def __init__(self, metadata_sequence):
        self._metadata_sequence = list(metadata_sequence)
        self.batch_requests = []

    def fetch_sheet_metadata(self, params=None):
        if len(self._metadata_sequence) > 1:
            return self._metadata_sequence.pop(0)
        return self._metadata_sequence[0]

    def batch_update(self, body):
        self.batch_requests.append(body)

    def values_get(self, range_ref):
        return {"values": []}


@dataclass
class FakeWorksheet:
    id: int


@dataclass
class FakeLayout:
    worksheet: FakeWorksheet
    header_row: int


def _metadata(sheet_id, row_count, validated_rows, allowed_values=None):
    allowed_values = allowed_values or ["Leetcode", "Atcoder"]
    row_data = []
    max_row = max(validated_rows) if validated_rows else 2
    validation = {
        "condition": {
            "type": "ONE_OF_LIST",
            "values": [{"userEnteredValue": value} for value in allowed_values],
        }
    }
    for row_number in range(1, max_row + 1):
        if row_number in validated_rows:
            row_data.append({"values": [{}, {"dataValidation": validation}]})
        else:
            row_data.append({"values": [{}, {}]})
    return {
        "sheets": [
            {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"rowCount": row_count},
                },
                "data": [{"startRow": 0, "rowData": row_data}],
            }
        ]
    }


class ValidationRepairTests(unittest.TestCase):
    def test_build_requests(self):
        expand = _build_expand_request(10, 200)
        self.assertEqual(expand["updateSheetProperties"]["properties"]["sheetId"], 10)
        repeat = _build_validation_repeat_request(
            10, header_row=13, target_row_count=200, column_index=5, validation={}
        )
        self.assertEqual(repeat["repeatCell"]["range"]["startRowIndex"], 13)
        self.assertEqual(repeat["repeatCell"]["range"]["endColumnIndex"], 5)

    def test_repair_when_append_row_outside_range(self):
        before = _metadata(1001, 120, validated_rows=list(range(14, 80)))
        after = _metadata(1001, 120, validated_rows=list(range(14, 121)))
        spreadsheet = FakeSpreadsheet([before, after])
        layout = FakeLayout(worksheet=FakeWorksheet(id=1001), header_row=13)
        result = ensure_validation_coverage(
            spreadsheet, layout, column_index=2, next_append_row=80
        )
        self.assertTrue(result.repaired)
        self.assertTrue(result.info.is_row_validated(80))
        self.assertEqual(len(spreadsheet.batch_requests), 1)

    def test_warn_when_no_source_rule_exists(self):
        metadata = _metadata(1001, 120, validated_rows=[])
        spreadsheet = FakeSpreadsheet([metadata])
        layout = FakeLayout(worksheet=FakeWorksheet(id=1001), header_row=13)
        result = ensure_validation_coverage(
            spreadsheet, layout, column_index=2, next_append_row=80
        )
        self.assertFalse(result.repaired)
        self.assertIn("No validation rule found", result.warning or "")
        self.assertEqual(len(spreadsheet.batch_requests), 0)

    def test_expand_when_near_sheet_end(self):
        before = _metadata(1001, 90, validated_rows=list(range(14, 80)))
        after = _metadata(1001, 1090, validated_rows=list(range(14, 1091)))
        spreadsheet = FakeSpreadsheet([before, after])
        layout = FakeLayout(worksheet=FakeWorksheet(id=1001), header_row=13)
        result = ensure_validation_coverage(
            spreadsheet,
            layout,
            column_index=2,
            next_append_row=85,
            expansion_buffer=1000,
            near_end_buffer=10,
        )
        self.assertTrue(result.repaired)
        self.assertEqual(result.expanded_row_count, 1090)


if __name__ == "__main__":
    unittest.main()

