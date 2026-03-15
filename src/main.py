import argparse
import logging
import os
from datetime import date

from config_loader import Config, load_config
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


def main() -> None:
    configure_logging()

    args = _parse_args()
    config_path = os.getenv("CONFIG_PATH", "config.json")
    config: Config | None = None
    mode = "daily"
    target = ""

    try:
        config = load_config(config_path)
        mode, target_dates, target = _resolve_mode_and_dates(args, config.timezone)
        run_sync(config, target_dates=target_dates, mode=mode)
    except Exception as exc:
        LOGGER.error("%s", exc)
        if isinstance(exc, ValueError):
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
