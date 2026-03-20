from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Callable, Dict, List

import requests

from config_loader import Config
from platforms.atcoder import fetch_solved_today as fetch_atcoder
from platforms.codeforces import fetch_solved_today as fetch_codeforces
from platforms.leetcode import fetch_solved_today as fetch_leetcode
from rules.engine import (
    load_rules,
    map_platform_value,
    write_drift_report,
)
from sheets.client import AuthenticationError, SheetAccessError, open_spreadsheet
from sheets.detector import SheetDetectionError, detect_log_sheet
from sheets.validator import SheetValidationError, validate_layout
from sheets.validation_repair import ensure_validation_coverage, get_next_append_row
from sheets.writer import SheetWriteError, append_entries, read_existing_keys
from utils.dates import today_in_timezone
from utils.fingerprint import build_fallback_key, normalize_link


LOGGER = logging.getLogger(__name__)


class CriticalSyncError(Exception):
    def __init__(
        self,
        message: str,
        platform: str = "N/A",
        mode: str = "daily",
        target: str = "",
        rows_written: int = 0,
    ):
        super().__init__(message)
        self.platform = platform
        self.mode = mode
        self.target = target
        self.rows_written = rows_written


@dataclass
class SyncSummary:
    mode: str
    target: str
    fetched: int
    duplicates_skipped: int
    rows_appended: int
    status: str


def _submission_key(entry: dict) -> str:
    link = normalize_link(str(entry.get("link", "")))
    if link:
        return link
    return build_fallback_key(
        platform=str(entry.get("platform", "")),
        title=str(entry.get("title", "")),
        date=str(entry.get("date", "")),
        username=str(entry.get("username", "")),
    )


def _normalize_submission(raw: dict, default_platform: str, username: str) -> dict:
    return {
        "date": str(raw.get("date", "")).strip(),
        "platform": str(raw.get("platform", default_platform)).strip().lower(),
        "title": str(raw.get("title", "")).strip(),
        "difficulty": str(raw.get("difficulty", "")).strip(),
        "link": str(raw.get("link", "")).strip(),
        "contest": str(raw.get("contest", "")).strip(),
        "language": str(raw.get("language", "")).strip(),
        "tags": raw.get("tags", ""),
        "notes": str(raw.get("notes", "")).strip(),
        "username": str(raw.get("username", username)).strip(),
    }


