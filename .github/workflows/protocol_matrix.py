#!/usr/bin/env python3
"""Generate a daily ACP protocol adaptation matrix for registry agents.

The matrix is intentionally unauthenticated: it probes what can be discovered
without user login by:
1. Launching each registered agent
2. Running `initialize`
3. Running a basic `session/new` check
4. Probing selected unstable methods

Outputs:
- .protocol-matrix/snapshots/YYYY-MM-DD.json
- .protocol-matrix/snapshots/YYYY-MM-DD.md
- .protocol-matrix/latest.json
- .protocol-matrix/latest.md
"""

from __future__ import annotations

import argparse
import copy
import fcntl
import json
import os
import select
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from verify_agents import build_agent_command, load_registry, prepare_binary

DEFAULT_INIT_TIMEOUT = 120.0
DEFAULT_RPC_TIMEOUT = 5.0
DEFAULT_EXIT_GRACE = 0.25
EXIT_GRACE_POLL_INTERVAL = 0.05
EXIT_GRACE_REAP_SLACK = 0.05
DEFAULT_SANDBOX_DIR = ".matrix-sandbox"
DEFAULT_OUTPUT_DIR = ".protocol-matrix"
DEFAULT_TABLE_MODE = "full"
PROTOCOL_VERSION = 1

TABLE_MODE_CHOICES = ("full", "capabilities")

METHOD_PROBES = (
    "session/list",
    "session/fork",
    "session/resume",
    "session/stop",
    "session/set_model",
)

SUCCESS_STATUSES = {"success", "invalid_params", "resource_not_found"}

CAPABILITY_COLUMNS = (
    ("loadSession", "loadSession"),
    ("sessionList", "session/list"),
    ("sessionFork", "session/fork"),
    ("sessionResume", "session/resume"),
    ("sessionStop", "session/stop"),
)


@dataclass
class ProbeOutcome:
    """Result of a single JSON-RPC method probe."""

    status: str
    code: int | None = None
    message: str | None = None


