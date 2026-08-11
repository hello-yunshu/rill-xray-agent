"""EventJournal segment semantics regression (P1-1 + P1-2).

P1-1: a torn (newline-incomplete) tail is legal ONLY on the newest active
segment (crash torn write -> writer truncates / reader skips). A partial tail
on any CLOSED historical segment is evidence corruption and must fail closed
for writers AND readers - never truncate, never silently skip.

P1-2: events must aggregate into the active segment; a new segment is created
only at the size boundary. Long runs must never degrade into one-event-per-
segment journals, restart must reuse a not-yet-full active segment, and total
bound rollover must delete only the OLDEST closed segments.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.canonical import canonical_bytes
from rill_xray_agent.event_journal import EventJournal, EventJournalError


def _evt(**kw):
    base = {'schemaVersion': 1, 'eventType': 'xray_config_changed',
            'component': 'xray', 'facts': {}, 'capturedAtEpochSeconds': 1000}
    base.update(kw)
    return base


def _append(j, n):
    for i in range(n):
        j.append_event(_evt(facts={'i': i}))


def _torn(root, seg_name):
    seg = root / seg_name
    with seg.open('ab') as f:
        f.write(b'{"partial": true')


class HistoricalTornTailTests(unittest.TestCase):
    """P1-1: closed historical segments fail closed on partial tails."""

    def test_newest_torn_tail_writer_recovers_and_continues(self):
        """Case A: complete, complete, partial on the newest segment."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=300)
            _append(j, 10)
            newest = sorted(root.glob('events-*.jsonl'))[-1]
            _torn(root, newest.name)
            j2 = EventJournal(root, segment_bytes=300)
            rec = j2.recover()
            self.assertTrue(rec['truncatedTail'])
            # only committed events remain
            seqs = [e['sequence'] for e in j2.read()]
            self.assertEqual(seqs, list(range(1, 11)))
            self.assertEqual(seqs, sorted(seqs))
            # sequence continues correctly
            j2.append_event(_evt())
            self.assertEqual([e['sequence'] for e in j2.read()][-1], 11)

    def test_historical_torn_tail_writer_fails_closed(self):
        """Case B: events-000001 torn + events-000002 valid -> FAIL CLOSED."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=300)
            _append(j, 10)
            self.assertGreater(len(sorted(root.glob('events-*.jsonl'))), 1)
            _torn(root, 'events-000001.jsonl')
            j2 = EventJournal(root, segment_bytes=300)
            with self.assertRaises(EventJournalError):
                j2.recover()
            # the corrupted historical evidence must not have been truncated
            self.assertTrue(root / 'events-000001.jsonl' is not None)
            raw = (root / 'events-000001.jsonl').read_bytes()
            self.assertTrue(raw.endswith(b'{"partial": true'))

    def test_historical_torn_tail_reader_fails_closed(self):
        """Case C: read-only open of an old segment with a partial tail."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=300)
            _append(j, 10)
            self.assertGreater(len(sorted(root.glob('events-*.jsonl'))), 1)
            _torn(root, 'events-000001.jsonl')
            j2 = EventJournal(root, segment_bytes=300, read_only=True)
            with self.assertRaises(EventJournalError):
                j2.read()
            # read-only must never repair the file
            raw = (root / 'events-000001.jsonl').read_bytes()
            self.assertTrue(raw.endswith(b'{"partial": true'))

    def test_old_segments_intact_newest_torn_recovers(self):
        """Case D: legal crash recovery must not be wounded by the P1-1 rule."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=300)
            _append(j, 10)
            newest = sorted(root.glob('events-*.jsonl'))[-1]
            _torn(root, newest.name)
            j2 = EventJournal(root, segment_bytes=300)
            rec = j2.recover()
            self.assertTrue(rec['truncatedTail'])
            seqs = [e['sequence'] for e in j2.read()]
            self.assertEqual(seqs[-1], 10)          # newest committed preserved
            self.assertEqual(seqs, sorted(seqs))    # monotonic
            self.assertEqual(len(seqs), len(set(seqs)))  # no duplicates


class SegmentAggregationTests(unittest.TestCase):
    """P1-2: real bounded segmentation, never one-event-per-file."""

    def test_small_events_aggregate_into_active_segment(self):
        """Case A: 100 small events must not produce 100 segments."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=100 * 1024)
            _append(j, 100)
            segs = j._data_segments()
            self.assertEqual(len(segs), 1)  # all fit the active segment
            self.assertEqual(len(j.read()), 100)

    def test_rotate_exactly_once_at_size_boundary(self):
        """Case B: the next event rotates exactly once when the active
        segment cannot hold it; subsequent appends reuse the new segment."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=600)
            # Fill the active segment until the NEXT event cannot fit.
            events = 0
            while True:
                nxt = dict(_evt(facts={'i': events}))
                nxt['sequence'] = events + 1
                nxt['eventId'] = 'e' * 64
                line_len = len(canonical_bytes(nxt)) + 1
                seg = root / 'events-000001.jsonl'
                if seg.exists() and seg.stat().st_size + line_len > 600:
                    break
                j.append_event(_evt(facts={'i': events}))
                events += 1
                self.assertLess(events, 50, 'segment never filled')
            before = len(j._data_segments())
            j.append_event(_evt(facts={'i': events}))       # rotate once
            self.assertEqual(len(j._data_segments()), before + 1)
            j.append_event(_evt(facts={'i': events + 1}))   # reuse active
            self.assertEqual(len(j._data_segments()), before + 1)

    def test_restart_reuses_not_full_active_segment(self):
        """Case C: restart must not unconditionally create a new segment."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=100 * 1024)
            _append(j, 3)
            self.assertEqual(len(j._data_segments()), 1)
            j2 = EventJournal(root, segment_bytes=100 * 1024)
            j2.append_event(_evt())
            self.assertEqual(len(j2._data_segments()), 1)
            self.assertEqual([e['sequence'] for e in j2.read()], [1, 2, 3, 4])

    def test_total_bound_evicts_oldest_never_active(self):
        """Case D: ring-buffer eviction deletes only closed segments."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=400, total_bytes=800)
            _append(j, 30)
            segs = j._data_segments()
            self.assertGreater(len(segs), 1)
            active = sorted(segs)[-1]
            total = sum(p.stat().st_size for p in j._data_segments())
            self.assertLessEqual(total, 800)             # steady-state bound
            self.assertTrue(active.exists())             # active never deleted
            seqs = [e['sequence'] for e in j.read()]
            self.assertEqual(seqs, sorted(seqs))         # sequence not regressed
            self.assertEqual(len(seqs), len(set(seqs)))  # no duplicates


if __name__ == '__main__':
    unittest.main()