def run_sync(
    config: Config,
    target_dates: List[date] | None = None,
    mode: str = "daily",
) -> SyncSummary:
    if target_dates is None:
        target_dates = [today_in_timezone(config.timezone)]
    ordered_dates = sorted(target_dates)
    target = (
        ordered_dates[0].isoformat()
        if len(ordered_dates) == 1
        else f"{ordered_dates[0].isoformat()}..{ordered_dates[-1].isoformat()}"
    )

    LOGGER.info("Mode: %s", mode)
    if mode == "single-date":
        LOGGER.info("Target date: %s", target)
    elif mode == "range-backfill":
        LOGGER.info("Date range: %s", target)

    try:
        loaded_rules = load_rules()
        spreadsheet = open_spreadsheet(config.sheet_id)
        layout = detect_log_sheet(spreadsheet, scan_rows=50)
        validate_layout(layout)
    except (
        AuthenticationError,
        SheetAccessError,
        SheetDetectionError,
        SheetValidationError,
    ) as exc:
        raise CriticalSyncError(
            str(exc), platform="google_sheets", mode=mode, target=target, rows_written=0
        ) from exc
    except Exception as exc:
        raise CriticalSyncError(
            f"Failed to load active rules: {exc}",
            platform="rules",
            mode=mode,
            target=target,
            rows_written=0,
        ) from exc

    adapters: Dict[str, Callable[[str, str, date, requests.Session], List[dict]]] = {
        "leetcode": fetch_leetcode,
        "codeforces": fetch_codeforces,
        "atcoder": fetch_atcoder,
    }

    usernames = config.platform_usernames()
    session = requests.Session()
    all_platform_failures: Dict[str, str] = {}
    fetched_total = 0
    duplicates_total = 0
    rows_appended_total = 0
    skipped_invalid_total: List[dict] = []

    for target_date in ordered_dates:
        if mode == "range-backfill":
            LOGGER.info("Processing date: %s", target_date.isoformat())

        platform_allowed_values: List[str] = []
        if "platform" in layout.column_map:
            next_append_row = get_next_append_row(layout)
            try:
                repair_result = ensure_validation_coverage(
                    spreadsheet,
                    layout,
                    column_index=layout.column_map["platform"],
                    next_append_row=next_append_row,
                )
                LOGGER.info(
                    "Platform validation coverage: %s | next append row: %s",
                    repair_result.coverage_description(),
                    repair_result.next_append_row,
                )
                if repair_result.repaired:
                    LOGGER.warning(
                        "Extended platform validation coverage%s.",
                        (
                            f" after expanding sheet to {repair_result.expanded_row_count} rows"
                            if repair_result.expanded_row_count
                            else ""
                        ),
                    )
                if repair_result.warning:
                    LOGGER.warning("%s", repair_result.warning)
                platform_allowed_values = repair_result.info.allowed_values
            except Exception as exc:
                LOGGER.warning(
                    "Unable to inspect or repair platform validation coverage: %s",
                    exc,
                )

        fetched_entries: List[dict] = []
        for platform, username in usernames.items():
            if not username:
                continue
            adapter = adapters[platform]
            try:
                entries = adapter(username, config.timezone, target_date, session)
                for entry in entries:
                    normalized = _normalize_submission(entry, platform, username)
                    mapped_platform, mapping_error = map_platform_value(
                        canonical_platform=str(normalized.get("platform", "")),
                        rules=loaded_rules,
                        allowed_values=platform_allowed_values,
                    )
                    if mapping_error:
                        LOGGER.warning(
                            "Skipping row due to unmappable platform '%s' for '%s'.",
                            normalized.get("platform", ""),
                            normalized.get("title", ""),
                        )
                        skipped_invalid_total.append(
                            {
                                "date": normalized.get("date", ""),
                                "platform": normalized.get("platform", ""),
                                "title": normalized.get("title", ""),
                                "link": normalized.get("link", ""),
                                "reason": mapping_error,
                            }
                        )
                        continue
                    normalized["platform"] = mapped_platform or normalized["platform"]
                    fetched_entries.append(normalized)
            except Exception as exc:
                LOGGER.warning(
                    "Platform '%s' fetch failed for %s: %s",
                    platform,
                    target_date.isoformat(),
                    exc,
                )
                all_platform_failures[f"{platform}:{target_date.isoformat()}"] = str(exc)

        fetched_total += len(fetched_entries)
        keyed_entries = [
            {"entry": entry, "key": _submission_key(entry)} for entry in fetched_entries
        ]

        try:
            existing_keys = read_existing_keys(layout, usernames)
        except Exception as exc:
            raise CriticalSyncError(
                f"Failed to read existing rows from sheet: {exc}",
                platform="google_sheets",
                mode=mode,
                target=target,
                rows_written=rows_appended_total,
            ) from exc

        unique_entries: List[dict] = []
        seen_new_keys = set()
        for item in keyed_entries:
            entry = item["entry"]
            key = item["key"]
            if key in existing_keys or key in seen_new_keys:
                duplicates_total += 1
                continue
            seen_new_keys.add(key)
            unique_entries.append(entry)

        try:
            rows_appended_total += append_entries(layout, unique_entries)
        except SheetWriteError as exc:
            raise CriticalSyncError(
                str(exc),
                platform="google_sheets",
                mode=mode,
                target=target,
                rows_written=rows_appended_total,
            ) from exc

    status = "SUCCESS" if not all_platform_failures else "SUCCESS_WITH_WARNINGS"
    if all_platform_failures:
        LOGGER.warning("Platform warnings: %s", all_platform_failures)

    LOGGER.info("Summary mode: %s", mode)
    LOGGER.info("Summary target: %s", target)
    LOGGER.info("Fetched: %s", fetched_total)
    LOGGER.info("Duplicates skipped: %s", duplicates_total)
    LOGGER.info("Rows skipped by rule mapping: %s", len(skipped_invalid_total))
    LOGGER.info("New rows appended: %s", rows_appended_total)
    LOGGER.info("Status: %s", status)

    report_path = write_drift_report(
        mode=mode,
        target=target,
        skipped_entries=skipped_invalid_total,
    )
    if report_path:
        LOGGER.warning("Rule drift report written: %s", report_path)

    return SyncSummary(
        mode=mode,
        target=target,
        fetched=fetched_total,
        duplicates_skipped=duplicates_total,
        rows_appended=rows_appended_total,
        status=status,
    )
