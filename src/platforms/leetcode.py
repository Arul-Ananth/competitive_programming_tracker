from __future__ import annotations

from datetime import date
from typing import Dict, List

import requests

from utils.dates import unix_to_local_date


LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"

RECENT_SUBMISSIONS_QUERY = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    title
    titleSlug
    timestamp
  }
}
"""

QUESTION_DIFFICULTY_QUERY = """
query questionData($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    difficulty
  }
}
"""


def _fetch_difficulty(
    session: requests.Session, title_slug: str, cache: Dict[str, str]
) -> str:
    if title_slug in cache:
        return cache[title_slug]

    payload = {
        "query": QUESTION_DIFFICULTY_QUERY,
        "variables": {"titleSlug": title_slug},
    }
    response = session.post(LEETCODE_GRAPHQL_URL, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    difficulty = (
        data.get("data", {}).get("question", {}).get("difficulty", "") or ""
    ).strip()
    cache[title_slug] = difficulty
    return difficulty


def fetch_solved_today(
    username: str, timezone_name: str, target_date: date, session: requests.Session | None = None
) -> List[dict]:
    if not username:
        return []

    http = session or requests.Session()
    http.headers.update(
        {
            "Content-Type": "application/json",
            "Referer": f"https://leetcode.com/{username}/",
            "User-Agent": "cp-tracker/1.0",
        }
    )

    payload = {
        "query": RECENT_SUBMISSIONS_QUERY,
        "variables": {"username": username, "limit": 50},
    }
    response = http.post(LEETCODE_GRAPHQL_URL, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    submissions = data.get("data", {}).get("recentAcSubmissionList", []) or []

    difficulty_cache: Dict[str, str] = {}
    results: List[dict] = []
    seen_links = set()

    for submission in submissions:
        timestamp = int(submission.get("timestamp", 0))
        solved_date = unix_to_local_date(timestamp, timezone_name)
        if solved_date != target_date:
            continue

        title = str(submission.get("title", "")).strip()
        slug = str(submission.get("titleSlug", "")).strip()
        if not title or not slug:
            continue

        link = f"https://leetcode.com/problems/{slug}/"
        if link in seen_links:
            continue
        seen_links.add(link)

        difficulty = ""
        try:
            difficulty = _fetch_difficulty(http, slug, difficulty_cache)
        except Exception:
            difficulty = ""

        results.append(
            {
                "date": target_date.isoformat(),
                "platform": "leetcode",
                "title": title,
                "difficulty": difficulty,
                "link": link,
                "contest": "",
                "language": "",
                "tags": "",
                "notes": "",
                "username": username,
            }
        )

    return results

