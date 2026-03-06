"""Tests for update_versions.py."""

import urllib.error
from unittest.mock import patch

import pytest

from update_versions import make_request


class TestMakeRequestServerErrors:
    """Test that make_request handles server errors (5xx) gracefully."""

    @patch("update_versions.urllib.request.urlopen")
    def test_502_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/owner/repo/releases/latest",
            code=502,
            msg="Bad Gateway",
            hdrs={},
            fp=None,
        )
        assert make_request("https://api.github.com/repos/owner/repo/releases/latest") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_503_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://api.github.com/repos/owner/repo/releases/latest",
            code=503,
            msg="Service Unavailable",
            hdrs={},
            fp=None,
        )
        assert make_request("https://api.github.com/repos/owner/repo/releases/latest") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_500_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=500,
            msg="Internal Server Error",
            hdrs={},
            fp=None,
        )
        assert make_request("https://example.com/api") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_404_returns_none(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )
        assert make_request("https://example.com/api") is None

    @patch("update_versions.urllib.request.urlopen")
    def test_403_raises(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=403,
            msg="Forbidden",
            hdrs={},
            fp=None,
        )
        with pytest.raises(urllib.error.HTTPError, match="403"):
            make_request("https://example.com/api")

    @patch("update_versions.urllib.request.urlopen")
    def test_429_raises(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/api",
            code=429,
            msg="Too Many Requests",
            hdrs={},
            fp=None,
        )
        with pytest.raises(urllib.error.HTTPError, match="429"):
            make_request("https://example.com/api")
