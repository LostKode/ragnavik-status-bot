import json
from pathlib import Path
import tempfile
import unittest

import status_monitor as monitor


class ClientPackReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        folder = Path(self.temp.name)
        saved = {name: getattr(monitor, name) for name in
                 ("STATE_DIR", "STATE_FILE", "LOCK_FILE", "EVENT_FILE", "public_json")}
        self.addCleanup(lambda: [setattr(monitor, name, value) for name, value in saved.items()])
        monitor.STATE_DIR = folder
        monitor.STATE_FILE = folder / "state.json"
        monitor.LOCK_FILE = folder / "state.lock"
        monitor.EVENT_FILE = folder / "events.jsonl"
        self.version = "1.1.20"
        self.title = "Mod compatibility updates"
        self.changes = ["Updated Epic Loot.", "Updated server dependencies."]
        self.calls = []

        def fake_public_json(url):
            self.calls.append(url)
            return {"schemaVersion": 1, "updatedAt": "2026-09-20T00:00:00Z",
                    "entries": [{"version": self.version, "publishedAt": "2026-09-19",
                                 "title": self.title, "changes": self.changes}]}

        monitor.public_json = fake_public_json

    def state(self):
        return json.loads(monitor.STATE_FILE.read_text())

    def test_existing_release_is_baseline_and_not_announced(self):
        monitor.check_client_pack()
        monitor.check_client_pack()
        self.assertEqual(self.state()["client_pack_version"], "1.1.20")
        self.assertEqual(self.state()["pending"], [])
        self.assertEqual(self.calls, [monitor.CLIENT_PACK_API, monitor.CLIENT_PACK_API])

    def test_newer_release_posts_readable_changelog_only_once(self):
        monitor.check_client_pack()
        self.version = "1.1.21"
        self.title = "Character selection reliability"
        self.changes = ["Updated Ragnavik UI to restore character selection."]
        monitor.check_client_pack()
        monitor.check_client_pack()
        state = self.state()
        self.assertEqual(state["client_pack_version"], "1.1.21")
        self.assertEqual(len(state["pending"]), 1)
        message = state["pending"][0]["message"]
        self.assertIn("Ragnavik client pack v1.1.21 is live", message)
        self.assertIn("Character selection reliability", message)
        self.assertIn("• Updated Ragnavik UI", message)
        self.assertIn(monitor.CLIENT_PACK_PAGE, message)
        self.assertNotIn("Thunderstore", message)
        self.assertEqual(len(monitor.EVENT_FILE.read_text().splitlines()), 1)

    def test_older_cached_version_does_not_repost(self):
        monitor.check_client_pack()
        self.version = "1.1.21"
        monitor.check_client_pack()
        self.version = "1.1.20"
        monitor.check_client_pack()
        self.assertEqual(len(self.state()["pending"]), 1)

    def test_missing_release_notes_is_retried_without_marking_announced(self):
        monitor.check_client_pack()
        self.version = "1.1.21"
        self.changes = []
        with self.assertRaisesRegex(ValueError, "incomplete"):
            monitor.check_client_pack()
        self.assertEqual(self.state()["client_pack_version"], "1.1.20")
        self.changes = ["Sound fix."]
        monitor.check_client_pack()
        self.assertEqual(self.state()["client_pack_version"], "1.1.21")

    def test_recovery_message_includes_latest_release(self):
        monitor.check_client_pack()
        message = monitor.recovery_message(self.state())
        self.assertIn("Ragnavik is live again", message)
        self.assertIn("v1.1.20", message)
        self.assertIn("Updated Epic Loot", message)
        self.assertIn(monitor.CLIENT_PACK_PAGE, message)


if __name__ == "__main__":
    unittest.main()
