"""Observer transition crash-idempotency fault matrix (spec 10, P1-A).

Drives the canonical `commit_transition` path through real crash windows using
the test-only `fault` injection hook (never set in production). Every case
proves one of the required properties:

  A  baseline crash before any event append  -> baseline exactly once
  B  baseline committed, crash before obs    -> baseline exactly once
  C  single-event transition crash before obs-> same transition only once
  D  multi-event partial commit -> restart    -> event1 not dup, event2..N done
  E  all events committed, crash before obs   -> no duplicates, converge to O1
  F  observation committed, crash after       -> no duplicate (O1,O1 -> no-op)
  G  same real transition happens again later -> still recorded (no over-dedup)
"""
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.canonical import atomic_write_json
from rill_xray_agent.event_journal import EventJournal
from rill_xray_agent.observer_transition import CHECKPOINT_NAME, commit_transition


def _obs(xray_sha='A', xray_ok=True, xray_svc=True,
         nginx_sha='A', nginx_ok=True, nginx_svc=True,
         install=False):
    """A safe observation whose semantic state is controllable per component."""
    return {
        'schemaVersion': 1,
        'capturedAtEpochSeconds': 1000,
        'xrayConfig': {'present': True, 'safe': True, 'sha256': xray_sha},
        'nginxConfig': {'present': True, 'safe': True, 'sha256': nginx_sha},
        'installConfig': {'present': install,
                          'safe': True, 'sha256': 'i' if install else None},
        'xrayValidation': {'ok': xray_ok},
        'nginxValidation': {'ok': nginx_ok},
        'services': {'xray': {'ok': xray_svc}, 'nginx': {'ok': nginx_svc}},
    }


def _count(journal, transition_id):
    """Number of surviving committed events carrying `transition_id`."""
    return sum(1 for e in journal.read() if e.get('transitionId') == transition_id)


class ObserverTransitionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory(prefix='rxa-oi-')
        self.root = Path(self._td.name)
        self.journal = EventJournal(self.root / 'history')
        self.out = self.root / 'xray-observation.json'
        self.checkpoint = self.root / CHECKPOINT_NAME

    def tearDown(self):
        self._td.cleanup()

    def _commit(self, previous, current, fault=None):
        return commit_transition(self.journal, self.out, self.checkpoint,
                                 previous, current, fault=fault)

    # -- Case A ---------------------------------------------------------
    def test_a_baseline_crash_before_event_append(self):
        baseline = _obs()
        with self.assertRaises(RuntimeError):
            self._commit(None, baseline, fault='after-checkpoint')
        r = self._commit(None, baseline)  # restart, no fault
        self.assertTrue(r['transition'])
        self.assertEqual(r['appended'], 1)
        self.assertEqual(r['idempotent'], 0)
        events = self.journal.read()
        self.assertEqual([e['eventType'] for e in events], ['baseline_observed'])
        self.assertEqual(len(events), 1)

    # -- Case B ---------------------------------------------------------
    def test_b_baseline_committed_crash_before_observation_replace(self):
        baseline = _obs()
        with self.assertRaises(RuntimeError):
            self._commit(None, baseline, fault='before-observation-replace')
        self.assertFalse(self.out.exists())  # observation not yet replaced
        r = self._commit(None, baseline)  # restart
        self.assertEqual(r['appended'], 0)
        self.assertEqual(r['idempotent'], 1)
        events = self.journal.read()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['eventType'], 'baseline_observed')

    # -- Case C ---------------------------------------------------------
    def test_c_single_event_transition_crash_before_observation(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')  # one event: xray_config_changed
        atomic_write_json(self.out, o0)  # disk already holds O0 (previous)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')
        self.assertEqual(self.journal.read()[0]['eventType'], 'xray_config_changed')
        r = self._commit(o0, o1)  # restart resume: previous still O0
        self.assertEqual(r['appended'], 0)
        self.assertEqual(r['idempotent'], 1)
        kinds = [e['eventType'] for e in self.journal.read()]
        self.assertEqual(kinds.count('xray_config_changed'), 1)

    # -- Case D ---------------------------------------------------------
    def test_d_multi_event_partial_commit_restart(self):
        o0 = _obs(xray_sha='A', xray_ok=True, xray_svc=True)
        o1 = _obs(xray_sha='B', xray_ok=False, xray_svc=False)
        atomic_write_json(self.out, o0)  # disk already holds O0 (previous)
        # 3 events: xray_config_changed, xray_validation_failed, xray_service_down
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='after-event-1')  # crash after event 1
        r = self._commit(o0, o1)  # restart resume
        self.assertEqual(r['idempotent'], 1)  # event 1 skipped
        self.assertEqual(r['appended'], 2)    # event 2..3 completed
        kinds = [e['eventType'] for e in self.journal.read() if e.get('transitionId')]
        self.assertEqual(kinds.count('xray_config_changed'), 1)
        self.assertEqual(kinds.count('xray_validation_failed'), 1)
        self.assertEqual(kinds.count('xray_service_down'), 1)

    # -- Case E ---------------------------------------------------------
    def test_e_all_events_committed_crash_before_observation(self):
        o0 = _obs(xray_sha='A', xray_ok=True, xray_svc=True)
        o1 = _obs(xray_sha='B', xray_ok=False, xray_svc=False)
        atomic_write_json(self.out, o0)  # disk already holds O0 (previous)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')
        before = self.journal.read()
        self.assertEqual(len(before), 3)  # all committed, obs not replaced
        r = self._commit(o0, o1)  # restart
        self.assertEqual(r['appended'], 0)
        self.assertEqual(r['idempotent'], 3)  # no duplicates
        self.assertEqual(len(self.journal.read()), 3)
        self.assertTrue(self.out.exists())  # observation converges to O1

    # -- Case F ---------------------------------------------------------
    def test_f_observation_committed_crash_after(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='after-observation-replace')
        self.assertTrue(self.out.exists())  # obs replaced before the crash
        r = self._commit(o1, o1)  # restart: derive_events(O1,O1) -> no-op
        self.assertFalse(r['transition'])
        self.assertEqual(r['appended'], 0)
        self.assertEqual(len(self.journal.read()), 1)  # no duplicate
        self.assertEqual(self.journal.read()[0]['eventType'], 'xray_config_changed')

    # -- Case G ---------------------------------------------------------
    def test_g_same_real_transition_again_later_is_recorded(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')
        # first real O0 -> O1
        r1 = self._commit(o0, o1)
        self.assertTrue(r1['transition'])
        first_id = self.journal.read()[0]['transitionId']
        # then genuinely O1 -> O0
        self._commit(o1, o0)
        # then again O0 -> O1 (a real second occurrence)
        r3 = self._commit(o0, o1)
        self.assertTrue(r3['transition'])
        self.assertEqual(r3['appended'], 1)
        # second real O0->O1 MUST be recorded: exactly 2 occurrences.
        self.assertEqual(_count(self.journal, first_id), 2)


if __name__ == '__main__':
    unittest.main()