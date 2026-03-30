import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, "src")

from config_loader import Config  # noqa: E402
from sync import run_sync  # noqa: E402


class FakeWorksheet:
    def __init__(self):
        self.read_calls = 0
        self.rows = [
            ["Date", "Title", "Link", "Platform"],
            ["2026-02-14", "Old Problem", "https://example.com/old", "Leetcode"],
        ]

    def get_all_values(self):
        self.read_calls += 1
        return [row[:] for row in self.rows]


class SyncCachingTests(unittest.TestCase):
    def test_range_backfill_reads_sheet_rows_once(self):
        worksheet = FakeWorksheet()
        layout = SimpleNamespace(
            worksheet=worksheet,
            header_row=1,
            column_map={"date": 1, "title": 2, "link": 3, "platform": 4},
            max_column=4,
        )
        config = Config(
            sheet_url="https://docs.google.com/spreadsheets/d/test-sheet/edit#gid=0",
            sheet_id="test-sheet",
            timezone="Asia/Kolkata",
            notification_email="user@example.com",
            leetcode="demo-user",
        )

        dates = [
            __import__("datetime").date(2026, 2, 15),
            __import__("datetime").date(2026, 2, 16),
            __import__("datetime").date(2026, 2, 17),
        ]
        appended_batches = []

        def fake_fetch(username, timezone_name, target_date, session):
            return [
                {
                    "date": target_date.isoformat(),
                    "platform": "leetcode",
                    "title": f"Problem {target_date.isoformat()}",
                    "link": f"https://example.com/{target_date.isoformat()}",
                }
            ]

        def fake_append_entries(_layout, entries):
            appended_batches.append([dict(entry) for entry in entries])
            return len(entries)

        validation_info = SimpleNamespace(
            allowed_values=["Leetcode"],
            is_row_validated=lambda row_number: True,
        )
        validation_result = SimpleNamespace(
            info=validation_info,
            next_append_row=3,
            repaired=False,
            warning=None,
            expanded_row_count=None,
            coverage_description=lambda: "2-999",
        )

        with (
            patch("sync.load_rules", return_value={"value_maps": {"platform": {}}}),
            patch("sync.open_spreadsheet", return_value=object()),
            patch("sync.detect_log_sheet", return_value=layout),
            patch("sync.validate_layout"),
            patch("sync.ensure_validation_coverage", return_value=validation_result),
            patch("sync.fetch_leetcode", side_effect=fake_fetch),
            patch("sync.fetch_codeforces", return_value=[]),
            patch("sync.fetch_atcoder", return_value=[]),
            patch("sync.map_platform_value", return_value=("Leetcode", None)),
            patch("sync.append_entries", side_effect=fake_append_entries),
            patch("sync.write_drift_report", return_value=None),
        ):
            summary = run_sync(config, target_dates=dates, mode="range-backfill")

        self.assertEqual(worksheet.read_calls, 1)
        self.assertEqual(summary.rows_appended, 3)
        self.assertEqual(len(appended_batches), 3)


if __name__ == "__main__":
    unittest.main()
