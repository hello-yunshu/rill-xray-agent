"""Runtime / feedback E2E (spec 15.4-15.7).

Full decision lifecycle across a Runtime restart:

    create observation + timeline
    -> diagnose                          (decision registered)
    -> inspect(diagnosisId)              (pending)
    -> feedback                          (moves to completed, fields preserved)
    -> inspect again
    -> restart Runtime
    -> inspect again                     (feedback persisted)

Plus:
    - fake feedback (random id) rejected
    - same-evidence diagnose idempotent (same diagnosisId, no conflict)
    - same-feedback idempotent
    - secret/redaction regression (secrets never persist through feedback)
"""
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from rill_xray_agent.event_journal import EventJournal
from rill_xray_agent.runtime_service import RuntimeService


def _obs(**kw):
    base = {
        'schemaVersion': 1, 'capturedAtEpochSeconds': 1000,
        'xrayConfig': {'present': True, 'safe': True, 'sha256': 'a' * 64},
        'nginxConfig': {'present': True, 'safe': True, 'treeSha256': 'b' * 64, 'files': 2},
        'installConfig': {'present': True, 'safe': True, 'sha256': 'c' * 64},
        'xrayValidation': {'ok': True, 'returnCode': 0},
        'nginxValidation': {'ok': True, 'returnCode': 0},
        'services': {'xray': {'ok': True, 'returnCode': 0}, 'nginx': {'ok': True, 'returnCode': 0}},
    }
    base.update(kw)
    return base


class RuntimeFeedbackE2ETests(unittest.TestCase):
    def _scratch(self, td):
        r = Path(td)
        (r / 'status').mkdir(parents=True)
        (r / 'status' / 'xray-observation.json').write_text(
            json.dumps(_obs(capturedAtEpochSeconds=int(time.time()))))
        return r

    def _svc(self, r):
        return RuntimeService(r / 'state', r / 'tx',
                              allowed_uids=[os.getuid()],
                              observation_path=r / 'status' / 'xray-observation.json',
                              timeline_dir=r / 'history')

    def _diagnose(self, svc):
        return svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'diagnose',
                           'body': {}}, peer_uid=os.getuid())

    def _feedback(self, svc, did, outcome='resolved', helpful=True, correct=True, extra=None):
        body = {'decisionId': did, 'outcome': outcome,
                'helpful': helpful, 'diagnosisCorrect': correct}
        if extra:
            body.update(extra)
        return svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'feedback',
                           'body': body}, peer_uid=os.getuid())

    def _fb_result(self, out):
        """The op wrapper nests the actual result under result['result']."""
        return out['result']['result']

    def _inspect(self, svc, did):
        return svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'inspect',
                           'body': {'decisionId': did}}, peer_uid=os.getuid())

    def test_full_lifecycle_survives_restart(self):
        with tempfile.TemporaryDirectory() as td:
            r = self._scratch(td)
            svc = self._svc(r)
            # 1. diagnose -> decision registered (pending)
            out = self._diagnose(svc)
            self.assertTrue(out['ok'], out)
            result = out['result']
            did = result['diagnosisId']
            gen = result['engineGeneration']
            self.assertEqual(result['status'], 'healthy')
            self.assertFalse(result['canApply'])
            # 2. inspect -> pending decision present
            ins = self._inspect(svc, did)
            self.assertTrue(ins['result']['pending'])
            # 3. feedback -> accepted, moves to completed
            fb = self._feedback(svc, did)
            self.assertTrue(fb['ok'], fb)
            self.assertTrue(self._fb_result(fb)['accepted'])
            # 4. inspect again -> completed, feedback fields preserved
            ins = self._inspect(svc, did)
            completed = ins['result']['completed']
            self.assertIsNotNone(completed)
            self.assertEqual(completed['identity']['capability'], 'doctor')
            self.assertEqual(completed['identity']['modelGeneration'], gen)
            # payloadMeta must carry the structured doctor fields
            self.assertEqual(completed['payloadMeta']['outcome'], 'resolved')
            self.assertIs(completed['payloadMeta']['helpful'], True)
            self.assertIs(completed['payloadMeta']['diagnosisCorrect'], True)
            # 5. restart Runtime (same roots)
            svc2 = self._svc(r)
            ins = self._inspect(svc2, did)
            completed = ins['result']['completed']
            self.assertIsNotNone(completed)
            self.assertEqual(completed['payloadMeta']['outcome'], 'resolved')
            self.assertEqual(completed['identity']['modelGeneration'], gen)

    def test_diagnose_same_evidence_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(self._scratch(td))
            a = self._diagnose(svc)
            b = self._diagnose(svc)
            self.assertEqual(a['result']['diagnosisId'], b['result']['diagnosisId'])
            # re-registration is idempotent, no identity conflict
            ins = self._inspect(svc, a['result']['diagnosisId'])
            self.assertTrue(ins['ok'])

    def test_same_feedback_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(self._scratch(td))
            did = self._diagnose(svc)['result']['diagnosisId']
            first = self._feedback(svc, did)
            self.assertTrue(self._fb_result(first)['accepted'])
            second = self._feedback(svc, did)
            self.assertTrue(second['ok'], second)
            self.assertEqual(self._fb_result(second)['status'], 'idempotent')

    def test_conflicting_feedback_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(self._scratch(td))
            did = self._diagnose(svc)['result']['diagnosisId']
            self._feedback(svc, did, outcome='resolved')
            # a different outcome for the same decision is a conflict
            conflict = self._feedback(svc, did, outcome='not-resolved')
            self.assertFalse(conflict['ok'], conflict)

    def test_fake_feedback_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(self._scratch(td))
            out = self._feedback(svc, 'deadbeef' * 8)
            self.assertFalse(out['ok'])
            self.assertEqual(out['error']['code'], 'unknownDecision')

    def test_secret_in_feedback_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(self._scratch(td))
            did = self._diagnose(svc)['result']['diagnosisId']
            out = self._feedback(svc, did, extra={'comment': 'vless://secret', 'helpful': True})
            self.assertFalse(out['ok'])
            # nothing was persisted
            ins = self._inspect(svc, did)
            self.assertIsNone(ins['result']['completed'])

    def test_feedback_preserves_only_structured_fields(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(self._scratch(td))
            did = self._diagnose(svc)['result']['diagnosisId']
            fb = self._feedback(svc, did, outcome='not-applicable',
                                helpful=False, correct=False)
            self.assertTrue(fb['ok'], fb)
            completed = self._inspect(svc, did)['result']['completed']
            pm = completed['payloadMeta']
            self.assertEqual(pm['outcome'], 'not-applicable')
            self.assertIs(pm['helpful'], False)
            self.assertIs(pm['diagnosisCorrect'], False)
            # no free-text / secret keys leaked into stored metadata
            self.assertNotIn('comment', pm)
            self.assertFalse(any('vless' in str(v) for v in pm.values()))

    def test_runtime_never_writes_to_observation_tree(self):
        with tempfile.TemporaryDirectory() as td:
            r = self._scratch(td)
            journal = EventJournal(r / 'history')
            journal.append_event({'schemaVersion': 1, 'eventType': 'baseline_observed',
                                  'component': 'agent', 'facts': {}})
            before = journal.verify()['events']
            svc = self._svc(r)
            self._diagnose(svc)
            self._feedback(svc, self._diagnose(svc)['result']['diagnosisId'])
            after = EventJournal(r / 'history').verify()['events']
            self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()