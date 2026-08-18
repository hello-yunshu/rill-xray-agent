#!/usr/bin/env python3
"""CLI dispatch regression: every registered subcommand must resolve through
the dispatch table (a past bug dropped 'feedback' from the dict, so the CLI
crashed with KeyError instead of submitting feedback over the socket)."""
import json
import os
import socket
import tempfile
import threading
import unittest
from pathlib import Path

from rill_xray_agent import cli


def _ok_response(method: str) -> dict:
    body = {'method': method, 'ok': True}
    if method == 'diagnose':
        body['result'] = {'status': 'healthy', 'diagnosisId': 'deadbeef' * 8}
    elif method == 'feedback':
        body['result'] = {'accepted': True}
    elif method == 'inspect':
        body['result'] = {'pending': 'x'}
    else:
        body['result'] = {'ok': True}
    return {'schemaVersion': 3, 'requestId': 't', 'ok': True, 'result': body['result'],
            'method': method}


class _FakeRuntime:
    def __init__(self, sock_path: Path):
        self.sock_path = sock_path
        self.server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server.bind(str(sock_path))
        self.server.listen(1)
        self.server.settimeout(5)
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        while True:
            try:
                conn, _ = self.server.accept()
            except socket.timeout:
                return
            except OSError:
                return
            with conn:
                data = b''
                while b'\n' not in data:
                    chunk = conn.recv(65_536)
                    if not chunk:
                        break
                    data += chunk
                if not data:
                    continue
                try:
                    req = json.loads(data.split(b'\n', 1)[0])
                except json.JSONDecodeError:
                    continue
                conn.sendall(json.dumps(_ok_response(req.get('method', ''))).encode() + b'\n')

    def close(self) -> None:
        try:
            self.server.close()
        except OSError:
            pass


class CliDispatchTest(unittest.TestCase):
    def test_all_subcommands_resolve_through_dispatch(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            sock = Path(td) / 'runtime.sock'
            fake = _FakeRuntime(sock)
            try:
                cases = [
                    (['status'], 0),
                    (['health'], 0),
                    (['metrics'], 0),
                    (['config'], 0),
                    (['snapshot'], 0),
                    (['diagnose'], 0),
                    (['inspect', 'deadbeef' * 8], 0),
                    (['timeline'], 0),
                    (['mode', 'observe-only'], 0),
                    (['route-status'], 0),
                    (['route-history'], 0),
                    (['auto-status'], 0),
                    (['auto-produce'], 0),
                    (['rillml-status'], 0),
                    (['feedback', 'deadbeef' * 8, '--outcome', 'resolved',
                      '--helpful', 'true', '--diagnosis-correct', 'true'], 0),
                ]
                for argv, want in cases:
                    argv = ['--socket', str(sock), '--json', *argv]
                    with self.subTest(argv=argv):
                        rc = cli.main(argv)
                        self.assertEqual(rc, want, f'dispatch failed for {argv}')
            finally:
                fake.close()


    def test_rillml_lifecycle_cli_requires_root(self) -> None:
        # Root-only RillML lifecycle (§P0-16): a non-root caller must fail
        # closed with rootRequired and NEVER touch the tree over IPC.
        import contextlib
        import io
        from unittest import mock
        buf = io.StringIO()
        with mock.patch('os.geteuid', return_value=1000), \
                mock.patch('os.name', 'posix'), \
                contextlib.redirect_stdout(buf):
            rc = cli.main(['--json', '--rillml-root', '/tmp/rillml-x', 'rillml', 'status'])
        self.assertEqual(rc, 1)
        out = json.loads(buf.getvalue())
        self.assertFalse(out['ok'])
        self.assertEqual(out['error']['code'], 'rootRequired')


if __name__ == '__main__':
    unittest.main()