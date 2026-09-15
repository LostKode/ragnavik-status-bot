import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

import status_monitor as monitor


@contextmanager
def _StateContext(state):
    yield state


class TransitionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        monitor.EVENT_FILE = Path(self.temp.name) / "events.jsonl"
        self.state = {"phase": "unknown", "pending": []}
        self.running = {"healthy": True, "reason": "running", "task": "task-a",
                        "container": "abcdef1234567890"}
        self.down = {"healthy": False, "reason": "Valheim host is down", "task": ""}

    def kinds(self):
        if not monitor.EVENT_FILE.exists():
            return []
        import json
        return [json.loads(line)["kind"] for line in monitor.EVENT_FILE.read_text().splitlines()]

    def test_initial_running_task_stays_quiet_until_ready_hook(self):
        monitor.reconcile(self.state, self.running, 1000)
        self.assertEqual(self.state["phase"], "unknown")
        self.assertEqual(self.kinds(), [])
        self.state["ready_container"] = "abcdef123456"
        monitor.reconcile(self.state, self.running, 1030)
        self.assertEqual(self.state["phase"], "live")
        self.assertEqual(self.kinds(), [])

    def test_unexpected_outage_alerts_once_and_recovery_posts_once(self):
        self.state["phase"] = "live"
        self.state["ready_container"] = "abcdef123456"
        monitor.reconcile(self.state, self.down, 1000)
        monitor.reconcile(self.state, self.down, 1000 + monitor.DOWN_GRACE - 1)
        self.assertEqual(self.kinds(), [])
        monitor.reconcile(self.state, self.down, 1000 + monitor.DOWN_GRACE)
        monitor.reconcile(self.state, self.down, 1000 + monitor.DOWN_GRACE + 60)
        self.assertEqual(self.kinds(), ["offline"])
        self.assertEqual([item["destination"] for item in self.state["pending"]],
                         ["channel", "dm"])
        monitor.reconcile(self.state, self.running, 1500)
        monitor.reconcile(self.state, self.running, 1530)
        self.assertEqual(self.kinds(), ["offline", "live"])

    def test_maintenance_waits_for_explicit_end_across_multiple_restarts(self):
        self.state["phase"] = "maintenance"
        self.state["ready_container"] = "abcdef123456"
        self.state["maintenance"] = {"reason": "UI update", "until": 2000,
                                     "finished": False}
        monitor.reconcile(self.state, self.running, 1000)
        self.assertEqual(self.state["phase"], "maintenance")
        self.assertEqual(self.kinds(), [])
        self.state.pop("ready_container")
        monitor.reconcile(self.state, self.down, 1010)
        self.state["ready_container"] = "abcdef123456"
        monitor.reconcile(self.state, self.running, 1030)
        self.assertEqual(self.state["phase"], "maintenance")
        self.assertEqual(self.kinds(), [])
        new_task = dict(self.running, container="123456abcdef7890")
        self.state.pop("ready_container")
        monitor.reconcile(self.state, self.down, 1040)
        self.state["ready_container"] = "123456abcdef"
        monitor.reconcile(self.state, new_task, 1060)
        self.assertEqual(self.state["phase"], "maintenance")
        self.assertEqual(self.kinds(), [])
        self.state["maintenance"]["finished"] = True
        monitor.reconcile(self.state, new_task, 1090)
        self.assertEqual(self.state["phase"], "live")
        self.assertEqual(self.kinds(), ["live"])

    def test_maintenance_expiry_with_server_still_live_posts_live(self):
        self.state["phase"] = "maintenance"
        self.state["ready_container"] = "abcdef123456"
        self.state["maintenance"] = {"reason": "UI update", "until": 2000,
                                     "finished": False}
        monitor.reconcile(self.state, self.running, 1900)
        self.assertEqual(self.kinds(), [])
        monitor.reconcile(self.state, self.running, 2000)
        self.assertEqual(self.kinds(), ["live"])
        self.assertEqual(self.state["phase"], "live")

    def test_maintenance_suppresses_alert_until_expiry(self):
        self.state["phase"] = "maintenance"
        self.state["maintenance"] = {"reason": "mod update", "until": 2000,
                                     "finished": False}
        monitor.reconcile(self.state, self.down, 1000)
        monitor.reconcile(self.state, self.down, 1900)
        self.assertEqual(self.kinds(), [])
        monitor.reconcile(self.state, self.down, 2000)
        monitor.reconcile(self.state, self.down, 2000 + monitor.DOWN_GRACE)
        self.assertEqual(self.kinds(), ["offline"])

    def test_internal_restart_has_longer_grace(self):
        self.state["phase"] = "live"
        self.state.pop("ready_container", None)
        monitor.reconcile(self.state, self.running, 1000)
        monitor.reconcile(self.state, self.running, 1000 + monitor.DOWN_GRACE)
        self.assertEqual(self.kinds(), [])
        monitor.reconcile(self.state, self.running, 1000 + monitor.RESTART_GRACE)
        self.assertEqual(self.kinds(), ["offline"])

    def test_verified_pre_update_backup_posts_once_during_maintenance(self):
        self.state["phase"] = "maintenance"
        self.state["maintenance"] = {"reason": "mod update", "until": 2000,
                                     "finished": False}
        saved = monitor.locked_state
        monitor.locked_state = lambda: _StateContext(self.state)
        self.addCleanup(lambda: setattr(monitor, "locked_state", saved))
        monitor.maintenance_backup_verified()
        self.assertEqual(self.kinds(), ["backup_verified"])
        self.assertEqual(self.state["pending"][0]["destination"], "logs")
        with self.assertRaisesRegex(RuntimeError, "already sent"):
            monitor.maintenance_backup_verified()

    def test_backup_notice_requires_maintenance(self):
        saved = monitor.locked_state
        monitor.locked_state = lambda: _StateContext(self.state)
        self.addCleanup(lambda: setattr(monitor, "locked_state", saved))
        with self.assertRaisesRegex(RuntimeError, "active maintenance"):
            monitor.maintenance_backup_verified()

    def test_old_ready_hook_does_not_mark_new_task_live(self):
        self.state["phase"] = "offline"
        self.state["ready_container"] = "abcdef123456"
        new_task = dict(self.running, container="123456abcdef7890")
        monitor.reconcile(self.state, new_task, 1000)
        self.assertEqual(self.state["phase"], "offline")
        self.state["ready_container"] = "123456abcdef"
        monitor.reconcile(self.state, new_task, 1030)
        self.assertEqual(self.state["phase"], "live")
        self.assertEqual(self.kinds(), ["live"])


if __name__ == "__main__":
    unittest.main()
