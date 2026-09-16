import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bot_api


class DeliveryRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        token_file = Path(self.temp.name) / "token"
        token_file.write_text("test-token")
        self.token_patch = patch.object(bot_api, "BOT_TOKEN_FILE", str(token_file))
        self.token_patch.start()
        self.addCleanup(self.token_patch.stop)
        self.calls = []
        self.request_patch = patch.object(
            bot_api, "discord_request",
            side_effect=lambda token, method, path, payload: self.calls.append(path),
        )
        self.request_patch.start()
        self.addCleanup(self.request_patch.stop)

    def item(self, destination):
        return {"destination": destination, "message": "test", "nonce": "nonce"}

    def test_player_notice_goes_to_announcements(self):
        bot_api.deliver(self.item("channel"))
        self.assertEqual(self.calls, [f"/channels/{bot_api.CHANNEL_ID}/messages"])

    def test_backup_notice_goes_to_logs(self):
        bot_api.deliver(self.item("logs"))
        self.assertEqual(self.calls, [f"/channels/{bot_api.LOGS_CHANNEL_ID}/messages"])

    def test_unknown_destination_does_not_leak_into_announcements(self):
        with self.assertRaisesRegex(ValueError, "Unknown Discord destination"):
            bot_api.deliver(self.item("unknown"))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
