"""Integration checks for the dashboard's loopback control boundary."""

from __future__ import annotations

import http.client
import importlib.util
import json
import math
import sys
import threading
import types
import unittest
from pathlib import Path


WEB_ROOT = Path(__file__).resolve().parents[1]


class _Manager:
    def __init__(self, *_args):
        self.stop_calls = 0
        self.non_finite_snapshot = False

    def snapshot(self):
        if self.non_finite_snapshot:
            return {"value": math.nan}
        return {"state": "idle"}

    def list_sessions(self):
        return {"sessions": []}

    def start(self, payload):
        return {"state": "running", "config": payload}

    def stop(self):
        self.stop_calls += 1
        return {"state": "idle"}

    def shutdown(self):
        self.stop_calls += 1


class _PhysicsRegistry:
    def __init__(self, *_args):
        pass

    def snapshot(self):
        return {"state": "ready"}


class _Plan:
    def as_payload(self):
        return {"primitive": "stand"}


class _Planner:
    def plan(self, _prompt):
        return _Plan()


class _Retarget:
    def __init__(self, *_args):
        pass

    def snapshot(self):
        return {"decodedG1PoseReady": True}

    def retarget(self, payload):
        chunk = payload.get("source", {}).get("motionTokenChunk", [])
        return {"state": "retargeted", "receivedFrames": len(chunk)}


