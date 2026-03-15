# Competitive Programming Tracker

Automation tool that logs daily solved problems from LeetCode, Codeforces, and AtCoder into Google Sheets.

## Features

- Runs daily via GitHub Actions (and supports manual run).
- Supports override modes: single date and date-range backfill.
- Appends only new rows (never edits or deletes existing rows).
- Prevents duplicates using:
  - Primary key: `link`
  - Fallback key: `SHA256(platform + title + date + username)`
- Auto-detects sheet tab, header row, and column mapping across flexible layouts.
- Sends failure notification emails for critical errors.
- One-file user configuration: `config.json`.

## Repository Model

This repo is designed for GitHub template usage.

1. Click **Use this template**.
2. Edit `config.json`.
3. Add required GitHub secrets.
4. Let workflow run daily in your fork.

Each fork runs independently.

## Quick Setup

1. Create a Google Cloud service account and enable Google Sheets API.
2. Share your Google Sheet with the service account email (`Editor`).
3. Add GitHub repository secrets in your fork.
4. Edit `config.json`.
5. Run the workflow manually once from Actions tab to verify setup.

## GitHub Secrets

In your GitHub fork, go to:

- `Settings` -> `Secrets and variables` -> `Actions` -> `New repository secret`

Create these secrets:

- `GOOGLE_SERVICE_ACCOUNT_JSON` (full service account JSON as a single-line value)
- `EMAIL_USER`
- `EMAIL_PASSWORD`
- Optional: `EMAIL_SMTP_HOST`, `EMAIL_SMTP_PORT`

Important:

- Secrets do not transfer automatically from a template repository to forks.

## Configuration

Edit only `config.json`:

```json
{
  "sheet_url": "https://docs.google.com/spreadsheets/d/REPLACE_WITH_SHEET_ID/edit#gid=0",
  "leetcode": "your_leetcode_username",
  "codeforces": "your_codeforces_username",
  "atcoder": "your_atcoder_username",
  "timezone": "Asia/Kolkata",
  "notification_email": "you@example.com"
}
```

`sheet_id` is automatically extracted from `sheet_url`.

## Sheet Layout Rules

The tracker scans the first 50 rows of every tab and auto-detects the first valid header row.

Required logical columns:

- `title`
- `link`

Recommended logical columns:

- `date`
- `platform`

Optional logical columns:

- `difficulty`
- `contest`
- `language`
- `tags`
- `notes`

Supported aliases:

- `title`: `Title`, `Problem`, `Question`
- `link`: `Link`, `URL`, `Problem Link`
- `date`: `Date`, `Solved On`
- `platform`: `Platform`, `Site`, `OJ`
- `difficulty`: `Difficulty`, `Level`

## Run Flow

Each run follows:

1. Load configuration
2. Validate sheet structure
3. Resolve run mode and target date(s)
4. Fetch submissions for each target date
5. Normalize data
6. Generate duplicate keys
7. Read existing keys
8. Filter duplicates
9. Append new rows
10. Print summary

For range backfill, dates are processed in chronological order, one date at a time.

## Logging Output

Example:

```text
Run date: 2026-03-15
Fetched: 5
Duplicates skipped: 3
New rows appended: 2
Status: SUCCESS
```

## Local Run

```bash
pip install -r requirements.txt
python src/main.py
```

Single date override:

```bash
python src/main.py --date 2026-03-15
```

Range backfill:

```bash
python src/main.py --from 2026-03-01 --to 2026-03-07
```

## GitHub Actions Manual Run

Scheduled runs continue to use the current day in your configured timezone.

Manual dispatch options:

- Daily mode: leave all inputs empty.
- Single date mode: set `date=2026-03-15`.
- Range mode: set `from_date=2026-03-01` and `to_date=2026-03-07`.

Validation rules:

- Do not combine `date` with `from_date` or `to_date`.
- `from_date` and `to_date` must be provided together.
- Dates must be `YYYY-MM-DD`.

## Project Structure

```text
cp-tracker/
  config.json
  requirements.txt
  src/
    main.py
    sync.py
    config_loader.py
    platforms/
      leetcode.py
      codeforces.py
      atcoder.py
    sheets/
      client.py
      detector.py
      validator.py
      writer.py
    utils/
      fingerprint.py
      dates.py
      logging_utils.py
      notification.py
  .github/workflows/
    daily-sync.yml
  README.md
```
