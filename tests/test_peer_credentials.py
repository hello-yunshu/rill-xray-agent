import json
import os
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from rill_xray_agent.canonical import canonical_bytes
from rill_xray_agent.payload_policy import sanitize_payload
from rill_xray_agent.peer_auth import AccessControl
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

    def test_peer_credentials_recorded(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            sock = r / 'r.sock'
            svc = RuntimeService(r / 'state', r / 'tx', allowed_uids=[os.getuid()])
            t = threading.Thread(target=svc.serve, args=(sock,), daemon=True)
            t.start()
            try:
                out = self.request(sock, {'schemaVersion': 3, 'requestId': 'x', 'capability': 'route',
                                          'method': 'health', 'body': {}})
                self.assertTrue(out['ok'], out)
            finally:
                svc.stop()
                t.join(timeout=3)
            lines = (r / 'state/access-log.jsonl').read_text().splitlines()
            self.assertTrue(lines)
            entry = json.loads(lines[0])
            self.assertIn('pid', entry)
            self.assertIn('uid', entry)
            self.assertIn('gid', entry)
            self.assertEqual(entry['uid'], os.getuid())
            self.assertTrue(entry['ok'])

    def test_acl_blocks_other_uid(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            sock = r / 'r.sock'
            svc = RuntimeService(r / 'state', r / 'tx', allowed_uids=[424242])
            t = threading.Thread(target=svc.serve, args=(sock,), daemon=True)
            t.start()
            try:
                out = self.request(sock, {'schemaVersion': 3, 'requestId': 'x', 'capability': 'route',
                                          'method': 'health', 'body': {}})
                self.assertFalse(out['ok'], out)
                self.assertEqual(out['error']['code'], 'forbiddenPeer')
            finally:
                svc.stop()
                t.join(timeout=3)

    def test_acl_default_is_fail_closed(self):
        # No allowlist must mean deny-everyone, never open.
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            sock = r / 'r.sock'
            svc = RuntimeService(r / 'state', r / 'tx')
            self.assertEqual(svc.acl.describe()['mode'], 'allowlist')
            self.assertEqual(svc.acl.describe()['allowedUids'], [])
            self.assertFalse(svc.acl.authorize((12345, os.getuid(), 1)))
            t = threading.Thread(target=svc.serve, args=(sock,), daemon=True)
            t.start()
            try:
                out = self.request(sock, {'schemaVersion': 3, 'requestId': 'x', 'capability': 'route',
                                          'method': 'health', 'body': {}})
                self.assertFalse(out['ok'], out)
                self.assertEqual(out['error']['code'], 'forbiddenPeer')
            finally:
                svc.stop()
                t.join(timeout=3)

    def test_acl_unknown_peer_creds_rejected(self):
        self.assertFalse(AccessControl([os.getuid()]).authorize(None))
        self.assertFalse(AccessControl([os.getuid()]).authorize((1, None, None)))
        self.assertFalse(AccessControl([]).authorize((1, os.getuid(), 1)))
        self.assertFalse(AccessControl().write_permitted(None))
        self.assertFalse(AccessControl().write_permitted(os.getuid()))

    def test_concurrency_limit_rejects_when_full(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            sock = r / 'r.sock'
            svc = RuntimeService(r / 'state', r / 'tx', max_concurrency=2)
            svc.sem.acquire(blocking=False)
            svc.sem.acquire(blocking=False)
            t = threading.Thread(target=svc.serve, args=(sock,), daemon=True)
            t.start()
            try:
                out = self.request(sock, {'schemaVersion': 3, 'requestId': 'x', 'capability': 'route',
                                          'method': 'health', 'body': {}})
                self.assertFalse(out['ok'], out)
                self.assertEqual(out['error']['code'], 'serverBusy')
            finally:
                svc.stop()
                t.join(timeout=3)

    def test_payload_allowlist_redacts_and_rejects(self):
        meta = sanitize_payload({'decisionId': 'd', 'capability': 'route', 'modelGeneration': 1,
                                 'terminalPayload': {'privateKey': 'SECRET', 'uuid': 'U1', 'ok': True}})
        self.assertEqual(meta['terminalPayload']['privateKey'], '<redacted>')
        self.assertEqual(meta['terminalPayload']['uuid'], '<redacted>')
        self.assertEqual(meta['terminalPayload']['ok'], True)
        with self.assertRaises(ValueError):
            sanitize_payload({'decisionId': 'd', 'capability': 'route', 'modelGeneration': 1,
                              'inbounds': [{'protocol': 'vless'}]})
        red = sanitize_payload({'decisionId': 'd', 'capability': 'route', 'modelGeneration': 1,
                                'terminalPayload': 'vless://example'})
        self.assertEqual(red['terminalPayload'], '<redacted>')

    def test_service_never_stores_forbidden_data(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            sock = r / 'r.sock'
            svc = RuntimeService(r / 'state', r / 'tx', allowed_uids=[os.getuid()])
            t = threading.Thread(target=svc.serve, args=(sock,), daemon=True)
            t.start()
            try:
                body = {'capability': 'route', 'decisionId': 'd1', 'modelGeneration': 1,
                        'createdAtEpochSeconds': 1}
                self.request(sock, {'schemaVersion': 3, 'requestId': 'a', 'capability': 'route',
                                    'method': 'register', 'body': body})
                self.request(sock, {'schemaVersion': 3, 'requestId': 'b', 'capability': 'route',
                                    'method': 'rootResult', 'body': {'decisionId': 'd1', 'result': {'ok': True}}})
                fb = {'decisionId': 'd1', 'capability': 'route', 'modelGeneration': 1,
                      'terminalPayload': {'privateKey': 'SECRET'}}
                self.request(sock, {'schemaVersion': 3, 'requestId': 'c', 'capability': 'route',
                                    'method': 'feedback', 'body': fb})
            finally:
                svc.stop()
                t.join(timeout=3)
            state = svc.state.load()
            self.assertNotIn('payload', state['completed']['d1'])
            blob = json.dumps(state)
            self.assertNotIn('SECRET', blob)
            self.assertNotIn('"payload":', blob)

    def test_feedback_rejects_xray_config_body(self):
        with tempfile.TemporaryDirectory() as td:
            svc = RuntimeService(Path(td) / 'state', Path(td) / 'tx')
            reg = {'capability': 'route', 'decisionId': 'd2', 'modelGeneration': 1, 'createdAtEpochSeconds': 1}
            self.assertTrue(svc.handle({'schemaVersion': 3, 'requestId': 'a', 'capability': 'route',
                                        'method': 'register', 'body': reg})['ok'])
            fb = {'decisionId': 'd2', 'capability': 'route', 'modelGeneration': 1,
                  'terminalPayload': {}, 'inbounds': [{'protocol': 'vless'}]}
            out = svc.handle({'schemaVersion': 3, 'requestId': 'b', 'capability': 'route',
                              'method': 'feedback', 'body': fb})
            self.assertFalse(out['ok'], out)
            self.assertEqual(svc.state.load()['pending']['d2']['rootResult'], None)


if __name__ == '__main__':
    unittest.main()