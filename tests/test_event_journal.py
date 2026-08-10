import json
import os
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.event_journal import EventJournal, EventJournalError
from rill_xray_agent.events import derive_events, config_digest, EVENT_TYPES


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


class EventDerivationTests(unittest.TestCase):
    def test_baseline_when_no_previous(self):
        events = derive_events(None, _obs())
        self.assertEqual([e['eventType'] for e in events], ['baseline_observed'])

    def test_same_observation_no_duplicate_event(self):
        events = derive_events(_obs(), _obs())
        self.assertEqual(events, [])

    def test_config_change_detected(self):
        changed = _obs(xrayConfig={'present': True, 'safe': True, 'sha256': 'd' * 64})
        events = derive_events(_obs(), changed)
        types = [e['eventType'] for e in events]
        self.assertIn('xray_config_changed', types)
        self.assertNotIn('nginx_config_changed', types)

    def test_validation_fail_recover(self):
        failed = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        types = [e['eventType'] for e in derive_events(_obs(), failed)]
        self.assertIn('xray_validation_failed', types)
        recovered = derive_events(failed, _obs())
        self.assertIn('xray_validation_recovered', [e['eventType'] for e in recovered])

    def test_service_down_up(self):
        down = _obs(services={'xray': {'ok': False, 'returnCode': 3}, 'nginx': {'ok': True}})
        types = [e['eventType'] for e in derive_events(_obs(), down)]
        self.assertIn('xray_service_down', types)
        up = derive_events(down, _obs())
        self.assertIn('xray_service_up', [e['eventType'] for e in up])

    def test_unsafe_path_detected(self):
        unsafe = _obs(xrayConfig={'present': True, 'safe': False})
        events = derive_events(_obs(), unsafe)
        self.assertIn('unsafe_path_detected', [e['eventType'] for e in events])

    def test_event_types_are_allowed(self):
        for e in derive_events(None, _obs()):
            self.assertIn(e['eventType'], EVENT_TYPES)


class EventJournalTests(unittest.TestCase):
    def test_append_and_read_order(self):
        with tempfile.TemporaryDirectory() as td:
            j = EventJournal(Path(td) / 'h')
            e1 = {'schemaVersion': 1, 'eventType': 'baseline_observed', 'component': 'agent', 'facts': {}}
            e2 = {'schemaVersion': 1, 'eventType': 'xray_config_changed', 'component': 'xray', 'facts': {}}
            j.append_event(e1)
            j.append_event(e2)
            events = j.read()
            self.assertEqual(len(events), 2)
            self.assertEqual([e['eventType'] for e in events], ['baseline_observed', 'xray_config_changed'])
            self.assertEqual(events[0]['sequence'], 1)
            self.assertEqual(events[1]['sequence'], 2)
            self.assertTrue(all(e['eventId'] for e in events))

    def test_limit_returns_most_recent(self):
        with tempfile.TemporaryDirectory() as td:
            j = EventJournal(Path(td) / 'h')
            for i in range(5):
                j.append_event({'schemaVersion': 1, 'eventType': 'xray_config_changed', 'component': 'xray', 'facts': {'i': i}})
            recent = j.read(limit=2)
            self.assertEqual(len(recent), 2)
            self.assertEqual([e['facts']['i'] for e in recent], [3, 4])

    def test_bounded_rollover_keeps_ring_buffer(self):
        with tempfile.TemporaryDirectory() as td:
            # tiny caps force constant rollover
            j = EventJournal(Path(td) / 'h', segment_bytes=300, total_bytes=600)
            for i in range(60):
                j.append_event({'schemaVersion': 1, 'eventType': 'xray_config_changed',
                                'component': 'xray', 'facts': {'i': i}})
            events = j.read()
            self.assertLessEqual(len(events), 60)
            # total size must never exceed the bound after rollover
            total = sum(p.stat().st_size for p in j._data_segments())
            self.assertLessEqual(total, 600)
            # sequences remain monotonic even after rollover
            seqs = [e['sequence'] for e in events]
            self.assertEqual(seqs, sorted(seqs))

    def test_read_only_rejects_append(self):
        with tempfile.TemporaryDirectory() as td:
            j = EventJournal(Path(td) / 'h', read_only=True)
            with self.assertRaises(EventJournalError):
                j.append_event({'schemaVersion': 1, 'eventType': 'xray_config_changed',
                                'component': 'xray', 'facts': {}})

    def test_symlink_segment_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            real = EventJournal(td / 'real')
            real.append_event({'schemaVersion': 1, 'eventType': 'baseline_observed', 'component': 'agent', 'facts': {}})
            attacker = td / 'other'
            attacker.mkdir()
            EventJournal(attacker).append_event({'schemaVersion': 1, 'eventType': 'xray_config_changed', 'component': 'xray', 'facts': {}})
            (td / 'h').mkdir()
            (td / 'h' / 'events-000001.jsonl').symlink_to(attacker / 'events-000001.jsonl')
            j = EventJournal(td / 'h', read_only=True)
            with self.assertRaises(EventJournalError):
                j.read()

    def test_corrupt_entry_detected(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            root = td / 'h'
            root.mkdir()
            j = EventJournal(root)
            j.append_event({'schemaVersion': 1, 'eventType': 'baseline_observed', 'component': 'agent', 'facts': {}})
            seg = root / 'events-000001.jsonl'
            seg.write_text(seg.read_text() + 'not-json\n')
            with self.assertRaises(EventJournalError):
                j.read()

    def test_verify(self):
        with tempfile.TemporaryDirectory() as td:
            j = EventJournal(Path(td) / 'h')
            for i in range(3):
                j.append_event({'schemaVersion': 1, 'eventType': 'xray_config_changed', 'component': 'xray', 'facts': {}})
            result = j.verify()
            self.assertEqual(result['events'], 3)


if __name__ == '__main__':
    unittest.main()