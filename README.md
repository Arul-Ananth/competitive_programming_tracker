# Competitive Programming Tracker

Competitive Programming Tracker automatically saves your solved problems from LeetCode, Codeforces, and AtCoder into a Google Sheet.

You solve problems. This project checks your accounts and appends only new solves to your sheet every day.

It is built for:

- students and aspiring developers
- people who want a clean coding log
- users who want automation without setting up a backend or database

## What It Does

- fetches solved problems from supported platforms
- writes them into your Google Sheet
- avoids duplicates
- never deletes rows
- never edits old rows during normal sync
- runs automatically with GitHub Actions
- also supports manual runs for a specific date or date range

## Supported Platforms

- LeetCode
- Codeforces
- AtCoder

## How It Works

Each run follows this flow:

1. Read your settings from `config.json`
2. Open your Google Sheet
3. Find the correct worksheet tab and header row
4. Fetch solved problems from your profiles
5. Check which rows already exist
6. Append only new rows

The tracker also supports dropdown-aware mapping for sheet columns like `platform`. If your sheet expects values like `Leetcode` or `Atcoder`, the tracker can map its internal values to those exact dropdown choices.

## Important Files

These are the main files most users should know:

- [config.json](C:/Dev/competitive_programming_tracker/config.json)
  - Your personal settings
  - Most users only need to edit this file

- [README.md](C:/Dev/competitive_programming_tracker/README.md)
  - This guide

- [main.py](C:/Dev/competitive_programming_tracker/src/main.py)
  - The program entry point
  - This is what you run locally

- [sync.py](C:/Dev/competitive_programming_tracker/src/sync.py)
  - The main sync workflow

- `src/platforms/`
  - Code that fetches solves from each platform

- `src/sheets/`
  - Code that reads and writes Google Sheets

- [active_rules.json](C:/Dev/competitive_programming_tracker/rules/active_rules.json)
  - The active mapping rules used during normal runs

- [daily-sync.yml](C:/Dev/competitive_programming_tracker/.github/workflows/daily-sync.yml)
  - The GitHub Actions workflow that runs daily

## Project Structure

```text
cp-tracker/
  config.json
  requirements.txt
  rules/
  src/
  .github/workflows/
  README.md
```

## What You Need Before Starting

You need:

1. a Google Sheet
2. a Google Cloud service account with Google Sheets API access
3. your LeetCode / Codeforces / AtCoder usernames
4. Python installed if you want to test locally
5. a GitHub repository if you want daily automation

## Quick Start

Setup is:

1. fill `config.json`
2. connect Google credentials
3. test locally once
4. enable GitHub Actions

## Step 1: Fill `config.json`

Open [config.json](C:/Dev/competitive_programming_tracker/config.json) and update it with your details.

Example:

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

What each field means:

- `sheet_url`
  - the full Google Sheet link
- `leetcode`
  - your LeetCode username
- `codeforces`
  - your Codeforces username
- `atcoder`
  - your AtCoder username
- `timezone`
  - used to decide what "today" means
- `notification_email`
  - optional email for failure alerts

## Step 2: Prepare Your Google Sheet

Your sheet needs a log table where the tracker can add rows.

Required columns:

- `title`
- `link`

Recommended columns:

- `date`
- `platform`

Optional columns:

- `difficulty`
- `contest`
- `language`
- `tags`
- `notes`

The tracker can detect common header names automatically.

Examples:

- `Title`, `Problem`, `Question`, `Program Title`
- `Link`, `URL`, `Problem Link`
- `Platform`, `Site`, `OJ`

Important:

- your header row should appear within the first 50 rows of the sheet tab
- the tracker scans tabs automatically and picks the first valid log table

## Step 3: Add Google Credentials

The tracker needs Google service account credentials.

### Local Run

If you have a local JSON file such as `src/service_account.json`, set this in PowerShell:

```powershell
$env:GOOGLE_SERVICE_ACCOUNT_FILE="C:\Dev\competitive_programming_tracker\src\service_account.json"
```

### GitHub Actions

In your GitHub repository:

1. open `Settings`
2. open `Secrets and variables`
3. open `Actions`
4. click `New repository secret`

Create this secret:

- `GOOGLE_SERVICE_ACCOUNT_JSON`

Paste the full JSON content as the secret value.

Important:

- do not commit your service account JSON file
- secrets do not transfer automatically to forks

## Step 4: Install Dependencies

From the project root:

```powershell
pip install -r requirements.txt
```

If you use the local virtual environment:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## Step 5: Run It Locally

From the project root:

```powershell
cd C:\Dev\competitive_programming_tracker
$env:GOOGLE_SERVICE_ACCOUNT_FILE="C:\Dev\competitive_programming_tracker\src\service_account.json"
python src\main.py
```

This runs the tracker in daily mode using today's date in your configured timezone.

### Run For One Specific Date

```powershell
python src\main.py --date 2026-03-15
```

### Run For A Date Range

```powershell
python src\main.py --from 2026-03-01 --to 2026-03-07
```

Use date range mode if you want to backfill older solves.

## Valid Date Arguments

These are valid:

