"""EventJournal sequence / segment continuity fail-closed (spec 15, P1-B).

Surviving committed events must form a continuous suffix. Legal bounded ring
rollover evicts the OLDEST prefix, so the first surviving sequence/segment may
exceed 1; but a hole located INSIDE the surviving set (a complete event line or
a whole middle segment deleted by corruption) must fail closed for both readers
and writers - it must never be reported as integrity=valid.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.event_journal import EventJournal, EventJournalError


def _evt(**kw):
    base = {'schemaVersion': 1, 'eventType': 'xray_config_changed',
            'component': 'xray', 'facts': {}, 'capturedAtEpochSeconds': 1000}
    base.update(kw)
    return base


def _append(j, n, start=1):
    for i in range(start, start + n):
        j.append_event(_evt(facts={'i': i}))


def _drop_line(root, sequence):
    """Remove the complete committed line holding `sequence` (real corruption:
    a full event line is deleted, leaving a gap in the surviving suffix)."""
    for seg in sorted(root.glob('events-*.jsonl')):
        lines = seg.read_bytes().split(b'\n')
        kept = []
        changed = False
        for line in lines:
            if not line:
                continue
            if json.loads(line).get('sequence') == sequence and not changed:
                changed = True
                continue
            kept.append(line)
        if changed:
            seg.write_bytes(b'\n'.join(kept) + b'\n')
            return
    raise AssertionError(f'sequence {sequence} not found in any segment')


class SequenceGapTests(unittest.TestCase):
    def test_middle_complete_event_removed_reader_fails_closed(self):
        """Sequence gap A: write 1,2,3; delete complete event 2; reader fails."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 3)
            _drop_line(root, 2)
            j2 = EventJournal(root, read_only=True)
            with self.assertRaises(EventJournalError):
                j2.read()

    def test_middle_complete_event_removed_writer_fails_closed(self):
        """Sequence gap B: writer recover() must also fail, never renumber."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root)
            _append(j, 3)
            _drop_line(root, 2)
            j2 = EventJournal(root)
            with self.assertRaises(EventJournalError):
                j2.recover()


class SegmentGapTests(unittest.TestCase):
    def _make_three_segments(self, td):
        root = Path(td) / 'h'
        j = EventJournal(root, segment_bytes=2000, total_bytes=10 ** 6)
        # Rotate through at least 3 segments with small segment bound.
        _append(j, 40)
        segs = sorted(p for p in j._data_segments())
        self.assertGreaterEqual(len(segs), 3)
        return root, segs

    def test_middle_segment_removed_reader_fails_closed(self):
        """Segment gap C (reader): delete the middle segment -> fail closed."""
        with tempfile.TemporaryDirectory() as td:
            root, segs = self._make_three_segments(td)
            middle = segs[len(segs) // 2]
            middle.unlink()
            j2 = EventJournal(root, read_only=True)
            with self.assertRaises(EventJournalError):
                j2.read()

    def test_middle_segment_removed_writer_fails_closed(self):
        """Segment gap C (writer): delete the middle segment -> fail closed."""
        with tempfile.TemporaryDirectory() as td:
            root, segs = self._make_three_segments(td)
            middle = segs[len(segs) // 2]
            middle.unlink()
            j2 = EventJournal(root)
            with self.assertRaises(EventJournalError):
                j2.recover()


class LegalRolloverTests(unittest.TestCase):
    def test_legal_oldest_prefix_rollover_passes(self):
        """Legal rollover D: total_bytes bound evicts the OLDEST closed
        segments; the surviving set stays a continuous suffix -> PASS."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=600, total_bytes=1800)
            _append(j, 60)
            events = j.read()
            seqs = [e['sequence'] for e in events]
            self.assertEqual(seqs, list(range(seqs[0], seqs[-1] + 1)))
            self.assertEqual(len(seqs), len(set(seqs)))
            # first surviving sequence legally > 1 (oldest prefix evicted)
            self.assertGreater(events[0]['sequence'], 1)

    def test_legal_surviving_sequence_suffix_passes(self):
        """Legal sequence prefix eviction E: surviving seq 51..100 -> PASS."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'h'
            j = EventJournal(root, segment_bytes=600, total_bytes=1800)
            _append(j, 100)
            seqs = [e['sequence'] for e in j.read()]
            self.assertEqual(seqs, list(range(seqs[0], 101)))
            # ensure the suffix is exactly contiguous and starts well past 1
            self.assertGreater(seqs[0], 1)
            self.assertEqual(seqs[-1], 100)


if __name__ == '__main__':
    unittest.main()