def _load_server_module():
    rl_service = types.ModuleType("rl_service")
    rl_service.RLTrainingManager = _Manager
    physics_service = types.ModuleType("physics_service")
    physics_service.PhysicsRuntimeRegistry = _PhysicsRegistry
    gr00t_service = types.ModuleType("gr00t_service")
    gr00t_service.DropbearPromptPlanner = _Planner
    gr00t_service.Gr00tRetargetService = _Retarget
    gr00t_service.Gr00tRuntimeInspector = _Manager
    gr00t_service.Gr00tTrainingManager = _Manager
    stubs = {
        "rl_service": rl_service,
        "physics_service": physics_service,
        "gr00t_service": gr00t_service,
    }
    previous = {name: sys.modules.get(name) for name in stubs}
    sys.modules.update(stubs)
    inserted_web_root = str(WEB_ROOT) not in sys.path
    if inserted_web_root:
        sys.path.insert(0, str(WEB_ROOT))
    try:
        spec = importlib.util.spec_from_file_location(
            "dropbear_test_server",
            WEB_ROOT / "serve.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if inserted_web_root:
            sys.path.remove(str(WEB_ROOT))
        for name, original in previous.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


SERVER = _load_server_module()


class DashboardControlBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = SERVER.ThreadingHTTPServer(
            ("127.0.0.1", 0),
            SERVER.Handler,
        )
        cls.port = cls.server.server_port
        cls.host = f"127.0.0.1:{cls.port}"
        cls.origin = f"http://{cls.host}"
        cls.thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.port,
            timeout=2,
        )
        request_headers = {"Host": self.host, **(headers or {})}
        connection.request(method, path, body=body, headers=request_headers)
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, json.loads(raw)

    def control_headers(self, **overrides):
        return {
            "Content-Type": "application/json",
            "Origin": self.origin,
            "X-Dropbear-Control-Token": SERVER.CONTROL_TOKEN,
            **overrides,
        }

    def test_token_is_issued_only_to_loopback_host(self):
        status, payload = self.request("GET", "/api/control-token")
        self.assertEqual(status, 200)
        self.assertEqual(payload["token"], SERVER.CONTROL_TOKEN)

        status, _payload = self.request(
            "GET",
            "/api/control-token",
            headers={"Host": f"attacker.invalid:{self.port}"},
        )
        self.assertEqual(status, 403)

    def test_post_requires_token_json_and_same_origin(self):
        status, _payload = self.request(
            "POST",
            "/api/rl/stop",
            body="{}",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 403)

        status, _payload = self.request(
            "POST",
            "/api/rl/stop",
            body="{}",
            headers=self.control_headers(
                Host=f"attacker.invalid:{self.port}",
            ),
        )
        self.assertEqual(status, 403)

        status, _payload = self.request(
            "POST",
            "/api/rl/stop",
            body="{}",
            headers=self.control_headers(
                Origin=f"http://attacker.invalid:{self.port}",
            ),
        )
        self.assertEqual(status, 403)

        status, _payload = self.request(
            "POST",
            "/api/rl/stop",
            body="{}",
            headers=self.control_headers(
                Referer=f"http://attacker.invalid:{self.port}/control",
            ),
        )
        self.assertEqual(status, 403)

        headers = self.control_headers()
        headers["Content-Type"] = "text/plain"
        status, _payload = self.request(
            "POST",
            "/api/rl/stop",
            body="{}",
            headers=headers,
        )
        self.assertEqual(status, 415)

        status, payload = self.request(
            "POST",
            "/api/rl/stop",
            body="{}",
            headers=self.control_headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["state"], "idle")

        status, _payload = self.request(
            "POST",
            "/api/not-an-endpoint",
            body="{}",
            headers={
                **self.control_headers(),
                "Content-Type": "text/plain",
            },
        )
        self.assertEqual(status, 415)

    def test_non_finite_and_non_object_json_are_rejected(self):
        for body in ("{\"value\":NaN}", "{\"value\":1e999}", "[]"):
            with self.subTest(body=body):
                status, _payload = self.request(
                    "POST",
                    "/api/rl/train",
                    body=body,
                    headers=self.control_headers(),
                )
                self.assertEqual(status, 400)

    def test_non_finite_responses_fail_closed_as_valid_json(self):
        SERVER.RL_MANAGER.non_finite_snapshot = True
        try:
            status, payload = self.request("GET", "/api/rl/status")
        finally:
            SERVER.RL_MANAGER.non_finite_snapshot = False
        self.assertEqual(status, 500)
        self.assertEqual(payload["error"], "response is not finite JSON")

    def test_hardware_observation_endpoint_is_explicitly_receive_only(self):
        status, payload = self.request("GET", "/api/hardware/observation")
        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "read_only_with_diagnostic_queries")
        self.assertFalse(payload["writeCapable"])
        self.assertFalse(payload["motionWriteCapable"])
        self.assertEqual(payload["txBytes"], 0)
        self.assertFalse(payload["complete"])

    def test_three_stage_http_gate_cannot_reach_physical_transport(self):
        SERVER.HARDWARE_CONTROL_GATE.revoke()
        try:
            status, first = self.request(
                "POST",
                "/api/hardware/control/advance",
                body=json.dumps({"stage": 1}),
                headers=self.control_headers(),
            )
            self.assertEqual(status, 200)
            self.assertEqual(first["stage"], 1)

            _status, gate_status = self.request(
                "GET", "/api/hardware/control/status"
            )
            acknowledgements = {
                key: True
                for key in gate_status["requiredAcknowledgements"]
            }
            status, second = self.request(
                "POST",
                "/api/hardware/control/advance",
                body=json.dumps({
                    "stage": 2,
                    "challenge": first["challenge"],
                    "acknowledgements": acknowledgements,
                }),
                headers=self.control_headers(),
            )
            self.assertEqual(status, 200)
            self.assertEqual(second["stage"], 2)

            status, third = self.request(
                "POST",
                "/api/hardware/control/advance",
                body=json.dumps({
                    "stage": 3,
                    "challenge": second["challenge"],
                    "confirm": True,
                }),
                headers=self.control_headers(),
            )
            self.assertEqual(status, 200)
            self.assertTrue(third["frontendArmed"])
            self.assertFalse(third["hardwareOutputEnabled"])

            status, disposition = self.request(
                "POST",
                "/api/hardware/command",
                body=json.dumps({
                    "schema": "dropbear-hardware-command-v1",
                    "leaseToken": third["leaseToken"],
                    "jointName": "left_knee",
                    "mode": "joint_position",
                    "valueSi": 0.1,
                }),
                headers=self.control_headers(),
            )
            self.assertEqual(status, 423)
            self.assertFalse(disposition["accepted"])
            self.assertEqual(
                disposition["disposition"],
                "PHYSICAL_TRANSPORT_LOCKED",
            )
        finally:
            SERVER.HARDWARE_CONTROL_GATE.revoke()

    def test_missing_hardware_acknowledgement_resets_http_gate(self):
        SERVER.HARDWARE_CONTROL_GATE.revoke()
        try:
            _status, first = self.request(
                "POST",
                "/api/hardware/control/advance",
                body=json.dumps({"stage": 1}),
                headers=self.control_headers(),
            )
            _status, gate_status = self.request(
                "GET", "/api/hardware/control/status"
            )
            acknowledgements = {
                key: True
                for key in gate_status["requiredAcknowledgements"]
            }
            acknowledgements["area_clear"] = False
            status, payload = self.request(
                "POST",
                "/api/hardware/control/advance",
                body=json.dumps({
                    "stage": 2,
                    "challenge": first["challenge"],
                    "acknowledgements": acknowledgements,
                }),
                headers=self.control_headers(),
            )
            self.assertEqual(status, 400)
            self.assertIn("every safety consideration", payload["error"])
            status, gate = self.request("GET", "/api/hardware/control/status")
            self.assertEqual(status, 200)
            self.assertEqual(gate["stage"], 0)
        finally:
            SERVER.HARDWARE_CONTROL_GATE.revoke()

    def test_full_precision_40_by_64_token_horizon_fits_bounded_json(self):
        frame = [
            ((index % 17) - 8) * 0.123456789012345
            for index in range(64)
        ]
        request_payload = {
            "schema": "dropbear-gr00t-retarget-request-v1",
            "sessionId": "http-envelope-regression",
            "sequence": 0,
            "source": {
                "kind": "nvidia-sonic-motion-token-chunk",
                "schema": "nvidia-gr00t-sonic-motion-token-chunk-40x64-v1",
                "motionTokenChunk": [frame for _ in range(40)],
                "producer": "isaac-gr00t-policy-server",
                "checkpoint": "sha256:test-only",
                "sequenceStart": 0,
            },
        }
        body = json.dumps(request_payload, separators=(",", ":"))
        self.assertGreater(len(body), 32_768)
        self.assertLess(len(body), SERVER.MAX_JSON_BODY_BYTES)
        status, payload = self.request(
            "POST",
            "/api/gr00t/retarget",
            body=body,
            headers=self.control_headers(),
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["receivedFrames"], 40)

    def test_loopback_detection_includes_ipv4_mapped_ipv6(self):
        self.assertTrue(SERVER._is_loopback_address("127.0.0.1"))
        self.assertTrue(SERVER._is_loopback_address("::1"))
        self.assertTrue(
            SERVER._is_loopback_address("::ffff:127.0.0.1")
        )
        self.assertFalse(SERVER._is_loopback_address("192.0.2.10"))

    def test_manager_shutdown_stops_both_training_services(self):
        rl_before = SERVER.RL_MANAGER.stop_calls
        gr00t_before = SERVER.GR00T_TRAINING.stop_calls
        SERVER._shutdown_managers()
        self.assertEqual(SERVER.RL_MANAGER.stop_calls, rl_before + 1)
        self.assertEqual(
            SERVER.GR00T_TRAINING.stop_calls,
            gr00t_before + 1,
        )


if __name__ == "__main__":
    unittest.main()