- no date arguments
- `--date YYYY-MM-DD`
- `--from YYYY-MM-DD --to YYYY-MM-DD`

These are not valid:

- `--date` with `--from`
- `--date` with `--to`
- `--from` without `--to`
- `--to` without `--from`

## What The Logs Mean

At the end of a run, you will see something like:

```text
Run date: 2026-03-15
Fetched: 5
Duplicates skipped: 3
New rows appended: 2
Status: SUCCESS
```

Meaning:

- `Fetched`: how many solves were found
- `Duplicates skipped`: how many already existed
- `New rows appended`: how many rows were added
- `Status`: overall result

## How Duplicate Prevention Works

The tracker is safe to re-run.

It first tries to detect duplicates using:

- `link`

If needed, it falls back to a fingerprint made from:

- platform
- title
- date
- username

This means re-running the same date should not create duplicate rows.

## GitHub Actions: Automatic Daily Runs

Main workflow:

- [daily-sync.yml](C:/Dev/competitive_programming_tracker/.github/workflows/daily-sync.yml)

This workflow:

- runs every day on a schedule
- can also be started manually

### How To Run Manually On GitHub

1. open your repository
2. go to `Actions`
3. choose `CP Tracker`
4. click `Run workflow`

You can use:

- Daily mode
  - leave inputs empty
- Single date mode
  - fill `date`
- Range mode
  - fill `from_date` and `to_date`

Examples:

- `date = 2026-03-15`
- `from_date = 2026-03-01`
- `to_date = 2026-03-07`

## Optional Email Notifications

If a critical failure happens, the tracker can send an email.

GitHub secrets:

- `EMAIL_USER`
- `EMAIL_PASSWORD`

Optional:

- `EMAIL_SMTP_HOST`
- `EMAIL_SMTP_PORT`

If you do not add email secrets, the tracker still works. It just cannot send failure alerts.

## Optional AI Rule Compilation

This project also supports optional AI-assisted rule compilation.

This is useful if:

- your sheet has custom dropdown values
- your headers are unusual
- you want help generating mapping rules

Important:

- normal daily sync does not use AI
- AI is only used when you explicitly run rule compilation

Rule files:

- [active_rules.json](C:/Dev/competitive_programming_tracker/rules/active_rules.json)
  - active rules used during normal sync
- [rules.draft.json](C:/Dev/competitive_programming_tracker/rules/rules.draft.json)
  - draft rules created during compilation
- [rules.schema.json](C:/Dev/competitive_programming_tracker/rules/rules.schema.json)
  - validation schema for rules

### Compile Rules

```powershell
python src\main.py --compile-rules
```

### Validate Rules

```powershell
python src\main.py --validate-rules
```

### Promote Draft Rules

```powershell
python src\main.py --promote-rules
```

If you do not have an API key or local model, that is fine. Normal sync still works.

## Optional: Local Ollama For Rule Compilation

If you want to use Ollama for rule compilation:

```powershell
$env:GOOGLE_SERVICE_ACCOUNT_FILE="C:\Dev\competitive_programming_tracker\src\service_account.json"
$env:LITELLM_MODEL="ollama/qwen2.5:14b"
$env:LITELLM_API_BASE="http://localhost:11434"
python src\main.py --compile-rules
```

Recommended local model for a 32 GB laptop:

- `ollama/qwen2.5:14b`

This is only for manual rule compilation. Daily sync still does not use AI.

## Safety Behavior

If the tracker cannot safely map a value, for example a platform dropdown label:

- it skips that row
- it prints a warning
- it writes details to `logs/rule_drift_report.json`

This is intentional. It prevents incorrect data from being written into your sheet.

## What The Tracker Does Not Do

To keep your data safe, normal sync does not:

- delete rows
- edit historical rows
- overwrite old entries
- guess risky values silently

## Troubleshooting

### Missing Google credentials

The tracker could not find:

- `GOOGLE_SERVICE_ACCOUNT_FILE`
or
- `GOOGLE_SERVICE_ACCOUNT_JSON`

For local PowerShell runs, set:

```powershell
$env:GOOGLE_SERVICE_ACCOUNT_FILE="C:\Dev\competitive_programming_tracker\src\service_account.json"
```

### No valid log sheet detected

Usually this means:

- the log table was not found in the first 50 rows
- required columns like `title` and `link` are missing
- the headers are too different from supported aliases

### Dropdown is not selected in new rows

Usually this means:

- the platform text did not match a dropdown value
- the dropdown validation range did not cover the new rows

The tracker tries to repair the platform dropdown range automatically and warns if it cannot.

## Recommended First Test

If this is your first setup, use this order:

1. fill `config.json`
2. set Google credentials locally
3. run `python src\main.py --date 2026-03-15`
4. check the sheet
5. re-run the same date
6. confirm duplicates are skipped
7. enable GitHub Actions after local success

## Short Summary

If you remember only three things:

1. edit [config.json](C:/Dev/competitive_programming_tracker/config.json)
2. provide Google credentials
3. run [main.py](C:/Dev/competitive_programming_tracker/src/main.py) locally once before depending on GitHub Actions
