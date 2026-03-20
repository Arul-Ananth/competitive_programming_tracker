import sys
import unittest
from dataclasses import dataclass

sys.path.insert(0, "src")

from sheets.introspection import (  # noqa: E402
    _parse_one_of_list,
    _parse_one_of_range,
    _parse_range_formula,
    extract_allowed_values_for_column,
    inspect_column_validation,
)


class FakeSpreadsheet:
    def __init__(self, metadata, range_values=None):
        self._metadata = metadata
        self._range_values = range_values or {}

    def fetch_sheet_metadata(self, params=None):
        return self._metadata

    def values_get(self, range_ref):
        return self._range_values.get(range_ref, {"values": []})


@dataclass
class FakeWorksheet:
    id: int


@dataclass
class FakeLayout:
    worksheet: FakeWorksheet
    header_row: int


class IntrospectionTests(unittest.TestCase):
    def test_parse_one_of_list(self):
        condition = {
            "values": [{"userEnteredValue": "Leetcode"}, {"userEnteredValue": "Atcoder"}]
        }
        self.assertEqual(_parse_one_of_list(condition), ["Leetcode", "Atcoder"])

    def test_parse_range_formula(self):
        self.assertEqual(_parse_range_formula("='Lists'!A1:A3"), "'Lists'!A1:A3")
        self.assertEqual(_parse_range_formula("'Values'!B2"), "'Values'!B2")

    def test_parse_one_of_range(self):
        spreadsheet = FakeSpreadsheet(
            metadata={},
            range_values={"'Lists'!A1:A3": {"values": [["Leetcode"], ["Atcoder"], ["CSES"]]}},
        )
        condition = {"values": [{"userEnteredValue": "='Lists'!A1:A3"}]}
        self.assertEqual(
            _parse_one_of_range(condition, spreadsheet), ["Leetcode", "Atcoder", "CSES"]
        )

    def test_extract_allowed_values_for_column(self):
        metadata = {
            "sheets": [
                {
                    "properties": {"sheetId": 1001, "gridProperties": {"rowCount": 500}},
                    "data": [
                        {
                            "startRow": 0,
                            "rowData": [
                                {"values": []},
                                {
                                    "values": [
                                        {},
                                        {
                                            "dataValidation": {
                                                "condition": {
                                                    "type": "ONE_OF_LIST",
                                                    "values": [
                                                        {"userEnteredValue": "Leetcode"},
                                                        {"userEnteredValue": "Atcoder"},
                                                    ],
                                                }
                                            }
                                        },
                                    ]
                                },
                            ],
                        }
                    ],
                }
            ]
        }
        spreadsheet = FakeSpreadsheet(metadata=metadata)
        layout = FakeLayout(worksheet=FakeWorksheet(id=1001), header_row=1)
        values = extract_allowed_values_for_column(spreadsheet, layout, column_index=2)
        self.assertEqual(values, ["Leetcode", "Atcoder"])

    def test_inspect_column_validation_returns_ranges(self):
        metadata = {
            "sheets": [
                {
                    "properties": {"sheetId": 1001, "gridProperties": {"rowCount": 500}},
                    "data": [
                        {
                            "startRow": 0,
                            "rowData": [
                                {"values": []},
                                {"values": [{}, {"dataValidation": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "Leetcode"}]}}}]},
                                {"values": [{}, {"dataValidation": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "Leetcode"}]}}}]},
                                {"values": [{}, {}]},
                                {"values": [{}, {"dataValidation": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": "Leetcode"}]}}}]},
                            ],
                        }
                    ],
                }
            ]
        }
        spreadsheet = FakeSpreadsheet(metadata=metadata)
        layout = FakeLayout(worksheet=FakeWorksheet(id=1001), header_row=1)
        info = inspect_column_validation(spreadsheet, layout, column_index=2)
        self.assertEqual(info.allowed_values, ["Leetcode"])
        self.assertEqual(
            [(item.start_row, item.end_row) for item in info.validated_ranges],
            [(2, 3), (5, 5)],
        )
        self.assertEqual(info.row_count, 500)


if __name__ == "__main__":
    unittest.main()
