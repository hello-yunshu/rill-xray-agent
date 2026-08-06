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
    def svc(self, td, max_completed=8):
        return RuntimeService(Path(td) / 'state', Path(td) / 'tx')

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
            svc = self.svc(td)
            self.evict_all(svc)
            state = svc.state.load()
            self.assertLessEqual(len(state['completed']), svc.state.max_completed)
            self.assertEqual(len(state['closed']), 12 - len(state['completed']))
            for did, tomb in state['closed'].items():
                self.assertEqual(tomb['decisionIdHash'], digest(did))
                self.assertEqual(set(tomb), {'decisionIdHash', 'identityHash', 'payloadHash', 'closedAtEpochSeconds'})

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

    def test_state_api_eviction(self):
        with tempfile.TemporaryDirectory() as td:
            st = RuntimeState(Path(td) / 's.json', max_completed=2)
            for i in range(4):
                did = f'q{i}'
                st.register('route', did, 1, 1)
                st.commit_root_result(did, {'ok': True})
                st.feedback({'decisionId': did, 'capability': 'route', 'modelGeneration': 1, 'terminalPayload': {}})
            s = st.load()
            self.assertEqual(len(s['completed']), 2)
            self.assertEqual(len(s['closed']), 2)
            self.assertTrue(all(set(t) == {'decisionIdHash', 'identityHash', 'payloadHash', 'closedAtEpochSeconds'}
                                for t in s['closed'].values()))
            again = st.feedback({'decisionId': 'q0', 'capability': 'route', 'modelGeneration': 1, 'terminalPayload': {}})
            self.assertEqual(again['status'], 'idempotent')
            with self.assertRaises(Exception) as cm:
                st.feedback({'decisionId': 'q0', 'capability': 'route', 'modelGeneration': 1, 'terminalPayload': {'x': 1}})
            self.assertIn('closed', str(cm.exception))


if __name__ == '__main__':
    unittest.main()
