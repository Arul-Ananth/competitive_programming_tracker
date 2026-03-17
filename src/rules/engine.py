from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List

from jsonschema import Draft202012Validator


RULES_DIR = Path("rules")
RULES_SCHEMA_PATH = RULES_DIR / "rules.schema.json"
ACTIVE_RULES_PATH = RULES_DIR / "active_rules.json"
DRAFT_RULES_PATH = RULES_DIR / "rules.draft.json"
DRIFT_REPORT_PATH = Path("logs") / "rule_drift_report.json"


class RulesError(Exception):
    pass


@dataclass(frozen=True)
class LoadedRules:
    data: Dict[str, Any]
    path: Path


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise RulesError(f"Rules file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RulesError(f"Invalid JSON in {path}: {exc}") from exc


def _load_schema() -> Dict[str, Any]:
    return _read_json(RULES_SCHEMA_PATH)


def validate_rules_dict(data: Dict[str, Any]) -> None:
    schema = _load_schema()
    validator = Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(data), key=lambda err: err.path)
    if errors:
        parts = []
        for err in errors:
            location = ".".join(str(x) for x in err.path) or "<root>"
            parts.append(f"{location}: {err.message}")
        raise RulesError("Rules schema validation failed: " + " | ".join(parts))

    column_map = data.get("column_map", {})
    for logical_name, details in column_map.items():
        header = str(details.get("header", "")).strip()
        index = int(details.get("index", 0))
        if not header or index <= 0:
            raise RulesError(
                f"Invalid column mapping for '{logical_name}'. Expected non-empty header and positive index."
            )


def load_rules(path: Path = ACTIVE_RULES_PATH) -> LoadedRules:
    data = _read_json(path)
    validate_rules_dict(data)
    return LoadedRules(data=data, path=path)


def save_draft_rules(data: Dict[str, Any], path: Path = DRAFT_RULES_PATH) -> Path:
    validate_rules_dict(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def validate_rules_file(path: Path) -> LoadedRules:
    data = _read_json(path)
    validate_rules_dict(data)
    return LoadedRules(data=data, path=path)


def promote_rules(
    draft_path: Path = DRAFT_RULES_PATH, active_path: Path = ACTIVE_RULES_PATH
) -> Path:
    loaded = validate_rules_file(draft_path)
    active_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        mode="w", delete=False, dir=str(active_path.parent), encoding="utf-8"
    ) as tmp_file:
        json.dump(loaded.data, tmp_file, indent=2)
        temp_path = Path(tmp_file.name)

    os.replace(temp_path, active_path)
    return active_path


def build_default_rules(sheet_id: str = "") -> Dict[str, Any]:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "version": "1.0.0",
        "generated_at": now,
        "source_sheet_id": sheet_id,
        "confidence": 0.0,
        "notes": "Default starter rules. Run --compile-rules and --promote-rules.",
        "column_map": {},
        "value_maps": {
            "platform": {
                "leetcode": "Leetcode",
                "codeforces": "Codeforces Contest",
                "atcoder": "Atcoder",
            }
        },
        "normalizers": {
            "platform_case": "sheet-value",
            "date_format": "YYYY-MM-DD",
        },
    }


def ensure_active_rules_exists(sheet_id: str = "") -> Path:
    if ACTIVE_RULES_PATH.exists():
        return ACTIVE_RULES_PATH
    ACTIVE_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE_RULES_PATH.write_text(
        json.dumps(build_default_rules(sheet_id=sheet_id), indent=2), encoding="utf-8"
    )
    return ACTIVE_RULES_PATH


def _ci_match(value: str, choices: Iterable[str]) -> str | None:
    target = value.strip().lower()
    for choice in choices:
        if choice.strip().lower() == target:
            return choice
    return None


def map_platform_value(
    canonical_platform: str, rules: LoadedRules, allowed_values: List[str]
) -> tuple[str | None, str | None]:
    canonical = canonical_platform.strip().lower()
    explicit = (
        rules.data.get("value_maps", {})
        .get("platform", {})
        .get(canonical, canonical_platform)
    )
    explicit = str(explicit).strip()

    if not allowed_values:
        return explicit, None

    direct = _ci_match(explicit, allowed_values)
    if direct:
        return direct, None

    canonical_match = _ci_match(canonical, allowed_values)
    if canonical_match:
        return canonical_match, None

    contains = [
        value
        for value in allowed_values
        if canonical and canonical in value.strip().lower()
    ]
    if len(contains) == 1:
        return contains[0], None

    reason = (
        f"Unable to map platform '{canonical_platform}' to an allowed dropdown value. "
        f"Allowed values: {allowed_values}"
    )
    return None, reason


def write_drift_report(
    mode: str,
    target: str,
    skipped_entries: List[Dict[str, Any]],
    path: Path = DRIFT_REPORT_PATH,
) -> Path | None:
    if not skipped_entries:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "mode": mode,
        "target": target,
        "skipped_count": len(skipped_entries),
        "entries": skipped_entries,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path

