"""P0-2: global WAL mutation fence.

While ANY unfinished operation intent exists (or the OperationLog reports
recovery-required) every state mutation (register / rootResult / feedback /
mode) must fail closed with error code `recoveryRequired` through the SINGLE
unified WAL entry (OperationLog.execute), while read-only surfaces (health /
metrics / config / inspect / snapshot) stay available.

Scenarios covered:
  FAULT_INTENT      -> pending intent -> new register -> recoveryRequired
  FAULT_STATE       -> pending intent -> new mutation -> recoveryRequired
  FAULT_LEDGER      -> pending intent -> new mutation -> recoveryRequired
  FAULT_AUDIT       -> pending intent -> new mutation -> recoveryRequired
  FAULT_TERMINAL    -> pending intent -> new mutation -> recoveryRequired
  every mutation kind fenced (register/rootResult/feedback/mode), reads open
  replay gap: max_completed=1 + ledger full -> d1 feedback leaves pending
               -> register(d0, different identity) must be recoveryRequired
  fence releases: fault cleared + recover() -> pending_count=0 -> mutation OK
  stale WAL must never overwrite post-recovery committed state
"""
import os
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.runtime_service import RuntimeService

FAULTS = [
    'RILL_OP_FAIL_AFTER_OPERATION_INTENT',
    'RILL_OP_FAIL_AFTER_STATE_COMMIT',
    'RILL_OP_FAIL_AFTER_LEDGER_COMMIT',
    'RILL_OP_FAIL_AFTER_AUDIT_EVENT',
    'RILL_OP_FAIL_AFTER_OPERATION_TERMINAL',
]


def envelope(method, body):
    return {'schemaVersion': 3, 'requestId': 'x1', 'capability': 'route',
            'method': method, 'body': body}


def make_service(td, max_completed=1, ledger_entries=8):
    return RuntimeService(Path(td) / 'state', Path(td) / 'tx',
                          max_completed=max_completed,
                          ledger_max_entries=ledger_entries,
                          allowed_uids=[os.getuid()])


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
    for out in (register(svc, did), root_result(svc, did), feedback(svc, did)):
        if not out['ok']:
            raise AssertionError(f'prime {did} failed: {out}')


def prepare_pending(svc, did='d1'):
    for out in (register(svc, did), root_result(svc, did)):
        if not out['ok']:
            raise AssertionError(f'prepare {did} failed: {out}')


def read_methods(svc):
    return {
        'health': svc.handle(envelope('health', {})),
        'metrics': svc.handle(envelope('metrics', {})),
        'config': svc.handle(envelope('config', {})),
        'inspect': svc.handle(envelope('inspect', {'decisionId': 'd0'})),
        'snapshot': svc.handle(envelope('snapshot', {})),
    }


def assert_fenced(svc, did='d0'):
    for method, out in (
        ('register', register(svc, did, gen=9)),
        ('rootResult', root_result(svc, did)),
        ('feedback', feedback(svc, did)),
        ('mode', svc.handle(envelope('mode', {'mode': 'normal'}), peer_uid=os.getuid())),
    ):
        if out['ok']:
            raise AssertionError(f'{method} must be fenced while recovery is pending: {out}')
        if out['error']['code'] != 'recoveryRequired':
            raise AssertionError(f'{method} must return recoveryRequired, got {out}')


def assert_reads_ok(svc):
    for name, out in read_methods(svc).items():
        if not out['ok']:
            raise AssertionError(f'read {name} must stay available during fence: {out}')


