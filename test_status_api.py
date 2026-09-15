import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

import status_monitor as monitor


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        saved = {name: getattr(monitor, name) for name in
                 ("STATE_DIR", "STATE_FILE", "LOCK_FILE", "EVENT_FILE",
                  "HOOK_TOKEN_FILE", "CONTROL_TOKEN_FILE", "probe")}
        self.addCleanup(lambda: [setattr(monitor, name, value) for name, value in saved.items()])
        folder = Path(self.temp.name)
        monitor.STATE_DIR = folder
        monitor.STATE_FILE = folder / "state.json"
        monitor.LOCK_FILE = folder / "state.lock"
        monitor.EVENT_FILE = folder / "events.jsonl"
        monitor.HOOK_TOKEN_FILE = str(folder / "hook-token")
        monitor.CONTROL_TOKEN_FILE = str(folder / "control-token")
        Path(monitor.HOOK_TOKEN_FILE).write_text("hook-test-token")
        Path(monitor.CONTROL_TOKEN_FILE).write_text("control-test-token")
        monitor.probe = lambda: {"healthy": True, "container": "abcdef1234567890",
                                 "reason": "running", "task": "task-a"}
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), monitor.StatusHandler)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def call(self, method, path, payload=None, token=None):
        data = json.dumps(payload).encode() if isinstance(payload, (dict, list)) else payload
        headers = {"Content-Type": "application/json"}
        if token == "hook":
            headers["X-Ragnavik-Token"] = "hook-test-token"
        if token == "control":
            headers["X-Ragnavik-Control"] = "control-test-token"
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        with urllib.request.urlopen(request, timeout=3) as response:
            return json.load(response) if response.status == 200 else None

    def test_control_endpoint_rejects_unauthorized_request(self):
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call("GET", "/state")
        self.assertEqual(error.exception.code, 403)

    def test_boss_report_requires_current_running_container(self):
        report = {"container": "abcdef123456", "keys": ["defeated_eikthyr"]}
        self.call("POST", "/bosses", report, "hook")
        self.assertEqual(self.call("GET", "/state", token="control")["boss_keys"],
                         ["defeated_eikthyr"])
        report["container"] = "deadbeef1234"
        with self.assertRaises(urllib.error.HTTPError) as error:
            self.call("POST", "/bosses", report, "hook")
        self.assertEqual(error.exception.code, 409)

    def test_maintenance_notice_queues_one_event_and_acknowledges(self):
        self.call("POST", "/maintenance/start", {"reason": "UI update", "hours": 1}, "control")
        item = self.call("GET", "/events", token="control")
        self.assertEqual(item["destination"], "channel")
        self.assertEqual(self.call("GET", "/state", token="control")["phase"], "maintenance")
        self.call("POST", "/ack", {"id": item["id"]}, "control")
        self.assertEqual(self.call("GET", "/events", token="control"), {})
        self.assertEqual(len(self.call("GET", "/recent", token="control")), 1)


if __name__ == "__main__":
    unittest.main()
