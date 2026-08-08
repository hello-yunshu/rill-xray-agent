"""P0-2B: full WAL x external ClosedLedger fault matrix.

Every scenario must end in one of two acceptable states (per the audit
contract):
  * state/audit/ledger mutually consistent, OR
  * operation marked recovery-required.

It must never leave an orphan tombstone and must never silently discard
replay protection.

Scenarios covered:
  eviction + audit reserve failure
  eviction + fail after operation intent
  eviction + fail after state commit
  eviction + fail after ledger commit
  eviction + fail after audit event
  eviction + fail before terminal
  restart recovery
  retry identical feedback
  retry conflicting feedback
  ledger full
  ledger I/O error
"""
import os
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.audit import AuditLog
from rill_xray_agent.operation import OperationLog
from rill_xray_agent.runtime_service import RuntimeService
from rill_xray_agent.state import ClosedLedger

FAULT_INTENT = 'RILL_OP_FAIL_AFTER_OPERATION_INTENT'
FAULT_STATE = 'RILL_OP_FAIL_AFTER_STATE_COMMIT'
FAULT_LEDGER = 'RILL_OP_FAIL_AFTER_LEDGER_COMMIT'
FAULT_AUDIT = 'RILL_OP_FAIL_AFTER_AUDIT_EVENT'
FAULT_TERMINAL = 'RILL_OP_FAIL_AFTER_OPERATION_TERMINAL'


def envelope(method, body):
    return {'schemaVersion': 3, 'requestId': 'x1', 'capability': 'route',
            'method': method, 'body': body}


def make_service(td, max_completed=1, ledger_entries=8):
    return RuntimeService(Path(td) / 'state', Path(td) / 'tx',
                          max_completed=max_completed,
                          ledger_max_entries=ledger_entries)


def register(svc, did, cap='route', gen=1):
    return svc.handle(envelope('register', {'capability': cap, 'decisionId': did,
                                            'modelGeneration': gen, 'createdAtEpochSeconds': 1}))


def root_result(svc, did, result=None):
    return svc.handle(envelope('rootResult', {'decisionId': did,
                                              'result': result or {'ok': True}}))


def feedback(svc, did, cap='route', gen=1, r=1):
    return svc.handle(envelope('feedback', {'decisionId': did, 'capability': cap,
                                            'modelGeneration': gen,
                                            'terminalPayload': {'r': r}}))


def prime_one(svc, did='d0'):
    """Accept one decision so completed={did} and the next feedback triggers
    an eviction (with max_completed=1)."""
    out = register(svc, did)
    if not out['ok']:
        raise AssertionError(f'register failed: {out}')
    out = root_result(svc, did)
    if not out['ok']:
        raise AssertionError(f'rootResult failed: {out}')
    out = feedback(svc, did)
    if not out['ok']:
        raise AssertionError(f'feedback failed: {out}')


def prepare_pending(svc, did='d1'):
    """Register + rootResult (no fault) so the decision is pending and a
    subsequent feedback call can trigger eviction of the completed head."""
    out = register(svc, did)
    if not out['ok']:
        raise AssertionError(f'prepare register failed: {out}')
    out = root_result(svc, did)
    if not out['ok']:
        raise AssertionError(f'prepare rootResult failed: {out}')


