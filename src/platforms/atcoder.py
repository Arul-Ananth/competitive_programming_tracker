from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import List
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

from utils.dates import parse_datetime_to_local_date


ATCODER_BASE_URL = "https://atcoder.jp"
ATCODER_PROBLEMS_SUBMISSIONS_URL = (
    "https://kenkoooo.com/atcoder/atcoder-api/v3/user/submissions"
)
ATCODER_PROBLEMS_META_URL = "https://kenkoooo.com/atcoder/resources/problems.json"
_PROBLEM_TITLE_MAP: dict[str, str] | None = None


def _row_cells(row) -> list:
    return row.find_all("td")


def _extract_submission_datetime(cells: list) -> str:
    if not cells:
        return ""
    time_tag = cells[0].find("time")
    if time_tag:
        for attr in ("datetime", "title"):
            value = time_tag.get(attr, "").strip()
            if value:
                return value
        return time_tag.get_text(strip=True)
    return cells[0].get_text(strip=True)


def _date_epoch_bounds(target_date: date, timezone_name: str) -> tuple[int, int]:
    tz = ZoneInfo(timezone_name)
    start_dt = datetime.combine(target_date, time.min, tzinfo=tz)
    end_dt = start_dt + timedelta(days=1)
    return int(start_dt.timestamp()), int(end_dt.timestamp())


def _build_task_link(contest_id: str, problem_id: str) -> str:
    if contest_id and problem_id:
        return f"{ATCODER_BASE_URL}/contests/{contest_id}/tasks/{problem_id}"
    return f"{ATCODER_BASE_URL}/"


def _get_problem_title_map(http: requests.Session) -> dict[str, str]:
    global _PROBLEM_TITLE_MAP
    if _PROBLEM_TITLE_MAP is not None:
        return _PROBLEM_TITLE_MAP

    response = http.get(ATCODER_PROBLEMS_META_URL, timeout=30)
    response.raise_for_status()
    problems = response.json()
    title_map: dict[str, str] = {}
    for item in problems:
        problem_id = str(item.get("id", "")).strip()
        title = str(item.get("title", "")).strip()
        if problem_id and title and problem_id not in title_map:
            title_map[problem_id] = title
    _PROBLEM_TITLE_MAP = title_map
    return title_map


def _fetch_from_atcoder_problems(
    username: str, timezone_name: str, target_date: date, http: requests.Session
) -> List[dict]:
    start_epoch, end_epoch = _date_epoch_bounds(target_date, timezone_name)
    response = http.get(
        ATCODER_PROBLEMS_SUBMISSIONS_URL,
        params={"user": username, "from_second": start_epoch},
        timeout=30,
    )
    response.raise_for_status()
    submissions = response.json()
    title_map = _get_problem_title_map(http)

    results: List[dict] = []
    seen_links = set()

    for submission in submissions:
        epoch = int(submission.get("epoch_second", 0))
        if epoch < start_epoch:
            continue
        if epoch >= end_epoch:
            continue

        result = str(submission.get("result", "")).upper().strip()
        if result != "AC":
            continue

        contest_id = str(submission.get("contest_id", "")).strip()
        problem_id = str(submission.get("problem_id", "")).strip()
        if not problem_id:
            continue

        link = _build_task_link(contest_id, problem_id)
        if link in seen_links:
            continue
        seen_links.add(link)

        title = title_map.get(problem_id, problem_id)
        language = str(submission.get("language", "")).strip()

        results.append(
            {
                "date": target_date.isoformat(),
                "platform": "atcoder",
                "title": title,
                "difficulty": "",
                "link": link,
                "contest": contest_id,
                "language": language,
                "tags": "",
                "notes": "",
                "username": username,
            }
        )

    return results


def _fetch_from_profile_submissions(
    username: str, timezone_name: str, target_date: date, http: requests.Session
) -> List[dict]:
    results: List[dict] = []
    seen_links = set()

    # AtCoder lists submissions in reverse chronological order.
    for page in range(1, 6):
        response = http.get(
            f"{ATCODER_BASE_URL}/users/{username}/submissions",
            params={"f.Status": "AC", "f.User": username, "page": page},
            timeout=30,
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        table = soup.find("table")
        if not table:
            break

        rows = table.find_all("tr")
        if len(rows) <= 1:
            break

        reached_older_rows = False
        for row in rows[1:]:
            cells = _row_cells(row)
            if len(cells) < 7:
                continue

            raw_dt = _extract_submission_datetime(cells)
            if not raw_dt:
                continue

            solved_date = parse_datetime_to_local_date(raw_dt, timezone_name)
            if solved_date < target_date:
                reached_older_rows = True
                continue
            if solved_date > target_date:
                continue

            task_link_tag = cells[1].find("a")
            if not task_link_tag:
                continue

            title = task_link_tag.get_text(strip=True)
            relative_link = task_link_tag.get("href", "").strip()
            link = urljoin(ATCODER_BASE_URL, relative_link)
            if not title or not link or link in seen_links:
                continue
            seen_links.add(link)

            language = cells[3].get_text(strip=True)
            result_text = cells[6].get_text(strip=True).upper()
            if "AC" not in result_text:
                continue

            contest = ""
            contest_link = cells[1].find("a")
            if contest_link:
                href = contest_link.get("href", "")
                parts = [part for part in href.split("/") if part]
                if len(parts) >= 2 and parts[0] == "contests":
                    contest = parts[1]

            results.append(
                {
                    "date": target_date.isoformat(),
                    "platform": "atcoder",
                    "title": title,
                    "difficulty": "",
                    "link": link,
                    "contest": contest,
                    "language": language,
                    "tags": "",
                    "notes": "",
                    "username": username,
                }
            )

        if reached_older_rows:
            break

    return results


def fetch_solved_today(
    username: str, timezone_name: str, target_date: date, session: requests.Session | None = None
) -> List[dict]:
    if not username:
        return []

    http = session or requests.Session()
    http.headers.update({"User-Agent": "cp-tracker/1.0"})

    try:
        return _fetch_from_profile_submissions(username, timezone_name, target_date, http)
    except requests.HTTPError as exc:
        response = exc.response
        if response is not None and response.status_code == 404:
            return _fetch_from_atcoder_problems(username, timezone_name, target_date, http)
        raise
