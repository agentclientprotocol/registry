"""Tests for jsonl_feed.py."""

import urllib.error
from unittest.mock import MagicMock, patch

from jsonl_feed import fetch_jsonl_tail


def _response(text: str) -> MagicMock:
    response = MagicMock()
    response.read.return_value = text.encode("utf-8")
    response.__enter__.return_value = response
    return response


class TestFetchJsonlTail:
    @patch("jsonl_feed.urllib.request.urlopen")
    def test_returns_only_the_last_max_lines(self, mock_urlopen):
        lines = "\n".join(f'{{"n": {i}}}' for i in range(5))
        mock_urlopen.return_value = _response(lines)

        records = fetch_jsonl_tail("https://example.com/feed.jsonl", max_lines=2)

        assert records == [{"n": 3}, {"n": 4}]

    @patch("jsonl_feed.urllib.request.urlopen")
    def test_skips_blank_lines(self, mock_urlopen):
        mock_urlopen.return_value = _response('{"n": 1}\n\n{"n": 2}\n')

        records = fetch_jsonl_tail("https://example.com/feed.jsonl", max_lines=10)

        assert records == [{"n": 1}, {"n": 2}]

    @patch("jsonl_feed.urllib.request.urlopen")
    def test_skips_malformed_json_lines(self, mock_urlopen):
        mock_urlopen.return_value = _response('{"n": 1}\nnot json\n{"n": 2}\n')

        records = fetch_jsonl_tail("https://example.com/feed.jsonl", max_lines=10)

        assert records == [{"n": 1}, {"n": 2}]

    @patch("jsonl_feed.urllib.request.urlopen")
    def test_skips_non_object_json_lines(self, mock_urlopen):
        mock_urlopen.return_value = _response('{"n": 1}\n[1, 2, 3]\n"just a string"\n')

        records = fetch_jsonl_tail("https://example.com/feed.jsonl", max_lines=10)

        assert records == [{"n": 1}]

    @patch("jsonl_feed.urllib.request.urlopen")
    def test_returns_empty_list_on_fetch_failure(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("boom")

        assert fetch_jsonl_tail("https://example.com/feed.jsonl", max_lines=10) == []
