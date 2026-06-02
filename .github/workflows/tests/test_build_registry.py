"""Tests for build_registry icon validation and dry-run."""

import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from build_registry import is_public_https_url, url_exists, validate_icon, validate_icon_monochrome


def socket_result(ip: str):
    return [(None, None, None, None, (ip, 443))]


class StubResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None


class TestUrlSafety:
    def test_rejects_non_https_urls(self, monkeypatch):
        monkeypatch.setattr("build_registry.socket.getaddrinfo", lambda *args, **kwargs: [])

        assert not is_public_https_url("http://example.com/archive.tar.gz")

    def test_rejects_private_addresses(self, monkeypatch):
        monkeypatch.setattr(
            "build_registry.socket.getaddrinfo",
            lambda *args, **kwargs: socket_result("127.0.0.1"),
        )

        assert not is_public_https_url("https://example.com/archive.tar.gz")

    def test_rejects_shared_address_space(self, monkeypatch):
        monkeypatch.setattr(
            "build_registry.socket.getaddrinfo",
            lambda *args, **kwargs: socket_result("100.64.0.1"),
        )

        assert not is_public_https_url("https://example.com/archive.tar.gz")

    def test_accepts_public_https_addresses(self, monkeypatch):
        monkeypatch.setattr(
            "build_registry.socket.getaddrinfo",
            lambda *args, **kwargs: socket_result("93.184.216.34"),
        )

        assert is_public_https_url("https://example.com/archive.tar.gz")

    def test_url_exists_retries_transient_dns_failure(self, monkeypatch):
        calls = 0

        def fake_getaddrinfo(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise OSError("temporary resolver failure")
            return socket_result("93.184.216.34")

        monkeypatch.setattr("build_registry.socket.getaddrinfo", fake_getaddrinfo)
        monkeypatch.setattr(
            "build_registry.URL_OPENER.open",
            lambda *args, **kwargs: StubResponse(),
        )
        monkeypatch.setattr("time.sleep", lambda *args, **kwargs: None)

        assert url_exists("https://example.com/archive.tar.gz")
        assert calls == 2


# --- validate_icon_monochrome ---


class TestValidateIconMonochrome:
    def _root(self, svg: str) -> ET.Element:
        return ET.fromstring(svg)

    def test_valid_fill_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path fill="currentColor" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_valid_stroke_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<line stroke="currentColor" x1="0" y1="0" x2="16" y2="16"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_valid_fill_on_svg_root(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
            '<path d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_valid_fill_none_with_stroke_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<circle fill="none" stroke="currentColor" cx="8" cy="8" r="7"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_hardcoded_hex_fill(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg"><path fill="#FF0000" d="M0 0h16v16H0z"/></svg>'
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded fill" in e for e in errors)
        assert any("must use currentColor" in e for e in errors)

    def test_hardcoded_named_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<rect fill="red" width="16" height="16"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any('fill="red"' in e for e in errors)

    def test_hardcoded_stroke_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<line stroke="#000" x1="0" y1="0" x2="16" y2="16"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded stroke" in e for e in errors)

    def test_no_fill_or_stroke_at_all(self):
        root = self._root('<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0h16v16H0z"/></svg>')
        errors = validate_icon_monochrome(root)
        assert errors == ["Icon must use currentColor for fills/strokes to support theming"]

    def test_inline_style_hardcoded(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path style="fill: #123456" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded style fill" in e for e in errors)

    def test_inline_style_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            '<path style="fill: currentColor" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_style_element_hardcoded(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            "<style>.a { fill: #FF0000; }</style>"
            '<path class="a" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        errors = validate_icon_monochrome(root)
        assert any("hardcoded CSS fill" in e for e in errors)

    def test_style_element_current_color(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg">'
            "<style>.a { fill: currentColor; }</style>"
            '<path class="a" d="M0 0h16v16H0z"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_mixed_elements_with_fill_none(self):
        """codex-acp style: fill on root, stroke on children, fill=none on some."""
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
            '<path d="M0 0h16v16H0z" fill-rule="nonzero"/>'
            '<circle cx="8" cy="8" r="3"/>'
            '<rect stroke="currentColor" fill="none" x="2" y="2" width="12" height="12"/>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []

    def test_inherit_fill_is_allowed(self):
        root = self._root(
            '<svg xmlns="http://www.w3.org/2000/svg" fill="currentColor">'
            '<g fill="inherit"><path d="M0 0z"/></g>'
            "</svg>"
        )
        assert validate_icon_monochrome(root) == []


# --- validate_icon ---


class TestValidateIcon:
    def _write_icon(self, tmpdir: Path, content: str) -> Path:
        p = tmpdir / "icon.svg"
        p.write_text(content)
        return p

    def test_valid_16x16(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            assert validate_icon(p) == []

    def test_valid_viewbox_only(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            assert validate_icon(p) == []

    def test_non_square(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="32">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("square" in e for e in errors)

    def test_wrong_size(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("16x16" in e for e in errors)

    def test_missing_dimensions(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("missing width/height" in e.lower() for e in errors)

    def test_invalid_xml(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(Path(d), "<not-closed>")
            errors = validate_icon(p)
            assert any("not valid SVG/XML" in e for e in errors)

    def test_non_svg_root(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(Path(d), "<div>hello</div>")
            errors = validate_icon(p)
            assert any("<svg>" in e for e in errors)

    def test_missing_file(self):
        errors = validate_icon(Path("/nonexistent/icon.svg"))
        assert any("Cannot read icon" in e for e in errors)

    def test_width_with_px_unit(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16px" height="16px">'
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            assert validate_icon(p) == []

    def test_html_comments_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._write_icon(
                Path(d),
                '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16">'
                "<!-- a comment -->"
                '<path fill="currentColor" d="M0 0z"/>'
                "</svg>",
            )
            errors = validate_icon(p)
            assert any("HTML comments" in e for e in errors)
