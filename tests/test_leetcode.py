import sys
import unittest
from datetime import date
from unittest.mock import patch

sys.path.insert(0, "src")

from platforms.leetcode import fetch_solved_today  # noqa: E402


class FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, responses_by_marker):
        self.responses_by_marker = {
            marker: list(responses) for marker, responses in responses_by_marker.items()
        }
        self.headers = {}

    def post(self, url, json, timeout):
        query = json.get("query", "")
        marker = None
        if "recentAcSubmissionList" in query:
            marker = "recent_ac"
        elif "recentSubmissionList" in query:
            marker = "recent"
        elif "submissionList(" in query:
            marker = "history"
        elif "questionData" in query:
            marker = "difficulty"
        else:
            raise AssertionError(f"Unexpected query: {query}")

        queue = self.responses_by_marker.get(marker)
        if not queue:
            raise AssertionError(f"No fake response configured for {marker}")
        return queue.pop(0)


class LeetCodeAdapterTests(unittest.TestCase):
    @patch("platforms.leetcode._fetch_difficulty", return_value="Medium")
    def test_recent_window_returns_single_deduped_result(self, _mock_difficulty):
        session = FakeSession(
            {
                "recent_ac": [
                    FakeResponse(
                        {
                            "data": {
                                "recentAcSubmissionList": [
                                    {
                                        "title": "Two Sum",
                                        "titleSlug": "two-sum",
                                        "timestamp": "1774184400",
                                    },
                                    {
                                        "title": "Two Sum",
                                        "titleSlug": "two-sum",
                                        "timestamp": "1774184500",
                                    },
                                ]
                            }
                        }
                    )
                ],
                "recent": [
                    FakeResponse(
                        {
                            "data": {
                                "recentSubmissionList": [
                                    {
                                        "title": "Two Sum",
                                        "titleSlug": "two-sum",
                                        "timestamp": "1774184400",
                                        "statusDisplay": "Accepted",
                                        "lang": "python3",
                                    }
                                ]
                            }
                        }
                    )
                ],
            }
        )

        results = fetch_solved_today(
            "demo-user", "Asia/Kolkata", date(2026, 3, 22), session
        )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Two Sum")
        self.assertEqual(results[0]["language"], "python3")
        self.assertEqual(results[0]["platform"], "leetcode")

    @patch("platforms.leetcode._fetch_difficulty", return_value="Hard")
    def test_historical_pagination_returns_older_match(self, _mock_difficulty):
        session = FakeSession(
            {
                "recent_ac": [
                    FakeResponse(
                        {
                            "data": {
                                "recentAcSubmissionList": [
                                    {
                                        "title": "Recent Problem",
                                        "titleSlug": "recent-problem",
                                        "timestamp": "1774610000",
                                    }
                                ]
                            }
                        }
                    )
                ],
                "recent": [
                    FakeResponse(
                        {
                            "data": {
                                "recentSubmissionList": [
                                    {
                                        "title": "Recent Problem",
                                        "titleSlug": "recent-problem",
                                        "timestamp": "1774610000",
                                        "statusDisplay": "Accepted",
                                        "lang": "java",
                                    }
                                ]
                            }
                        }
                    )
                ],
                "history": [
                    FakeResponse(
                        {
                            "data": {
                                "submissionList": {
                                    "lastKey": "page-2",
                                    "hasNext": True,
                                    "submissions": [
                                        {
                                            "id": "1",
                                            "title": "Older Problem",
                                            "titleSlug": "older-problem",
                                            "statusDisplay": "Accepted",
                                            "lang": "python3",
                                            "timestamp": "1771677000",
                                        },
                                        {
                                            "id": "2",
                                            "title": "Noise Problem",
                                            "titleSlug": "noise-problem",
                                            "statusDisplay": "Wrong Answer",
                                            "lang": "python3",
                                            "timestamp": "1771676000",
                                        },
                                    ],
                                }
                            }
                        }
                    ),
                    FakeResponse(
                        {
                            "data": {
                                "submissionList": {
                                    "lastKey": None,
                                    "hasNext": False,
                                    "submissions": [
                                        {
                                            "id": "3",
                                            "title": "Oldest Problem",
                                            "titleSlug": "oldest-problem",
                                            "statusDisplay": "Accepted",
                                            "lang": "cpp",
                                            "timestamp": "1771500000",
                                        }
                                    ],
                                }
                            }
                        }
                    ),
                ],
            }
        )

        with patch("platforms.leetcode.HISTORY_PAGE_DELAY_SECONDS", 0):
            results = fetch_solved_today(
                "demo-user", "Asia/Kolkata", date(2026, 2, 21), session
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "Older Problem")
        self.assertEqual(results[0]["language"], "python3")

    def test_warns_when_historical_endpoint_returns_null(self):
        session = FakeSession(
            {
                "recent_ac": [
                    FakeResponse(
                        {
                            "data": {
                                "recentAcSubmissionList": [
                                    {
                                        "title": "Recent Problem",
                                        "titleSlug": "recent-problem",
                                        "timestamp": "1774610000",
                                    }
                                ]
                            }
                        }
                    )
                ],
                "recent": [
                    FakeResponse(
                        {
                            "data": {
                                "recentSubmissionList": [
                                    {
                                        "title": "Recent Problem",
                                        "titleSlug": "recent-problem",
                                        "timestamp": "1774610000",
                                        "statusDisplay": "Accepted",
                                        "lang": "java",
                                    }
                                ]
                            }
                        }
                    )
                ],
                "history": [
                    FakeResponse({"data": {"submissionList": {"hasNext": None, "submissions": None}}})
                ],
            }
        )

        with self.assertLogs("platforms.leetcode", level="WARNING") as logs:
            results = fetch_solved_today(
                "demo-user", "Asia/Kolkata", date(2026, 2, 21), session
            )

        self.assertEqual(results, [])
        self.assertTrue(
            any("public history endpoint returned no paginated data" in line for line in logs.output)
        )


if __name__ == "__main__":
    unittest.main()
