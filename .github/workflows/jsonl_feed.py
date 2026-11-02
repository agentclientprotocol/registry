"""Fetch the tail of an append-only newline-delimited JSON (JSONL) feed.

Used by custom agent sources whose release feed is a single growing `.jsonl`
file. Knows nothing about record shape -- callers interpret the fields.
"""

import json
import urllib.error
import urllib.request

_USER_AGENT = "ACP-Registry-Version-Checker/1.0"


def fetch_jsonl_tail(url: str, max_lines: int) -> list[dict]:
    """Fetch `url` and parse up to the last `max_lines` non-blank JSON records.

    Malformed or non-object lines are skipped. Returns an empty list on
    fetch failure (network error, 404, non-2xx status).
    """
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            text = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return []

    lines = [line for line in text.splitlines() if line.strip()]

    records: list[dict] = []
    for line in lines[-max_lines:]:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return records
