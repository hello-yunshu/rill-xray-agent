"""Observer transition crash-idempotency fault matrix (spec 10, P1-A / P1-B).

Drives the canonical `commit_transition` / `recover_pending_transition` paths
through real crash windows using the test-only `fault` injection hook (never
set in production). Every case proves one of the required properties:

  A  baseline crash before any event append    -> baseline exactly once
  B  baseline committed, crash before obs      -> baseline exactly once
  C  single-event transition crash before obs  -> same transition only once
  D  multi-event partial commit -> restart     -> event1 not dup, event2..N done
  E  all events committed, crash before obs    -> no duplicates, converge to O1
  F  observation committed, crash after        -> no duplicate (O1,O1 -> no-op)
  G  same real transition happens again later  -> still recorded (no over-dedup)

  H  pending O0->O1, live moved to O2 while down -> recover O0->O1 THEN O1->O2
  I  multi-event pending + live moved to O2       -> complete O0->O1, then O1->O2
  J  malformed checkpoint                     -> observer fails closed
  K  symlink checkpoint                       -> observer fails closed
  L  checkpoint eventTransitionIds tampered   -> observer fails closed
  M  same booleans but returnCode changes     -> pending recovered from projection

Plus checkpoint-integrity and recovery-ordering regression cases.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.canonical import atomic_write_json
from rill_xray_agent.errors import ObserverTransitionError
from rill_xray_agent.event_journal import EventJournal
from rill_xray_agent.events import observation_state_fingerprint
from rill_xray_agent.observer_transition import (CHECKPOINT_NAME, commit_transition,
                                                 load_checkpoint,
                                                 recover_pending_transition)

HEX64 = '0' * 64


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

    def _recover(self, fault=None):
        return recover_pending_transition(self.journal, self.out,
                                          self.checkpoint, fault=fault)

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

    # -- Case H (critical): pending O0->O1, live moved to O2 -------------
    def test_h_pending_recovered_first_when_live_changed(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')
        o2 = _obs(xray_sha='C')
        atomic_write_json(self.out, o0)  # disk anchor = O0
        # observer sees O1, crash before observation replace (event durable)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')
        # host changes O1 -> O2 while observer is down
        # restart: FIRST recover pending O0->O1 from the checkpoint projection
        recovered = self._recover()
        self.assertEqual(observation_state_fingerprint(recovered),
                         observation_state_fingerprint(o1))
        # THEN process the live O2 as a new transition O1 -> O2
        r = self._commit(recovered, o2)
        self.assertTrue(r['transition'])
        events = self.journal.read()
        kinds = [e['eventType'] for e in events]
        # O0->O1 (A->B) and O1->O2 (B->C): two config changes, no duplicates
        self.assertEqual(kinds.count('xray_config_changed'), 2)
        ids = [e['transitionId'] for e in events]
        self.assertEqual(len(ids), len(set(ids)))  # every transition exactly once
        self.assertFalse(self.checkpoint.exists())

    # -- Case I: multi-event pending + live current changes --------------
    def test_i_multi_event_pending_then_live_changed(self):
        o0 = _obs(xray_sha='A', xray_ok=True, xray_svc=True)
        o1 = _obs(xray_sha='B', xray_ok=False, xray_svc=False)
        o1['xrayValidation']['returnCode'] = 1
        o2 = _obs(xray_sha='C', xray_ok=False, xray_svc=False)
        o2['xrayValidation']['returnCode'] = 2
        atomic_write_json(self.out, o0)
        # partial commit: crash after event 1 of 3
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='after-event-1')
        # host evolves to O2 during downtime
        recovered = self._recover()
        self.assertEqual(observation_state_fingerprint(recovered),
                         observation_state_fingerprint(o1))
        # O0->O1 now fully complete: 3 events
        self.assertEqual(len(self.journal.read()), 3)
        # then O1 -> O2 (config C; validation stays failed, service stays down)
        r = self._commit(recovered, o2)
        self.assertTrue(r['transition'])
        events = self.journal.read()
        kinds = [e['eventType'] for e in events]
        self.assertEqual(kinds.count('xray_config_changed'), 2)   # A->B and B->C
        self.assertEqual(kinds.count('xray_validation_failed'), 1)  # only O0->O1
        self.assertEqual(kinds.count('xray_service_down'), 1)       # only O0->O1
        ids = [e['transitionId'] for e in events]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertFalse(self.checkpoint.exists())

    # -- Case J: malformed checkpoint fails closed -----------------------
    def test_j_malformed_checkpoint_fails_closed(self):
        valid = {
            'schemaVersion': 2,
            'previousStateDigest': HEX64,
            'currentStateDigest': '1' * 64,
            'eventTransitionIds': ['2' * 64],
            'currentObservation': {'xrayConfig': {'present': True, 'safe': True,
                                                  'sha256': 'A'}},
        }
        variants = {
            'invalid-json': '{not json',
            'empty': '',
            'not-object': '[1,2]',
            'wrong-schema': {**valid, 'schemaVersion': 1},
            'missing-current-digest':
                {k: v for k, v in valid.items() if k != 'currentStateDigest'},
            'invalid-digest': {**valid, 'currentStateDigest': 'not-hex'},
            'ids-wrong-type': {**valid, 'eventTransitionIds': 'notalist'},
            'ids-empty': {**valid, 'eventTransitionIds': []},
            'duplicate-ids': {**valid, 'eventTransitionIds': ['2' * 64, '2' * 64]},
            'invalid-transition-id': {**valid, 'eventTransitionIds': ['zz']},
            'missing-current-observation':
                {k: v for k, v in valid.items() if k != 'currentObservation'},
            'current-observation-wrong-type': {**valid, 'currentObservation': []},
        }
        for name, payload in variants.items():
            with self.subTest(name=name):
                text = json.dumps(payload) if isinstance(payload, dict) else payload
                self.checkpoint.write_text(text)
                with self.assertRaises(ObserverTransitionError):
                    load_checkpoint(self.checkpoint)
                # fail closed: checkpoint untouched, journal + observation unwritten
                self.assertTrue(self.checkpoint.exists())
                self.assertEqual(self.journal.read(), [])
                self.assertFalse(self.out.exists())

    def test_j_malformed_checkpoint_blocks_recovery(self):
        self.checkpoint.write_text('{bad json')
        with self.assertRaises(ObserverTransitionError):
            self._recover()

    # -- Case K: symlink checkpoint fails closed -------------------------
    def test_k_symlink_checkpoint_fails_closed(self):
        target = self.root / 'ext-checkpoint.json'
        target.write_text(json.dumps({
            'schemaVersion': 2,
            'previousStateDigest': HEX64,
            'currentStateDigest': '1' * 64,
            'eventTransitionIds': ['2' * 64],
            'currentObservation': {},
        }))
        self.checkpoint.symlink_to(target)
        with self.assertRaises(ObserverTransitionError):
            load_checkpoint(self.checkpoint)
        # symlink target is never followed / used; nothing is written
        self.assertTrue(self.checkpoint.is_symlink())
        self.assertEqual(self.journal.read(), [])
        self.assertFalse(self.out.exists())
        with self.assertRaises(ObserverTransitionError):
            self._recover()

    def test_k_non_regular_checkpoint_fails_closed(self):
        self.checkpoint.mkdir()  # a directory is not a legal checkpoint
        with self.assertRaises(ObserverTransitionError):
            load_checkpoint(self.checkpoint)

    # -- Case L: eventTransitionIds tampered (structurally valid) --------
    def test_l_checkpoint_ids_mismatch_fails_closed(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')
        atomic_write_json(self.out, o0)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')
        # tamper the id plan (still structurally valid 64-hex ids)
        cp = json.loads(self.checkpoint.read_text())
        cp['eventTransitionIds'] = ['f' * 64]
        self.checkpoint.write_text(json.dumps(cp))
        with self.assertRaises(ObserverTransitionError):
            self._recover()
        # fail closed: event journal, observation and checkpoint unchanged
        self.assertEqual(len(self.journal.read()), 1)
        self.assertEqual(json.loads(self.out.read_text())['xrayConfig']['sha256'], 'A')
        self.assertTrue(self.checkpoint.exists())

    def test_l_checkpoint_projection_inconsistent_fails_closed(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')
        atomic_write_json(self.out, o0)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')
        # tamper the saved projection so it no longer matches currentStateDigest
        cp = json.loads(self.checkpoint.read_text())
        cp['currentObservation'] = _obs(xray_sha='Z')
        self.checkpoint.write_text(json.dumps(cp))
        with self.assertRaises(ObserverTransitionError):
            self._recover()
        self.assertTrue(self.checkpoint.exists())

    # -- Case M: same booleans but returnCode changes --------------------
    def test_m_same_booleans_but_returncode_changes(self):
        o0 = _obs(xray_sha='A', xray_ok=True, xray_svc=True)
        # O1: validation FAIL rc=1 (config unchanged -> no config event)
        o1 = _obs(xray_sha='A', xray_ok=False, xray_svc=True)
        o1['xrayValidation']['returnCode'] = 1
        # live O2: same booleans, rc=2
        o2 = _obs(xray_sha='A', xray_ok=False, xray_svc=True)
        o2['xrayValidation']['returnCode'] = 2
        atomic_write_json(self.out, o0)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')
        # the committed event facts carry the pending rc=1, not live rc=2
        self.assertEqual(self.journal.read()[0]['facts']['returnCode'], 1)
        # restart: recovery must use the checkpoint projection (rc=1)
        recovered = self._recover()
        self.assertEqual(recovered['xrayValidation']['returnCode'], 1)
        # fingerprints of O1 and O2 are equal (returnCode is not in the digest)
        self.assertEqual(observation_state_fingerprint(o1),
                         observation_state_fingerprint(o2))
        # O1 -> O2 (rc change alone) is a no-op transition
        r = self._commit(recovered, o2)
        self.assertFalse(r['transition'])
        self.assertEqual(len(self.journal.read()), 1)  # no duplicate, no new event

    # -- recovery ordering: commit must not skip a pending transition ----
    def test_commit_fails_closed_on_unrecovered_pending(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')
        o2 = _obs(xray_sha='C')
        atomic_write_json(self.out, o0)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')  # pending O0->O1
        # committing O0->O2 directly (skipping recovery) must fail closed
        with self.assertRaises(ObserverTransitionError):
            self._commit(o0, o2)
        self.assertEqual(len(self.journal.read()), 1)
        self.assertTrue(self.checkpoint.exists())
        self.assertEqual(json.loads(self.out.read_text())['xrayConfig']['sha256'], 'A')

    # -- recovery itself is idempotent across a crash mid-recovery --------
    def test_recovery_is_idempotent_across_crash(self):
        o0 = _obs(xray_sha='A')
        o1 = _obs(xray_sha='B')
        atomic_write_json(self.out, o0)
        with self.assertRaises(RuntimeError):
            self._commit(o0, o1, fault='before-observation-replace')
        with self.assertRaises(RuntimeError):
            self._recover(fault='before-pending-observation')
        # crash before observation write: checkpoint still present, anchor O0
        self.assertTrue(self.checkpoint.exists())
        self.assertEqual(json.loads(self.out.read_text())['xrayConfig']['sha256'], 'A')
        # second recovery completes exactly once
        recovered = self._recover()
        self.assertEqual(observation_state_fingerprint(recovered),
                         observation_state_fingerprint(o1))
        self.assertEqual(len(self.journal.read()), 1)
        self.assertFalse(self.checkpoint.exists())

    # -- no-pending fast path ---------------------------------------------
    def test_recover_returns_none_when_no_pending(self):
        self.assertIsNone(self._recover())


if __name__ == '__main__':
    unittest.main()