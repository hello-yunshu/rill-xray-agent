import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.canonical import digest
from rill_xray_agent.runtime_service import RuntimeService
from rill_xray_agent.state import RuntimeState


def envelope(method, body):
    return {'schemaVersion': 3, 'requestId': 'x1', 'capability': 'route', 'method': method, 'body': body}


class Tests(unittest.TestCase):
    def svc(self, td, max_completed=2, ledger_entries=16):
        return RuntimeService(Path(td) / 'state', Path(td) / 'tx', max_completed=max_completed,
                              ledger_max_entries=ledger_entries)

    def envelope(self, method, body):
        return {'schemaVersion': 3, 'requestId': 'x1', 'capability': 'route', 'method': method, 'body': body}

    def full(self, svc, did, gen=1, cap='route', result={'ok': True}, payload=None):
        reg = {'capability': cap, 'decisionId': did, 'modelGeneration': gen, 'createdAtEpochSeconds': 1}
        out = svc.handle(self.envelope('register', reg))
        self.assertTrue(out['ok'], out)
        if cap == 'route':
            self.assertTrue(svc.handle(self.envelope('rootResult', {'decisionId': did, 'result': result}))['ok'])
        fb = payload or {'decisionId': did, 'capability': cap, 'modelGeneration': gen, 'terminalPayload': {'r': 1}}
        out = svc.handle(self.envelope('feedback', fb))
        self.assertTrue(out['ok'], out)
        return fb

    def evict_all(self, svc, n=12):
        for i in range(n):
            self.full(svc, f'd{i}')

    def test_eviction_moves_to_closed_tombstone(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self.svc(td, max_completed=2, ledger_entries=16)
            self.evict_all(svc)
            state = svc.state.load()
            self.assertLessEqual(len(state['completed']), 2)
            self.assertEqual(len(state['completed']), 2)
            self.assertNotIn('closed', state, 'external ledger is the single source of truth')
            ledger = svc.state.ledger
            self.assertGreaterEqual(ledger.count(), 1)
            entries = ledger.entries()
            self.assertEqual(len(entries), ledger.count())
            self.assertIsNone(state.get('closed'))

    def test_replay_after_eviction_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self.svc(td)
            self.evict_all(svc)
            fb = {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1, 'terminalPayload': {'r': 1}}
            out = svc.handle(self.envelope('feedback', fb))
            self.assertTrue(out['ok'], out)
            self.assertEqual(out['result']['result']['status'], 'idempotent')
            self.assertEqual(svc.audit.verify()['events'], 36, 'replay must not add audit events')

    def test_replay_conflict_after_eviction(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self.svc(td)
            self.evict_all(svc)
            fb = {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1, 'terminalPayload': {'r': 999}}
            out = svc.handle(self.envelope('feedback', fb))
            self.assertFalse(out['ok'], out)
            self.assertEqual(out['error']['code'], 'contractViolation')

    def test_register_same_identity_after_eviction_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self.svc(td)
            self.evict_all(svc)
            reg = {'capability': 'route', 'decisionId': 'd0', 'modelGeneration': 1, 'createdAtEpochSeconds': 1}
            out = svc.handle(self.envelope('register', reg))
            self.assertTrue(out['ok'], out)
            self.assertEqual(out['result']['result']['status'], 'idempotent')

    def test_register_different_identity_after_eviction_conflict(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self.svc(td)
            self.evict_all(svc)
            reg = {'capability': 'route', 'decisionId': 'd0', 'modelGeneration': 2, 'createdAtEpochSeconds': 1}
            out = svc.handle(self.envelope('register', reg))
            self.assertFalse(out['ok'], out)
            self.assertEqual(out['error']['code'], 'contractViolation')

    def test_single_feedback_transaction_entry(self):
        # P1: RuntimeState.feedback (the second, direct-ledger transaction
        # path) was removed; the ONLY production feedback mutation entry is
        # RuntimeService -> OperationLog. Eviction therefore flows through the
        # WAL and 'closed' never lives in the state mirror.
        with tempfile.TemporaryDirectory() as td:
            st = RuntimeState(Path(td) / 's.json', max_completed=2, max_ledger_entries=8)
            self.assertFalse(hasattr(st, 'feedback'),
                             'RuntimeState must not expose a direct feedback mutation')
            svc = RuntimeService(Path(td) / 'state', Path(td) / 'tx',
                                 max_completed=2, ledger_max_entries=8)
            for i in range(4):
                did = f'q{i}'
                reg = {'capability': 'route', 'decisionId': did, 'modelGeneration': 1,
                       'createdAtEpochSeconds': 1}
                out = svc.handle(self.envelope('register', reg))
                self.assertTrue(out['ok'], out)
                self.assertTrue(svc.handle(self.envelope('rootResult', {'decisionId': did,
                                                                        'result': {'ok': True}}))['ok'])
                fb = {'decisionId': did, 'capability': 'route', 'modelGeneration': 1,
                      'terminalPayload': {}}
                out = svc.handle(self.envelope('feedback', fb))
                self.assertTrue(out['ok'], out)
            s = svc.state.load()
            self.assertEqual(len(s['completed']), 2)
            self.assertNotIn('closed', s, 'external ledger is the single source of truth')
            self.assertTrue(all(set(t) == {'payloadHash', 'closedAtEpochSeconds'}
                                for t in svc.state.ledger.entries().values()))
            svc2 = RuntimeService(Path(td) / 'state', Path(td) / 'tx',
                                  max_completed=2, ledger_max_entries=8)
            again = {'decisionId': 'q0', 'capability': 'route', 'modelGeneration': 1,
                     'terminalPayload': {}}
            out = svc2.handle(self.envelope('feedback', again))
            self.assertTrue(out['ok'], out)
            self.assertEqual(out['result']['result']['status'], 'idempotent')
            conflict = {'decisionId': 'q0', 'capability': 'route', 'modelGeneration': 1,
                        'terminalPayload': {'x': 1}}
            out = svc2.handle(self.envelope('feedback', conflict))
            self.assertFalse(out['ok'], 'conflicting replay must fail closed')
            self.assertIn('closed', out['error']['message'].lower())

    def test_ledger_externalized_on_disk(self):
        from rill_xray_agent.state import ClosedLedger
        with tempfile.TemporaryDirectory() as td:
            ledger = ClosedLedger(Path(td) / 'ledger', max_entries=2)
            ledger.put('d0', digest('id0'), digest('p0'), 1000)
            ledger.put('d1', digest('id1'), digest('p1'), 1000)
            self.assertEqual(ledger.count(), 2)
            self.assertTrue((Path(td) / 'ledger' / f'{digest("d0")}.json').is_file())
            with self.assertRaises(Exception) as cm:
                ledger.put('d2', digest('id2'), digest('p2'), 1000)
            self.assertEqual(cm.exception.__class__.__name__, 'LedgerFullError')
            self.assertIsNone(ledger.get('never'))
            self.assertFalse((Path(td) / 'ledger' / f'{digest("d0")}.json').read_text().__contains__('decision0_id'))

    def test_put_hashed_identical_tombstone_idempotent(self):
        """P0-2A: the identical tombstone must succeed regardless of the
        replay window (even inside it) instead of failing as ledger full."""
        from rill_xray_agent.state import ClosedLedger
        with tempfile.TemporaryDirectory() as td:
            ledger = ClosedLedger(Path(td) / 'l1', max_entries=1,
                                  replay_protection_seconds=21600)
            ledger.put('d0', digest('id0'), digest('p0'), 1000)  # inside window now
            self.assertTrue(ledger.put('d0', digest('id0'), digest('p0'), 1000),
                            'identical tombstone must be idempotent in-window')
            self.assertEqual(ledger.count(), 1)

    def test_put_hashed_conflict_fails_closed(self):
        """P0-2A: same decision, differing identity or payload -> fail closed
        even when the replay window has expired."""
        from rill_xray_agent.state import ClosedLedger
        with tempfile.TemporaryDirectory() as td:
            ledger = ClosedLedger(Path(td) / 'l2', max_entries=4,
                                  replay_protection_seconds=1)
            ledger.put_hashed(digest('d0'), digest('id0'), digest('p0'), 1000 - 100000)
            with self.assertRaises(Exception) as cm:
                ledger.put_hashed(digest('d0'), digest('id1'), digest('p0'), 1000)
            self.assertEqual(cm.exception.__class__.__name__, 'LedgerFullError')
            with self.assertRaises(Exception) as cm:
                ledger.put_hashed(digest('d0'), digest('id0'), digest('p1'), 1000)
            self.assertEqual(cm.exception.__class__.__name__, 'LedgerFullError')
            self.assertEqual(ledger.count(), 1, 'conflict must not add entries')

    def test_put_hashed_capacity_with_identical_idempotent(self):
        """P0-2A: at capacity, a repeated identical entry stays idempotent
        while a genuinely new entry fails closed."""
        from rill_xray_agent.state import ClosedLedger
        with tempfile.TemporaryDirectory() as td:
            ledger = ClosedLedger(Path(td) / 'l3', max_entries=1)
            ledger.put_hashed(digest('d0'), digest('id0'), digest('p0'), 1000)
            self.assertTrue(ledger.put_hashed(digest('d0'), digest('id0'), digest('p0'), 1000),
                            'identical at capacity must still be idempotent')
            with self.assertRaises(Exception) as cm:
                ledger.put_hashed('d1', digest('id1'), digest('p1'), 1000)
            self.assertEqual(cm.exception.__class__.__name__, 'LedgerFullError')


if __name__ == '__main__':
    unittest.main()
