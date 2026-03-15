import logging
import os
import smtplib
from email.message import EmailMessage


LOGGER = logging.getLogger(__name__)


def send_email_notification(
    recipient: str,
    error_message: str,
    run_date: str,
    platform: str = "N/A",
    mode: str = "daily",
    target: str = "",
    rows_written: int = 0,
) -> bool:
    if not recipient:
        LOGGER.warning("Notification email is not configured; skipping failure email.")
        return False

    email_user = os.getenv("EMAIL_USER", "").strip()
    email_password = os.getenv("EMAIL_PASSWORD", "").strip()
    smtp_host = os.getenv("EMAIL_SMTP_HOST", "smtp.gmail.com").strip()
    smtp_port = int(os.getenv("EMAIL_SMTP_PORT", "587"))

    if not email_user or not email_password:
        LOGGER.error(
            "EMAIL_USER or EMAIL_PASSWORD is missing; unable to send failure email."
        )
        return False

    message = EmailMessage()
    message["Subject"] = f"[CP Tracker] Critical failure on {run_date}"
    message["From"] = email_user
    message["To"] = recipient
    target_line = target if target else run_date
    message.set_content(
        "\n".join(
            [
                "Competitive Programming Tracker encountered a critical error.",
                "",
                f"Run date: {run_date}",
                f"Mode: {mode}",
                f"Target: {target_line}",
                f"Platform: {platform}",
                f"Error: {error_message}",
                f"Rows written before failure: {rows_written}",
                "",
                "Check GitHub Actions workflow logs for details and retry.",
            ]
        )
    )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
            smtp.starttls()
            smtp.login(email_user, email_password)
            smtp.send_message(message)
        LOGGER.info("Failure notification email sent to %s.", recipient)
        return True
    except Exception:
        LOGGER.exception("Failed to send failure notification email.")
        return False
