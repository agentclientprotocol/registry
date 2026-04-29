"""Tests for protocol_matrix helper logic."""

import os
import stat
import subprocess
import sys

import pytest

from protocol_matrix import (
    ProbeOutcome,
    build_initialize_params,
    choose_distribution,
    classify_rpc_response,
    ensure_binary_executable,
    feature_cell,
    format_capabilities,
    parse_agent_csv,
    probe_params_for_method,
    render_markdown,
    request_with_timeout,
    response_exposes_models,
    reuse_previous_record,
    select_agents,
    should_probe_agent,
    summarize_results,
)


def make_record(
    *,
    version: str = "1.2.3",
    distribution: str = "npx",
    init_status: str = "success",
    session_new_status: str = "success",
    list_status: str = "success",
    fork_status: str = "method_not_found",
    resume_status: str = "method_not_found",
    stop_status: str = "method_not_found",
    set_model_status: str = "method_not_found",
    set_model_signal: bool = False,
    reused_from_previous: bool = False,
    probed_at: str | None = "2026-03-06T12:00:00+00:00",
) -> dict:
    return {
        "id": "agent-1",
        "registryVersion": version,
        "repository": None,
        "website": None,
        "distribution": distribution,
        "initialize": {"status": init_status, "code": None, "message": None},
        "authMethods": ["agent"],
        "setModelSignal": set_model_signal,
        "sessionNew": {"status": session_new_status, "code": None, "message": None},
        "capabilities": {
            "loadSession": True,
            "sessionList": True,
            "sessionFork": False,
            "sessionResume": False,
            "sessionStop": False,
            "setModel": False,
        },
        "methodProbes": {
            "session/list": {"status": list_status, "code": None, "message": None},
            "session/fork": {"status": fork_status, "code": None, "message": None},
            "session/resume": {"status": resume_status, "code": None, "message": None},
            "session/stop": {"status": stop_status, "code": None, "message": None},
            "session/set_model": {"status": set_model_status, "code": None, "message": None},
        },
        "reusedFromPrevious": reused_from_previous,
        "probedAt": probed_at,
    }


def test_build_initialize_params_matches_auth_probe_capabilities():
    params = build_initialize_params()

    assert params["protocolVersion"] == 1
    assert params["clientCapabilities"]["terminal"] is True
    assert params["clientCapabilities"]["_meta"] == {
        "terminal_output": True,
        "terminal-auth": True,
    }


def test_ensure_binary_executable_sets_exec_bit(tmp_path):
    exe = tmp_path / "agent"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o644)

    outcome = ensure_binary_executable([str(exe)], "binary")

    assert outcome is None
    assert exe.stat().st_mode & stat.S_IXUSR
    assert os.access(exe, os.X_OK)


def test_ensure_binary_executable_ignores_non_binary(tmp_path):
    exe = tmp_path / "agent"
    exe.write_text("#!/bin/sh\n")
    exe.chmod(0o644)

    outcome = ensure_binary_executable([str(exe)], "npx")

    assert outcome is None
    assert not exe.stat().st_mode & stat.S_IXUSR


def test_parse_agent_csv_handles_empty_values_and_whitespace():
    assert parse_agent_csv(None) == []
    assert parse_agent_csv("") == []
    assert parse_agent_csv(" codex-acp, crow-cli ,, gemini ") == [
        "codex-acp",
        "crow-cli",
        "gemini",
    ]


def test_select_agents_applies_include_and_skip_filters():
    agents = [{"id": "codex-acp"}, {"id": "crow-cli"}, {"id": "gemini"}]

    selected, unknown_skip = select_agents(
        agents,
        include_csv="codex-acp,crow-cli,gemini",
        skip_csv="crow-cli",
    )

    assert [agent["id"] for agent in selected] == ["codex-acp", "gemini"]
    assert unknown_skip == []


def test_select_agents_rejects_unknown_included_agents():
    with pytest.raises(ValueError, match="Unknown agent"):
        select_agents([{"id": "codex-acp"}], include_csv="missing-agent")


def test_select_agents_reports_unknown_skipped_agents_without_failing():
    selected, unknown_skip = select_agents([{"id": "codex-acp"}], skip_csv="crow-cli")

    assert [agent["id"] for agent in selected] == ["codex-acp"]
    assert unknown_skip == ["crow-cli"]


