"""Doctor feedback replay through REAL ClosedLedger eviction (P1-3).

The same Doctor feedback must be idempotent in all four lifecycle states:

    pending -> completed -> evicted (closed ledger) -> after restart

Even after a completed decision is evicted to the ClosedLedger, the tombstone
retains the safe feedback identity metadata (capability, modelGeneration) so
the canonical feedback projection can be rebuilt: exact replay PASSES, any
change to outcome/helpful/diagnosisCorrect is a conflict, and the semantics
survive a Runtime restart. Tombstones never store raw config, secrets or free
text.
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from rill_xray_agent.runtime_service import RuntimeService


def _obs(root, captured=None):
    obs = {
        'schemaVersion': 1, 'capturedAtEpochSeconds': int(captured or time.time()),
        'xrayConfig': {'present': True, 'safe': True, 'sha256': 'a' * 64},
        'nginxConfig': {'present': True, 'safe': True, 'treeSha256': 'b' * 64, 'files': 2},
        'installConfig': {'present': True, 'safe': True, 'sha256': 'c' * 64},
        'xrayValidation': {'ok': True, 'returnCode': 0},
        'nginxValidation': {'ok': True, 'returnCode': 0},
        'services': {'xray': {'ok': True, 'returnCode': 0}, 'nginx': {'ok': True, 'returnCode': 0}},
    }
    (root / 'status').mkdir(parents=True, exist_ok=True)
    (root / 'status' / 'xray-observation.json').write_text(json.dumps(obs))
    return root


class ClosedFeedbackReplayTests(unittest.TestCase):
    def _svc(self, r, max_completed=1):
        return RuntimeService(r / 'state', r / 'tx',
                              allowed_uids=[os.getuid()],
                              max_completed=max_completed,
                              observation_path=r / 'status' / 'xray-observation.json',
                              timeline_dir=r / 'history')

    def _req(self, svc, method, body):
        return svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': method,
                           'body': body}, peer_uid=os.getuid())

    def _diagnose(self, svc):
        return self._req(svc, 'diagnose', {})

    def _feedback(self, svc, did, outcome='resolved', helpful=True, correct=True, extra=None):
        body = {'decisionId': did, 'outcome': outcome,
                'helpful': helpful, 'diagnosisCorrect': correct}
        if extra:
            body.update(extra)
        return self._req(svc, 'feedback', body)

    def _inspect(self, svc, did):
        return self._req(svc, 'inspect', {'decisionId': did})

    def _evict_pair(self, r, captured_a, captured_b):
        """diagnose A + feedback A, then diagnose B + feedback B (distinct
        evidence -> distinct diagnosisId). With max_completed=1 the second
        accepted feedback evicts the lexicographically-first completed
        decision, so the caller re-inspects to learn WHICH one is closed."""
        _obs(r, captured=captured_a)
        svc = self._svc(r, max_completed=1)
        a = self._diagnose(svc)
        self.assertTrue(a['ok'], a)
        did_a = a['result']['diagnosisId']
        self.assertTrue(self._feedback(svc, did_a)['ok'])
        _obs(r, captured=captured_b)
        b = self._diagnose(svc)
        self.assertTrue(b['ok'], b)
        did_b = b['result']['diagnosisId']
        self.assertNotEqual(did_a, did_b, 'distinct evidence -> distinct decision')
        self.assertTrue(self._feedback(svc, did_b)['ok'])
        evicted, survivor = None, None
        for did in (did_a, did_b):
            ins = self._inspect(svc, did)
            if ins['result']['closed'] is not None:
                evicted = (did, ins['result']['closed'])
            elif ins['result']['completed'] is not None:
                survivor = did
        self.assertIsNotNone(evicted, 'one decision must be evicted')
        self.assertIsNotNone(survivor, 'one decision must remain completed')
        return svc, did_a, did_b, evicted, survivor

    def test_exact_replay_idempotent_after_eviction_and_restart(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            now = int(time.time())
            svc, did_a, did_b, (evicted_did, tomb), _ = self._evict_pair(
                r, now - 60, now)
            # tombstone metadata: hashes + safe identity metadata only
            self.assertIn('capability', tomb)
            self.assertIn('modelGeneration', tomb)
            self.assertEqual(tomb['capability'], 'doctor')
            allow = {'decisionIdHash', 'identityHash', 'payloadHash',
                     'closedAtEpochSeconds', 'schemaVersion', 'capability',
                     'modelGeneration'}
            self.assertLessEqual(set(tomb), allow)
            self.assertFalse(any('vless' in str(v) for v in tomb.values()))
            # EXACT replay after eviction -> idempotent PASS
            replay = self._feedback(svc, evicted_did)
            self.assertTrue(replay['ok'], replay)
            self.assertEqual(replay['result']['result']['status'], 'idempotent')
            # restart -> exact replay still PASS
            svc2 = self._svc(r, max_completed=1)
            after = self._feedback(svc2, evicted_did)
            self.assertTrue(after['ok'], after)
            self.assertEqual(after['result']['result']['status'], 'idempotent')

    def test_conflicting_replay_after_eviction_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            now = int(time.time())
            svc, _, _, (evicted_did, tomb), _ = self._evict_pair(
                r, now - 60, now)
            self.assertIsNotNone(tomb)
            for delta in (
                    {'helpful': False},                # same outcome, changed helpful
                    {'diagnosisCorrect': False},       # changed diagnosisCorrect
                    {'outcome': 'not-resolved'},       # changed outcome
            ):
                body = {'decisionId': evicted_did, 'outcome': 'resolved',
                        'helpful': True, 'diagnosisCorrect': True}
                body.update(delta)
                conflict = self._req(svc, 'feedback', body)
                self.assertFalse(conflict['ok'], conflict)

    def test_restart_preserves_eviction_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            now = int(time.time())
            svc, _, _, (evicted_did, tomb), _ = self._evict_pair(
                r, now - 60, now)
            self.assertIsNotNone(tomb)
            svc2 = self._svc(r, max_completed=1)
            # restart -> exact replay PASS, conflict replay FAIL
            exact = self._feedback(svc2, evicted_did)
            self.assertTrue(exact['ok'], exact)
            self.assertEqual(exact['result']['result']['status'], 'idempotent')
            conflict = self._feedback(svc2, evicted_did, outcome='not-applicable')
            self.assertFalse(conflict['ok'], conflict)


if __name__ == '__main__':
    unittest.main()