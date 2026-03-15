from __future__ import annotations

from datetime import date
from typing import List

import requests

from utils.dates import unix_to_local_date


CODEFORCES_STATUS_URL = "https://codeforces.com/api/user.status"


def _build_problem_link(problem: dict) -> str:
    contest_id = problem.get("contestId")
    index = problem.get("index")
    if contest_id and index:
        return f"https://codeforces.com/contest/{contest_id}/problem/{index}"
    return "https://codeforces.com/problemset"


def fetch_solved_today(
    username: str, timezone_name: str, target_date: date, session: requests.Session | None = None
) -> List[dict]:
    if not username:
        return []

    http = session or requests.Session()
    response = http.get(
        CODEFORCES_STATUS_URL,
        params={"handle": username, "from": 1, "count": 300},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("status") != "OK":
        raise RuntimeError(
            f"Codeforces API error for user '{username}': {payload.get('comment', 'unknown error')}"
        )

    results: List[dict] = []
    seen_links = set()

    for submission in payload.get("result", []):
        if submission.get("verdict") != "OK":
            continue

        solved_date = unix_to_local_date(
            int(submission.get("creationTimeSeconds", 0)), timezone_name
        )
        if solved_date != target_date:
            continue

        problem = submission.get("problem", {})
        title = str(problem.get("name", "")).strip()
        if not title:
            continue

        link = _build_problem_link(problem)
        if link in seen_links:
            continue
        seen_links.add(link)

        rating = problem.get("rating")
        contest_id = problem.get("contestId")
        language = str(submission.get("programmingLanguage", "")).strip()

        results.append(
            {
                "date": target_date.isoformat(),
                "platform": "codeforces",
                "title": title,
                "difficulty": str(rating) if rating else "",
                "link": link,
                "contest": str(contest_id) if contest_id else "",
                "language": language,
                "tags": ", ".join(problem.get("tags", [])),
                "notes": "",
                "username": username,
            }
        )

    return results

