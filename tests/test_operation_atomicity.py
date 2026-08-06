import json
import os
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.audit import AuditLog
from rill_xray_agent.operation import OperationLog
from rill_xray_agent.runtime_service import RuntimeService

FAULTS = [
    ('RILL_OP_FAIL_AFTER_OPERATION_INTENT', 'state untouched'),
    ('RILL_OP_FAIL_AFTER_STATE_COMMIT', 'state committed, audit pending'),
    ('RILL_OP_FAIL_AFTER_AUDIT_EVENT', 'state and audit committed, terminal pending'),
    ('RILL_OP_FAIL_AFTER_OPERATION_TERMINAL', 'terminal written'),
]


def make_service(td):
    svc = RuntimeService(Path(td) / 'state', Path(td) / 'tx')
    return svc


class Tests(unittest.TestCase):
    def op_envelope(self, method, body):
        return {'schemaVersion': 3, 'requestId': 'x1', 'capability': 'route', 'method': method, 'body': body}

    def test_mode_roundtrip_with_audit(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            out = svc.handle(self.op_envelope('mode', {'mode': 'safe-disabled'}))
            self.assertTrue(out['ok'])
            self.assertEqual(out['result']['result']['mode'], 'safe-disabled')
            cfg = svc.handle(self.op_envelope('config', {}))['result']
            self.assertEqual(cfg['mode'], 'safe-disabled')
            self.assertEqual(svc.audit.verify()['events'], 1)
            self.assertEqual(svc.ops.pending_count(), 0)

    def test_fault_injection_recovery(self):
        for env_name, _desc in FAULTS:
            with tempfile.TemporaryDirectory() as td:
                os.environ[env_name] = '1'
                try:
                    svc = make_service(td)
                    out = svc.handle(self.op_envelope('mode', {'mode': 'normal'}))
                    self.assertFalse(out['ok'], f'{env_name} should fail')
                finally:
                    os.environ.pop(env_name, None)
                svc2 = make_service(td)
                report = svc2.recovery
                self.assertEqual(report['unresolved'], [], f'{env_name}: unresolved {report}')
                self.assertEqual(svc2.ops.pending_count(), 0, f'{env_name}: pending ops left')
                cfg = svc2.state.load()
                health = svc2.handle(self.op_envelope('health', {}))['result']
                self.assertEqual(health['status'], 'ready', f'{env_name}: health {health}')
                if env_name == 'RILL_OP_FAIL_AFTER_OPERATION_INTENT':
                    self.assertEqual(cfg['mode'], 'observe-only', f'{env_name}: intent fault must cancel op')
                    head = svc2.audit.verify()
                    self.assertEqual(head['events'], 0, f'{env_name}: no committed event expected {head}')
                else:
                    self.assertEqual(cfg['mode'], 'normal', f'{env_name}: state not consistent')
                    head = svc2.audit.verify()
                    self.assertEqual(head['events'], 1, f'{env_name}: audit events {head}')

    def test_audit_capacity_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            tiny = AuditLog(Path(td) / 'audit', segment_bytes=1, total_bytes=1)
            ops = OperationLog(Path(td) / 'ops', audit=tiny)
            state = Path(td) / 'state.json'

            def fn(s):
                return {'mode': 'normal'}, {'mode': 'normal'}

            with self.assertRaises(Exception):
                ops.execute('mode', state, fn, 'runtime.mode.changed', {'mode': 'normal'})
            self.assertFalse(state.exists(), 'state must not commit when audit capacity fails')
            self.assertEqual(ops.pending_count(), 0)

    def test_no_double_audit_on_restart_replay(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            out = svc.handle(self.op_envelope('mode', {'mode': 'observe-only'}))
            self.assertTrue(out['ok'])
            svc2 = make_service(td)
            self.assertEqual(svc2.audit.verify()['events'], 1)
            self.assertEqual(svc2.ops.pending_count(), 0)

    def test_register_feedback_flow_atomic(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            body = {'capability': 'route', 'decisionId': 'd-1', 'modelGeneration': 1, 'createdAtEpochSeconds': 1}
            self.assertTrue(svc.handle(self.op_envelope('register', body))['ok'])
            self.assertTrue(svc.handle(self.op_envelope('rootResult', {'decisionId': 'd-1', 'result': {'ok': True}}))['ok'])
            fb = {'decisionId': 'd-1', 'capability': 'route', 'modelGeneration': 1, 'terminalPayload': {'r': 1}}
            self.assertTrue(svc.handle(self.op_envelope('feedback', fb))['ok'])
            self.assertEqual(svc.audit.verify()['events'], 3)
            again = svc.handle(self.op_envelope('feedback', fb))
            self.assertTrue(again['ok'])
            self.assertEqual(again['result']['result']['status'], 'idempotent')
            self.assertEqual(svc.audit.verify()['events'], 3, 'idempotent replay must not add audit events')


if __name__ == '__main__':
    unittest.main()