def short_message(message: str, max_len: int = 220) -> str:
    """Compact long messages for JSON/markdown outputs."""
    compact = " ".join(message.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def choose_distribution(distribution: dict[str, Any]) -> str | None:
    """Choose one distribution to probe per agent."""
    for preferred in ("npx", "uvx", "binary"):
        if preferred in distribution:
            return preferred
    if distribution:
        return sorted(distribution.keys())[0]
    return None


def parse_agent_csv(raw: str | None) -> list[str]:
    """Parse a comma-separated agent list."""
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def select_agents(
    agents: list[dict[str, Any]],
    include_csv: str | None = None,
    skip_csv: str | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Apply include/skip filters and report unknown skipped agents."""
    available_ids = {agent["id"] for agent in agents}
    include_ids = parse_agent_csv(include_csv)
    skip_ids = parse_agent_csv(skip_csv)

    unknown_include = [agent_id for agent_id in include_ids if agent_id not in available_ids]
    if unknown_include:
        raise ValueError(f"Unknown agent(s): {', '.join(unknown_include)}")

    unknown_skip = [agent_id for agent_id in skip_ids if agent_id not in available_ids]
    skip_set = set(skip_ids)

    filtered = agents
    if include_ids:
        include_set = set(include_ids)
        filtered = [agent for agent in filtered if agent["id"] in include_set]
    if skip_set:
        filtered = [agent for agent in filtered if agent["id"] not in skip_set]

    return filtered, unknown_skip


def load_previous_snapshot(snapshot_path: Path) -> dict[str, Any] | None:
    """Load the previous matrix snapshot if it exists and is well-formed."""
    if not snapshot_path.exists():
        return None

    try:
        snapshot = json.loads(snapshot_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Warning: Could not read previous snapshot {snapshot_path}: {exc}", file=sys.stderr)
        return None

    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("agents"), list):
        print(f"Warning: Ignoring invalid previous snapshot at {snapshot_path}", file=sys.stderr)
        return None

    return snapshot


def index_snapshot_agents(snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Index previous snapshot rows by agent id."""
    if snapshot is None:
        return {}

    indexed: dict[str, dict[str, Any]] = {}
    for record in snapshot.get("agents", []):
        if not isinstance(record, dict):
            continue
        agent_id = record.get("id")
        if isinstance(agent_id, str) and agent_id:
            indexed[agent_id] = record
    return indexed


def should_probe_agent(
    agent: dict[str, Any],
    previous_record: dict[str, Any] | None,
    dist_type: str | None,
) -> bool:
    """Return whether the agent should be re-probed for the current run."""
    if previous_record is None:
        return True

    if previous_record.get("registryVersion") != agent.get("version"):
        return True

    return previous_record.get("distribution") != (dist_type or "none")


def reuse_previous_record(
    agent: dict[str, Any],
    previous_record: dict[str, Any],
    dist_type: str | None,
    fallback_probed_at: str | None,
) -> dict[str, Any]:
    """Reuse a previous snapshot row for an unchanged agent version."""
    record = copy.deepcopy(previous_record)
    record["id"] = agent["id"]
    record["name"] = agent.get("name", agent["id"])
    record["registryVersion"] = agent.get("version")
    record["repository"] = agent.get("repository")
    record["distribution"] = dist_type or "none"
    record["reusedFromPrevious"] = True
    if not record.get("probedAt"):
        record["probedAt"] = fallback_probed_at
    return record


def infer_auth_type(method: dict[str, Any]) -> str:
    """Infer auth method type, matching registry auth checker semantics."""
    auth_type = method.get("type")
    if isinstance(auth_type, str) and auth_type:
        return auth_type

    meta = method.get("_meta", {})
    if isinstance(meta, dict):
        if "terminal-auth" in meta:
            return "terminal"
        if "agent-auth" in meta:
            return "agent"
        if "env-var-auth" in meta:
            return "env_var"

    # Backward-compatible default in ACP auth docs.
    return "agent"


def normalize_auth_methods(raw_auth_methods: list[Any]) -> list[str]:
    """Return unique auth method types."""
    types: set[str] = set()
    for item in raw_auth_methods:
        if isinstance(item, dict):
            types.add(infer_auth_type(item))
    return sorted(types)


def capability_present(capabilities: dict[str, Any], key: str) -> bool:
    """Capabilities are advertised by field presence with a non-null value."""
    return key in capabilities and capabilities[key] is not None


def build_initialize_params() -> dict[str, Any]:
    """Build the client initialize payload used for protocol probing."""
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "clientInfo": {
            "name": "ACP Registry Protocol Matrix",
            "version": "0.1.0",
        },
        "clientCapabilities": {
            "terminal": True,
            "fs": {
                "readTextFile": True,
                "writeTextFile": True,
            },
            "_meta": {
                "terminal_output": True,
                "terminal-auth": True,
            },
        },
    }


def response_exposes_models(message: dict[str, Any] | None) -> bool:
    """Return whether a successful response includes session model state."""
    if not message or "result" not in message:
        return False

    result = message["result"]
    return isinstance(result, dict) and result.get("models") is not None


def classify_rpc_response(message: dict[str, Any]) -> ProbeOutcome:
    """Convert a JSON-RPC response payload into a normalized probe outcome."""
    if "result" in message:
        return ProbeOutcome(status="success")

    error = message.get("error")
    if not isinstance(error, dict):
        return ProbeOutcome(status="error", message="Invalid error payload")

    raw_code = error.get("code")
    code: int | None
    try:
        code = int(raw_code) if raw_code is not None else None
    except (TypeError, ValueError):
        code = None

    msg = short_message(str(error.get("message", ""))) if error.get("message") else None
    msg_lower = (msg or "").lower()

    if code == -32601:
        return ProbeOutcome(status="method_not_found", code=code, message=msg)
    if code == -32000 or "auth_required" in msg_lower or "authentication" in msg_lower:
        return ProbeOutcome(status="auth_required", code=code, message=msg)
    if code == -32602:
        return ProbeOutcome(status="invalid_params", code=code, message=msg)
    if code == -32002:
        return ProbeOutcome(status="resource_not_found", code=code, message=msg)
    if code == -32800:
        return ProbeOutcome(status="cancelled", code=code, message=msg)

    return ProbeOutcome(status="error", code=code, message=msg)


def read_jsonrpc_line(proc: subprocess.Popen, timeout: float) -> dict[str, Any] | None:
    """Read one newline-delimited JSON-RPC message from stdout."""
    if proc.stdout is None:
        return None

    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        return None

    line = proc.stdout.readline()
    if not line:
        return None

    try:
        parsed = json.loads(line)
    except json.JSONDecodeError:
        return {"_decode_error": short_message(line.strip(), max_len=320)}

    if isinstance(parsed, dict):
        return parsed
    return {"_decode_error": short_message(line.strip(), max_len=320)}


def send_jsonrpc_request(
    proc: subprocess.Popen,
    request_id: int,
    method: str,
    params: dict[str, Any],
) -> None:
    """Send one JSON-RPC request over stdin."""
    if proc.stdin is None:
        raise RuntimeError("Process stdin is unavailable")

    payload = {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params,
    }
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def process_exit_outcome(
    exit_code: int,
    method: str,
) -> tuple[ProbeOutcome, dict[str, Any] | None]:
    """Build a normalized process-exit outcome for a pending request."""
    return (
        ProbeOutcome(
            status="process_error",
            message=f"process exited with code {exit_code} before responding to {method}",
        ),
        None,
    )


def reconcile_timed_out_request(
    proc: subprocess.Popen,
    request_id: int,
    method: str,
    exit_grace: float,
) -> tuple[ProbeOutcome, dict[str, Any] | None] | None:
    """Reconcile a timed-out request with a near-immediate exit or late response."""
    if exit_grace <= 0:
        return None

    deadline = time.monotonic() + exit_grace
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        message = read_jsonrpc_line(proc, min(remaining, EXIT_GRACE_POLL_INTERVAL))
        if message is None:
            exit_code = proc.poll()
            if exit_code is not None:
                return process_exit_outcome(exit_code, method)
            continue

        if "_decode_error" in message:
            return (
                ProbeOutcome(status="decode_error", message=message["_decode_error"]),
                None,
            )

        if message.get("id") == request_id and ("result" in message or "error" in message):
            return classify_rpc_response(message), message

    exit_code = proc.poll()
    if exit_code is not None:
        return process_exit_outcome(exit_code, method)

    if EXIT_GRACE_REAP_SLACK > 0:
        try:
            exit_code = proc.wait(timeout=EXIT_GRACE_REAP_SLACK)
        except subprocess.TimeoutExpired:
            exit_code = None
        if exit_code is not None:
            return process_exit_outcome(exit_code, method)

    return None


def request_with_timeout(
    proc: subprocess.Popen,
    request_id: int,
    method: str,
    params: dict[str, Any],
    timeout: float,
    exit_grace: float = DEFAULT_EXIT_GRACE,
) -> tuple[ProbeOutcome, dict[str, Any] | None]:
    """Send request and wait for the response with matching id."""
    exit_code = proc.poll()
    if exit_code is not None:
        return process_exit_outcome(exit_code, method)

    try:
        send_jsonrpc_request(proc, request_id, method, params)
    except (BrokenPipeError, OSError) as exc:
        exit_code = proc.poll()
        exit_suffix = f" (exit code {exit_code})" if exit_code is not None else ""
        return (
            ProbeOutcome(
                status="process_error",
                message=short_message(f"{type(exc).__name__}: {exc}{exit_suffix}"),
            ),
            None,
        )

    deadline = time.monotonic() + timeout

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        message = read_jsonrpc_line(proc, remaining)
        if message is None:
            exit_code = proc.poll()
            if exit_code is not None:
                return process_exit_outcome(exit_code, method)
            break

        if "_decode_error" in message:
            return (
                ProbeOutcome(status="decode_error", message=message["_decode_error"]),
                None,
            )

        if message.get("id") == request_id and ("result" in message or "error" in message):
            return classify_rpc_response(message), message

    reconciled = reconcile_timed_out_request(proc, request_id, method, exit_grace)
    if reconciled is not None:
        return reconciled

    return (
        ProbeOutcome(status="no_response", message=f"timeout after {timeout:.1f}s"),
        None,
    )


def collect_stderr_tail(proc: subprocess.Popen, max_chars: int = 1200) -> str | None:
    """Collect available stderr output without blocking on inherited pipes."""
    if proc.stderr is None:
        return None

    if proc.poll() is None:
        return None

    fd = proc.stderr.fileno()
    try:
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    except OSError:
        return None

    chunks: list[bytes] = []
    while True:
        try:
            data = os.read(fd, 4096)
        except BlockingIOError:
            break
        except OSError:
            break

        if not data:
            break
        chunks.append(data)

    if not chunks:
        return None

    tail = b"".join(chunks).decode(errors="replace")[-max_chars:]
    return short_message(tail, max_len=max_chars)


def stop_process(proc: subprocess.Popen) -> None:
    """Terminate process gracefully, then force kill if needed."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)


def probe_params_for_method(
    method: str,
    session_id: str,
    cwd: str,
) -> dict[str, Any]:
    """Create method-specific probe payloads."""
    if method == "session/list":
        return {}
    if method in {"session/fork", "session/resume"}:
        return {
            "sessionId": session_id,
            "cwd": cwd,
            "mcpServers": [],
        }
    if method == "session/stop":
        return {"sessionId": session_id}
    if method == "session/set_model":
        return {
            "sessionId": session_id,
            "modelId": "matrix-model",
        }
    raise ValueError(f"Unsupported probe method: {method}")


def status_short(status: str) -> str:
    """Compact status labels for markdown cells."""
    mapping = {
        "success": "ok",
        "auth_required": "auth",
        "method_not_found": "no",
        "invalid_params": "params",
        "resource_not_found": "missing",
        "no_response": "timeout",
        "decode_error": "decode",
        "process_error": "proc_err",
        "not_probed": "-",
    }
    return mapping.get(status, "err")


def feature_cell(advertised: bool, outcome: ProbeOutcome) -> str:
    """Render `signal/probe` feature status, e.g. `Y/yes`, `N/no`."""
    advertised_part = "Y" if advertised else "N"

    probe_map = {
        "success": "yes",
        "invalid_params": "yes",
        "resource_not_found": "yes",
        "auth_required": "auth",
        "method_not_found": "no",
        "no_response": "timeout",
        "decode_error": "decode",
        "not_probed": "-",
    }
    return f"{advertised_part}/{probe_map.get(outcome.status, 'err')}"


def format_capabilities(capabilities: dict[str, bool]) -> str:
    """Summarize capabilities advertised during the `initialize` handshake."""
    advertised = [label for key, label in CAPABILITY_COLUMNS if capabilities.get(key, False)]
    return ", ".join(advertised) if advertised else "-"


def render_aligned_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a fixed-width table inside a markdown code block."""
    widths = [len(header) for header in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def format_row(values: list[str]) -> str:
        return "  ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    separator = "  ".join("-" * width for width in widths)
    return [
        "```text",
        format_row(headers),
        separator,
        *(format_row(row) for row in rows),
        "```",
    ]


def summarize_results(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Build top-level summary metrics."""
    summary: dict[str, Any] = {
        "agentsProbed": len(records),
        "agentsProbedThisRun": 0,
        "agentsReused": 0,
        "initializeSuccess": 0,
        "sessionNewAuthRequired": 0,
        "features": {},
    }

    for method in METHOD_PROBES:
        summary["features"][method] = {
            "supported": 0,
            "authRequired": 0,
            "methodNotFound": 0,
            "other": 0,
        }

    for record in records:
        if record.get("reusedFromPrevious"):
            summary["agentsReused"] += 1
        else:
            summary["agentsProbedThisRun"] += 1

        init_status = record["initialize"]["status"]
        if init_status == "success":
            summary["initializeSuccess"] += 1

        session_new_status = record["sessionNew"]["status"]
        if session_new_status == "auth_required":
            summary["sessionNewAuthRequired"] += 1

        for method in METHOD_PROBES:
            status = record["methodProbes"][method]["status"]
            counters = summary["features"][method]
            if status in SUCCESS_STATUSES:
                counters["supported"] += 1
            elif status == "auth_required":
                counters["authRequired"] += 1
            elif status == "method_not_found":
                counters["methodNotFound"] += 1
            else:
                counters["other"] += 1

    return summary


def render_markdown(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    date_str: str,
    generated_at: str,
    table_mode: str = DEFAULT_TABLE_MODE,
) -> str:
    """Render the human-readable matrix report."""
    if table_mode not in TABLE_MODE_CHOICES:
        raise ValueError(f"Unsupported table mode: {table_mode}")

    lines = [
        f"# ACP Protocol Adaptation Matrix — {date_str}",
        "",
        f"_Generated at {generated_at}_",
        "",
        f"- Agents in report: **{summary['agentsProbed']}**",
        f"- Probed this run: **{summary['agentsProbedThisRun']}**",
        f"- Reused unchanged versions: **{summary['agentsReused']}**",
        f"- `initialize` success: **{summary['initializeSuccess']}**",
        (f"- `session/new` returned `auth_required`: **{summary['sessionNewAuthRequired']}**"),
        "",
    ]

    if table_mode == "capabilities":
        lines.extend(
            [
                (
                    "Legend: `Capabilities` lists the capabilities advertised in the "
                    "`initialize` response via `agentCapabilities` and "
                    "`sessionCapabilities`."
                ),
                "",
            ]
        )
    else:
        lines.extend(
            [
                (
                    "Legend: feature cells use `Signal/Probe` format. "
                    "For `session/list`, `session/fork`, `session/resume`, and `session/stop`, "
                    "`Y`/`N` means the capability was advertised. For `session/set_model`, "
                    "`Y`/`N` means session responses exposed `models`. Probe values: "
                    "`yes`, `no`, `auth`, `timeout`, `decode`, `err`, `-`."
                ),
                (
                    "`Capabilities` lists the capabilities advertised in the "
                    "`initialize` response via `agentCapabilities` and "
                    "`sessionCapabilities`."
                ),
                "",
            ]
        )

    result_rows: list[list[str]] = []
    for record in records:
        caps = record["capabilities"]
        probes = record["methodProbes"]
        auth_types = record["authMethods"]

        auth_cell = ", ".join(auth_types) if auth_types else "-"
        version_cell = record.get("registryVersion") or "-"

        if table_mode == "capabilities":
            result_rows.append(
                [
                    record["id"],
                    version_cell,
                    record["distribution"],
                    status_short(record["initialize"]["status"]),
                    auth_cell,
                    format_capabilities(caps),
                ]
            )
            continue

        set_model_advertised = bool(record.get("setModelSignal", caps.get("setModel")))

        result_rows.append(
            [
                record["id"],
                version_cell,
                record["distribution"],
                status_short(record["initialize"]["status"]),
                auth_cell,
                status_short(record["sessionNew"]["status"]),
                format_capabilities(caps),
                feature_cell(caps["sessionList"], ProbeOutcome(**probes["session/list"])),
                feature_cell(caps["sessionFork"], ProbeOutcome(**probes["session/fork"])),
                feature_cell(caps["sessionResume"], ProbeOutcome(**probes["session/resume"])),
                feature_cell(caps["sessionStop"], ProbeOutcome(**probes["session/stop"])),
                feature_cell(
                    set_model_advertised,
                    ProbeOutcome(**probes["session/set_model"]),
                ),
            ]
        )

    table_headers = ["Agent", "Version", "Dist", "Init", "Auth", "Capabilities"]
    if table_mode == "full":
        table_headers = [
            "Agent",
            "Version",
            "Dist",
            "Init",
            "Auth",
            "session/new",
            "Capabilities",
            "session/list",
            "session/fork",
            "session/resume",
            "session/stop",
            "session/set_model",
        ]

    lines.extend(render_aligned_table(headers=table_headers, rows=result_rows))

    lines.extend(
        [
            "",
            "## Method Probe Summary",
            "",
            "| Method | Supported | Auth Required | Method Not Found | Other |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )

    for method in METHOD_PROBES:
        counters = summary["features"][method]
        lines.append(
            "| "
            + " | ".join(
                [
                    f"`{method}`",
                    str(counters["supported"]),
                    str(counters["authRequired"]),
                    str(counters["methodNotFound"]),
                    str(counters["other"]),
                ]
            )
            + " |"
        )

    return "\n".join(lines) + "\n"


def ensure_distribution_runtime(dist_type: str) -> ProbeOutcome | None:
    """Return an error outcome if required launcher command is missing."""
    if dist_type == "npx" and shutil.which("npx") is None:
        return ProbeOutcome(status="process_error", message="`npx` not found in PATH")
    if dist_type == "uvx" and shutil.which("uvx") is None:
        return ProbeOutcome(status="process_error", message="`uvx` not found in PATH")
    return None


def ensure_binary_executable(cmd: list[str], dist_type: str) -> ProbeOutcome | None:
    """Ensure binary distribution executables are runnable before spawning."""
    if dist_type != "binary" or os.name == "nt" or not cmd:
        return None

    exe_path = Path(cmd[0])
    if not exe_path.exists():
        return None

    try:
        current_mode = exe_path.stat().st_mode
    except OSError as exc:
        return ProbeOutcome(
            status="process_error",
            message=short_message(f"Failed to inspect executable {exe_path}: {exc}"),
        )

    if current_mode & 0o111:
        return None

    try:
        exe_path.chmod(current_mode | 0o755)
    except OSError as exc:
        return ProbeOutcome(
            status="process_error",
            message=short_message(f"Failed to make executable {exe_path}: {exc}"),
        )

    return None


def probe_agent(
    agent: dict[str, Any],
    sandbox_base: Path,
    init_timeout: float,
    rpc_timeout: float,
) -> dict[str, Any]:
    """Probe one agent and return snapshot row."""
    started_at = time.monotonic()
    agent_id = agent["id"]
    distribution = agent.get("distribution", {})
    dist_type = choose_distribution(distribution)

    default_row = {
        "id": agent_id,
        "name": agent.get("name", agent_id),
        "registryVersion": agent.get("version"),
        "repository": agent.get("repository"),
        "distribution": dist_type or "none",
        "initialize": asdict(ProbeOutcome(status="process_error", message="Not probed")),
        "protocolVersion": None,
        "agentInfoVersion": None,
        "authMethods": [],
        "setModelSignal": False,
        "capabilities": {
            "loadSession": False,
            "sessionList": False,
            "sessionFork": False,
            "sessionResume": False,
            "sessionStop": False,
            "setModel": False,
        },
        "sessionNew": asdict(ProbeOutcome(status="not_probed")),
        "methodProbes": {
            method: asdict(ProbeOutcome(status="not_probed")) for method in METHOD_PROBES
        },
        "stderrTail": None,
        "commandPreview": None,
        "workspaceCwd": None,
        "durationSeconds": None,
        "processExitCode": None,
        "probedAt": None,
        "reusedFromPrevious": False,
    }

    if not dist_type:
        default_row["initialize"] = asdict(
            ProbeOutcome(status="process_error", message="No distribution available")
        )
        return default_row

    runtime_error = ensure_distribution_runtime(dist_type)
    if runtime_error:
        default_row["initialize"] = asdict(runtime_error)
        return default_row

    sandbox = sandbox_base / dist_type / agent_id
    sandbox.mkdir(parents=True, exist_ok=True)
    workspace_dir = (sandbox / "workspace").resolve()
    workspace_dir.mkdir(parents=True, exist_ok=True)
    default_row["workspaceCwd"] = str(workspace_dir)

    if dist_type == "binary":
        success, message = prepare_binary(agent, sandbox)
        if not success:
            default_row["initialize"] = asdict(
                ProbeOutcome(status="process_error", message=message)
            )
            return default_row

    cmd, cwd, env = build_agent_command(agent, dist_type, sandbox)
    if not cmd:
        default_row["initialize"] = asdict(
            ProbeOutcome(status="process_error", message=f"Failed to build command for {dist_type}")
        )
        return default_row

    executable_error = ensure_binary_executable(cmd, dist_type)
    if executable_error is not None:
        default_row["initialize"] = asdict(executable_error)
        return default_row

    default_row["commandPreview"] = " ".join(cmd[:4])

    home_dir = sandbox / "home"
    home_dir.mkdir(parents=True, exist_ok=True)
    full_env = {
        "HOME": str(home_dir),
        "TERM": "dumb",
        **env,
    }

    proc: subprocess.Popen | None = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            env={**dict(os.environ), **full_env},
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )

        request_id = 1
        init_outcome, init_message = request_with_timeout(
            proc,
            request_id,
            "initialize",
            build_initialize_params(),
            init_timeout,
        )
        request_id += 1
        default_row["initialize"] = asdict(init_outcome)

        session_id = "sess_matrix_probe"
        if init_outcome.status == "success" and init_message and "result" in init_message:
            result = init_message["result"]
            if isinstance(result, dict):
                default_row["protocolVersion"] = result.get("protocolVersion")
                agent_info = result.get("agentInfo", {})
                if isinstance(agent_info, dict):
                    default_row["agentInfoVersion"] = agent_info.get("version")

                raw_auth = result.get("authMethods", [])
                if isinstance(raw_auth, list):
                    default_row["authMethods"] = normalize_auth_methods(raw_auth)

                agent_caps = result.get("agentCapabilities", {})
                if not isinstance(agent_caps, dict):
                    agent_caps = {}
                session_caps = agent_caps.get("sessionCapabilities", {})
                if not isinstance(session_caps, dict):
                    session_caps = {}

                default_row["capabilities"] = {
                    "loadSession": bool(agent_caps.get("loadSession", False)),
                    "sessionList": capability_present(session_caps, "list"),
                    "sessionFork": capability_present(session_caps, "fork"),
                    "sessionResume": capability_present(session_caps, "resume"),
                    "sessionStop": capability_present(session_caps, "stop"),
                    "setModel": False,
                }

                session_new_outcome, session_new_message = request_with_timeout(
                    proc,
                    request_id,
                    "session/new",
                    {
                        "cwd": str(workspace_dir),
                        "mcpServers": [],
                    },
                    rpc_timeout,
                )
                request_id += 1
                default_row["sessionNew"] = asdict(session_new_outcome)

                if response_exposes_models(session_new_message):
                    default_row["setModelSignal"] = True
                    default_row["capabilities"]["setModel"] = True

                if session_new_outcome.status == "success" and session_new_message:
                    session_result = session_new_message.get("result", {})
                    if isinstance(session_result, dict):
                        maybe_session_id = session_result.get("sessionId")
                        if isinstance(maybe_session_id, str) and maybe_session_id:
                            session_id = maybe_session_id

                for method in METHOD_PROBES:
                    params = probe_params_for_method(
                        method=method,
                        session_id=session_id,
                        cwd=str(workspace_dir),
                    )
                    outcome, message = request_with_timeout(
                        proc,
                        request_id,
                        method,
                        params,
                        rpc_timeout,
                    )
                    if response_exposes_models(message):
                        default_row["setModelSignal"] = True
                        default_row["capabilities"]["setModel"] = True
                    default_row["methodProbes"][method] = asdict(outcome)
                    request_id += 1
    except Exception as exc:  # noqa: BLE001
        default_row["initialize"] = asdict(
            ProbeOutcome(
                status="process_error",
                message=short_message(f"{type(exc).__name__}: {exc}"),
            )
        )
    finally:
        if proc is not None:
            stop_process(proc)
            default_row["processExitCode"] = proc.returncode
            default_row["stderrTail"] = collect_stderr_tail(proc)

        default_row["durationSeconds"] = round(time.monotonic() - started_at, 3)

    return default_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ACP protocol adaptation matrix")
    parser.add_argument(
        "--agent",
        help="Comma-separated list of agent IDs to probe (default: all)",
    )
    parser.add_argument(
        "--skip-agent",
        help="Comma-separated list of agent IDs to skip",
    )
    parser.add_argument(
        "--max-agents",
        type=int,
        default=0,
        help="Limit number of agents for quick local runs",
    )
    parser.add_argument(
        "--init-timeout",
        type=float,
        default=DEFAULT_INIT_TIMEOUT,
        help=f"Timeout for initialize request in seconds (default: {DEFAULT_INIT_TIMEOUT})",
    )
    parser.add_argument(
        "--rpc-timeout",
        type=float,
        default=DEFAULT_RPC_TIMEOUT,
        help=f"Timeout for each probe request in seconds (default: {DEFAULT_RPC_TIMEOUT})",
    )
    parser.add_argument(
        "--sandbox-dir",
        default=DEFAULT_SANDBOX_DIR,
        help=f"Sandbox directory (default: {DEFAULT_SANDBOX_DIR})",
    )
    parser.add_argument(
        "--output-dir",
        default=DEFAULT_OUTPUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--table-mode",
        choices=TABLE_MODE_CHOICES,
        default=DEFAULT_TABLE_MODE,
        help=(f"Markdown main table mode (default: {DEFAULT_TABLE_MODE})"),
    )
    parser.add_argument(
        "--changed-only",
        action="store_true",
        help=(
            "Probe only agents whose registry version or selected distribution changed "
            "since the previous snapshot; reuse unchanged rows from latest.json"
        ),
    )
    parser.add_argument(
        "--date",
        help="Snapshot date in YYYY-MM-DD (default: current UTC date)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    registry_dir = Path(__file__).resolve().parents[2]
    sandbox_base = registry_dir / args.sandbox_dir
    output_base = registry_dir / args.output_dir
    snapshots_dir = output_base / "snapshots"
    snapshots_dir.mkdir(parents=True, exist_ok=True)

    # Keep timezone.utc for compatibility with local Python <3.11 while CI uses 3.14.
    date_str = args.date or datetime.now(timezone.utc).date().isoformat()  # noqa: UP017
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()  # noqa: UP017

    agents = load_registry(registry_dir)

    try:
        agents, unknown_skips = select_agents(
            agents,
            include_csv=args.agent,
            skip_csv=args.skip_agent,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if unknown_skips:
        print(
            f"Ignoring unknown skipped agent(s): {', '.join(unknown_skips)}",
            file=sys.stderr,
        )

    if args.max_agents > 0:
        agents = agents[: args.max_agents]

    agents.sort(key=lambda item: item["id"])
    latest_json_path = output_base / "latest.json"
    previous_snapshot = load_previous_snapshot(latest_json_path) if args.changed_only else None
    previous_records = index_snapshot_agents(previous_snapshot)
    previous_generated_at = None
    if previous_snapshot is not None:
        previous_generated_at = previous_snapshot.get("generatedAt")
        print(f"Loaded previous snapshot from {latest_json_path}")
    elif args.changed_only:
        print("No previous snapshot found; probing all agents")

    print(f"Processing {len(agents)} agent(s)")

    records: list[dict[str, Any]] = []
    for idx, agent in enumerate(agents, 1):
        dist_type = choose_distribution(agent.get("distribution", {}))
        previous_record = previous_records.get(agent["id"])
        if args.changed_only and not should_probe_agent(agent, previous_record, dist_type):
            print(f"[{idx}/{len(agents)}] {agent['id']} (reuse)")
            records.append(
                reuse_previous_record(
                    agent,
                    previous_record,
                    dist_type,
                    fallback_probed_at=previous_generated_at,
                )
            )
            continue

        print(f"[{idx}/{len(agents)}] {agent['id']}")
        record = probe_agent(
            agent=agent,
            sandbox_base=sandbox_base,
            init_timeout=args.init_timeout,
            rpc_timeout=args.rpc_timeout,
        )
        record["probedAt"] = generated_at
        record["reusedFromPrevious"] = False
        records.append(record)

    summary = summarize_results(records)
    snapshot = {
        "date": date_str,
        "generatedAt": generated_at,
        "tableMode": args.table_mode,
        "changedOnly": args.changed_only,
        "summary": summary,
        "agents": records,
    }

    markdown = render_markdown(
        records,
        summary,
        date_str,
        generated_at,
        table_mode=args.table_mode,
    )

    dated_json_path = snapshots_dir / f"{date_str}.json"
    dated_md_path = snapshots_dir / f"{date_str}.md"
    latest_md_path = output_base / "latest.md"

    dated_json_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    dated_md_path.write_text(markdown)
    latest_json_path.write_text(json.dumps(snapshot, indent=2) + "\n")
    latest_md_path.write_text(markdown)

    print(f"Wrote: {dated_json_path}")
    print(f"Wrote: {dated_md_path}")
    print(f"Wrote: {latest_json_path}")
    print(f"Wrote: {latest_md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
