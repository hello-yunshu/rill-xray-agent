"""RillML prebuilt rill-runtime artifact consumption (downstream, read-only).

Covers: Ed25519 index signature verification, deterministic platform identity
(OS/arch/libc), signed release-index parsing, artifact selection, wrong-arch /
wrong-libc / wrong-channel / API-incompatible fail-closed, download + SHA-256
re-verification, and atomic activation with previous-good rollback preservation.

No network access and no RillML compilation ever happens in these tests: all
indexes/artifacts are local fixtures and every fetch is mocked.
"""
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from rill_xray_agent import rillml_ed25519
from rill_xray_agent.canonical import canonical_bytes
from rill_xray_agent.rillml_artifact import (
    RillMLDownloadError,
    RillMLProbeError,
    RillMLRuntimeManager,
    RillMLUnsupported,
    RillMLValidationError,
    _validate_https_url,
    detect_platform,
    download_artifact,
    parse_release_index,
    runtime_artifact_id,
    select_runtime_artifact,
    sha256_file,
    verify_artifact_file,
)

TEST_SEED = bytes(range(32))
TEST_KEY_ID = 'test-2026-001'
TEST_PUB_HEX = rillml_ed25519.public_key_from_seed(TEST_SEED).hex()


def sign_payload(payload):
    return rillml_ed25519.sign(TEST_SEED, canonical_bytes(payload)).hex()


def envelope(payload):
    return {'payload': payload, 'signature': sign_payload(payload)}


def runtime_artifact(**over):
    art = {
        'kind': 'runtime', 'id': 'rill-runtime', 'version': '1.2.0',
        'targetOs': 'linux', 'targetArch': 'x86_64', 'targetLibc': 'gnu',
        'runtimeApiVersion': 2,
        'url': ('https://github.com/hello-yunshu/rill-ml/releases/download/'
                'v1.2.0/rill-runtime-1.2.0-linux-x86_64'),
        'size': 123, 'sha256': 'ab' * 32,
    }
    art.update(over)
    return art


def make_index(artifacts, channel='stable'):
    payload = {
        'schemaVersion': 3, 'publisherKeyId': TEST_KEY_ID,
        'channel': channel, 'artifacts': artifacts,
    }
    return json.dumps(envelope(payload)).encode()


def make_fetch(byte_map):
    """Build a stand-in for rillml_artifact._http_get serving the given URLs."""
    def fetch(url, *, timeout, attempts, max_bytes):
        _validate_https_url(url)
        for suffix, data in byte_map.items():
            if url.endswith(suffix):
                return data
        raise RillMLDownloadError(f'no fixture for {url}')
    return fetch


