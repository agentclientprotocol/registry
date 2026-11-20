"""Focused standard-library tests for capability-aware session closing."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from protocol_matrix import (
    METHOD_PROBES,
    PROBE_SCHEMA_VERSION,
    ProbeOutcome,
    build_snapshot,
    classify_rpc_response,
    close_capability_advertised,
    feature_cell,
    main,
    probe_agent,
    probe_indicates_support,
    render_markdown,
    reuse_previous_record,
    run_method_probes,
    snapshot_schema_is_current,
    summarize_results,
)


def make_record(close_status: str = "not_applicable") -> dict:
    """Build one schema-v2 result row for rendering and summary tests."""
    return {
        "id": "agent-1",
        "name": "Agent One",
        "registryVersion": "1.2.3",
        "repository": None,
        "website": None,
        "distribution": "npx",
        "initialize": {"status": "success", "code": None, "message": None},
        "protocolVersion": 1,
        "agentInfoVersion": "1.2.3",
        "authMethods": ["agent"],
        "setModelSignal": False,
        "capabilities": {
            "loadSession": True,
            "sessionList": True,
            "sessionFork": False,
            "sessionResume": False,
            "sessionClose": close_status != "not_applicable",
            "setModel": False,
        },
        "sessionNew": {"status": "success", "code": None, "message": None},
        "methodProbes": {
            "session/list": {"status": "success", "code": None, "message": None},
            "session/fork": {
                "status": "method_not_found",
                "code": -32601,
                "message": "Method not found",
            },
            "session/resume": {
                "status": "method_not_found",
                "code": -32601,
                "message": "Method not found",
            },
            "session/set_model": {
                "status": "invalid_params",
                "code": -32602,
                "message": "Unknown model",
            },
            "session/close": {"status": close_status, "code": None, "message": None},
        },
        "stderrTail": None,
        "commandPreview": "npx agent",
        "workspaceCwd": "/tmp/workspace",
        "durationSeconds": 0.1,
        "processExitCode": 0,
        "probedAt": "2026-08-12T06:00:00+00:00",
        "reusedFromPrevious": False,
    }


class CloseCapabilityTests(unittest.TestCase):
    def test_only_present_objects_advertise_close(self):
        self.assertTrue(close_capability_advertised({"close": {}}))
        self.assertTrue(close_capability_advertised({"close": {"_meta": None}}))
        self.assertTrue(close_capability_advertised({"close": {"_meta": {"vendor": "example"}}}))
        for capabilities in (
            {},
            {"close": None},
            {"close": True},
            {"close": "yes"},
            {"close": {"_meta": "invalid"}},
        ):
            with self.subTest(capabilities=capabilities):
                self.assertFalse(close_capability_advertised(capabilities))

    def test_advertised_close_runs_once_last_with_created_session_id(self):
        calls = []

        def request(request_id, method, params, timeout):
            calls.append((request_id, method, params, timeout))
            result = {"_meta": {"trace": "ok"}} if method == "session/close" else {}
            return ProbeOutcome(status="success"), {"result": result}

        next_id, outcomes, exposes_models = run_method_probes(
            request=request,
            request_id=10,
            probe_session_id="legacy-fallback",
            close_session_id="created-session",
            cwd="/tmp/workspace",
            timeout=2.5,
            close_advertised=True,
        )

        self.assertEqual([method for _, method, _, _ in calls], list(METHOD_PROBES))
        self.assertEqual(calls[-1][1], "session/close")
        self.assertEqual(calls[-1][2], {"sessionId": "created-session"})
        self.assertEqual(sum(method == "session/close" for _, method, _, _ in calls), 1)
        self.assertEqual(outcomes["session/close"].status, "success")
        self.assertEqual(next_id, 15)
        self.assertFalse(exposes_models)

    def test_probe_agent_wires_capability_and_created_session_id_to_close(self):
        calls = []

        def request_with_timeout(proc, request_id, method, params, timeout):
            calls.append((request_id, method, params, timeout))
            if method == "initialize":
                return ProbeOutcome(status="success"), {
                    "result": {
                        "protocolVersion": 1,
                        "agentCapabilities": {
                            "sessionCapabilities": {"close": {"_meta": {"source": "test"}}}
                        },
                    }
                }
            if method == "session/new":
                return ProbeOutcome(status="success"), {"result": {"sessionId": "created-session"}}
            return ProbeOutcome(status="success"), {"result": {}}

        fake_process = SimpleNamespace(returncode=0)
        agent = {
            "id": "agent-1",
            "name": "Agent One",
            "version": "1.2.3",
            "distribution": {"npx": {"package": "agent-one"}},
        }

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("protocol_matrix.ensure_distribution_runtime", return_value=None),
            patch(
                "protocol_matrix.build_agent_command",
                return_value=(["fake-agent"], None, {}),
            ),
            patch("protocol_matrix.build_agent_process_env", return_value={}),
            patch("protocol_matrix.subprocess.Popen", return_value=fake_process),
            patch(
                "protocol_matrix.request_with_timeout",
                side_effect=request_with_timeout,
            ),
            patch("protocol_matrix.stop_process"),
            patch("protocol_matrix.collect_stderr_tail", return_value=None),
        ):
            record = probe_agent(
                agent=agent,
                sandbox_base=Path(temp_dir),
                init_timeout=5.0,
                rpc_timeout=1.0,
            )

        self.assertTrue(record["capabilities"]["sessionClose"])
        self.assertEqual(record["methodProbes"]["session/close"]["status"], "success")
        self.assertEqual(calls[-1][1], "session/close")
        self.assertEqual(calls[-1][2], {"sessionId": "created-session"})
        self.assertNotEqual(calls[-1][2]["sessionId"], "sess_matrix_probe")

    def test_probe_agent_does_not_close_when_session_creation_fails(self):
        agent = {
            "id": "agent-1",
            "name": "Agent One",
            "version": "1.2.3",
            "distribution": {"npx": {"package": "agent-one"}},
        }

        for session_new_status in ("error", "auth_required"):
            with self.subTest(session_new_status=session_new_status):
                calls = []

                def request_with_timeout(
                    proc,
                    request_id,
                    method,
                    params,
                    timeout,
                    *,
                    calls=calls,
                    session_new_status=session_new_status,
                ):
                    calls.append((request_id, method, params, timeout))
                    if method == "initialize":
                        return ProbeOutcome(status="success"), {
                            "result": {
                                "protocolVersion": 1,
                                "agentCapabilities": {"sessionCapabilities": {"close": {}}},
                            }
                        }
                    if method == "session/new":
                        return ProbeOutcome(status=session_new_status), None
                    return ProbeOutcome(status="success"), {"result": {}}

                fake_process = SimpleNamespace(returncode=0)
                with (
                    tempfile.TemporaryDirectory() as temp_dir,
                    patch("protocol_matrix.ensure_distribution_runtime", return_value=None),
                    patch(
                        "protocol_matrix.build_agent_command",
                        return_value=(["fake-agent"], None, {}),
                    ),
                    patch("protocol_matrix.build_agent_process_env", return_value={}),
                    patch("protocol_matrix.subprocess.Popen", return_value=fake_process),
                    patch(
                        "protocol_matrix.request_with_timeout",
                        side_effect=request_with_timeout,
                    ),
                    patch("protocol_matrix.stop_process"),
                    patch("protocol_matrix.collect_stderr_tail", return_value=None),
                ):
                    record = probe_agent(
                        agent=agent,
                        sandbox_base=Path(temp_dir),
                        init_timeout=5.0,
                        rpc_timeout=1.0,
                    )

                methods = [method for _, method, _, _ in calls]
                self.assertNotIn("session/close", methods)
                self.assertEqual(record["sessionNew"]["status"], session_new_status)
                self.assertEqual(
                    record["methodProbes"]["session/close"]["status"],
                    "not_probed",
                )

    def test_probe_agent_does_not_close_without_a_valid_session_id(self):
        agent = {
            "id": "agent-1",
            "name": "Agent One",
            "version": "1.2.3",
            "distribution": {"npx": {"package": "agent-one"}},
        }

        for session_result in ({}, {"sessionId": ""}, {"sessionId": 42}):
            with self.subTest(session_result=session_result):
                calls = []

                def request_with_timeout(
                    proc,
                    request_id,
                    method,
                    params,
                    timeout,
                    *,
                    calls=calls,
                    session_result=session_result,
                ):
                    calls.append((request_id, method, params, timeout))
                    if method == "initialize":
                        return ProbeOutcome(status="success"), {
                            "result": {
                                "protocolVersion": 1,
                                "agentCapabilities": {"sessionCapabilities": {"close": {}}},
                            }
                        }
                    if method == "session/new":
                        return ProbeOutcome(status="success"), {"result": session_result}
                    return ProbeOutcome(status="success"), {"result": {}}

                fake_process = SimpleNamespace(returncode=0)
                with (
                    tempfile.TemporaryDirectory() as temp_dir,
                    patch("protocol_matrix.ensure_distribution_runtime", return_value=None),
                    patch(
                        "protocol_matrix.build_agent_command",
                        return_value=(["fake-agent"], None, {}),
                    ),
                    patch("protocol_matrix.build_agent_process_env", return_value={}),
                    patch("protocol_matrix.subprocess.Popen", return_value=fake_process),
                    patch(
                        "protocol_matrix.request_with_timeout",
                        side_effect=request_with_timeout,
                    ),
                    patch("protocol_matrix.stop_process"),
                    patch("protocol_matrix.collect_stderr_tail", return_value=None),
                ):
                    record = probe_agent(
                        agent=agent,
                        sandbox_base=Path(temp_dir),
                        init_timeout=5.0,
                        rpc_timeout=1.0,
                    )

                methods = [method for _, method, _, _ in calls]
                self.assertNotIn("session/close", methods)
                self.assertEqual(record["sessionNew"]["status"], "success")
                self.assertEqual(
                    record["methodProbes"]["session/close"]["status"],
                    "not_probed",
                )

    def test_probe_agent_does_not_close_after_ambiguous_session_new_response(self):
        calls = []

        def request_with_timeout(proc, request_id, method, params, timeout):
            calls.append((request_id, method, params, timeout))
            if method == "initialize":
                return ProbeOutcome(status="success"), {
                    "result": {
                        "protocolVersion": 1,
                        "agentCapabilities": {"sessionCapabilities": {"close": {}}},
                    }
                }
            if method == "session/new":
                message = {
                    "result": {"sessionId": "ambiguous-session"},
                    "error": {"code": -32602, "message": "Invalid params"},
                }
                return classify_rpc_response(message), message
            return ProbeOutcome(status="success"), {"result": {}}

        fake_process = SimpleNamespace(returncode=0)
        agent = {
            "id": "agent-1",
            "name": "Agent One",
            "version": "1.2.3",
            "distribution": {"npx": {"package": "agent-one"}},
        }

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("protocol_matrix.ensure_distribution_runtime", return_value=None),
            patch(
                "protocol_matrix.build_agent_command",
                return_value=(["fake-agent"], None, {}),
            ),
            patch("protocol_matrix.build_agent_process_env", return_value={}),
            patch("protocol_matrix.subprocess.Popen", return_value=fake_process),
            patch(
                "protocol_matrix.request_with_timeout",
                side_effect=request_with_timeout,
            ),
            patch("protocol_matrix.stop_process"),
            patch("protocol_matrix.collect_stderr_tail", return_value=None),
        ):
            record = probe_agent(
                agent=agent,
                sandbox_base=Path(temp_dir),
                init_timeout=5.0,
                rpc_timeout=1.0,
            )

        methods = [method for _, method, _, _ in calls]
        self.assertNotIn("session/close", methods)
        self.assertEqual(record["sessionNew"]["status"], "invalid_response")
        self.assertEqual(
            record["methodProbes"]["session/close"]["status"],
            "not_probed",
        )

    def test_probe_agent_does_not_close_when_capability_is_omitted_or_null(self):
        agent = {
            "id": "agent-1",
            "name": "Agent One",
            "version": "1.2.3",
            "distribution": {"npx": {"package": "agent-one"}},
        }

        for session_capabilities in ({}, {"close": None}):
            with self.subTest(session_capabilities=session_capabilities):
                calls = []

                def request_with_timeout(
                    proc,
                    request_id,
                    method,
                    params,
                    timeout,
                    *,
                    calls=calls,
                    session_capabilities=session_capabilities,
                ):
                    calls.append((request_id, method, params, timeout))
                    if method == "initialize":
                        return ProbeOutcome(status="success"), {
                            "result": {
                                "protocolVersion": 1,
                                "agentCapabilities": {"sessionCapabilities": session_capabilities},
                            }
                        }
                    if method == "session/new":
                        return ProbeOutcome(status="success"), {
                            "result": {"sessionId": "created-session"}
                        }
                    return ProbeOutcome(status="success"), {"result": {}}

                fake_process = SimpleNamespace(returncode=0)
                with (
                    tempfile.TemporaryDirectory() as temp_dir,
                    patch("protocol_matrix.ensure_distribution_runtime", return_value=None),
                    patch(
                        "protocol_matrix.build_agent_command",
                        return_value=(["fake-agent"], None, {}),
                    ),
                    patch("protocol_matrix.build_agent_process_env", return_value={}),
                    patch("protocol_matrix.subprocess.Popen", return_value=fake_process),
                    patch(
                        "protocol_matrix.request_with_timeout",
                        side_effect=request_with_timeout,
                    ),
                    patch("protocol_matrix.stop_process"),
                    patch("protocol_matrix.collect_stderr_tail", return_value=None),
                ):
                    record = probe_agent(
                        agent=agent,
                        sandbox_base=Path(temp_dir),
                        init_timeout=5.0,
                        rpc_timeout=1.0,
                    )

                self.assertNotIn("session/close", [method for _, method, _, _ in calls])
                self.assertFalse(record["capabilities"]["sessionClose"])
                self.assertEqual(
                    record["methodProbes"]["session/close"]["status"],
                    "not_applicable",
                )

    def test_unadvertised_close_is_not_applicable_and_makes_no_call(self):
        calls = []

        def request(request_id, method, params, timeout):
            calls.append((request_id, method, params, timeout))
            return ProbeOutcome(status="success"), {"result": {}}

        next_id, outcomes, _ = run_method_probes(
            request=request,
            request_id=20,
            probe_session_id="legacy-fallback",
            close_session_id="created-session",
            cwd="/tmp/workspace",
            timeout=1.0,
            close_advertised=False,
        )

        self.assertNotIn("session/close", [method for _, method, _, _ in calls])
        self.assertEqual(outcomes["session/close"].status, "not_applicable")
        self.assertEqual(next_id, 24)

    def test_advertised_close_without_active_session_is_not_probed(self):
        calls = []

        def request(request_id, method, params, timeout):
            calls.append((request_id, method, params, timeout))
            return ProbeOutcome(status="success"), {"result": {}}

        next_id, outcomes, _ = run_method_probes(
            request=request,
            request_id=30,
            probe_session_id="legacy-fallback",
            close_session_id=None,
            cwd="/tmp/workspace",
            timeout=1.0,
            close_advertised=True,
        )

        self.assertNotIn("session/close", [method for _, method, _, _ in calls])
        self.assertEqual(outcomes["session/close"].status, "not_probed")
        self.assertIn("No active session", outcomes["session/close"].message or "")
        self.assertEqual(next_id, 34)

    def test_close_error_remains_visible_and_does_not_count_as_support(self):
        for status, code, message, expected_cell in (
            ("invalid_params", -32602, "Invalid params", "Y/params"),
            ("resource_not_found", -32002, "Session not found", "Y/missing"),
        ):
            with self.subTest(status=status):

                def request(
                    request_id,
                    method,
                    params,
                    timeout,
                    *,
                    status=status,
                    code=code,
                    message=message,
                ):
                    if method == "session/close":
                        return (
                            ProbeOutcome(status=status, code=code, message=message),
                            {"error": {"code": code, "message": message}},
                        )
                    return ProbeOutcome(status="success"), {"result": {}}

                _, outcomes, _ = run_method_probes(
                    request=request,
                    request_id=40,
                    probe_session_id="legacy-fallback",
                    close_session_id="created-session",
                    cwd="/tmp/workspace",
                    timeout=1.0,
                    close_advertised=True,
                )

                close_outcome = outcomes["session/close"]
                self.assertEqual(close_outcome.status, status)
                self.assertEqual(close_outcome.code, code)
                self.assertEqual(close_outcome.message, message)
                self.assertFalse(probe_indicates_support("session/close", close_outcome.status))
                self.assertTrue(probe_indicates_support("session/list", status))
                self.assertEqual(
                    feature_cell(True, close_outcome, method="session/close"),
                    expected_cell,
                )

                record = make_record(close_status=status)
                record["methodProbes"]["session/close"] = {
                    "status": status,
                    "code": code,
                    "message": message,
                }
                close_summary = summarize_results([record])["features"]["session/close"]
                self.assertEqual(close_summary["supported"], 0)
                self.assertEqual(close_summary["other"], 1)

    def test_close_success_requires_an_object_response(self):
        def request(request_id, method, params, timeout):
            result = None if method == "session/close" else {}
            return ProbeOutcome(status="success"), {"result": result}

        _, outcomes, _ = run_method_probes(
            request=request,
            request_id=50,
            probe_session_id="legacy-fallback",
            close_session_id="created-session",
            cwd="/tmp/workspace",
            timeout=1.0,
            close_advertised=True,
        )

        self.assertEqual(outcomes["session/close"].status, "invalid_response")

    def test_close_success_rejects_invalid_meta(self):
        def request(request_id, method, params, timeout):
            result = {"_meta": "invalid"} if method == "session/close" else {}
            return ProbeOutcome(status="success"), {"result": result}

        _, outcomes, _ = run_method_probes(
            request=request,
            request_id=60,
            probe_session_id="legacy-fallback",
            close_session_id="created-session",
            cwd="/tmp/workspace",
            timeout=1.0,
            close_advertised=True,
        )

        self.assertEqual(outcomes["session/close"].status, "invalid_response")

    def test_close_response_rejects_result_and_error(self):
        def request(request_id, method, params, timeout):
            if method == "session/close":
                return ProbeOutcome(status="success"), {
                    "result": {},
                    "error": {"code": -32602, "message": "Invalid params"},
                }
            return ProbeOutcome(status="success"), {"result": {}}

        _, outcomes, _ = run_method_probes(
            request=request,
            request_id=70,
            probe_session_id="legacy-fallback",
            close_session_id="created-session",
            cwd="/tmp/workspace",
            timeout=1.0,
            close_advertised=True,
        )

        close_outcome = outcomes["session/close"]
        self.assertEqual(close_outcome.status, "invalid_response")
        self.assertIn("exactly one", close_outcome.message or "")
        self.assertFalse(probe_indicates_support("session/close", close_outcome.status))


class ProbeSchemaTests(unittest.TestCase):
    def test_only_schema_2_snapshot_is_reusable(self):
        self.assertTrue(snapshot_schema_is_current({"probeSchemaVersion": 2, "agents": []}))
        for snapshot in (
            None,
            {"agents": []},
            {"probeSchemaVersion": 1, "agents": []},
            {"probeSchemaVersion": 3, "agents": []},
            {"probeSchemaVersion": 2.0, "agents": []},
            {"probeSchemaVersion": "2", "agents": []},
        ):
            with self.subTest(snapshot=snapshot):
                self.assertFalse(snapshot_schema_is_current(snapshot))

    def test_snapshot_and_markdown_emit_close_schema_without_stop_keys(self):
        records = [make_record()]
        summary = summarize_results(records)
        snapshot = build_snapshot(
            records=records,
            summary=summary,
            date_str="2026-08-12",
            generated_at="2026-08-12T06:00:00+00:00",
            table_mode="full",
            changed_only=True,
        )
        markdown = render_markdown(
            records,
            summary,
            "2026-08-12",
            "2026-08-12T06:00:00+00:00",
        )
        serialized = json.dumps(snapshot)

        self.assertEqual(snapshot["probeSchemaVersion"], PROBE_SCHEMA_VERSION)
        self.assertIn('"sessionClose"', serialized)
        self.assertIn('"session/close"', serialized)
        self.assertNotIn("sessionStop", serialized)
        self.assertNotIn("session/stop", serialized)
        self.assertIn("Probe schema version: **2**", markdown)
        self.assertIn("session/close", markdown)
        self.assertNotIn("session/stop", markdown)

    def test_summary_distinguishes_not_applicable_and_not_probed(self):
        not_applicable = make_record(close_status="not_applicable")
        not_probed = make_record(close_status="not_probed")
        summary = summarize_results([not_applicable, not_probed])
        close_summary = summary["features"]["session/close"]

        self.assertEqual(close_summary["supported"], 0)
        self.assertEqual(close_summary["notApplicable"], 1)
        self.assertEqual(close_summary["notProbed"], 1)

    def test_reuse_deep_copies_previous_schema_2_record(self):
        previous = make_record(close_status="success")
        original_name = previous["name"]
        reused = reuse_previous_record(
            {
                "id": "agent-1",
                "name": "Renamed Agent",
                "version": "1.2.3",
                "repository": "https://example.com/repository",
                "website": None,
            },
            previous,
            "npx",
            "2026-08-11T06:00:00+00:00",
        )

        self.assertEqual(previous["name"], original_name)
        self.assertFalse(previous["reusedFromPrevious"])
        self.assertEqual(reused["name"], "Renamed Agent")
        self.assertTrue(reused["reusedFromPrevious"])

    def test_main_reuses_only_schema_2_rows(self):
        agent = {
            "id": "agent-1",
            "name": "Agent One",
            "version": "1.2.3",
            "repository": None,
            "website": None,
            "distribution": {"npx": {"package": "agent-one"}},
        }

        for schema_version, should_reuse in (
            (2, True),
            (None, False),
            (1, False),
            (3, False),
        ):
            with (
                self.subTest(schema_version=schema_version),
                tempfile.TemporaryDirectory() as temp_dir,
            ):
                output_dir = Path(temp_dir) / "matrix"
                output_dir.mkdir()
                previous_snapshot = {
                    "generatedAt": "2026-08-11T06:00:00+00:00",
                    "agents": [make_record(close_status="success")],
                }
                if schema_version is not None:
                    previous_snapshot["probeSchemaVersion"] = schema_version
                (output_dir / "latest.json").write_text(
                    json.dumps(previous_snapshot), encoding="utf-8"
                )

                args = SimpleNamespace(
                    agent=None,
                    skip_agent=None,
                    max_agents=0,
                    init_timeout=5.0,
                    rpc_timeout=1.0,
                    sandbox_dir=str(Path(temp_dir) / "sandbox"),
                    output_dir=str(output_dir),
                    table_mode="full",
                    changed_only=True,
                    date="2026-08-12",
                )
                fresh_record = make_record(close_status="success")
                with (
                    patch("protocol_matrix.parse_args", return_value=args),
                    patch("protocol_matrix.load_registry", return_value=[agent]),
                    patch(
                        "protocol_matrix.probe_agent",
                        return_value=fresh_record,
                    ) as probe,
                ):
                    self.assertEqual(main(), 0)

                written = json.loads((output_dir / "latest.json").read_text())
                self.assertEqual(written["probeSchemaVersion"], 2)
                self.assertEqual(written["agents"][0]["reusedFromPrevious"], should_reuse)
                self.assertEqual(probe.call_count, 0 if should_reuse else 1)


if __name__ == "__main__":
    unittest.main()
