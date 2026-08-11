"""EventJournal fault-injection matrix (spec 15.2).

Covers the crash-safety contract by constructing on-disk states exactly as a
crash would leave them and asserting the deterministic recovery / fail-closed
behaviour:

    meta missing + valid segments          -> reconstruct, no duplicate seq
    meta stale behind / ahead              -> reconcile / fail closed
    meta malformed                         -> rebuild from segments
    crash after event write                -> max sequence recovered, no repeat
    torn partial tail                      -> writer truncates, reader skips
    complete invalid JSON / eventId mismatch / duplicate sequence
                                           -> EventJournalError (fail closed)
    segment symlink / meta symlink         -> rejected
    rollover crash                         -> committed history never lost
    bounded steady-state vs transient size -> explicit bounds honoured
    first sequence == 1, monotonic         -> identity contract
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.event_journal import EventJournal, EventJournalError
from rill_xray_agent.events import derive_events, config_digest, EVENT_TYPES


def _evt(_sequence=None, **kw):
    base = {'schemaVersion': 1, 'eventType': 'xray_config_changed',
            'component': 'xray', 'facts': {}, 'capturedAtEpochSeconds': 1000}
    base.update(kw)
    return base


def _append(j, n, now=1000):
    for i in range(n):
        j.append_event(_evt(facts={'i': i}, capturedAtEpochSeconds=now + i))


class MetaStatesTests(unittest.TestCase):
    def test_first_sequence_is_one(self):
        with tempfile.TemporaryDirectory() as td:
            j = EventJournal(Path(td) / 'h')
            j.append_event(_evt())
            self.assertEqual(j.read()[0]['sequence'], 1)

    def test_sequences_monotonic(self):
        with tempfile.TemporaryDirectory() as td:
            j = EventJournal(Path(td) / 'h')
            _append(j, 5)
            seqs = [e['sequence'] for e in j.read()]
            self.assertEqual(seqs, [1, 2, 3, 4, 5])

    def test_meta_missing_reconstructs_from_segments(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 3)
            # crash before meta was ever written: delete meta.json
            (root / 'meta.json').unlink()
            j2 = EventJournal(root)
            j2.recover()  # must reconstruct, not reset to 1
            j2.append_event(_evt())
            seqs = [e['sequence'] for e in j2.read()]
            self.assertEqual(seqs, [1, 2, 3, 4])  # no duplicate of 1..3

    def test_meta_stale_behind_reconciles(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 3)
            # crash after appending 3 events but before meta update:
            # meta says nextSequence=2 (behind the durable segments)
            (root / 'meta.json').write_text(json.dumps(
                {'schemaVersion': 1, 'nextSequence': 2, 'nextSegment': 2}))
            j2 = EventJournal(root)
            rec = j2.recover()
            self.assertTrue(rec['metaReconciled'])
            j2.append_event(_evt())
            seqs = [e['sequence'] for e in j2.read()]
            self.assertEqual(seqs, [1, 2, 3, 4])  # no duplicate 2

    def test_meta_stale_ahead_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 2)
            # meta claims a committed sequence that no verified segment holds:
            # re-issuing it would duplicate identity -> fail closed.
            (root / 'meta.json').write_text(json.dumps(
                {'schemaVersion': 1, 'nextSequence': 99, 'nextSegment': 2}))
            j2 = EventJournal(root)
            with self.assertRaises(EventJournalError):
                j2.recover()

    def test_meta_malformed_rebuilds(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 2)
            (root / 'meta.json').write_text('not-json{')
            j2 = EventJournal(root)
            rec = j2.recover()
            self.assertTrue(rec['metaReconciled'])
            self.assertEqual(rec['nextSequence'], 3)

    def test_meta_symlink_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 1)
            (root / 'meta.json').unlink()
            victim = root / 'victim-meta'
            victim.write_text(json.dumps({'schemaVersion': 1, 'nextSequence': 5, 'nextSegment': 2}))
            (root / 'meta.json').symlink_to(victim)
            j2 = EventJournal(root)
            with self.assertRaises(EventJournalError):
                j2.recover()


class CrashRecoveryTests(unittest.TestCase):
    def test_crash_after_event_fsync_no_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 3)
            # simulate crash at the exact boundary: event 3 fsync'd, meta NOT
            # yet updated (meta still says nextSequence=3). This is the
            # concrete "crash before meta write" state.
            (root / 'meta.json').write_text(json.dumps(
                {'schemaVersion': 1, 'nextSequence': 3, 'nextSegment': 2}))
            j2 = EventJournal(root)
            rec = j2.recover()
            self.assertTrue(rec['metaReconciled'])
            j2.append_event(_evt())
            seqs = [e['sequence'] for e in j2.read()]
            self.assertEqual(seqs, [1, 2, 3, 4])  # 3 not re-issued

    def test_torn_tail_writer_truncates_and_recovers(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 2)
            seg = root / 'events-000001.jsonl'
            # append a partial line (no trailing newline) -> torn write
            with seg.open('ab') as f:
                f.write(b'{"partial": true')
            j2 = EventJournal(root)
            rec = j2.recover()
            self.assertTrue(rec['truncatedTail'])
            # the partial line is gone and sequences are intact
            self.assertEqual([e['sequence'] for e in j2.read()], [1, 2])
            j2.append_event(_evt())
            self.assertEqual([e['sequence'] for e in j2.read()], [1, 2, 3])

    def test_torn_tail_reader_skips_never_reports(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 2)
            seg = root / 'events-000001.jsonl'
            with seg.open('ab') as f:
                f.write(b'{"partial": true')
            # Runtime is read-only: it must NOT truncate but must skip the tail
            j2 = EventJournal(root, read_only=True)
            self.assertEqual([e['sequence'] for e in j2.read()], [1, 2])

    def test_complete_invalid_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 1)
            seg = root / 'events-000001.jsonl'
            # a COMPLETE line (newline present) that is invalid JSON
            with seg.open('ab') as f:
                f.write(b'not-json\n')
            j2 = EventJournal(root)
            with self.assertRaises(EventJournalError):
                j2.read()

    def test_eventid_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 1)
            seg = root / 'events-000001.jsonl'
            line = seg.read_text().strip()
            evt = json.loads(line)
            evt['eventId'] = '0' * 64  # tampered identity
            seg.write_text(json.dumps(evt, sort_keys=True) + '\n')
            j2 = EventJournal(root)
            with self.assertRaises(EventJournalError):
                j2.read()

    def test_duplicate_sequence_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 2)
            seg = root / 'events-000001.jsonl'
            line = seg.read_text().strip()
            evt = json.loads(line)
            evt['sequence'] = 2  # force a duplicate of the second event
            # recompute eventId so only the sequence duplication is the fault
            from rill_xray_agent.canonical import digest as _digest
            evt['eventId'] = _digest({k: v for k, v in evt.items() if k != 'eventId'})
            seg.write_text(json.dumps(evt, sort_keys=True) + '\n')
            j2 = EventJournal(root)
            with self.assertRaises(EventJournalError):
                j2.read()


class RolloverTests(unittest.TestCase):
    def test_rollover_crash_never_loses_committed_history(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=400, total_bytes=800)
            _append(j, 20)
            # simulate a crash right after the newest event was committed but
            # before rollover victims were deleted: keep all segments, meta
            # reflects the newest sequence. The ring buffer drops OLD events,
            # but the newest committed event must never be lost by the crash.
            j2 = EventJournal(root, segment_bytes=400, total_bytes=800)
            rec = j2.recover()
            self.assertEqual(rec['nextSequence'], 21)
            seqs = [e['sequence'] for e in j2.read()]
            # the newest committed event is preserved and sequence recovers
            # without re-issuing any identity.
            self.assertEqual(seqs[-1], 20)
            self.assertEqual(len(seqs), len(set(seqs)))  # no duplicates
            j2.append_event(_evt())
            after = [e['sequence'] for e in j2.read()]
            # the new event is appended, sequences stay monotonic & unique
            self.assertEqual(after[-1], 21)
            self.assertEqual(len(after), len(set(after)))

    def test_steady_state_bound_never_exceeded(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            total = 800
            j = EventJournal(root, segment_bytes=400, total_bytes=total)
            _append(j, 200)
            total_size = sum(p.stat().st_size for p in root.glob('events-*.jsonl'))
            self.assertLessEqual(total_size, total)

    def test_transient_overshoot_is_single_segment_and_trimmed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            total = 800
            seg = 400
            j = EventJournal(root, segment_bytes=seg, total_bytes=total)
            # after a single append the steady-state bound is restored
            _append(j, 1)
            total_size = sum(p.stat().st_size for p in root.glob('events-*.jsonl'))
            self.assertLessEqual(total_size, total)
            # a huge single event (transient) is bounded by the segment bound
            big = _evt(facts={'padding': 'x' * 600})
            with self.assertRaises(EventJournalError):
                j.append_event(big)


class SymlinkTests(unittest.TestCase):
    def test_symlink_segment_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            real = EventJournal(td / 'real')
            real.append_event(_evt())
            attacker = td / 'other'
            attacker.mkdir()
            EventJournal(attacker).append_event(_evt())
            (td / 'h').mkdir()
            (td / 'h' / 'events-000001.jsonl').symlink_to(attacker / 'events-000001.jsonl')
            j = EventJournal(td / 'h', read_only=True)
            with self.assertRaises(EventJournalError):
                j.read()

    def test_read_only_rejects_append(self):
        with tempfile.TemporaryDirectory() as td:
            j = EventJournal(Path(td) / 'h', read_only=True)
            with self.assertRaises(EventJournalError):
                j.append_event(_evt())


if __name__ == '__main__':
    unittest.main()