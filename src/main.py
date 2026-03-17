import argparse
import logging
import os
from datetime import date
from pathlib import Path

from config_loader import Config, load_config
from rules.compiler import build_adapter_contract_samples, compile_rules_with_llm
from rules.engine import (
    ACTIVE_RULES_PATH,
    DRAFT_RULES_PATH,
    RulesError,
    promote_rules,
    save_draft_rules,
    validate_rules_file,
)
from sheets.client import open_spreadsheet
from sheets.detector import detect_log_sheet
from sheets.introspection import extract_allowed_values_for_column, sample_existing_rows
from sheets.validator import validate_layout
from sync import run_sync
from utils.dates import iter_date_range, parse_strict_date, today_in_timezone
from utils.logging_utils import configure_logging
from utils.notification import send_email_notification


LOGGER = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Competitive Programming Tracker")
    parser.add_argument("--date", dest="date", help="Run for a specific date (YYYY-MM-DD)")
    parser.add_argument(
        "--from", dest="from_date", help="Backfill start date (YYYY-MM-DD)"
    )
    parser.add_argument("--to", dest="to_date", help="Backfill end date (YYYY-MM-DD)")
    parser.add_argument(
        "--compile-rules",
        dest="compile_rules",
        action="store_true",
        help="Generate rules.draft.json using LiteLLM and sheet introspection.",
    )
    parser.add_argument(
        "--validate-rules",
        dest="validate_rules",
        action="store_true",
        help="Validate a rules JSON file against schema.",
    )
    parser.add_argument(
        "--promote-rules",
        dest="promote_rules",
        action="store_true",
        help="Promote rules.draft.json to active_rules.json after validation.",
    )
    parser.add_argument(
        "--rules-path",
        dest="rules_path",
        default="",
        help="Rules file path for --validate-rules (default: rules/rules.draft.json).",
    )
    return parser.parse_args()


def _resolve_mode_and_dates(args: argparse.Namespace, timezone_name: str):
    date_arg = (args.date or "").strip()
    from_arg = (args.from_date or "").strip()
    to_arg = (args.to_date or "").strip()

    if date_arg and (from_arg or to_arg):
        raise ValueError("Invalid arguments: --date cannot be combined with --from/--to.")
    if from_arg and not to_arg:
        raise ValueError("Invalid arguments: --from requires --to.")
    if to_arg and not from_arg:
        raise ValueError("Invalid arguments: --to requires --from.")

    if date_arg:
        target_date = parse_strict_date(date_arg)
        return "single-date", [target_date], target_date.isoformat()

    if from_arg and to_arg:
        from_date = parse_strict_date(from_arg)
        to_date = parse_strict_date(to_arg)
        target_dates = iter_date_range(from_date, to_date)
        return (
            "range-backfill",
            target_dates,
            f"{from_date.isoformat()}..{to_date.isoformat()}",
        )

    today = today_in_timezone(timezone_name)
    return "daily", [today], today.isoformat()


def _resolve_action(args: argparse.Namespace) -> str:
    selected = [
        bool(args.compile_rules),
        bool(args.validate_rules),
        bool(args.promote_rules),
    ]
    if sum(selected) > 1:
        raise ValueError(
            "Invalid arguments: choose only one of --compile-rules, --validate-rules, --promote-rules."
        )
    if args.compile_rules:
        return "compile-rules"
    if args.validate_rules:
        return "validate-rules"
    if args.promote_rules:
        return "promote-rules"
    return "sync"


def _validate_action_args(args: argparse.Namespace, action: str) -> None:
    if action != "sync" and any([(args.date or "").strip(), (args.from_date or "").strip(), (args.to_date or "").strip()]):
        raise ValueError(
            "Date arguments (--date/--from/--to) are only valid for sync runs."
        )


def _build_compile_context(config: Config) -> dict:
    spreadsheet = open_spreadsheet(config.sheet_id)
    layout = detect_log_sheet(spreadsheet, scan_rows=50)
    validate_layout(layout)
    column_map_context = {
        logical: {
            "header": layout.headers[index - 1] if index - 1 < len(layout.headers) else "",
            "index": index,
        }
        for logical, index in layout.column_map.items()
    }
    platform_allowed_values = []
    if "platform" in layout.column_map:
        platform_allowed_values = extract_allowed_values_for_column(
            spreadsheet, layout, layout.column_map["platform"]
        )
    return {
        "sheet_id": config.sheet_id,
        "worksheet_title": layout.worksheet_title,
        "header_row": layout.header_row,
        "column_map": column_map_context,
        "platform_allowed_values": platform_allowed_values,
        "historical_samples": sample_existing_rows(layout, sample_size=100),
        "adapter_contract_samples": build_adapter_contract_samples(),
    }


def main() -> None:
    configure_logging()

    args = _parse_args()
    action = _resolve_action(args)
    _validate_action_args(args, action)
    config_path = os.getenv("CONFIG_PATH", "config.json")
    config: Config | None = None
    mode = "daily"
    target = ""

    try:
        if action == "validate-rules":
            path = Path(args.rules_path.strip()) if args.rules_path.strip() else DRAFT_RULES_PATH
            loaded = validate_rules_file(path)
            LOGGER.info("Rules file is valid: %s", loaded.path)
            return

        if action == "promote-rules":
            promoted_path = promote_rules(draft_path=DRAFT_RULES_PATH, active_path=ACTIVE_RULES_PATH)
            LOGGER.info("Promoted draft rules to active rules: %s", promoted_path)
            return

        config = load_config(config_path)
        if action == "compile-rules":
            context = _build_compile_context(config)
            compiled = compile_rules_with_llm(context)
            draft_path = save_draft_rules(compiled, path=DRAFT_RULES_PATH)
            LOGGER.info("Draft rules written: %s", draft_path)
            return

        mode, target_dates, target = _resolve_mode_and_dates(args, config.timezone)
        run_sync(config, target_dates=target_dates, mode=mode)
    except Exception as exc:
        LOGGER.error("%s", exc)
        if isinstance(exc, (ValueError, RulesError)):
            raise
        if action != "sync":
            raise
        run_date = (
            date.today().isoformat()
            if config is None
            else today_in_timezone(config.timezone).isoformat()
        )
        recipient = (
            config.notification_email
            if config and config.notification_email
            else os.getenv("NOTIFICATION_EMAIL", "")
        )
        platform = getattr(exc, "platform", "N/A")
        mode_for_email = getattr(exc, "mode", mode)
        target_for_email = getattr(exc, "target", target)
        rows_written = getattr(exc, "rows_written", 0)
        send_email_notification(
            recipient=recipient,
            error_message=str(exc),
            run_date=run_date,
            platform=platform,
            mode=mode_for_email,
            target=target_for_email,
            rows_written=rows_written,
        )
        raise


if __name__ == "__main__":
    main()
