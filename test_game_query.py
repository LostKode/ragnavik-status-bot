import struct
import socket
import threading
import unittest
from unittest.mock import patch
from contextlib import contextmanager
import status_monitor as monitor

def reply(packet):
    fields = monitor.challenge_fields(packet[3:3 + int.from_bytes(packet[1:3], 'little')])
    return (b'\x21\x0d' + struct.pack('<I', fields[1][1]) + b'\x11' + bytes(8)
            + b'\x19' + struct.pack('<Q', fields[3][1]) + b'\x20\x0d')

class QueryTests(unittest.TestCase):
    def serve(self, replies):
        server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        server.bind(('127.0.0.1', 0)); server.settimeout(1)
        self.addCleanup(server.close)
        requests=[]
        def receive():
            try:
                for reply in replies:
                    packet, address=server.recvfrom(4096); requests.append(packet)
                    if reply is not None: server.sendto(reply(packet) if callable(reply) else reply,address)
            except OSError: pass
        thread=threading.Thread(target=receive,daemon=True);thread.start()
        with patch.multiple(monitor, QUERY_HOST='127.0.0.1',QUERY_PORT=server.getsockname()[1],QUERY_TIMEOUT=.1):
            result=monitor.query_game()
        thread.join(1)
        return result,requests
    def test_private_game_challenge_exchange(self):
        result,requests=self.serve([reply])
        self.assertTrue(result[0]);self.assertEqual(len(requests),1)
        self.assertEqual(len(requests[0]),512);self.assertEqual(requests[0][0],32)
    def test_silent_socket_is_not_ready(self):
        self.assertFalse(self.serve([None])[0][0])
    def test_truncated_reply_is_not_ready(self):
        self.assertFalse(self.serve([b'\x21\x0d'])[0][0])
    def test_wrong_protocol_is_not_ready(self):
        self.assertFalse(self.serve([b'not a game server'])[0][0])
    def test_stale_nonce_is_not_ready(self):
        self.assertFalse(self.serve([lambda p: reply(p)[:16] + bytes(8) + b'\x20\x0d'])[0][0])
    def test_wrong_connection_is_not_ready(self):
        self.assertFalse(self.serve([lambda p: reply(p)[:2] + bytes(4) + reply(p)[6:]])[0][0])
    def test_missing_challenge_is_not_ready(self):
        self.assertFalse(self.serve([lambda p: reply(p)[:6] + reply(p)[15:]])[0][0])
    def test_old_ready_hook_does_not_hide_network_failure(self):
        @contextmanager
        def state(): yield {'ready_container':'abcdef','ready_at':'2026-09-24T10:00:00+00:00'}
        with patch.multiple(monitor,PROBE_MODE='hooks',locked_state=state),patch.object(monitor,'query_game',return_value=(False,'timed out')):
            self.assertFalse(monitor.probe()['healthy'])
    def test_announce_live_refuses_failed_query(self):
        with patch.object(monitor,'probe',return_value={'healthy':False,'reason':'timed out'}):
            with self.assertRaises(RuntimeError): monitor.announce_live()
