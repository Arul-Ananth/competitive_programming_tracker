from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import List
from zoneinfo import ZoneInfo


DATE_FORMAT = "%Y-%m-%d"
DATE_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def today_in_timezone(timezone_name: str) -> date:
    return datetime.now(ZoneInfo(timezone_name)).date()


def unix_to_local_date(timestamp: int, timezone_name: str) -> date:
    return datetime.fromtimestamp(timestamp, tz=ZoneInfo(timezone_name)).date()


def parse_strict_date(date_text: str) -> date:
    raw = date_text.strip()
    if not DATE_REGEX.match(raw):
        raise ValueError(f"Invalid date format '{date_text}'. Expected YYYY-MM-DD.")
    parsed = datetime.strptime(raw, DATE_FORMAT).date()
    if parsed.isoformat() != raw:
        raise ValueError(f"Invalid date value '{date_text}'. Expected YYYY-MM-DD.")
    return parsed


def iter_date_range(start_date: date, end_date: date) -> List[date]:
    if start_date > end_date:
        raise ValueError("Invalid range: from_date must be <= to_date.")
    current = start_date
    dates: List[date] = []
    while current <= end_date:
        dates.append(current)
        current += timedelta(days=1)
    return dates


def parse_datetime_to_local_date(raw_value: str, timezone_name: str) -> date:
    cleaned = raw_value.strip()
    if not cleaned:
        raise ValueError("Empty datetime string.")

    patterns = [
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S",
    ]

    parsed: datetime | None = None
    for pattern in patterns:
        try:
            parsed = datetime.strptime(cleaned, pattern)
            break
        except ValueError:
            continue

    if parsed is None:
        # Handles values like "2026-03-15 20:10:30+0900 (JST)".
        trimmed = cleaned.split(" (", 1)[0].strip()
        for pattern in patterns:
            try:
                parsed = datetime.strptime(trimmed, pattern)
                break
            except ValueError:
                continue

    if parsed is None:
        raise ValueError(f"Unsupported datetime format: {raw_value}")

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=ZoneInfo("UTC"))

    return parsed.astimezone(ZoneInfo(timezone_name)).date()