def test_choose_distribution_prefers_npx():
    assert choose_distribution({"binary": {}, "npx": {}}) == "npx"


def test_choose_distribution_prefers_uvx_when_npx_missing():
    assert choose_distribution({"binary": {}, "uvx": {}}) == "uvx"


def test_choose_distribution_returns_none_for_empty():
    assert choose_distribution({}) is None


def test_should_probe_agent_skips_unchanged_version_and_distribution():
    agent = {"id": "agent-1", "version": "1.2.3"}
    previous_record = {"id": "agent-1", "registryVersion": "1.2.3", "distribution": "npx"}

    assert not should_probe_agent(agent, previous_record, "npx")


def test_should_probe_agent_reprobes_when_version_changes():
    agent = {"id": "agent-1", "version": "1.2.4"}
    previous_record = {"id": "agent-1", "registryVersion": "1.2.3", "distribution": "npx"}

    assert should_probe_agent(agent, previous_record, "npx")


def test_reuse_previous_record_updates_metadata_and_marks_row_reused():
    agent = {
        "id": "agent-1",
        "name": "Agent One",
        "version": "1.2.3",
        "repository": "https://example.com/repo",
        "website": "https://example.com/docs",
    }
    previous_record = make_record(probed_at=None)

    reused = reuse_previous_record(agent, previous_record, "npx", "2026-03-05T00:00:00+00:00")

    assert reused["name"] == "Agent One"
    assert reused["registryVersion"] == "1.2.3"
    assert reused["repository"] == "https://example.com/repo"
    assert reused["website"] == "https://example.com/docs"
    assert reused["distribution"] == "npx"
    assert reused["reusedFromPrevious"] is True
    assert reused["probedAt"] == "2026-03-05T00:00:00+00:00"


def test_probe_params_for_methods_match_schema():
    cwd = "/tmp/matrix-workspace"
    session_id = "sess-123"

    assert probe_params_for_method("session/list", session_id, cwd) == {}
    assert probe_params_for_method("session/fork", session_id, cwd) == {
        "sessionId": session_id,
        "cwd": cwd,
        "mcpServers": [],
    }
    assert probe_params_for_method("session/resume", session_id, cwd) == {
        "sessionId": session_id,
        "cwd": cwd,
        "mcpServers": [],
    }
    assert probe_params_for_method("session/stop", session_id, cwd) == {
        "sessionId": session_id,
    }
    assert probe_params_for_method("session/set_model", session_id, cwd) == {
        "sessionId": session_id,
        "modelId": "matrix-model",
    }


def test_response_exposes_models_only_when_present():
    assert response_exposes_models(
        {
            "result": {
                "sessionId": "sess-123",
                "models": {
                    "currentModelId": "model-a",
                    "availableModels": [{"modelId": "model-a", "name": "A"}],
                },
            }
        }
    )
    assert not response_exposes_models({"result": {"sessionId": "sess-123"}})
    assert not response_exposes_models({"error": {"code": -32601, "message": "Method not found"}})


def test_classify_rpc_response_method_not_found():
    outcome = classify_rpc_response({"error": {"code": -32601, "message": "Method not found"}})
    assert outcome.status == "method_not_found"
    assert outcome.code == -32601


def test_classify_rpc_response_auth_required():
    outcome = classify_rpc_response({"error": {"code": -32000, "message": "auth_required"}})
    assert outcome.status == "auth_required"
    assert outcome.code == -32000


def test_classify_rpc_response_success():
    outcome = classify_rpc_response({"result": {"ok": True}})
    assert outcome.status == "success"


def test_request_with_timeout_reports_exited_process():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import sys; sys.exit(7)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    proc.wait(timeout=2)

    outcome, message = request_with_timeout(proc, 1, "initialize", {}, 0.1)

    assert outcome.status == "process_error"
    assert "code 7" in (outcome.message or "")
    assert message is None


