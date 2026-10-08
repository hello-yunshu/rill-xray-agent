import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rill_xray_agent.rillml_artifact import (
    MAX_IPC_LINE_BYTES,
    RillMLDownloadError,
    RillMLProbeError,
    _HTTPSOnlyRedirectHandler,
    _http_get,
    _ipc_call,
    probe_runtime,
)


class _Socket:
    def settimeout(self, value):
        self.timeout = value


class _Raw:
    _sock = _Socket()


class _FP:
    raw = _Raw()


class _Response:
    def __init__(self, data, length=None):
        self.data = data
        self.headers = {} if length is None else {'Content-Length': str(length)}
        self.fp = _FP()
        self.read = 0

    def __enter__(self): return self
    def __exit__(self, *args): return False
    def geturl(self): return 'https://example.invalid/artifact'
    def read1(self, n):
        block, self.data = self.data[:n], self.data[n:]
        self.read += len(block)
        return block


class _Opener:
    def __init__(self, response): self.response = response
    def open(self, request, timeout): return self.response


class RillMLBoundedIoTest(unittest.TestCase):
    def test_http_body_is_read_at_most_limit_plus_one(self):
        response = _Response(b'x' * 100)
        with mock.patch('rill_xray_agent.rillml_artifact.urllib.request.build_opener',
                        return_value=_Opener(response)):
            with self.assertRaises(RillMLDownloadError):
                _http_get('https://example.invalid/artifact', timeout=1,
                          attempts=1, max_bytes=8)
        self.assertEqual(response.read, 9)

    def test_content_length_rejects_before_body_read(self):
        response = _Response(b'x' * 10, length=10)
        with mock.patch('rill_xray_agent.rillml_artifact.urllib.request.build_opener',
                        return_value=_Opener(response)):
            with self.assertRaises(RillMLDownloadError):
                _http_get('https://example.invalid/artifact', timeout=1,
                          attempts=1, max_bytes=8)
        self.assertEqual(response.read, 0)

    def test_redirect_handler_rejects_http_downgrade(self):
        req = __import__('urllib.request').request.Request('https://example.invalid/a')
        with self.assertRaises(Exception):
            _HTTPSOnlyRedirectHandler().redirect_request(
                req, None, 302, 'Found', {}, 'http://example.invalid/b')

    def test_ipc_accepts_exact_bound_and_rejects_one_byte_over(self):
        def process_for(size):
            code = ("import sys; n=int(sys.argv[1]); p=sys.stdout.buffer; "
                    "p.write(b'{\"x\":\"'); p.write(b'a'*(n-9)); "
                    "p.write(b'\"}\\n'); p.flush()")
            return subprocess.Popen([sys.executable, '-c', code, str(size)], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
        proc = process_for(MAX_IPC_LINE_BYTES)
        self.assertEqual(len(_ipc_call(proc, {'method': 'probe'}, timeout=3)['x']),
                         MAX_IPC_LINE_BYTES - 9)
        proc.wait(timeout=3)
        for stream in (proc.stdin, proc.stdout, proc.stderr): stream.close()
        proc = process_for(MAX_IPC_LINE_BYTES + 1)
        with self.assertRaises(RillMLProbeError):
            _ipc_call(proc, {'method': 'probe'}, timeout=3)
        proc.kill()
        proc.wait(timeout=3)
        for stream in (proc.stdin, proc.stdout, proc.stderr): stream.close()

    def test_ipc_eof_and_invalid_json_fail_closed(self):
        for output in (b'', b'not-json\n'):
            code = 'import sys;sys.stdout.buffer.write(' + repr(output) + ')'
            proc = subprocess.Popen([sys.executable, '-c', code], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, bufsize=0)
            with self.assertRaises(RillMLProbeError):
                _ipc_call(proc, {'method': 'probe'}, timeout=3)
            proc.wait(timeout=3)
            for stream in (proc.stdin, proc.stdout, proc.stderr): stream.close()

    @unittest.skipUnless(os.name == 'posix', 'probe process-group cleanup requires POSIX')
    def test_probe_deadline_kills_slow_runtime(self):
        with tempfile.TemporaryDirectory() as td:
            runtime = Path(td) / 'slow-runtime'
            runtime.write_text('#!/usr/bin/python3\nimport time\ntime.sleep(10)\n')
            runtime.chmod(0o755)
            with self.assertRaises(RillMLProbeError):
                probe_runtime(runtime, timeout=0.15)


if __name__ == '__main__':
    unittest.main()
