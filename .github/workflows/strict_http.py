"""HTTP for custom sources that check every URL against an allowlist.

A followed redirect could leave the allowlist, so a 3xx raises `urllib.error.HTTPError`
like any other non-2xx status.
"""

import urllib.request

USER_AGENT = "ACP-Registry-Version-Checker/1.0"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def open_url(url: str, method: str = "GET", headers: dict[str, str] | None = None):
    """Opens `url` without following redirects. Non-2xx raises `HTTPError`."""
    request = urllib.request.Request(
        url, method=method, headers={"User-Agent": USER_AGENT, **(headers or {})}
    )
    return _OPENER.open(request, timeout=30)


def head(url: str, headers: dict[str, str] | None = None) -> tuple[str, int]:
    """Returns (content type, content length or -1) for a 2xx HEAD."""
    with open_url(url, "HEAD", headers) as response:
        length = response.headers.get("Content-Length", "")
        return response.headers.get_content_type(), int(length) if length.isdigit() else -1
