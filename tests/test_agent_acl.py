import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from rill_xray_agent.agent_service import AgentService
from rill_xray_agent.canonical import canonical_bytes
from rill_xray_agent.runtime_service import RuntimeService


class Tests(unittest.TestCase):
    def request(self, sock, payload, timeout=5):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(.5)
                    s.connect(str(sock))
                    s.sendall(canonical_bytes(payload) + b'\n')
                    data = s.recv(65536)
                    if data:
                        return json.loads(data)
            except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError, json.JSONDecodeError) as exc:
                last = exc
                time.sleep(.02)
        raise AssertionError(f'no response: {last!r}')

    def start_runtime(self, r, uid):
        svc = RuntimeService(r / 'state', r / 'tx', allowed_uids=[0, uid])
        t = threading.Thread(target=svc.serve, args=(r / 'r.sock',), daemon=True)
        t.start()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                    s.settimeout(.5)
                    s.connect(str(r / 'r.sock'))
                break
            except OSError:
                time.sleep(.02)
        else:
            raise AssertionError('runtime listener never became ready')
        return svc, t

    def test_agent_default_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            svc = AgentService(r / 'r.sock')
            self.assertEqual(svc.allowed_uids, set())
            self.assertFalse(svc.method_allowed('health', os.getuid()))
            t = threading.Thread(target=svc.serve, args=(r / 'a.sock',), daemon=True)
            t.start()
            try:
                out = self.request(r / 'a.sock', {'schemaVersion': 3, 'requestId': 'x',
                                                  'capability': 'route', 'method': 'health', 'body': {}})
                self.assertFalse(out['ok'], out)
                self.assertEqual(out['error']['code'], 'forbiddenPeer')
            finally:
                svc.stop()
                t.join(timeout=3)

    def test_method_role_policy(self):
        self.assertTrue(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('mode', 0))
        self.assertFalse(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('mode', 4242))
        self.assertTrue(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('register', 4242))
        self.assertTrue(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('rootResult', 4242))
        self.assertTrue(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('feedback', 4242))
        self.assertTrue(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('health', 4242))
        self.assertFalse(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('health', None))
        self.assertFalse(AgentService('/x', allowed_uids=[0, 4242]).method_allowed('reset', 0))
        self.assertFalse(AgentService('/x', allowed_uids=[4242]).method_allowed('health', 0))

    def test_agent_allows_operator_write_forbidden_method_from_operator(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            rt, rt_t = self.start_runtime(r, os.getuid())
            ag = AgentService(r / 'r.sock', allowed_uids=[os.getuid()])
            t = threading.Thread(target=ag.serve, args=(r / 'a.sock',), daemon=True)
            t.start()
            try:
                out = self.request(r / 'a.sock', {'schemaVersion': 3, 'requestId': 'x',
                                                  'capability': 'route', 'method': 'health', 'body': {}})
                self.assertTrue(out['ok'], out)
                mode = self.request(r / 'a.sock', {'schemaVersion': 3, 'requestId': 'm',
                                                   'capability': 'route', 'method': 'mode',
                                                   'body': {'mode': 'safe-disabled'}})
                self.assertFalse(mode['ok'], mode)
                self.assertEqual(mode['error']['code'], 'forbiddenPeer')
            finally:
                ag.stop()
                t.join(timeout=3)
                rt.stop()
                rt_t.join(timeout=3)


if __name__ == '__main__':
    unittest.main()