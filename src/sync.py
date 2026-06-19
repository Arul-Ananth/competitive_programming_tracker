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
from sheets.introspection import ColumnValidationInfo
from sheets.validator import SheetValidationError, validate_layout
from sheets.validation_repair import ensure_validation_coverage, get_next_append_row
from sheets.writer import (
    SheetWriteError,
    append_entries,
    read_existing_keys_from_rows,
)
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


@dataclass
class SheetRuntime:
    loaded_rules: object
    spreadsheet: object
    layout: object
    usernames: Dict[str, str]
    existing_keys: set[str]
    next_append_row: int


@dataclass
class PlatformValidationState:
    allowed_values: List[str]
    info: ColumnValidationInfo | None


@dataclass
class DateFetchResult:
    entries: List[dict]
    failures: Dict[str, str]
    skipped_invalid: List[dict]


@dataclass
class DedupeResult:
    unique_entries: List[dict]
    duplicates_skipped: int


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


def _ordered_dates_and_target(
    config: Config, target_dates: List[date] | None
) -> tuple[List[date], str]:
    if target_dates is None:
        target_dates = [today_in_timezone(config.timezone)]
    ordered_dates = sorted(target_dates)
    target = (
        ordered_dates[0].isoformat()
        if len(ordered_dates) == 1
        else f"{ordered_dates[0].isoformat()}..{ordered_dates[-1].isoformat()}"
    )
    return ordered_dates, target


def _log_run_start(mode: str, target: str) -> None:
    LOGGER.info("Mode: %s", mode)
    if mode == "single-date":
        LOGGER.info("Target date: %s", target)
    elif mode == "range-backfill":
        LOGGER.info("Date range: %s", target)


def _load_sheet_runtime(config: Config, mode: str, target: str) -> SheetRuntime:
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

    usernames = config.platform_usernames()
    try:
        sheet_rows = layout.worksheet.get_all_values()
        existing_keys = read_existing_keys_from_rows(layout, usernames, sheet_rows)
    except Exception as exc:
        raise CriticalSyncError(
            f"Failed to read existing rows from sheet: {exc}",
            platform="google_sheets",
            mode=mode,
            target=target,
            rows_written=0,
        ) from exc

    return SheetRuntime(
        loaded_rules=loaded_rules,
        spreadsheet=spreadsheet,
        layout=layout,
        usernames=usernames,
        existing_keys=existing_keys,
        next_append_row=get_next_append_row(layout, rows=sheet_rows),
    )


def _refresh_platform_validation(
    spreadsheet: object, layout: object, next_append_row: int
) -> PlatformValidationState:
    if "platform" not in layout.column_map:
        return PlatformValidationState(allowed_values=[], info=None)

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
        return PlatformValidationState(
            allowed_values=repair_result.info.allowed_values,
            info=repair_result.info,
        )
    except Exception as exc:
        LOGGER.warning(
            "Unable to inspect or repair platform validation coverage: %s",
            exc,
        )
        return PlatformValidationState(allowed_values=[], info=None)


def _needs_validation_refresh(
    validation: PlatformValidationState, next_append_row: int
) -> bool:
    return validation.info is not None and not validation.info.is_row_validated(
        next_append_row
    )


def _platform_adapters() -> Dict[
    str, Callable[[str, str, date, requests.Session], List[dict]]
]:
    return {
        "leetcode": fetch_leetcode,
        "codeforces": fetch_codeforces,
        "atcoder": fetch_atcoder,
    }


