"""Tests for strict_http.py against a real local server."""

import threading
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import strict_http


class _Handler(BaseHTTPRequestHandler):
    hits: list[str] = []

    def _respond(self, body: bool):
        self.hits.append(self.path)
        if self.path.startswith("/redirect"):
            self.send_response(int(self.path.rsplit("/", 1)[1]))
            self.send_header("Location", "/target")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        payload = b"0123456789"
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        if body:
            self.wfile.write(payload)

    def do_GET(self):
        self._respond(body=True)

    def do_HEAD(self):
        self._respond(body=False)

    def log_message(self, *args):
        pass


@pytest.fixture
def server():
    _Handler.hits = []
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_redirects_are_raised_not_followed(server, code, method):
    with pytest.raises(urllib.error.HTTPError) as raised:
        strict_http.open_url(f"{server}/redirect/{code}", method)
    assert raised.value.code == code
    assert "/target" not in _Handler.hits


def test_get_returns_the_body(server):
    with strict_http.open_url(f"{server}/file") as response:
        assert response.read() == b"0123456789"
    assert _Handler.hits == ["/file"]


def test_head_reports_type_and_length(server):
    assert strict_http.head(f"{server}/file") == ("application/octet-stream", 10)
