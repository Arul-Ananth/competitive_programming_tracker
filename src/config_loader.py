import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict
from zoneinfo import ZoneInfo


SHEET_ID_PATTERN = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")


@dataclass(frozen=True)
class Config:
    sheet_url: str
    sheet_id: str
    timezone: str
    notification_email: str
    leetcode: str = ""
    codeforces: str = ""
    atcoder: str = ""

    def platform_usernames(self) -> Dict[str, str]:
        return {
            "leetcode": self.leetcode,
            "codeforces": self.codeforces,
            "atcoder": self.atcoder,
        }


class ConfigError(Exception):
    pass


def _extract_sheet_id(sheet_url: str) -> str:
    match = SHEET_ID_PATTERN.search(sheet_url)
    if not match:
        raise ConfigError("Unable to extract Google Sheet ID from sheet_url.")
    return match.group(1)


def _validate_timezone(timezone_name: str) -> None:
    try:
        ZoneInfo(timezone_name)
    except Exception as exc:
        raise ConfigError(f"Invalid timezone: {timezone_name}") from exc


def load_config(path: str = "config.json") -> Config:
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {config_path}: {exc}") from exc

    sheet_url = str(data.get("sheet_url", "")).strip()
    timezone_name = str(data.get("timezone", "")).strip()
    notification_email = str(data.get("notification_email", "")).strip()

    if not sheet_url:
        raise ConfigError("Missing required field: sheet_url")
    if not timezone_name:
        raise ConfigError("Missing required field: timezone")
    if not notification_email:
        raise ConfigError("Missing required field: notification_email")

    _validate_timezone(timezone_name)
    sheet_id = _extract_sheet_id(sheet_url)

    leetcode = str(data.get("leetcode", "")).strip()
    codeforces = str(data.get("codeforces", "")).strip()
    atcoder = str(data.get("atcoder", "")).strip()

    if not any([leetcode, codeforces, atcoder]):
        raise ConfigError(
            "At least one platform username is required (leetcode/codeforces/atcoder)."
        )

    return Config(
        sheet_url=sheet_url,
        sheet_id=sheet_id,
        timezone=timezone_name,
        notification_email=notification_email,
        leetcode=leetcode,
        codeforces=codeforces,
        atcoder=atcoder,
    )