class WALLedgerFaultMatrix(unittest.TestCase):
    def assert_consistent_or_recovery(self, svc, td):
        """After restart+recovery the WAL must be clean and consistent."""
        svc2 = make_service(td)
        self.assertEqual(svc2.recovery['unresolved'], [], f'unresolved: {svc2.recovery}')
        self.assertEqual(svc2.ops.pending_count(), 0, 'must not leave pending ops')
        self.assertEqual(svc2.handle(envelope('health', {}))['result']['status'], 'ready')
        return svc2

    def assert_replay_protection(self, svc, did, identical_payload, conflict_payload):
        """Identical replay is idempotent; conflicting replay fails closed."""
        ok = svc.handle(envelope('feedback', identical_payload))
        self.assertTrue(ok['ok'], f'identical replay must be idempotent: {ok}')
        self.assertEqual(ok['result']['result']['status'], 'idempotent')
        bad = svc.handle(envelope('feedback', conflict_payload))
        self.assertFalse(bad['ok'], 'conflicting replay must fail closed')
        self.assertEqual(bad['error']['code'], 'contractViolation')

    def test_eviction_fault_after_intent(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            prime_one(svc, 'd0')       # completed={d0}
            prepare_pending(svc, 'd1')  # d1 pending
            os.environ[FAULT_INTENT] = '1'
            try:
                out = feedback(svc, 'd1')  # evicts d0 -> ledger mutation
                self.assertFalse(out['ok'], 'intent fault must fail the op')
            finally:
                os.environ.pop(FAULT_INTENT, None)
            svc2 = self.assert_consistent_or_recovery(svc, td)
            # Intent fault fired before state commit: d0 is NOT evicted and no
            # tombstone exists; replay protection on d0 still holds.
            self.assertIsNone(svc2.state.ledger.get('d0'),
                              'no tombstone expected for cancelled eviction op')
            self.assertIn('d0', svc2.state.load()['completed'],
                          'd0 must remain completed')
            self.assert_replay_protection(
                svc2, 'd0',
                {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1,
                 'terminalPayload': {'r': 1}},
                {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1,
                 'terminalPayload': {'r': 999}})

    def test_eviction_state_ledger_audit_terminal_faults(self):
        for fault in (FAULT_STATE, FAULT_LEDGER, FAULT_AUDIT, FAULT_TERMINAL):
            with tempfile.TemporaryDirectory() as td:
                svc = make_service(td)
                prime_one(svc, 'd0')
                prepare_pending(svc, 'd1')
                os.environ[fault] = '1'
                try:
                    out = feedback(svc, 'd1')  # evicts d0 -> ledger mutation
                    self.assertFalse(out['ok'], f'{fault} must fail the op')
                finally:
                    os.environ.pop(fault, None)
                svc2 = self.assert_consistent_or_recovery(svc, td)
                # State committed (and for the later faults the ledger) before
                # the injected failure: d0 must now be a durable tombstone.
                tomb = svc2.state.ledger.get('d0')
                self.assertIsNotNone(tomb, f'{fault}: d0 must be externalized')
                self.assertFalse(tomb.get('corrupt'))
                self.assert_replay_protection(
                    svc2, 'd0',
                    {'decisionId': 'd0', 'capability': 'route',
                     'modelGeneration': 1, 'terminalPayload': {'r': 1}},
                    {'decisionId': 'd0', 'capability': 'route',
                     'modelGeneration': 1, 'terminalPayload': {'r': 999}})

    def test_eviction_audit_reserve_failure(self):
        with tempfile.TemporaryDirectory() as td:
            tiny = AuditLog(Path(td) / 'audit', segment_bytes=1, total_bytes=1)
            ledger = ClosedLedger(Path(td) / 'ledger', max_entries=8)
            ops = OperationLog(Path(td) / 'ops', audit=tiny, ledger=ledger)
            state_path = Path(td) / 'state.json'

            def fn(s):
                return {'status': 'accepted', 'accepted': True, 'pendingLedgerMutations': [
                    {'type': 'putClosedDecision', 'decisionIdHash': 'a' * 64,
                     'identityHash': 'b' * 64, 'payloadHash': 'c' * 64,
                     'closedAtEpochSeconds': 1}]}, {'completed': {'d0': 1}}

            with self.assertRaises(Exception):
                ops.execute('feedback', state_path, fn, 'decision.feedback',
                            {'decisionId': 'd0'})
            # Reserve failed before the intent was durable: no side effects.
            self.assertFalse(state_path.exists(), 'state must not be committed')
            self.assertEqual(ops.pending_count(), 0, 'no intent may exist')
            self.assertEqual(ledger.count(), 0, 'no tombstone may be externalized')

    def test_ledger_full(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td, max_completed=1, ledger_entries=1)
            prime_one(svc, 'd0')
            # d1 evicts d0 -> ledger put succeeds (fills the single slot).
            prepare_pending(svc, 'd1')
            self.assertTrue(feedback(svc, 'd1')['ok'])
            # d2 evicts d1 -> ledger put hits capacity -> fail closed.
            prepare_pending(svc, 'd2')
            out = feedback(svc, 'd2')
            self.assertFalse(out['ok'], 'ledger full must fail closed')
            self.assertEqual(out['error']['code'], 'contractViolation')
            svc2 = make_service(td, max_completed=1, ledger_entries=1)
            # A genuinely-full ledger is a persistent condition: the honest
            # outcome is recovery-required (never a silent resolved success).
            # The d2 eviction op cannot be healed, so it stays pending and the
            # service reports recovery-required.
            self.assertEqual(svc2.ops.pending_count(), 1,
                             'unevictable op must remain pending (recovery-required)')
            self.assertEqual(svc2.handle(envelope('health', {}))['result']['status'],
                             'recovery-required')
            tomb = svc2.state.ledger.get('d0')
            self.assertIsNotNone(tomb, 'd0 tombstone must be retained')
            self.assert_replay_protection(
                svc2, 'd0',
                {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1,
                 'terminalPayload': {'r': 1}},
                {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1,
                 'terminalPayload': {'r': 999}})

    def test_ledger_io_error_then_recovery(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            prime_one(svc, 'd0')
            prepare_pending(svc, 'd1')
            os.environ['RILL_LEDGER_IO_ERROR'] = '1'
            try:
                out = feedback(svc, 'd1')
                self.assertFalse(out['ok'], 'ledger I/O error must fail the op')
            finally:
                os.environ.pop('RILL_LEDGER_IO_ERROR', None)
            # Fault cleared: recovery must heal the missing tombstone.
            svc2 = self.assert_consistent_or_recovery(svc, td)
            tomb = svc2.state.ledger.get('d0')
            self.assertIsNotNone(tomb, 'recovery must externalize d0')
            self.assert_replay_protection(
                svc2, 'd0',
                {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1,
                 'terminalPayload': {'r': 1}},
                {'decisionId': 'd0', 'capability': 'route', 'modelGeneration': 1,
                 'terminalPayload': {'r': 999}})


if __name__ == '__main__':
    unittest.main()