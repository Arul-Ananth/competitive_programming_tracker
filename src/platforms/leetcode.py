from __future__ import annotations

import logging
import time
from datetime import date
from typing import Dict, List

import requests

from utils.dates import unix_to_local_date


LOGGER = logging.getLogger(__name__)

LEETCODE_GRAPHQL_URL = "https://leetcode.com/graphql"
LEETCODE_REQUEST_TIMEOUT = 30
RECENT_WINDOW_LIMIT = 50
HISTORY_PAGE_SIZE = 20
HISTORY_MAX_PAGES = 50
HISTORY_PAGE_DELAY_SECONDS = 0.15

RECENT_AC_SUBMISSIONS_QUERY = """
query recentAcSubmissions($username: String!, $limit: Int!) {
  recentAcSubmissionList(username: $username, limit: $limit) {
    title
    titleSlug
    timestamp
  }
}
"""

RECENT_SUBMISSIONS_QUERY = """
query recentSubmissions($username: String!, $limit: Int!) {
  recentSubmissionList(username: $username, limit: $limit) {
    title
    titleSlug
    timestamp
    statusDisplay
    lang
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

SUBMISSION_LIST_QUERY = """
query submissionList($offset: Int, $limit: Int, $lastKey: String, $questionSlug: String) {
  submissionList(offset: $offset, limit: $limit, lastKey: $lastKey, questionSlug: $questionSlug) {
    lastKey
    hasNext
    submissions {
      id
      title
      titleSlug
      statusDisplay
      lang
      timestamp
    }
  }
}
"""


def _graphql_query(
    session: requests.Session, query: str, variables: Dict[str, object]
) -> dict:
    response = session.post(
        LEETCODE_GRAPHQL_URL,
        json={"query": query, "variables": variables},
        timeout=LEETCODE_REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if data.get("errors"):
        raise requests.HTTPError(f"LeetCode GraphQL error: {data['errors']}")
    return data


def _fetch_difficulty(
    session: requests.Session, title_slug: str, cache: Dict[str, str]
) -> str:
    if title_slug in cache:
        return cache[title_slug]

    data = _graphql_query(
        session,
        QUESTION_DIFFICULTY_QUERY,
        {"titleSlug": title_slug},
    )
    difficulty = (
        data.get("data", {}).get("question", {}).get("difficulty", "") or ""
    ).strip()
    cache[title_slug] = difficulty
    return difficulty


def _submission_key(submission: dict) -> tuple[str, str]:
    return (
        str(submission.get("titleSlug", "")).strip(),
        str(submission.get("timestamp", "")).strip(),
    )


def _accepted_on_target_date(
    submissions: List[dict], timezone_name: str, target_date: date
) -> List[dict]:
    filtered: List[dict] = []
    for submission in submissions:
        status = str(submission.get("statusDisplay", "Accepted")).strip()
        if status and status.lower() != "accepted":
            continue
        timestamp = int(str(submission.get("timestamp", 0)).strip() or 0)
        solved_date = unix_to_local_date(timestamp, timezone_name)
        if solved_date != target_date:
            continue
        filtered.append(submission)
    return filtered


def _recent_language_lookup(
    session: requests.Session, username: str
) -> Dict[tuple[str, str], dict]:
    data = _graphql_query(
        session,
        RECENT_SUBMISSIONS_QUERY,
        {"username": username, "limit": RECENT_WINDOW_LIMIT},
    )
    submissions = data.get("data", {}).get("recentSubmissionList", []) or []
    return {_submission_key(item): item for item in submissions}


def _recent_accepted_submissions(session: requests.Session, username: str) -> List[dict]:
    data = _graphql_query(
        session,
        RECENT_AC_SUBMISSIONS_QUERY,
        {"username": username, "limit": RECENT_WINDOW_LIMIT},
    )
    return data.get("data", {}).get("recentAcSubmissionList", []) or []


def _oldest_submission_date(
    submissions: List[dict], timezone_name: str
) -> date | None:
    oldest: date | None = None
    for submission in submissions:
        timestamp = int(str(submission.get("timestamp", 0)).strip() or 0)
        solved_date = unix_to_local_date(timestamp, timezone_name)
        if oldest is None or solved_date < oldest:
            oldest = solved_date
    return oldest


def _build_results(
    submissions: List[dict],
    target_date: date,
    session: requests.Session,
    difficulty_cache: Dict[str, str],
    language_lookup: Dict[tuple[str, str], dict] | None = None,
) -> List[dict]:
    results: List[dict] = []
    seen_links = set()
    language_lookup = language_lookup or {}

    for submission in submissions:
        title = str(submission.get("title", "")).strip()
        slug = str(submission.get("titleSlug", "")).strip()
        if not title or not slug:
            continue

        link = f"https://leetcode.com/problems/{slug}/"
        if link in seen_links:
            continue
        seen_links.add(link)

        lookup = language_lookup.get(_submission_key(submission), {})
        language = str(
            lookup.get("lang", submission.get("lang", ""))
        ).strip()

        difficulty = ""
        try:
            difficulty = _fetch_difficulty(session, slug, difficulty_cache)
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
                "language": language,
                "tags": "",
                "notes": "",
            }
        )

    return results


def _historical_submission_list(
    session: requests.Session,
    timezone_name: str,
    target_date: date,
) -> List[dict] | None:
    results: List[dict] = []
    seen_keys = set()
    offset = 0
    last_key: str | None = None
    pages_seen = 0
    saw_any_page = False

    while pages_seen < HISTORY_MAX_PAGES:
        data = _graphql_query(
            session,
            SUBMISSION_LIST_QUERY,
            {
                "offset": offset,
                "limit": HISTORY_PAGE_SIZE,
                "lastKey": last_key,
                "questionSlug": None,
            },
        )
        payload = data.get("data", {}).get("submissionList")
        if not payload or payload.get("submissions") is None:
            return None if not saw_any_page else results

        saw_any_page = True
        pages_seen += 1
        submissions = payload.get("submissions", []) or []
        if not submissions:
            break

        page_had_target = False
        oldest_page_date: date | None = None

        for submission in submissions:
            timestamp = int(str(submission.get("timestamp", 0)).strip() or 0)
            solved_date = unix_to_local_date(timestamp, timezone_name)
            if oldest_page_date is None or solved_date < oldest_page_date:
                oldest_page_date = solved_date

            status = str(submission.get("statusDisplay", "")).strip().lower()
            if solved_date != target_date or status != "accepted":
                continue

            key = _submission_key(submission)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            results.append(submission)
            page_had_target = True

        if oldest_page_date is not None and oldest_page_date < target_date and not page_had_target:
            break

        has_next = bool(payload.get("hasNext"))
        if not has_next:
            break

        last_key = payload.get("lastKey")
        offset += HISTORY_PAGE_SIZE
        time.sleep(HISTORY_PAGE_DELAY_SECONDS)

    if pages_seen >= HISTORY_MAX_PAGES:
        LOGGER.warning(
            "LeetCode historical pagination stopped at the safety cap of %s pages for %s.",
            HISTORY_MAX_PAGES,
            target_date.isoformat(),
        )

    return results


def fetch_solved_today(
    username: str,
    timezone_name: str,
    target_date: date,
    session: requests.Session | None = None,
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

    difficulty_cache: Dict[str, str] = {}
    recent_accepted = _recent_accepted_submissions(http, username)
    recent_language_lookup = _recent_language_lookup(http, username)
    recent_matches = _accepted_on_target_date(
        recent_accepted, timezone_name, target_date
    )
    if recent_matches:
        LOGGER.info(
            "LeetCode fetch path for %s: recent-window", target_date.isoformat()
        )
        return _build_results(
            recent_matches,
            target_date,
            http,
            difficulty_cache,
            language_lookup=recent_language_lookup,
        )

    oldest_recent_date = _oldest_submission_date(recent_accepted, timezone_name)
    if oldest_recent_date is None or target_date >= oldest_recent_date:
        LOGGER.info(
            "LeetCode fetch path for %s: recent-window (no matches)",
            target_date.isoformat(),
        )
        return []

    historical_matches = _historical_submission_list(http, timezone_name, target_date)
    if historical_matches is None:
        LOGGER.warning(
            "LeetCode public history endpoint returned no paginated data for %s. "
            "The anonymous public window currently reaches only back to %s for user %s.",
            target_date.isoformat(),
            oldest_recent_date.isoformat(),
            username,
        )
        return []

    if historical_matches:
        LOGGER.info(
            "LeetCode fetch path for %s: historical-pagination",
            target_date.isoformat(),
        )
        return _build_results(
            historical_matches,
            target_date,
            http,
            difficulty_cache,
        )

    LOGGER.info(
        "LeetCode fetch path for %s: historical-pagination (no matches)",
        target_date.isoformat(),
    )
    return []
