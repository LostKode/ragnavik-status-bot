import http.server
import json
from pathlib import Path
import tempfile
import threading
import unittest
import unittest.mock
import urllib.error
import urllib.request

from anticheat_receiver import EventQueue, format_event, handler, start_receiver, validate_event


class AntiCheatReceiverTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.token = root / "token"
        self.token.write_text("secret")
        self.queue = EventQueue(root / "events.sqlite3")
        self.server = http.server.ThreadingHTTPServer(
            ("127.0.0.1", 0), handler(self.queue, self.token))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def event(self, event_id="event-1"):
        return {"eventId": event_id, "type": "mismatch", "server": "Ragnavik",
                "steamId": "76561198000000000", "characterName": "Viking",
                "catosVersion": "1.0.4", "problems": ["missing required example.mod v1.2.3"]}

    def post(self, payload, token="secret"):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.server.server_port}/anticheat",
            data=json.dumps(payload).encode(), method="POST",
            headers={"Content-Type": "application/json", "X-Ragnavik-Anticheat": token})
        try:
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.status
        except urllib.error.HTTPError as exc:
            return exc.code

    def test_mismatch_is_persisted_for_log_delivery(self):
        self.assertEqual(self.post(self.event()), 202)
        queued = self.queue.next()
        self.assertEqual(queued["destination"], "log")
        self.assertIn("mod mismatch", queued["message"])
        self.assertIn("missing required example.mod", queued["message"])
        self.queue.ack(queued["id"])
        self.assertIsNone(self.queue.next())

    def test_duplicate_event_is_idempotent(self):
        self.assertEqual(self.post(self.event()), 202)
        self.assertEqual(self.post(self.event()), 204)
        queued = self.queue.next()
        self.queue.ack(queued["id"])
        self.assertIsNone(self.queue.next())

    def test_bad_token_and_unknown_fields_are_rejected(self):
        self.assertEqual(self.post(self.event(), token="wrong"), 403)
        event = self.event()
        event["content"] = "unvalidated"
        self.assertEqual(self.post(event), 400)
        self.assertIsNone(self.queue.next())

    def test_timeout_is_validated_and_formatted(self):
        event = {"eventId": "event-2", "type": "timeout", "server": "Ragnavik",
                 "steamId": "", "characterName": "", "catosVersion": "1.0.4",
                 "timeoutSeconds": 15.0}
        clean = validate_event(event)
        message = format_event(clean)
        self.assertIn("no mod-list reply", message)
        self.assertIn("15s", message)

    def test_receiver_start_failure_is_wrapped(self):
        with unittest.mock.patch("anticheat_receiver.EventQueue", side_effect=PermissionError("denied")):
            with self.assertRaisesRegex(RuntimeError, "receiver could not start: denied"):
                start_receiver()

    def test_mentions_are_not_special_at_delivery(self):
        event = self.event()
        event["problems"] = ["unauthorized `mod` from @everyone\nsecond line"]
        message = format_event(validate_event(event))
        self.assertIn("@everyone", message)
        self.assertNotIn("`mod`", message)
        self.assertNotIn("\nsecond line", message)
        # bot_api.deliver also supplies allowed_mentions.parse = [], making mentions inert.


if __name__ == "__main__":
    unittest.main()
