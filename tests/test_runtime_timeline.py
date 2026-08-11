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


def _evt(event_type, component='xray'):
    return {'schemaVersion': 1, 'eventType': event_type, 'component': component, 'facts': {}}


class RuntimeTimelineTests(unittest.TestCase):
    def _svc(self, td, allowed=True):
        r = Path(td)
        return RuntimeService(r / 'state', r / 'tx',
                              allowed_uids=[os.getuid()] if allowed else [],
                              observation_path=r / 'status' / 'xray-observation.json',
                              timeline_dir=r / 'history')

    def test_timeline_returns_events(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            journal = EventJournal(r / 'history')
            journal.append_event(_evt('baseline_observed', 'agent'))
            journal.append_event(_evt('xray_config_changed'))
            svc = self._svc(td)
            out = svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'timeline', 'body': {}})
            self.assertTrue(out['ok'])
            self.assertTrue(out['result']['available'])
            types = [e['eventType'] for e in out['result']['events']]
            self.assertEqual(types, ['baseline_observed', 'xray_config_changed'])

    def test_timeline_available_false_on_missing_history(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(td)
            out = svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'timeline', 'body': {}})
            self.assertTrue(out['ok'])
            self.assertFalse(out['result']['available'])

    def test_diagnose_healthy(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            (r / 'status').mkdir(parents=True)
            # The diagnose path uses the real clock; a fresh observation is
            # required for HEALTHY, so capture with the current time.
            (r / 'status' / 'xray-observation.json').write_text(
                json.dumps(_obs(capturedAtEpochSeconds=int(time.time()))))
            svc = self._svc(td)
            out = svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'diagnose',
                              'body': {}}, peer_uid=os.getuid())
            self.assertTrue(out['ok'])
            self.assertEqual(out['result']['diagnosisCode'], 'HEALTHY')
            self.assertFalse(out['result']['canApply'])

    def test_diagnose_requires_privileged_peer(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(td, allowed=False)
            out = svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'diagnose',
                              'body': {}}, peer_uid=999999)
            self.assertFalse(out['ok'])

    def test_diagnose_missing_observation_insufficient(self):
        with tempfile.TemporaryDirectory() as td:
            svc = self._svc(td)
            out = svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'diagnose',
                              'body': {}}, peer_uid=os.getuid())
            self.assertTrue(out['ok'])
            self.assertEqual(out['result']['status'], 'insufficient-evidence')

    def test_runtime_reads_history_but_never_appends(self):
        with tempfile.TemporaryDirectory() as td:
            r = Path(td)
            journal = EventJournal(r / 'history')
            journal.append_event(_evt('baseline_observed', 'agent'))
            before = journal.verify()['events']
            svc = self._svc(td)
            svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'timeline', 'body': {}})
            svc.handle({'schemaVersion': 3, 'requestId': 'x', 'method': 'diagnose',
                        'body': {}}, peer_uid=os.getuid())
            after = EventJournal(r / 'history').verify()['events']
            self.assertEqual(before, after)


if __name__ == '__main__':
    unittest.main()