import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rill_xray_agent.canonical import digest
from rill_xray_agent.health import health, scan_transactions
from rill_xray_agent.root_txn import RootTransaction

STATES = ['prepared', 'applying', 'applied', 'verified', 'commit-intent',
          'rollback-intent', 'rollbackUnverified']

# Real crash points wired into root_txn.fault(): each maps to a durable
# persistence boundary in the production transaction.
COMMIT_POINTS = ['PREPARED', 'APPLYING', 'MANAGED_MUTATION', 'APPLIED', 'VERIFIED', 'COMMIT_INTENT']
ROLLBACK_POINTS = ['ROLLBACK_INTENT', 'MANAGED_RESTORE', 'GENERATION_RESTORE', 'ROLLBACK_BUNDLE',
                   'RESULT', 'RECEIPT', 'DELIVERY', 'TERMINAL']


class Tests(unittest.TestCase):
    def run_transaction(self, td, crash_at=None):
        r = Path(td)
        m = r / 'managed'
        m.write_text('old')
        g = r / 'gen'
        g.write_text('1\n')
        tx = RootTransaction(r / 'tx', r / 'delivery', g)
        req = {'recommendationId': 'd-1', 'configurationGeneration': 1}
        try:
            tx.apply(req, m, lambda: m.write_text('new'), lambda: True)
            outcome = 'committed'
        except Exception:
            outcome = 'crashed'
        w = tx.root / tx.work_dir_name('d-1')
        return tx, m, g, w, os.environ.pop('CRASH_EARLY', None)

    def test_hash_directory_is_used(self):
        with tempfile.TemporaryDirectory() as td:
            tx, m, g, w, _ = self.run_transaction(td)
            self.assertEqual(w.name, digest('d-1'))
            self.assertNotIn('d-1', w.name)

    def test_full_state_machine_committed(self):
        with tempfile.TemporaryDirectory() as td:
            tx, m, g, w, _ = self.run_transaction(td)
            self.assertEqual(read_state(w), 'committed')
            self.assertEqual(g.read_text().strip(), '2')
            h = health(Path(td) / 'state', tx.root)
            self.assertEqual(h['status'], 'ready')

    def test_rollback_state_machine(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            m = r / 'managed'
            m.write_text('old')
            g = r / 'gen'
            g.write_text('1\n')
            tx = RootTransaction(r / 'tx', r / 'delivery', g)
            req = {'recommendationId': 'd-2', 'configurationGeneration': 1}

            def apply_fn():
                m.write_text('partial')

            out = tx.apply(req, m, apply_fn, lambda: False)
            self.assertEqual(out['status'], 'rolledBack')
            self.assertEqual(read_state(tx.root / tx.work_dir_name('d-2')), 'rolledBack')
            self.assertEqual(m.read_text(), 'old')
            self.assertEqual(g.read_text().strip(), '1')

    def test_rollback_recovery_for_each_intermediate_state(self):
        for state in ['prepared', 'applying', 'applied', 'verified', 'commit-intent', 'rollback-intent', 'rollbackUnverified']:
            with tempfile.TemporaryDirectory() as td:
                r = Path(td)
                m = r / 'managed'
                m.write_text('old')
                g = r / 'gen'
                g.write_text('1\n')
                tx = RootTransaction(r / 'tx', r / 'delivery', g)
                w = tx.root / tx.work_dir_name('d-3')
                w.mkdir(parents=True, exist_ok=True)
                (w / 'request.json').write_text('{"recommendationId":"d-3","configurationGeneration":1}')
                (w / 'backup-metadata.json').write_text(
                    '{"managedExisted":true,"managedPath":"' + str(m) + '","oldGeneration":1,"newGeneration":2}')
                (w / 'managed.backup').write_text('old')
                if state in {'applying', 'applied', 'verified', 'commit-intent', 'rollback-intent'}:
                    m.write_text('partially-changed')
                if state == 'rollbackUnverified':
                    (w / 'managed.partial').write_text('x')
                (w / 'state.json').write_text('{"schemaVersion":1,"state":"' + state + '"}')
                tx.recover_all()
                self.assertEqual(read_state(w), 'rolledBack', state)
                self.assertEqual(m.read_text(), 'old', state)
                self.assertTrue((w / 'commit-bundle.json').exists(), state)
                self.assertTrue((r / 'delivery/route-delivery.json').is_file(), state)

    def test_recommendation_id_never_a_path(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            m = r / 'managed'
            m.write_text('old')
            g = r / 'gen'
            g.write_text('1\n')
            tx = RootTransaction(r / 'tx', r / 'delivery', g)
            for bad in ['../x', 'a/b', 'x' * 200, '', 'a b']:
                with self.assertRaises(Exception):
                    tx.apply({'recommendationId': bad, 'configurationGeneration': 1}, m, lambda: None, lambda: True)
            if (r / 'tx').exists():
                self.assertEqual(list((r / 'tx').iterdir()), [], 'no stray path dirs')

    def test_fault_at_each_commit_point_recoverable(self):
        for point in COMMIT_POINTS:
            with tempfile.TemporaryDirectory() as td:
                r = Path(td)
                m = r / 'managed'
                m.write_text('old')
                g = r / 'gen'
                g.write_text('1\n')
                tx = RootTransaction(r / 'tx', r / 'delivery', g)
                req = {'recommendationId': 'd-c', 'configurationGeneration': 1}
                with patch.dict(os.environ, {f'RILL_FAULT_{point}': '1'}):
                    try:
                        tx.apply(req, m, lambda: m.write_text('new'), lambda: True)
                    except Exception:
                        pass
                recovered = tx.recover_all()
                w = tx.root / tx.work_dir_name('d-c')
                self.assertIn(w.name, recovered, point)
                final = read_state(w)
                self.assertIn(final, {'committed', 'rolledBack'}, point)
                self.assertTrue((w / 'commit-bundle.json').exists(), point)
                h = health(Path(td) / 'state', tx.root)
                self.assertEqual(h['status'], 'ready', f'{point}: {h}')

    def test_fault_at_each_rollback_point_recoverable(self):
        for point in ROLLBACK_POINTS:
            with tempfile.TemporaryDirectory() as td:
                r = Path(td)
                m = r / 'managed'
                m.write_text('old')
                g = r / 'gen'
                g.write_text('1\n')
                tx = RootTransaction(r / 'tx', r / 'delivery', g)
                req = {'recommendationId': 'd-r', 'configurationGeneration': 1}
                with patch.dict(os.environ, {f'RILL_FAULT_{point}': '1'}):
                    def apply_fn():
                        m.write_text('partial')
                    try:
                        tx.apply(req, m, apply_fn, lambda: False)
                    except Exception:
                        pass
                w = tx.root / tx.work_dir_name('d-r')
                tx.recover_all()
                self.assertEqual(read_state(w), 'rolledBack', point)
                self.assertEqual(m.read_text(), 'old', point)
                self.assertTrue((r / 'delivery/route-delivery.json').is_file(), point)
                h = health(Path(td) / 'state', tx.root)
                self.assertEqual(h['status'], 'ready', f'{point}: {h}')

    def test_health_recovery_required_for_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            txroot = r / 'tx'
            w = txroot / 'some-dir'
            w.mkdir(parents=True)
            (w / 'state.json').write_text('{"state":"applied"}')
            self.assertEqual(health(r / 'state', txroot)['status'], 'recovery-required')
            self.assertEqual(scan_transactions(txroot)['incomplete'], 1)


def read_state(w):
    import json
    return json.loads((w / 'state.json').read_text())['state']


if __name__ == '__main__':
    unittest.main()