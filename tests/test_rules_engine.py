import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "src")

from rules.engine import (  # noqa: E402
    RulesError,
    build_default_rules,
    load_rules,
    map_platform_value,
    save_draft_rules,
    validate_rules_dict,
    write_drift_report,
)


class RulesEngineTests(unittest.TestCase):
    def test_validate_rules_dict_accepts_default(self):
        rules = build_default_rules(sheet_id="abc")
        validate_rules_dict(rules)

    def test_validate_rules_dict_rejects_bad_column_map(self):
        rules = build_default_rules()
        rules["column_map"] = {"title": {"header": "", "index": 0}}
        with self.assertRaises(RulesError):
            validate_rules_dict(rules)

    def test_map_platform_value_uses_explicit_map(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rules.json"
            data = build_default_rules()
            data["value_maps"]["platform"]["atcoder"] = "Atcoder"
            save_draft_rules(data, path=path)
            loaded = load_rules(path=path)
            mapped, error = map_platform_value("atcoder", loaded, ["Atcoder", "Leetcode"])
            self.assertEqual(mapped, "Atcoder")
            self.assertIsNone(error)

    def test_map_platform_value_skip_on_unknown(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "rules.json"
            data = build_default_rules()
            data["value_maps"]["platform"]["codeforces"] = "Codeforces Contest"
            save_draft_rules(data, path=path)
            loaded = load_rules(path=path)
            mapped, error = map_platform_value("codeforces", loaded, ["Leetcode", "Atcoder"])
            self.assertIsNone(mapped)
            self.assertIn("Unable to map platform", error or "")

    def test_write_drift_report(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "drift.json"
            path = write_drift_report(
                mode="daily",
                target="2026-03-16",
                skipped_entries=[{"platform": "atcoder", "reason": "missing"}],
                path=output,
            )
            self.assertEqual(path, output)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(payload["skipped_count"], 1)


if __name__ == "__main__":
    unittest.main()

