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
        self.version = "1.1.10"
        self.published_at = "2026-09-15T18:02:41Z"
        self.readme = "| Version | Changes |\n|---|---|\n| 1.1.11 | OdinHorse sound fix.<br>New UI layout. |\n"
        self.calls = []

        def fake_public_json(url):
            self.calls.append(url)
            if url == monitor.CLIENT_PACK_API:
                return {"latest": {"version_number": self.version,
                                   "date_created": self.published_at}}
            return {"markdown": self.readme}

        monitor.public_json = fake_public_json

    def state(self):
        return json.loads(monitor.STATE_FILE.read_text())

    def test_existing_release_is_baseline_and_not_announced(self):
        monitor.check_client_pack()
        monitor.check_client_pack()
        self.assertEqual(self.state()["client_pack_version"], "1.1.10")
        self.assertEqual(self.state()["pending"], [])
        self.assertEqual(self.calls, [monitor.CLIENT_PACK_API, monitor.CLIENT_PACK_API])

    def test_newer_release_posts_readable_changelog_only_once(self):
        monitor.check_client_pack()
        self.version = "1.1.11"
        self.published_at = "2026-09-16T01:00:00Z"
        monitor.check_client_pack()
        monitor.check_client_pack()
        state = self.state()
        self.assertEqual(state["client_pack_version"], "1.1.11")
        self.assertEqual(len(state["pending"]), 1)
        message = state["pending"][0]["message"]
        self.assertIn("Ragnavik client pack v1.1.11 is live", message)
        self.assertIn("• OdinHorse sound fix.", message)
        self.assertIn("• New UI layout.", message)
        self.assertIn(monitor.CLIENT_PACK_PAGE, message)
        self.assertEqual(len(monitor.EVENT_FILE.read_text().splitlines()), 1)

    def test_older_cached_version_does_not_repost(self):
        monitor.check_client_pack()
        self.version = "1.1.11"
        self.published_at = "2026-09-16T01:00:00Z"
        monitor.check_client_pack()
        self.version = "1.1.10"
        self.published_at = "2026-09-15T18:02:41Z"
        monitor.check_client_pack()
        self.assertEqual(len(self.state()["pending"]), 1)

    def test_missing_release_notes_is_retried_without_marking_announced(self):
        monitor.check_client_pack()
        self.version = "1.1.11"
        self.published_at = "2026-09-16T01:00:00Z"
        self.readme = "No changelog row yet"
        with self.assertRaisesRegex(ValueError, "no readable changelog"):
            monitor.check_client_pack()
        self.assertEqual(self.state()["client_pack_version"], "1.1.10")
        self.readme = "| 1.1.11 | Sound fix. |"
        monitor.check_client_pack()
        self.assertEqual(self.state()["client_pack_version"], "1.1.11")


if __name__ == "__main__":
    unittest.main()
