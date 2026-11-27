"""Order the Air registry by repository stars at build time."""

import http.client
import re
import time
import urllib.error
import urllib.parse

from github_api import make_request


def github_repository(url: str | None) -> str | None:
    if not url:
        return None
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return None
    if (
        parsed.scheme != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.query
        or parsed.fragment
    ):
        return None
    match = re.fullmatch(r"/([\w.-]+)/([\w.-]+?)(?:\.git)?/?", parsed.path, re.ASCII)
    return "/".join(match.groups()).lower() if match else None


def sort_air_agents_by_stars(agents: list[dict]) -> list[dict]:
    counts: dict[str, int | None] = {}
    deadline = time.monotonic() + 30
    rate_limited = False
    for agent in agents:
        repository = github_repository(agent.get("repository"))
        if repository is None or repository in counts:
            continue
        counts[repository] = None
        remaining = deadline - time.monotonic()
        if rate_limited or remaining <= 0:
            continue
        try:
            data = make_request(
                f"https://api.github.com/repos/{repository}", timeout=min(5, remaining)
            )
        except urllib.error.HTTPError as error:
            rate_limited = error.code in (403, 429)
            continue
        except (http.client.HTTPException, UnicodeError):
            continue
        count = data.get("stargazers_count") if isinstance(data, dict) else None
        if type(count) is int and count >= 0:
            counts[repository] = count

    unavailable = sum(count is None for count in counts.values())
    if unavailable:
        print(f"Warning: GitHub stars unavailable for {unavailable} Air repositories")

    def sort_key(agent: dict) -> tuple:
        count = counts.get(github_repository(agent.get("repository")))
        return (
            count is None,
            -count if count is not None else 0,
            agent["name"].casefold(),
            agent["id"],
        )

    return sorted(agents, key=sort_key)
