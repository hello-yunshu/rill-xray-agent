import hashlib
import json
import stat
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from rill_xray_agent import backup
from rill_xray_agent.errors import BackupError


class BackupSecurityTest(unittest.TestCase):
    def test_safe_json_secret_beyond_two_mib_is_excluded_from_archive(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'state'
            root.mkdir()
            secret = b'vless://synthetic-secret@example.invalid#test'
            (root / 'timeline.json').write_bytes(b'{"events":"' + b'x' * (2 * 1024 * 1024) + secret + b'"}')
            archive = Path(td) / 'state.zip'
            manifest = backup.create_backup(archive, [('runtime', root)])
            self.assertEqual(manifest['entries'], [])
            with zipfile.ZipFile(archive) as zf:
                self.assertNotIn(secret, zf.read('MANIFEST.json'))
                self.assertEqual(zf.namelist(), ['MANIFEST.json'])

    def test_unknown_binary_and_recursive_secret_json_are_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'state'
            root.mkdir()
            (root / 'unknown.bin').write_bytes(b'ordinary bytes')
            (root / 'safe.json').write_text('{"nested":{"privateKey":"synthetic"}}')
            archive = Path(td) / 'state.zip'
            self.assertEqual(backup.create_backup(archive, [('runtime', root)])['entries'], [])

    def test_roundtrip_and_manifest_hash(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'state'
            root.mkdir()
            payload = b'{"mode":"observe-only"}\n'
            (root / 'state.json').write_bytes(payload)
            archive = Path(td) / 'state.zip'
            manifest = backup.create_backup(archive, [('runtime', root)])
            self.assertEqual(manifest['entries'][0]['sha256'], hashlib.sha256(payload).hexdigest())
            self.assertEqual(backup.verify_backup(archive), manifest)
            target = Path(td) / 'restored'
            backup.restore_backup(archive, target)
            self.assertEqual((target / 'runtime/state.json').read_bytes(), payload)

    def test_oversized_manifest_is_rejected_before_unbounded_read(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / 'oversized.zip'
            with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_STORED) as zf:
                zf.writestr('MANIFEST.json', b' ' * (backup.MAX_MANIFEST + 1))
            with self.assertRaises(BackupError):
                backup.verify_backup(archive)

    def test_manifest_missing_required_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            archive = Path(td) / 'missing-schema.zip'
            with zipfile.ZipFile(archive, 'w') as zf:
                zf.writestr('MANIFEST.json', b'{"entries":[]}')
            with self.assertRaises(BackupError):
                backup.verify_backup(archive)

    def test_short_write_and_interrupted_write_complete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            calls = []
            real_write = backup.os.write
            def short_write(fd, data):
                calls.append(len(data))
                if len(calls) == 1:
                    return real_write(fd, data[:2])
                if len(calls) == 2:
                    raise InterruptedError()
                if len(calls) == 3:
                    return real_write(fd, data[:1])
                return real_write(fd, data)
            with mock.patch('rill_xray_agent.safe_fs.os.write', side_effect=short_write):
                from rill_xray_agent.safe_fs import write_beneath
                write_beneath(root, 'data/runtime/state.json', b'abcdef')
            self.assertEqual((root / 'data/runtime/state.json').read_bytes(), b'abcdef')

    def test_zero_write_preserves_old_file_and_cleans_temporary(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            from rill_xray_agent.safe_fs import write_beneath
            write_beneath(root, 'data/runtime/state.json', b'old')
            with mock.patch('rill_xray_agent.safe_fs.os.write', return_value=0):
                with self.assertRaises(OSError):
                    write_beneath(root, 'data/runtime/state.json', b'new')
            self.assertEqual((root / 'data/runtime/state.json').read_bytes(), b'old')
            self.assertEqual(list((root / 'data/runtime').iterdir()), [root / 'data/runtime/state.json'])


if __name__ == '__main__':
    unittest.main()