class WALMutationFence(unittest.TestCase):

    def test_single_fault_within_eviction_blocks_all_mutations(self):
        for fault in FAULTS:
            with tempfile.TemporaryDirectory() as td:
                svc = make_service(td)
                prime_one(svc, 'd0')
                prepare_pending(svc, 'd1')
                os.environ[fault] = '1'
                try:
                    out = feedback(svc, 'd1')
                    self.assertFalse(out['ok'], f'{fault} must fail the op')
                finally:
                    os.environ.pop(fault, None)
                # The injected failure leaves an unfinished intent.
                self.assertEqual(svc.ops.pending_count(), 1,
                                 f'{fault}: intent must be pending')
                self.assertEqual(svc.handle(envelope('health', {}))['result']['status'],
                                 'recovery-required')
                # All four mutation kinds are fenced closed with the dedicated code.
                assert_fenced(svc)
                # Read surfaces stay available (and keep safe defaults).
                assert_reads_ok(svc)
                conf = svc.handle(envelope('config', {}))['result']
                self.assertFalse(conf['boundedAutoAllowed'])
                # Recovery clears the intent -> fence lifts.
                svc.ops.recover()
                self.assertEqual(svc.ops.pending_count(), 0)
                out = register(svc, 'd3')
                self.assertTrue(out['ok'], f'recovery must lift the fence: {out}')

    def test_pending_intent_blocks_register_even_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            prime_one(svc, 'd0')
            prepare_pending(svc, 'd1')
            os.environ['RILL_OP_FAIL_AFTER_STATE_COMMIT'] = '1'
            try:
                feedback(svc, 'd1')
            finally:
                os.environ.pop('RILL_OP_FAIL_AFTER_STATE_COMMIT', None)
            # Same identity replay is normally idempotent; while the WAL is
            # unfinished it must still fail closed (never silently re-run).
            out = svc.handle(envelope('register', {'capability': 'route', 'decisionId': 'd0',
                                                   'modelGeneration': 1, 'createdAtEpochSeconds': 1}))
            self.assertFalse(out['ok'])
            self.assertEqual(out['error']['code'], 'recoveryRequired')

    def test_replay_gap_eviction_full_ledger_blocked_until_resolved(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td, max_completed=1, ledger_entries=1)
            prime_one(svc, 'd0')        # completed={d0}, ledger empty
            prepare_pending(svc, 'd1')  # d1 pending
            out = feedback(svc, 'd1')   # evicts d0 -> d0 tombstone fills slot 1
            self.assertTrue(out['ok'], out)
            prepare_pending(svc, 'd2')  # d2 pending
            out = feedback(svc, 'd2')   # evicts d1 -> ledger capacity full
            self.assertFalse(out['ok'], 'ledger full must fail closed')
            self.assertEqual(out['error']['code'], 'contractViolation')
            self.assertEqual(svc.ops.pending_count(), 1,
                             'unevictable op must stay pending (recovery-required)')
            # Replay gap: d0 was already evicted to the ledger; re-registering
            # d0 with a DIFFERENT identity on the SAME runtime must be blocked
            # by the WAL fence, not evaluated against the ledger.
            out = register(svc, 'd0', gen=9)  # different identity
            self.assertFalse(out['ok'])
            self.assertEqual(out['error']['code'], 'recoveryRequired')
            # Reads stay open during the fence.
            assert_reads_ok(svc)
            # Resolve the persistent capacity obstruction, then recover:
            # the fence lifts and fresh mutations are accepted.
            from rill_xray_agent.canonical import digest
            stale = (Path(td) / 'state' / 'closed-ledger' / f'{digest("d0")}.json')
            stale.unlink()
            report = svc.ops.recover()
            self.assertFalse(report['unresolved'], report)
            self.assertEqual(svc.ops.pending_count(), 0)
            out = register(svc, 'd3')
            self.assertTrue(out['ok'], out)
            # The recovered WAL postState must not clobber the NEW committed
            # state: d3 must still be registered.
            s = svc.state.load()
            self.assertIn('d3', s['pending'])
            self.assertEqual(s['pending']['d3']['identity']['modelGeneration'], 1)

    def test_stale_wal_never_overwrites_post_recovery_state(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            prime_one(svc, 'd0')
            prepare_pending(svc, 'd1')
            os.environ['RILL_OP_FAIL_AFTER_OPERATION_INTENT'] = '1'
            try:
                feedback(svc, 'd1')  # fails right after the intent is durable
            finally:
                os.environ.pop('RILL_OP_FAIL_AFTER_OPERATION_INTENT', None)
            svc.ops.recover()  # cancels the pre-state intent -> fence lifted
            self.assertEqual(svc.ops.pending_count(), 0)
            # The pre-fault pending state (d1 registered + root result) must
            # survive untouched -- the stale WAL must never clobber it.
            s0 = svc.state.load()
            self.assertIn('d1', s0['pending'],
                          'pre-fault pending state must survive recovery')
            # Commit fresh state AFTER recovery.
            out = register(svc, 'd9')
            self.assertTrue(out['ok'], out)
            out = root_result(svc, 'd9')
            self.assertTrue(out['ok'], out)
            out = feedback(svc, 'd9')
            self.assertTrue(out['ok'], out)
            s = svc.state.load()
            self.assertIn('d9', s['completed'],
                          'post-recovery commits must survive intact')
            self.assertEqual(s['pending'].keys(), {'d1'},
                             'recovered pre-fault state must not be overwritten')

    def test_mode_mutation_fenced_and_config_read_safe(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            prime_one(svc, 'd0')
            prepare_pending(svc, 'd1')
            os.environ['RILL_OP_FAIL_AFTER_OPERATION_INTENT'] = '1'
            try:
                feedback(svc, 'd1')
            finally:
                os.environ.pop('RILL_OP_FAIL_AFTER_OPERATION_INTENT', None)
            out = svc.handle(envelope('mode', {'mode': 'safe-disabled'}), peer_uid=os.getuid())
            self.assertFalse(out['ok'])
            self.assertEqual(out['error']['code'], 'recoveryRequired')
            conf = svc.handle(envelope('config', {}))['result']
            self.assertEqual(conf['mode'], 'observe-only')
            self.assertFalse(conf['boundedAutoAllowed'])


if __name__ == '__main__':
    unittest.main()