def test_request_with_timeout_reclassifies_timeout_when_process_exits_during_grace():
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            ("import sys,time; sys.stdin.readline(); time.sleep(0.03); sys.exit(9)"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    outcome, message = request_with_timeout(proc, 1, "initialize", {}, 0.005, exit_grace=0.5)

    assert outcome.status == "process_error"
    assert "code 9" in (outcome.message or "")
    assert message is None


def test_request_with_timeout_keeps_no_response_when_process_stays_alive():
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            ("import sys,time; sys.stdin.readline(); time.sleep(1)"),
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        outcome, message = request_with_timeout(
            proc,
            1,
            "initialize",
            {},
            0.02,
            exit_grace=0.05,
        )
    finally:
        proc.terminate()
        proc.wait(timeout=2)

    assert outcome.status == "no_response"
    assert "timeout after 0.0s" in (outcome.message or "")
    assert message is None


def test_feature_cell_formats_advertised_and_probe():
    cell = feature_cell(True, ProbeOutcome(status="invalid_params"))
    assert cell == "Y/yes"


def test_format_capabilities_lists_advertised_initialize_capabilities():
    summary = format_capabilities(
        {
            "loadSession": True,
            "sessionList": True,
            "sessionFork": False,
            "sessionResume": True,
            "sessionStop": False,
        }
    )

    assert summary == "loadSession, session/list, session/resume"


def test_summarize_results_counts_statuses():
    records = [
        make_record(
            session_new_status="auth_required",
            list_status="success",
            fork_status="auth_required",
            resume_status="method_not_found",
            stop_status="error",
            set_model_status="invalid_params",
        )
    ]
    summary = summarize_results(records)
    assert summary["agentsProbed"] == 1
    assert summary["agentsProbedThisRun"] == 1
    assert summary["agentsReused"] == 0
    assert summary["initializeSuccess"] == 1
    assert summary["sessionNewAuthRequired"] == 1
    assert summary["features"]["session/list"]["supported"] == 1
    assert summary["features"]["session/fork"]["authRequired"] == 1
    assert summary["features"]["session/resume"]["methodNotFound"] == 1
    assert summary["features"]["session/stop"]["other"] == 1
    assert summary["features"]["session/set_model"]["supported"] == 1


def test_summarize_results_counts_reused_rows():
    summary = summarize_results([make_record(reused_from_previous=True)])

    assert summary["agentsProbed"] == 1
    assert summary["agentsProbedThisRun"] == 0
    assert summary["agentsReused"] == 1


def test_render_markdown_full_mode_contains_matrix_headers_and_signal_legend():
    records = [make_record(set_model_signal=True)]
    summary = summarize_results(records)
    md = render_markdown(records, summary, "2026-03-06", "2026-03-06T12:00:00+00:00")
    header_line = md.split("```text\n", maxsplit=1)[1].splitlines()[0]

    assert "# ACP Protocol Adaptation Matrix — 2026-03-06" in md
    assert "- Agents in report: **1**" in md
    assert "- Probed this run: **1**" in md
    assert "- Reused unchanged versions: **0**" in md
    assert "Legend: feature cells use `Signal/Probe` format." in md
    assert "For `session/set_model`, `Y`/`N` means session responses exposed `models`." in md
    assert "`Capabilities` lists the capabilities advertised in the `initialize` response" in md
    assert "```text" in md
    assert "Version" in header_line
    assert "Capabilities" in header_line
    assert "session/new" in header_line
    assert "session/list" in header_line
    assert "session/set_model" in header_line
    assert "agent-1" in md
    assert "1.2.3" in md
    assert "npx" in md
    assert "loadSession, session/list" in md
    assert "Y/yes" in md


def test_render_markdown_capabilities_mode_renders_capabilities_only_table():
    records = [make_record(set_model_signal=True)]
    summary = summarize_results(records)
    md = render_markdown(
        records,
        summary,
        "2026-03-06",
        "2026-03-06T12:00:00+00:00",
        table_mode="capabilities",
    )
    header_line = md.split("```text\n", maxsplit=1)[1].splitlines()[0]

    assert (
        "Legend: `Capabilities` lists the capabilities advertised in the `initialize` response"
        in md
    )
    assert "Version" in header_line
    assert "Capabilities" in header_line
    assert "session/new" not in header_line
    assert "session/list" not in header_line
    assert "session/set_model" not in header_line
    assert "1.2.3" in md
    assert "loadSession, session/list" in md
    assert "## Method Probe Summary" in md
