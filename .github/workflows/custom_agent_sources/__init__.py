"""Per-(agent_id, channel) overrides for agents whose releases aren't
discoverable through npm, PyPI, or GitHub Releases.

Each override matches `CustomSourceFn`: given the agent's parsed `agent.json`,
report the latest release found (or `None`, or an `UpdateError` on failure).
It does not compare that against the current version -- update_versions.py's
`resolve_update()` owns that for every source, standard or custom.

To add a source: write `<agent_id>.py` here with a function matching
`CustomSourceFn`, then register it in update_versions.py's
`CUSTOM_AGENT_SOURCES` table.
"""

from collections.abc import Callable

from common import LatestRelease, UpdateError

CustomSourceFn = Callable[[dict], tuple[LatestRelease | None, UpdateError | None]]

__all__ = ["CustomSourceFn"]