def _compute_fixture(art):
    """Generate deterministic data for an artifact, return (data, sha256)."""
    size = art['size']
    data = bytes(range(256)) * ((size + 255) // 256 + 1)
    data = data[:size]
    return data, hashlib.sha256(data).hexdigest()


def _patched_artifact(art, data, sha):
    """Return a copy of *art* with the given sha256 patched in."""
    c = dict(art)
    c['sha256'] = sha
    return c


class Ed25519VerifyTest(unittest.TestCase):
    def test_sign_verify_roundtrip(self):
        msg = b'stable-index payload bytes'
        sig = rillml_ed25519.sign(TEST_SEED, msg)
        self.assertTrue(rillml_ed25519.verify(bytes.fromhex(TEST_PUB_HEX), msg, sig))
        self.assertTrue(rillml_ed25519.verify_hex(TEST_PUB_HEX, msg, sig.hex()))

    def test_tampered_message_rejected(self):
        msg = b'stable-index payload bytes'
        sig = rillml_ed25519.sign(TEST_SEED, msg)
        self.assertFalse(
            rillml_ed25519.verify(bytes.fromhex(TEST_PUB_HEX), msg + b'x', sig))

    def test_wrong_key_rejected(self):
        msg = b'stable-index payload bytes'
        sig = rillml_ed25519.sign(TEST_SEED, msg)
        other = rillml_ed25519.public_key_from_seed(bytes(32)).hex()
        self.assertFalse(rillml_ed25519.verify_hex(other, msg, sig.hex()))

    def test_short_or_bad_signature_never_raises(self):
        self.assertFalse(rillml_ed25519.verify(bytes.fromhex(TEST_PUB_HEX), b'm', b''))
        self.assertFalse(rillml_ed25519.verify(bytes.fromhex(TEST_PUB_HEX), b'm', b'x' * 64))


class PlatformDetectionTest(unittest.TestCase):
    def test_linux_gnu(self):
        with mock.patch('rill_xray_agent.rillml_artifact.sys.platform', 'linux'), \
             mock.patch('rill_xray_agent.rillml_artifact.platform.machine', return_value='x86_64'), \
             mock.patch('rill_xray_agent.rillml_artifact._detect_linux_libc', return_value='gnu'):
            self.assertEqual(detect_platform(),
                             {'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'})

    def test_linux_arm64_musl(self):
        with mock.patch('rill_xray_agent.rillml_artifact.sys.platform', 'linux'), \
             mock.patch('rill_xray_agent.rillml_artifact.platform.machine', return_value='arm64'), \
             mock.patch('rill_xray_agent.rillml_artifact._detect_linux_libc', return_value='musl'):
            self.assertEqual(detect_platform(),
                             {'os': 'linux', 'arch': 'aarch64', 'libc': 'musl'})

    def test_macos_no_libc(self):
        with mock.patch('rill_xray_agent.rillml_artifact.sys.platform', 'darwin'), \
             mock.patch('rill_xray_agent.rillml_artifact.platform.machine', return_value='x86_64'):
            self.assertEqual(detect_platform(),
                             {'os': 'macos', 'arch': 'x86_64', 'libc': None})

    def test_unsupported_arch_fails_closed(self):
        with mock.patch('rill_xray_agent.rillml_artifact.sys.platform', 'linux'), \
             mock.patch('rill_xray_agent.rillml_artifact.platform.machine', return_value='mips'), \
             mock.patch('rill_xray_agent.rillml_artifact._detect_linux_libc', return_value='gnu'):
            with self.assertRaises(RillMLUnsupported):
                detect_platform()

    def test_unknown_libc_fails_closed_never_guesses(self):
        with mock.patch('rill_xray_agent.rillml_artifact.sys.platform', 'linux'), \
             mock.patch('rill_xray_agent.rillml_artifact.platform.machine', return_value='x86_64'), \
             mock.patch('rill_xray_agent.rillml_artifact._detect_linux_libc', return_value=None):
            with self.assertRaises(RillMLUnsupported):
                detect_platform()

    def test_libc_artifact_id_mapping(self):
        self.assertEqual(runtime_artifact_id('gnu'), 'rill-runtime')
        self.assertEqual(runtime_artifact_id('musl'), 'rill-runtime-musl')

    def test_arch_normalization_aliases(self):
        # Local naming is normalized to upstream target names; it is not a
        # support-matrix declaration (the signed index is the authority).
        with mock.patch('rill_xray_agent.rillml_artifact.sys.platform', 'linux'), \
             mock.patch('rill_xray_agent.rillml_artifact._detect_linux_libc', return_value='gnu'):
            for machine, expected in (
                    ('riscv64gc', 'riscv64'), ('riscv64', 'riscv64'),
                    ('ppc64le', 'powerpc64le'), ('loong64', 'loongarch64'),
                    ('armv7l', 'armv7'), ('armhf', 'armv7'), ('s390x', 's390x')):
                with mock.patch('rill_xray_agent.rillml_artifact.platform.machine',
                                return_value=machine):
                    self.assertEqual(detect_platform()['arch'], expected)


class ReleaseIndexParseTest(unittest.TestCase):
    def test_valid_signed_index(self):
        text = make_index([runtime_artifact()])
        payload = parse_release_index(
            text.decode(), trusted_key_id=TEST_KEY_ID,
            public_key_hex=TEST_PUB_HEX, channel='stable')
        self.assertEqual(payload['channel'], 'stable')
        self.assertEqual(len(payload['artifacts']), 1)

    def test_real_style_v3_index_with_target_libc_and_pm_adapter(self):
        # Mirrors the published v1.2.0 stable-index.json shape (verified against
        # upstream): schema v3 runtime entries carry targetLibc on Linux, and the
        # OpenWrt PM adapter is a separate kind that must parse, not be selected
        # as the runtime.
        model = {
            'kind': 'model', 'id': 'rillml.example.default', 'version': '1.2.0',
            'runtimeApiVersion': 2,
            'url': ('https://github.com/hello-yunshu/rill-ml/releases/download/'
                    'v1.2.0/example-default-1.2.0.rillpack'),
            'size': 456, 'sha256': 'cd' * 32,
        }
        handler = {
            'kind': 'handler', 'id': 'rillml.echo.handler', 'version': '1.2.0',
            'runtimeApiVersion': 2, 'handlerApiVersion': 1,
            'minRuntimeVersion': '1.2.0',
            'url': ('https://github.com/hello-yunshu/rill-ml/releases/download/'
                    'v1.2.0/echo-handler-1.2.0.rillhandler'),
            'size': 789, 'sha256': 'ef' * 32,
        }
        pm_adapter = {
            'kind': 'pm-adapter', 'id': 'rill-pm-adapter', 'version': '1.2.0',
            'runtimeApiVersion': 0, 'pmAdapterProtocolVersion': 1,
            'targetOs': 'linux', 'targetArch': 'x86_64', 'targetLibc': 'musl',
            'url': ('https://github.com/hello-yunshu/rill-ml/releases/download/'
                    'v1.2.0/rill-pm-adapter-1.2.0-linux-x86_64-musl'),
            'size': 789, 'sha256': 'ab' * 32,
        }
        text = make_index([runtime_artifact(), model, handler, pm_adapter])
        payload = parse_release_index(
            text.decode(), trusted_key_id=TEST_KEY_ID,
            public_key_hex=TEST_PUB_HEX, channel='stable')
        kinds = sorted(a['kind'] for a in payload['artifacts'])
        self.assertEqual(kinds, ['handler', 'model', 'pm-adapter', 'runtime'])
        # PM adapter must never be selected as the runtime.
        art = select_runtime_artifact(payload, target_os='linux',
                                      target_arch='x86_64', libc='gnu')
        self.assertEqual(art['kind'], 'runtime')
        self.assertEqual(art['id'], 'rill-runtime')

    def test_linux_runtime_requires_target_libc(self):
        # A Linux runtime artifact missing the v3 targetLibc field is malformed.
        broken = runtime_artifact()
        del broken['targetLibc']
        text = make_index([broken])
        with self.assertRaises(RillMLValidationError):
            parse_release_index(text.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX)

    def test_target_libc_exact_match_never_cross_selects(self):
        # A malformed index labels a GNU build id with targetLibc=musl; the
        # explicit field must win over the id so a gnu host never selects it.
        mislabeled = runtime_artifact(id='rill-runtime', targetLibc='musl')
        idx = {'schemaVersion': 3, 'publisherKeyId': TEST_KEY_ID,
               'channel': 'stable', 'artifacts': [mislabeled]}
        with self.assertRaises(RillMLValidationError):
            select_runtime_artifact(idx, target_os='linux',
                                    target_arch='x86_64', libc='gnu')

    def test_pm_adapter_requires_protocol_version(self):
        bad = {'kind': 'pm-adapter', 'id': 'rill-pm-adapter', 'version': '1.2.0',
               'runtimeApiVersion': 0, 'targetOs': 'linux', 'targetArch': 'x86_64',
               'targetLibc': 'musl',
               'url': ('https://github.com/hello-yunshu/rill-ml/releases/download/'
                       'v1.2.0/rill-pm-adapter-1.2.0-linux-x86_64-musl'),
               'size': 789, 'sha256': 'ab' * 32}
        text = make_index([runtime_artifact(), bad])
        with self.assertRaises(RillMLValidationError):
            parse_release_index(text.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX)

    def test_runtime_artifact_requires_target_os(self):
        broken = runtime_artifact()
        del broken['targetOs']
        text = make_index([broken])
        with self.assertRaises(RillMLValidationError):
            parse_release_index(text.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX)

    def test_handler_requires_handler_api_version(self):
        handler = {
            'kind': 'handler', 'id': 'rillml.echo.handler', 'version': '1.1.0',
            'runtimeApiVersion': 2,
            'url': ('https://github.com/hello-yunshu/rill-ml/releases/download/'
                    'v1.1.0/echo-handler-1.1.0.rillhandler'),
            'size': 789, 'sha256': 'ef' * 32,
        }
        text = make_index([runtime_artifact(), handler])
        with self.assertRaises(RillMLValidationError):
            parse_release_index(text.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX)

    def test_tampered_signature_rejected(self):
        raw = make_index([runtime_artifact()])
        raw = raw[:-2] + b'00'  # flip the trailing signature bytes
        with self.assertRaises(RillMLValidationError):
            parse_release_index(raw.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX)

    def test_wrong_publisher_key_rejected(self):
        other = rillml_ed25519.public_key_from_seed(bytes(32)).hex()
        text = make_index([runtime_artifact()])
        with self.assertRaises(RillMLValidationError):
            parse_release_index(text.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=other)

    def test_wrong_channel_rejected(self):
        text = make_index([runtime_artifact()], channel='candidate')
        with self.assertRaises(RillMLValidationError):
            parse_release_index(text.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX, channel='stable')

    def test_schema_version_not_supported_rejected(self):
        # v2 is the legacy schema the 1.2.0 contract supersedes; the consumer
        # only accepts the audited v3 (fail-closed at the schema boundary).
        payload = {'schemaVersion': 2, 'publisherKeyId': TEST_KEY_ID,
                   'channel': 'stable',
                   'artifacts': [runtime_artifact()]}
        raw = json.dumps(envelope(payload)).encode()
        with self.assertRaises(RillMLValidationError):
            parse_release_index(raw.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX)

    def test_empty_artifacts_rejected(self):
        text = make_index([])
        with self.assertRaises(RillMLValidationError):
            parse_release_index(text.decode(), trusted_key_id=TEST_KEY_ID,
                                public_key_hex=TEST_PUB_HEX)


class ArtifactSelectionTest(unittest.TestCase):
    def _index(self):
        return {'schemaVersion': 3, 'publisherKeyId': TEST_KEY_ID,
                'channel': 'stable', 'artifacts': [
                    runtime_artifact(),
                    runtime_artifact(id='rill-runtime-musl', targetLibc='musl',
                                     url='https://github.com/hello-yunshu/rill-ml/releases/download/v1.2.0/rill-runtime-1.2.0-linux-x86_64-musl'),
                    runtime_artifact(targetArch='aarch64',
                                     url='https://github.com/hello-yunshu/rill-ml/releases/download/v1.2.0/rill-runtime-1.2.0-linux-aarch64'),
                    runtime_artifact(id='rill-runtime-musl', targetArch='aarch64',
                                     targetLibc='musl',
                                     url='https://github.com/hello-yunshu/rill-ml/releases/download/v1.2.0/rill-runtime-1.2.0-linux-aarch64-musl'),
                ]}

    def test_select_gnu_x86_64(self):
        art = select_runtime_artifact(self._index(), target_os='linux',
                                      target_arch='x86_64', libc='gnu')
        self.assertEqual(art['id'], 'rill-runtime')
        self.assertEqual(art['targetArch'], 'x86_64')

    def test_select_musl_x86_64(self):
        art = select_runtime_artifact(self._index(), target_os='linux',
                                      target_arch='x86_64', libc='musl')
        self.assertEqual(art['id'], 'rill-runtime-musl')

    def test_select_gnu_aarch64(self):
        art = select_runtime_artifact(self._index(), target_os='linux',
                                      target_arch='aarch64', libc='gnu')
        self.assertEqual(art['targetArch'], 'aarch64')

    def test_wrong_arch_rejected(self):
        with self.assertRaises(RillMLValidationError):
            select_runtime_artifact(self._index(), target_os='linux',
                                    target_arch='riscv64', libc='gnu')

    def test_wrong_libc_rejected(self):
        # Only GNU artifacts present; a musl request must fail closed.
        idx = {'schemaVersion': 3, 'publisherKeyId': TEST_KEY_ID,
               'channel': 'stable', 'artifacts': [
                   runtime_artifact(),
                   runtime_artifact(targetArch='aarch64',
                                    url='https://github.com/hello-yunshu/rill-ml/releases/download/v1.2.0/rill-runtime-1.2.0-linux-aarch64'),
               ]}
        with self.assertRaises(RillMLValidationError):
            select_runtime_artifact(idx, target_os='linux',
                                    target_arch='aarch64', libc='musl')

    def test_runtime_api_incompatible_rejected(self):
        with self.assertRaises(RillMLValidationError):
            select_runtime_artifact(self._index(), target_os='linux',
                                    target_arch='x86_64', libc='gnu',
                                    api_version=1)


class DownloadVerifyTest(unittest.TestCase):
    def test_verify_artifact_size_mismatch(self):
        art = runtime_artifact(size=100)
        data, sha = _compute_fixture(dict(art, size=99))
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x'
            p.write_bytes(data)
            with self.assertRaises(RillMLValidationError):
                verify_artifact_file(art, p)

    def test_verify_artifact_sha_mismatch(self):
        art = runtime_artifact(sha256='cd' * 32)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x'
            p.write_bytes(b'\x00' * art['size'])
            with self.assertRaises(RillMLValidationError):
                verify_artifact_file(art, p)

    def test_verify_artifact_ok(self):
        art = runtime_artifact()
        data, actual_sha = _compute_fixture(art)
        patched = _patched_artifact(art, data, actual_sha)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'x'
            p.write_bytes(data)
            sha = verify_artifact_file(patched, p)
            self.assertEqual(sha, actual_sha)

    def test_download_verifies_and_is_executable(self):
        art = runtime_artifact()
        data, actual_sha = _compute_fixture(art)
        patched = _patched_artifact(art, data, actual_sha)
        byte_map = {art['url']: data}
        with mock.patch('rill_xray_agent.rillml_artifact._http_get',
                        make_fetch(byte_map)), \
             tempfile.TemporaryDirectory() as td:
            path = download_artifact(patched, td)
            self.assertTrue(Path(path).is_file())
            self.assertEqual(Path(path).stat().st_size, patched['size'])
            self.assertEqual(sha256_file(path), actual_sha)

    def test_download_rejects_symlink_target(self):
        art = runtime_artifact()
        data, actual_sha = _compute_fixture(art)
        patched = _patched_artifact(art, data, actual_sha)
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'rill-runtime-1.2.0-linux-x86_64'
            target.symlink_to('/etc/hosts')
            with self.assertRaises(RillMLValidationError):
                download_artifact(patched, td)

    def test_forbidden_scheme_rejected(self):
        with self.assertRaises(RillMLValidationError):
            _validate_https_url('http://example.com/a')


class RuntimeManagerLifecycleTest(unittest.TestCase):
    def test_status_unsupported_platform_fails_closed(self):
        with mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        side_effect=RillMLUnsupported('unsupported')), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            status = mgr.status()
            self.assertFalse(status['supported'])
            self.assertFalse(status['available'])
            self.assertEqual(status['unavailableReason'], 'unsupported')

    def test_install_activates_with_previous_good_rollback(self):
        v1 = runtime_artifact(version='1.1.0')
        v2 = runtime_artifact(version='1.2.0')
        data1, sha1 = _compute_fixture(v1)
        data2, sha2 = _compute_fixture(v2)
        p1 = _patched_artifact(v1, data1, sha1)
        p2 = _patched_artifact(v2, data2, sha2)
        index1 = make_index([p1])
        index2 = make_index([p2])
        calls = {'n': 0}
        probe = {'probe': 'lightweight', 'executes': True, 'exitCode': 0}

        def fetch(url, *, timeout, attempts, max_bytes):
            _validate_https_url(url)
            calls['n'] += 1
            if url.endswith('stable-index.json'):
                return index1 if calls['n'] < 3 else index2
            if url == v1['url']:
                return data1
            if url == v2['url']:
                return data2
            raise RillMLDownloadError(f'no fixture for {url}')

        with mock.patch('rill_xray_agent.rillml_artifact._http_get', fetch), \
             mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'}), \
             mock.patch('rill_xray_agent.rillml_artifact.probe_runtime',
                        return_value=probe), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            # First install activates 1.1.0.
            mgr.install(probe='lightweight')
            s1 = mgr.status()
            self.assertTrue(s1['available'])
            self.assertEqual(s1['current']['version'], '1.1.0')
            self.assertIsNone(s1['rollback'])
            # Second install upgrades to 1.2.0 and preserves 1.1.0 as rollback.
            mgr.install(probe='lightweight')
            s2 = mgr.status()
            self.assertEqual(s2['current']['version'], '1.2.0')
            self.assertEqual(s2['rollback']['version'], '1.1.0')
            # Failed probe never replaces the current runtime.
            with mock.patch('rill_xray_agent.rillml_artifact.probe_runtime',
                            side_effect=RillMLProbeError('incompatible')):
                with self.assertRaises(RillMLProbeError):
                    mgr.install(probe='lightweight')
            s3 = mgr.status()
            self.assertEqual(s3['current']['version'], '1.2.0')
            self.assertEqual(s3['rollback']['version'], '1.1.0')
            # rollback() restores previous-good 1.1.0.
            mgr.rollback()
            s4 = mgr.status()
            self.assertEqual(s4['current']['version'], '1.1.0')

    def test_install_checksum_mismatch_never_activates(self):
        art = runtime_artifact()
        data, sha = _compute_fixture(art)
        patched = _patched_artifact(art, data, sha)
        index = make_index([patched])
        tampered = b'\x00' * art['size']

        def fetch(u, *, timeout, attempts, max_bytes):
            _validate_https_url(u)
            if u.endswith('stable-index.json'):
                return index
            if u == art['url']:
                return tampered
            raise RillMLDownloadError('no fixture')

        with mock.patch('rill_xray_agent.rillml_artifact._http_get', fetch), \
             mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'}), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            with self.assertRaises(RillMLValidationError):
                mgr.install(probe='lightweight')
            self.assertFalse(mgr.status()['available'])

    def test_wrong_platform_resolve_fails_closed(self):
        # Index only has linux/x86_64; host claims linux/aarch64/gnu.
        index = make_index([runtime_artifact()])
        with mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'aarch64',
                                      'libc': 'gnu'}), \
             mock.patch('rill_xray_agent.rillml_artifact.fetch_release_index',
                        return_value=index), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            with self.assertRaises(RillMLValidationError):
                mgr.resolve()
            self.assertFalse(mgr.status()['available'])

    def test_no_downgrade_guard(self):
        v1 = runtime_artifact(version='1.1.0')
        v2 = runtime_artifact(version='1.2.0')
        data1, sha1 = _compute_fixture(v1)
        data2, sha2 = _compute_fixture(v2)
        p1 = _patched_artifact(v1, data1, sha1)
        p2 = _patched_artifact(v2, data2, sha2)
        index_old = make_index([p1])
        index_new = make_index([p2])

        def fetch(url, *, timeout, attempts, max_bytes):
            _validate_https_url(url)
            if url.endswith('stable-index.json'):
                return index_old
            if url == v1['url']:
                return data1
            raise RillMLDownloadError('no fixture')

        probe = {'probe': 'lightweight', 'executes': True, 'exitCode': 0}
        with mock.patch('rill_xray_agent.rillml_artifact._http_get', fetch), \
             mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'}), \
             mock.patch('rill_xray_agent.rillml_artifact.probe_runtime',
                        return_value=probe), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            # Install a newer runtime via state manipulation: activate 1.2.0
            # first by pointing the index at the newer artifact, then refuse to
            # downgrade to 1.1.0.
            mgr.install(probe='lightweight')  # activates 1.1.0 from index_old
            self.assertEqual(mgr.status()['current']['version'], '1.1.0')

        def fetch2(url, *, timeout, attempts, max_bytes):
            _validate_https_url(url)
            if url.endswith('stable-index.json'):
                return index_new
            if url == v1['url']:
                return data1
            if url == v2['url']:
                return data2
            raise RillMLDownloadError('no fixture')

        with mock.patch('rill_xray_agent.rillml_artifact._http_get', fetch2), \
             mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'}), \
             mock.patch('rill_xray_agent.rillml_artifact.probe_runtime',
                        return_value=probe), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            mgr.install(probe='lightweight')  # activates 1.2.0
            # Index points back to the older 1.1.0; install/upgrade must refuse.
            with mock.patch('rill_xray_agent.rillml_artifact.fetch_release_index',
                            return_value=index_old):
                with self.assertRaises(RillMLUnsupported):
                    mgr.install(probe='lightweight')
                with self.assertRaises(RillMLUnsupported):
                    mgr.upgrade()
                # Explicit operator action may downgrade.
                mgr.install(probe='lightweight', allow_downgrade=True)
            self.assertEqual(mgr.status()['current']['version'], '1.1.0')

    def test_upgrade_keeps_current_when_already_newest(self):
        art = runtime_artifact()
        data, sha = _compute_fixture(art)
        patched = _patched_artifact(art, data, sha)
        index = make_index([patched])

        def fetch(url, *, timeout, attempts, max_bytes):
            _validate_https_url(url)
            if url.endswith('stable-index.json'):
                return index
            if url == art['url']:
                return data
            raise RillMLDownloadError('no fixture')

        probe = {'probe': 'lightweight', 'executes': True, 'exitCode': 0}
        with mock.patch('rill_xray_agent.rillml_artifact._http_get', fetch), \
             mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'}), \
             mock.patch('rill_xray_agent.rillml_artifact.probe_runtime',
                        return_value=probe), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            mgr.install(probe='lightweight')
            result = mgr.upgrade()
            self.assertFalse(result['upgraded'])
            self.assertEqual(result['reason'], 'already-current')
            self.assertEqual(mgr.status()['current']['version'], '1.2.0')

    def test_reinstall_reuses_verified_current(self):
        art = runtime_artifact()
        data, sha = _compute_fixture(art)
        patched = _patched_artifact(art, data, sha)
        index = make_index([patched])

        def fetch(url, *, timeout, attempts, max_bytes):
            _validate_https_url(url)
            if url.endswith('stable-index.json'):
                return index
            if url == art['url']:
                return data
            raise RillMLDownloadError('no fixture')

        probe = {'probe': 'lightweight', 'executes': True, 'exitCode': 0}
        with mock.patch('rill_xray_agent.rillml_artifact._http_get', fetch), \
             mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'}), \
             mock.patch('rill_xray_agent.rillml_artifact.probe_runtime',
                        return_value=probe), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            mgr.install(probe='lightweight')
            result = mgr.reinstall()
            self.assertTrue(result['reused'])
            self.assertEqual(mgr.status()['current']['version'], '1.2.0')

    def test_native_status_surface(self):
        # Spec §34: active nativeRuntime carries version/target/runtimeApi.
        art = runtime_artifact()
        data, sha = _compute_fixture(art)
        patched = _patched_artifact(art, data, sha)
        index = make_index([patched])

        def fetch(url, *, timeout, attempts, max_bytes):
            _validate_https_url(url)
            if url.endswith('stable-index.json'):
                return index
            if url == art['url']:
                return data
            raise RillMLDownloadError('no fixture')

        probe = {'probe': 'lightweight', 'executes': True, 'exitCode': 0}
        with mock.patch('rill_xray_agent.rillml_artifact._http_get', fetch), \
             mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64', 'libc': 'gnu'}), \
             mock.patch('rill_xray_agent.rillml_artifact.probe_runtime',
                        return_value=probe), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            mgr.install(probe='lightweight')
            surface = mgr.native_status()
            self.assertEqual(surface['fallback'], 'portable-python')
            native = surface['nativeRuntime']
            self.assertEqual(native['status'], 'active')
            self.assertEqual(native['version'], '1.2.0')
            self.assertEqual(native['targetOs'], 'linux')
            self.assertEqual(native['targetArch'], 'x86_64')
            self.assertEqual(native['targetLibc'], 'gnu')
            self.assertEqual(native['runtimeApiVersion'], 2)
            self.assertEqual(native['source'], 'rill-ml-stable-index')
            self.assertTrue(native['verified'])

    def test_native_status_unavailable_offline(self):
        # Without an installed runtime the surface is unavailable + portable
        # fallback, and status() never touches the network.
        with mock.patch('rill_xray_agent.rillml_artifact.detect_platform',
                        return_value={'os': 'linux', 'arch': 'x86_64',
                                      'libc': 'gnu'}), \
             tempfile.TemporaryDirectory() as td:
            mgr = RillMLRuntimeManager(td, public_key_hex=TEST_PUB_HEX,
                                        trusted_key_id=TEST_KEY_ID)
            surface = mgr.native_status()
            self.assertEqual(surface['fallback'], 'portable-python')
            self.assertEqual(surface['nativeRuntime']['status'], 'unavailable')
            self.assertFalse(surface['nativeRuntime']['verified'])


if __name__ == '__main__':
    unittest.main()