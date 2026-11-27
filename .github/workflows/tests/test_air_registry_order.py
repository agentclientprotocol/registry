import http.client
import urllib.error
from unittest.mock import Mock

import pytest

import air_registry_order
from air_registry_order import github_repository, sort_air_agents_by_stars


def agent(agent_id, name, repository=None):
    return {"id": agent_id, "name": name, "repository": repository}


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/Owner/Repo", "owner/repo"),
        ("https://github.com/Owner/Repo.git/", "owner/repo"),
        (None, None),
        ("https://example.com/owner/repo", None),
        ("https://github.com.evil.example/owner/repo", None),
        ("https://user@github.com/owner/repo", None),
        ("https://github.com/owner/repo/tree/main", None),
        ("https://github.com/owner/repo?other=value", None),
        ("http://github.com/owner/repo", None),
        ("https://[invalid/owner/repo", None),
    ],
)
def test_github_repository(url, expected):
    assert github_repository(url) == expected


def test_star_order_deduplicates_repositories_and_keeps_unknown_counts_last(monkeypatch):
    request = Mock(side_effect=[{"stargazers_count": 10}, {"stargazers_count": 20}, None])
    monkeypatch.setattr(air_registry_order, "make_request", request)
    agents = [
        agent("low", "Zulu", "https://github.com/owner/low"),
        agent("high-b", "Beta", "https://github.com/owner/high"),
        agent("high-a", "alpha", "https://github.com/OWNER/HIGH.git"),
        agent("failed", "Aardvark", "https://github.com/owner/unavailable"),
        agent("missing", "Omega"),
    ]
    before = list(agents)

    ordered = sort_air_agents_by_stars(agents)

    assert [entry["id"] for entry in ordered] == ["high-a", "high-b", "low", "failed", "missing"]
    assert agents == before
    assert request.call_count == 3
    assert all(call.kwargs["timeout"] <= 5 for call in request.call_args_list)


@pytest.mark.parametrize("status", [403, 429])
def test_rate_limit_stops_lookups_and_falls_back_to_names(monkeypatch, status):
    request = Mock(
        side_effect=urllib.error.HTTPError("https://api.github.com/", status, "", {}, None)
    )
    monkeypatch.setattr(air_registry_order, "make_request", request)
    agents = [
        agent("beta", "Beta", "https://github.com/owner/beta"),
        agent("alpha", "Alpha", "https://github.com/owner/alpha"),
    ]

    assert [entry["id"] for entry in sort_air_agents_by_stars(agents)] == ["alpha", "beta"]
    assert request.call_count == 1


def test_request_budget_keeps_collected_counts(monkeypatch):
    request = Mock(return_value={"stargazers_count": 1})
    monkeypatch.setattr(air_registry_order, "make_request", request)
    monkeypatch.setattr(air_registry_order.time, "monotonic", Mock(side_effect=[0, 29, 31]))
    agents = [
        agent("known", "Zulu", "https://github.com/owner/known"),
        agent("unknown", "Alpha", "https://github.com/owner/unknown"),
    ]

    assert [entry["id"] for entry in sort_air_agents_by_stars(agents)] == ["known", "unknown"]
    request.assert_called_once_with("https://api.github.com/repos/owner/known", timeout=1)


@pytest.mark.parametrize("count", [None, True, -1, "100", 1.5])
def test_invalid_counts_are_unknown(monkeypatch, count):
    monkeypatch.setattr(
        air_registry_order, "make_request", Mock(return_value={"stargazers_count": count})
    )
    agents = [agent("z", "Same"), agent("a", "same", "https://github.com/owner/repo")]

    assert [entry["id"] for entry in sort_air_agents_by_stars(agents)] == ["a", "z"]


def test_zero_stars_is_a_known_count(monkeypatch):
    monkeypatch.setattr(
        air_registry_order, "make_request", Mock(return_value={"stargazers_count": 0})
    )
    agents = [agent("missing", "Alpha"), agent("zero", "Zulu", "https://github.com/owner/repo")]

    assert [entry["id"] for entry in sort_air_agents_by_stars(agents)] == ["zero", "missing"]


@pytest.mark.parametrize(
    "error",
    [http.client.IncompleteRead(b""), UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid")],
)
def test_broken_responses_do_not_block_publication(monkeypatch, error):
    monkeypatch.setattr(air_registry_order, "make_request", Mock(side_effect=error))
    agents = [agent("beta", "Beta", "https://github.com/owner/repo"), agent("alpha", "Alpha")]

    assert [entry["id"] for entry in sort_air_agents_by_stars(agents)] == ["alpha", "beta"]
