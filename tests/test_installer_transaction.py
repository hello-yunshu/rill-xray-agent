import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh'


@unittest.skipUnless(os.name == 'posix', 'installer transaction runs on POSIX')
class InstallerTransactionTest(unittest.TestCase):
    def test_destdir_upgrade_copy_failure_restores_previous_payload(self):
        with tempfile.TemporaryDirectory(prefix='rill-installer-txn-') as td:
            temp = Path(td)
            prefix = temp / 'root'
            old_exe = prefix / 'opt/rill-xray-agent/bin/rill-xray-agent'
            old_exe.parent.mkdir(parents=True)
            old_exe.write_text('#!/bin/sh\necho previous\n')
            old_exe.chmod(0o755)
            (prefix / 'opt/rill-xray-agent/bin/previous-marker').write_text('old payload')
            config = prefix / 'etc/rill-xray-agent/config.json'
            config.parent.mkdir(parents=True)
            config.write_text('{"mode":"observe-only","routeAssistEnabled":false,"boundedAutoAllowed":false}\n')

            wrapper_dir = temp / 'bin'
            wrapper_dir.mkdir()
            marker = temp / 'failed-once'
            cp = wrapper_dir / 'cp'
            cp.write_text(
                '#!/bin/sh\n'
                'for last do :; done\n'
                'case "$last" in\n'
                '  *"/opt/rill-xray-agent/")\n'
                '    if [ ! -e "$RILL_FAIL_CP_MARKER" ]; then : > "$RILL_FAIL_CP_MARKER"; exit 42; fi\n'
                '    ;;\n'
                'esac\n'
                'exec /bin/cp "$@"\n')
            cp.chmod(0o755)
            env = dict(os.environ)
            env.update({'DESTDIR': str(prefix), 'PATH': f'{wrapper_dir}:{env.get("PATH", "")}',
                        'RILL_FAIL_CP_MARKER': str(marker)})
            result = subprocess.run(['bash', str(INSTALLER), '--upgrade'], env=env,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    text=True, timeout=120)
            self.assertNotEqual(result.returncode, 0, result.stdout)
            self.assertTrue(marker.exists(), result.stdout)
            self.assertEqual(old_exe.read_text(), '#!/bin/sh\necho previous\n')
            self.assertEqual((prefix / 'opt/rill-xray-agent/bin/previous-marker').read_text(),
                             'old payload')
            self.assertEqual(config.read_text(),
                             '{"mode":"observe-only","routeAssistEnabled":false,"boundedAutoAllowed":false}\n')
            tx_root = prefix / 'var/lib/rill-xray-agent-root/transactions'
            self.assertFalse(list(tx_root.glob('.upgrade-*')))


if __name__ == '__main__':
    unittest.main()
