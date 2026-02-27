"""Tests for shared registry utilities."""

import json
import tempfile
from pathlib import Path

from registry_utils import (
    extract_npm_package_name,
    extract_npm_package_version,
    extract_pypi_package_name,
    load_quarantine,
    normalize_version,
)


class TestExtractNpmPackageName:
    def test_scoped_with_version(self):
        assert extract_npm_package_name("@google/gemini-cli@0.30.0") == "@google/gemini-cli"

    def test_scoped_without_version(self):
        assert extract_npm_package_name("@google/gemini-cli") == "@google/gemini-cli"

    def test_unscoped_with_version(self):
        assert extract_npm_package_name("some-package@1.2.3") == "some-package"

    def test_unscoped_without_version(self):
        assert extract_npm_package_name("some-package") == "some-package"

    def test_empty_string(self):
        assert extract_npm_package_name("") == ""


class TestExtractNpmPackageVersion:
    def test_scoped_with_version(self):
        assert extract_npm_package_version("@google/gemini-cli@0.30.0") == "0.30.0"

    def test_scoped_without_version(self):
        assert extract_npm_package_version("@google/gemini-cli") is None

    def test_unscoped_with_version(self):
        assert extract_npm_package_version("some-package@1.2.3") == "1.2.3"

    def test_unscoped_without_version(self):
        assert extract_npm_package_version("some-package") is None


class TestExtractPypiPackageName:
    def test_with_double_equals(self):
        assert extract_pypi_package_name("some-package==1.2.3") == "some-package"

    def test_with_at_version(self):
        assert extract_pypi_package_name("some-package@1.2.3") == "some-package"

    def test_with_gte(self):
        assert extract_pypi_package_name("some-package>=1.0") == "some-package"

    def test_plain_name(self):
        assert extract_pypi_package_name("some-package") == "some-package"


class TestNormalizeVersion:
    def test_already_semver(self):
        assert normalize_version("1.2.3") == "1.2.3"

    def test_two_parts(self):
        assert normalize_version("1.2") == "1.2.0"

    def test_one_part(self):
        assert normalize_version("1") == "1.0.0"

    def test_four_parts_truncated(self):
        assert normalize_version("1.2.3.4") == "1.2.3"


class TestLoadQuarantine:
    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as d:
            assert load_quarantine(Path(d)) == {}

    def test_empty_object(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "quarantine.json"
            p.write_text("{}")
            assert load_quarantine(Path(d)) == {}

    def test_with_entries(self):
        with tempfile.TemporaryDirectory() as d:
            data = {"bad-agent": "broke auth", "other": "removed"}
            p = Path(d) / "quarantine.json"
            p.write_text(json.dumps(data))
            assert load_quarantine(Path(d)) == data

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "quarantine.json"
            p.write_text("not json")
            assert load_quarantine(Path(d)) == {}
