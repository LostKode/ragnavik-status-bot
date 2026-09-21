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

    def error(self, path, payload):
        try:
            self.call("POST", path, payload, "hook")
        except urllib.error.HTTPError as exc:
            return exc.code, json.load(exc)
        self.fail("expected an HTTP error")

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

    def test_progress_baselines_then_announces_named_player_and_boss_milestones(self):
        baseline = {
            "server": "Ragnavik",
            "instance": "abcdef123456",
            "bosses": [],
            "players": [{"id": "player-1", "name": "Ragnavik", "level": 9}],
            "milestoneStep": 10,
        }
        self.call("POST", "/progress", baseline, "hook")
        self.assertEqual(self.call("GET", "/events", token="control"), {})

        progress = dict(baseline)
        progress["bosses"] = ["defeated_eikthyr"]
        progress["players"] = [{"id": "player-1", "name": "Ragnavik", "level": 10}]
        self.call("POST", "/progress", progress, "hook")

        first = self.call("GET", "/events", token="control")
        self.assertEqual(first["destination"], "longhouse")
        self.assertIn("Eikthyr", first["message"])
        self.call("POST", "/ack", {"id": first["id"]}, "control")
        second = self.call("GET", "/events", token="control")
        self.assertEqual(second["destination"], "longhouse")
        self.assertEqual(second["message"], "Ragnavik reached EpicMMO level 10!")

    def test_progress_uses_current_ingame_name_without_repeating_milestone(self):
        baseline = {
            "server": "Ragnavik",
            "instance": "abcdef123456",
            "bosses": [],
            "players": [{"id": "player-1", "name": "Old Name", "level": 19}],
            "milestoneStep": 10,
        }
        self.call("POST", "/progress", baseline, "hook")
        baseline["players"] = [{"id": "player-1", "name": "New Name", "level": 20}]
        self.call("POST", "/progress", baseline, "hook")
        event = self.call("GET", "/events", token="control")
        self.assertEqual(event["message"], "New Name reached EpicMMO level 20!")
        self.call("POST", "/ack", {"id": event["id"]}, "control")
        self.call("POST", "/progress", baseline, "hook")
        self.assertEqual(self.call("GET", "/events", token="control"), {})

    def test_boss_kill_lists_killer_and_nearby_ingame_names_once(self):
        baseline = {
            "server": "Ragnavik",
            "instance": "abcdef123456",
            "bosses": [],
            "players": [],
            "bossKills": [],
            "milestoneStep": 10,
        }
        self.call("POST", "/progress", baseline, "hook")
        report = dict(baseline)
        report["bossKills"] = [{
            "id": "boss-zdo-1",
            "key": "defeated_eikthyr",
            "boss": "Eikthyr",
            "killer": "Ragnavik",
            "participants": ["Jamrican", "Ragnavik"],
        }]
        self.call("POST", "/progress", report, "hook")
        event = self.call("GET", "/events", token="control")
        self.assertEqual(event["destination"], "longhouse")
        self.assertEqual(event["message"],
                         "Ragnavik milestone: Eikthyr has been defeated! "
                         "Killing blow: Ragnavik. Party: Jamrican, Ragnavik.")
        self.call("POST", "/ack", {"id": event["id"]}, "control")
        self.call("POST", "/progress", report, "hook")
        self.assertEqual(self.call("GET", "/events", token="control"), {})

        # The later world-key update must not create a second generic boss post.
        report["bossKills"] = []
        report["bosses"] = ["defeated_eikthyr"]
        self.call("POST", "/progress", report, "hook")
        self.assertEqual(self.call("GET", "/events", token="control"), {})

    def test_maintenance_notice_queues_one_event_and_acknowledges(self):
        self.call("POST", "/maintenance/start", {"reason": "UI update", "hours": 1}, "control")
        item = self.call("GET", "/events", token="control")
        self.assertEqual(item["destination"], "announcements")
        self.assertEqual(self.call("GET", "/state", token="control")["phase"], "maintenance")
        self.call("POST", "/ack", {"id": item["id"]}, "control")
        self.assertEqual(self.call("GET", "/events", token="control"), {})
        self.assertEqual(len(self.call("GET", "/recent", token="control")), 1)


    def test_progress_validation_returns_safe_actionable_json(self):
        report = {"server": "Ragnavik", "instance": "abcdef123456", "bosses": [],
                  "players": [{"id": "player-1", "name": "", "level": 10}],
                  "bossKills": [], "milestoneStep": 10}
        status, body = self.error("/progress", report)
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "invalid_progress")
        self.assertIn("players", body["detail"])
        self.assertNotIn("hook-test-token", json.dumps(body))

    def test_progress_accepts_payload_larger_than_old_16k_limit(self):
        report = {"server": "Ragnavik", "instance": "abcdef123456", "bosses": [],
                  "players": [{"id": f"player-{index}", "name": "V" * 80, "level": 10}
                              for index in range(64)],
                  "bossKills": [{"id": f"kill-{kill}", "key": "", "boss": "Boss",
                                 "killer": "Viking", "participants": ["P" * 80] * 64}
                                for kill in range(20)],
                  "milestoneStep": 10}
        self.assertGreater(len(json.dumps(report).encode()), 16384)
        self.call("POST", "/progress", report, "hook")

    def test_progress_accepts_omitted_empty_arrays_from_unity_json(self):
        report = {"server": "Ragnavik", "instance": "abcdef123456", "bosses": [],
                  "milestoneStep": 10}
        self.call("POST", "/progress", report, "hook")

    def test_progress_counts_private_boss_keys_by_player_and_retains_offline_players(self):
        report = {"server": "Ragnavik", "instance": "abcdef123456", "bosses": [],
                  "players": [], "bossKills": [], "milestoneStep": 10,
                  "playerBosses": [
                      {"id": "player-1", "bosses": ["defeated_eikthyr", "defeated_frozenking"]},
                      {"id": "player-2", "bosses": ["defeated_eikthyr"]},
                  ]}
        self.call("POST", "/progress", report, "hook")
        counts = self.call("GET", "/state", token="control")["boss_player_counts"]
        self.assertEqual(counts, {"defeated_eikthyr": 2, "defeated_frozenking": 1})

        report["playerBosses"] = [{"id": "player-2", "bosses": []}]
        self.call("POST", "/progress", report, "hook")
        counts = self.call("GET", "/state", token="control")["boss_player_counts"]
        self.assertEqual(counts, {"defeated_eikthyr": 1, "defeated_frozenking": 1})




if __name__ == "__main__":
    unittest.main()
