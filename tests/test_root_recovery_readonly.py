import os
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.runtime_service import RuntimeService
from rill_xray_agent.root_txn import RootTransaction

ROOT = Path(__file__).resolve().parents[1]


def snapshot_txn(root: Path):
    """Capture hashes + mtimes of every file under the root txn area."""
    snap = {}
    if not root.exists():
        return snap
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink():
            snap[str(path.relative_to(root))] = (path.read_bytes(), path.stat().st_mtime_ns)
    return snap


def build_transaction(td, did, generation, managed_text='old'):
    r = Path(td)
    managed = r / 'managed'
    managed.write_text(managed_text)
    gen = r / 'gen'
    gen.write_text(f'{generation}\n')
    tx = RootTransaction(r / 'tx', r / 'delivery', gen)
    req = {'recommendationId': did, 'configurationGeneration': generation}
    tx.apply(req, managed, lambda: managed.write_text(managed_text + '-new'), lambda: True)
    return tx, managed, gen


class ReadOnlyRecoveryTests(unittest.TestCase):
    def test_scan_is_read_only(self):
        # scan_recovery_state must never create or modify a single file.
        with tempfile.TemporaryDirectory() as td:
            tx, managed, gen, work = build_no_commit(td, 'r1')
            before = snapshot(Path(td) / 'tx')
            rep = tx.scan_recovery_state()
            self.assertGreater(len(rep), 0)
            self.assertTrue(all('safe' in r and 'recoveryRequired' in r for r in rep))
            self.assertEqual(snapshot(Path(td) / 'tx'), before)
            self.assertEqual(gen.read_text().strip(), '1')

    def test_incomplete_startup_recovery_required_readonly(self):
        # A Runtime starting with an incomplete root transaction must come up,
        # report recovery-required, and modify ZERO transaction files.
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            txroot = r / 'tx'
            w = txroot / 'hash-dir'
            w.mkdir(parents=True)
            (w / 'state.json').write_text('{"state":"applied"}')
            gen = r / 'gen'
            gen.write_text('1\n')
            before = snapshot(txroot)
            svc = RuntimeService(r / 'state', txroot)
            self.assertTrue(svc.recovery_required)
            self.assertGreaterEqual(len(svc.recovery['unresolved']), 1)
            self.assertEqual(snapshot(txroot), before, 'Runtime must not rewrite tx area')
            self.assertEqual(gen.read_text().strip(), '1')
            h = svc.handle({'schemaVersion': 3, 'requestId': 'x', 'capability': 'route',
                            'method': 'health', 'body': {}})['result']
            self.assertEqual(h['status'], 'recovery-required')
            self.assertFalse(h['canRecommend'])
            self.assertFalse(h['canApply'])

    def test_rollback_unverified_is_never_safe(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            txroot = r / 'tx'
            w = txroot / 'd-rollback-unverified'
            w.mkdir(parents=True)
            (w / 'state.json').write_text('{"state":"rollbackUnverified"}')
            svc = RuntimeService(r / 'state', txroot)
            scan = [x for x in svc.txn_scan if x['workDir'] == 'd-rollback-unverified'][0]
            self.assertFalse(scan['safe'])
            self.assertTrue(scan['recoveryRequired'])

    def test_committed_history_unchanged_on_startup(self):
        # Committed transactions must not be re-materialized by startup.
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            txroot = r / 'tx'
            state = r / 'state'
            for gen in (1, 2, 3):
                managed = r / 'managed'
                gfile = state / 'generation'
                managed.write_text('base')
                gfile.parent.mkdir(parents=True, exist_ok=True)
                gfile.write_text(f'{gen}\n')
                tx = RootTransaction(txroot, state / 'delivery', gfile)
                req = {'recommendationId': f'd-{gen}', 'configurationGeneration': gen}
                tx.apply(req, managed, lambda: managed.write_text('new'), lambda: True)
                gen_final = int(gfile.read_text().strip())
            self.assertEqual(gen_final, 4)
            before_tx = snapshot(txroot)
            before_delivery = (state / 'delivery/route-delivery.json').read_bytes()
            svc = RuntimeService(state, txroot)
            self.assertFalse(svc.recovery_required)
            self.assertEqual(snapshot(txroot), before_tx)
            self.assertEqual((state / 'delivery/route-delivery.json').read_bytes(), before_delivery)
            self.assertEqual((state / 'generation').read_text().strip(), '4')
            h = svc.health_status()
            self.assertEqual(h['status'], 'ready')

    def test_systemd_readonly_contract_static(self):
        # P0-1 C: production systemd contract keeps the root txn area read-only
        # and the Runtime source must not invoke mutating recovery.
        unit = ROOT / 'systemd/rill-xray-agent-runtime.service'
        text = unit.read_text()
        self.assertIn('ReadOnlyPaths=/var/lib/rill-xray-agent-root', text)
        # The production Runtime must not run mutating recovery.
        runtime_src = (ROOT / 'python/rill_xray_agent/runtime_service.py').read_text()
        self.assertNotIn('.recover_all(', runtime_src)
        self.assertIn('.scan_recovery_state()', runtime_src)


def snapshot(root):
    out = {}
    if not root.exists():
        return out
    for path in sorted(root.rglob('*')):
        if path.is_file() and not path.is_symlink():
            out[str(path.relative_to(root))] = (path.read_bytes(), path.stat().st_mtime_ns)
    return out


def build_no_commit(td, did):
    r = Path(td)
    managed = r / 'managed'
    managed.write_text('base')
    gen = r / 'gen'
    gen.write_text('1\n')
    tx = RootTransaction(r / 'tx', r / 'delivery', gen)
    w = tx.root / tx.work_dir_name(did)
    w.mkdir(parents=True, exist_ok=True)
    (w / 'request.json').write_text('{"recommendationId":"%s","configurationGeneration":1}' % did)
    (w / 'state.json').write_text('{"state":"applied"}')
    return tx, managed, gen, w


if __name__ == '__main__':
    unittest.main()