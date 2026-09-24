import socket
import threading
import unittest
from unittest.mock import patch
from contextlib import contextmanager
import status_monitor as monitor

INFO = b'\xff\xff\xff\xffI\x11Ragnavik\x00world\x00valheim\x00Valheim\x00' + bytes(9)

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
                    if reply is not None: server.sendto(reply,address)
            except OSError: pass
        thread=threading.Thread(target=receive,daemon=True);thread.start()
        with patch.multiple(monitor, QUERY_HOST='127.0.0.1',QUERY_PORT=server.getsockname()[1],QUERY_TIMEOUT=.1):
            result=monitor.query_game()
        thread.join(1)
        return result,requests
    def test_successful_challenge_exchange(self):
        result,requests=self.serve([b'\xff\xff\xff\xffAabcd',INFO])
        self.assertTrue(result[0]);self.assertTrue(requests[1].endswith(b'abcd'))
    def test_silent_socket_is_not_ready(self):
        self.assertFalse(self.serve([None])[0][0])
    def test_truncated_info_is_not_ready(self):
        self.assertFalse(self.serve([b'\xff\xff\xff\xffI\x11'])[0][0])
    def test_wrong_protocol_is_not_ready(self):
        self.assertFalse(self.serve([b'not a game server'])[0][0])
    def test_old_ready_hook_does_not_hide_network_failure(self):
        @contextmanager
        def state(): yield {'ready_container':'abcdef','ready_at':'2026-09-24T10:00:00+00:00'}
        with patch.multiple(monitor,PROBE_MODE='hooks',locked_state=state),patch.object(monitor,'query_game',return_value=(False,'timed out')):
            self.assertFalse(monitor.probe()['healthy'])
    def test_announce_live_refuses_failed_query(self):
        with patch.object(monitor,'probe',return_value={'healthy':False,'reason':'timed out'}):
            with self.assertRaises(RuntimeError): monitor.announce_live()