def _fetch_entries_for_date(
    config: Config,
    target_date: date,
    usernames: Dict[str, str],
    loaded_rules: object,
    allowed_platform_values: List[str],
    session: requests.Session,
) -> DateFetchResult:
    fetched_entries: List[dict] = []
    platform_failures: Dict[str, str] = {}
    skipped_invalid: List[dict] = []
    adapters = _platform_adapters()

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
                    allowed_values=allowed_platform_values,
                )
                if mapping_error:
                    LOGGER.warning(
                        "Skipping row due to unmappable platform '%s' for '%s'.",
                        normalized.get("platform", ""),
                        normalized.get("title", ""),
                    )
                    skipped_invalid.append(
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
            platform_failures[f"{platform}:{target_date.isoformat()}"] = str(exc)

    return DateFetchResult(
        entries=fetched_entries,
        failures=platform_failures,
        skipped_invalid=skipped_invalid,
    )


def _dedupe_entries(entries: List[dict], existing_keys: set[str]) -> DedupeResult:
    unique_entries: List[dict] = []
    seen_new_keys = set()

    for entry in entries:
        key = _submission_key(entry)
        if key in existing_keys or key in seen_new_keys:
            continue
        seen_new_keys.add(key)
        unique_entries.append(entry)

    duplicates_skipped = len(entries) - len(unique_entries)
    return DedupeResult(
        unique_entries=unique_entries,
        duplicates_skipped=duplicates_skipped,
    )


def _remember_appended_entries(entries: List[dict], existing_keys: set[str]) -> None:
    for entry in entries:
        existing_keys.add(_submission_key(entry))


def _log_summary(
    mode: str,
    target: str,
    fetched_total: int,
    duplicates_total: int,
    skipped_invalid_total: List[dict],
    rows_appended_total: int,
    status: str,
) -> None:
    LOGGER.info("Summary mode: %s", mode)
    LOGGER.info("Summary target: %s", target)
    LOGGER.info("Fetched: %s", fetched_total)
    LOGGER.info("Duplicates skipped: %s", duplicates_total)
    LOGGER.info("Rows skipped by rule mapping: %s", len(skipped_invalid_total))
    LOGGER.info("New rows appended: %s", rows_appended_total)
    LOGGER.info("Status: %s", status)


def run_sync(
    config: Config,
    target_dates: List[date] | None = None,
    mode: str = "daily",
) -> SyncSummary:
    ordered_dates, target = _ordered_dates_and_target(config, target_dates)
    _log_run_start(mode, target)
    runtime = _load_sheet_runtime(config, mode, target)
    session = requests.Session()
    all_platform_failures: Dict[str, str] = {}
    fetched_total = 0
    duplicates_total = 0
    rows_appended_total = 0
    skipped_invalid_total: List[dict] = []

    validation = _refresh_platform_validation(
        runtime.spreadsheet, runtime.layout, runtime.next_append_row
    )

    for target_date in ordered_dates:
        if mode == "range-backfill":
            LOGGER.info("Processing date: %s", target_date.isoformat())

        if _needs_validation_refresh(validation, runtime.next_append_row):
            validation = _refresh_platform_validation(
                runtime.spreadsheet, runtime.layout, runtime.next_append_row
            )

        fetch_result = _fetch_entries_for_date(
            config=config,
            target_date=target_date,
            usernames=runtime.usernames,
            loaded_rules=runtime.loaded_rules,
            allowed_platform_values=validation.allowed_values,
            session=session,
        )
        fetched_total += len(fetch_result.entries)
        all_platform_failures.update(fetch_result.failures)
        skipped_invalid_total.extend(fetch_result.skipped_invalid)

        dedupe_result = _dedupe_entries(fetch_result.entries, runtime.existing_keys)
        duplicates_total += dedupe_result.duplicates_skipped

        try:
            appended_count = append_entries(runtime.layout, dedupe_result.unique_entries)
            rows_appended_total += appended_count
        except SheetWriteError as exc:
            raise CriticalSyncError(
                str(exc),
                platform="google_sheets",
                mode=mode,
                target=target,
                rows_written=rows_appended_total,
            ) from exc

        _remember_appended_entries(dedupe_result.unique_entries, runtime.existing_keys)
        runtime.next_append_row += appended_count

    status = "SUCCESS" if not all_platform_failures else "SUCCESS_WITH_WARNINGS"
    if all_platform_failures:
        LOGGER.warning("Platform warnings: %s", all_platform_failures)

    _log_summary(
        mode=mode,
        target=target,
        fetched_total=fetched_total,
        duplicates_total=duplicates_total,
        skipped_invalid_total=skipped_invalid_total,
        rows_appended_total=rows_appended_total,
        status=status,
    )

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
