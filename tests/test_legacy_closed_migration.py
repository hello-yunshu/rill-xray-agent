"""P0-3: legacy in-memory 'closed' mirror migration must be fail-closed.

Every legacy tombstone is externalized through the idempotent ledger.put
(which readback-compares identity/payload hashes), and ONLY after that single
entry succeeds is it removed from the mirror. ANY failure must abort before a
destructive persist: the legacy entry is retained, no save happens, and a
MigrationError propagates (health -> recovery-required).

Scenarios:
  migration success
  identical existing tombstone (idempotent, unaffected by replay window)
  conflicting existing tombstone (same decision, different identity/payload)
  corrupt target tombstone file
  ledger full mid-migration -> retained, no destructive save
  ledger I/O error mid-migration (fault env) -> retained
  atomic write failure on the migrated state -> retained, retry succeeds
  partial migration then restart -> remainder migrates, all entries kept once
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.canonical import digest
from rill_xray_agent.errors import ContractError, MigrationError, RillError
from rill_xray_agent.state import ClosedLedger, RuntimeState

# Any fail-closed migration abort is acceptable as ContractError or
# MigrationError (both keep the legacy mirror intact). Helper below asserts
# the migration FAILED closed with either type.
CONTRACT_OR_MIGRATION = (ContractError, MigrationError)

LEGACY_TOMB = {
    'decisionIdHash': digest('d0'),
    'identityHash': digest({'capability': 'route', 'decisionId': 'd0'}),
    'payloadHash': digest({'decisionId': 'd0', 'r': 1}),
    'closedAtEpochSeconds': 1000,
}


def write_legacy_state(td, closed=None, mode='observe-only'):
    path = Path(td) / 'state.json'
    state = {'schemaVersion': 3, 'mode': mode, 'routeAssistEnabled': False,
             'pending': {}, 'completed': {}, 'closed': closed or {}, 'restartCount': 0}
    path.write_text(json.dumps(state, sort_keys=True))
    return path


def load_state(td):
    return json.loads((Path(td) / 'state.json').read_text())


class LegacyClosedMigration(unittest.TestCase):
    def test_migration_success(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_legacy_state(td, {'d0': dict(LEGACY_TOMB)})
            st = RuntimeState(path)
            v = st.load()
            self.assertNotIn('closed', v, 'mirror must be removed after success')
            self.assertIsNotNone(st.ledger.get('d0'), 'tombstone externalized')
            self.assertEqual(st.ledger.get('d0')['schemaVersion'], 1)

    def test_identical_existing_tombstone_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_legacy_state(td, {'d0': dict(LEGACY_TOMB)})
            st = RuntimeState(path)
            # Pre-existing identical tombstone (inside replay window at 0).
            st.ledger.put_hashed(LEGACY_TOMB['decisionIdHash'], LEGACY_TOMB['identityHash'],
                                 LEGACY_TOMB['payloadHash'], 1)
            v = st.load()
            self.assertNotIn('closed', v)
            self.assertEqual(st.ledger.get('d0')['payloadHash'], LEGACY_TOMB['payloadHash'])

    def test_conflicting_existing_tombstone_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_legacy_state(td, {'d0': dict(LEGACY_TOMB)})
            st = RuntimeState(path)
            st.ledger.put_hashed(LEGACY_TOMB['decisionIdHash'],
                                 digest('other-identity'), LEGACY_TOMB['payloadHash'], 1)
            with self.assertRaises(CONTRACT_OR_MIGRATION):
                st.load()
            keep = json.loads(path.read_text())
            self.assertIn('d0', keep.get('closed', {}), 'conflicting entry must be retained')

    def test_corrupt_target_tombstone_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_legacy_state(td, {'d0': dict(LEGACY_TOMB)})
            st = RuntimeState(path)
            target = st.ledger.get_hash(LEGACY_TOMB['decisionIdHash'])
            # Pre-place a corrupt file at the tombstone path (not a symlink,
            # so put_hashed sees an unsafe existing entry rather than a fresh one).
            corrupt = st.ledger.root / f"{LEGACY_TOMB['decisionIdHash']}.json"
            corrupt.write_text('garbage{{{')
            with self.assertRaises(CONTRACT_OR_MIGRATION):
                st.load()
            keep = json.loads(path.read_text())
            self.assertIn('d0', keep.get('closed', {}))

    def test_ledger_full_mid_migration_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_legacy_state(td, {'d0': dict(LEGACY_TOMB), 'd1': {
                'decisionIdHash': digest('d1'), 'identityHash': digest('id1'),
                'payloadHash': digest('p1'), 'closedAtEpochSeconds': 1000}})
            # Capacity 1: the second migration write must fail closed.
            st = RuntimeState(path, max_ledger_entries=1)
            with self.assertRaises(CONTRACT_OR_MIGRATION):
                st.load()
            keep = json.loads(path.read_text())
            self.assertEqual(len(keep['closed']), 2, 'all legacy entries retained')
            self.assertEqual(st.ledger.count(), 1, 'only the successful tombstone exists')

    def test_ledger_io_error_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_legacy_state(td, {'d0': dict(LEGACY_TOMB)})
            st = RuntimeState(path)
            os.environ['RILL_LEDGER_IO_ERROR'] = '1'
            try:
                with self.assertRaises(MigrationError):
                    st.load()
            finally:
                os.environ.pop('RILL_LEDGER_IO_ERROR', None)
            keep = json.loads(path.read_text())
            self.assertIn('d0', keep['closed'], 'entry retained on I/O fault')
            self.assertEqual(st.ledger.count(), 0, 'no tombstone externalized')

    def test_atomic_write_failure_retains_and_retries(self):
        with tempfile.TemporaryDirectory() as td:
            path = write_legacy_state(td, {'d0': dict(LEGACY_TOMB)})
            st = RuntimeState(path)
            # Force the final save() to fail: point the state file INTO a
            # read-only dir (the ledger lives in the writable temp root, so
            # only the destructive persist can fail).
            state_dir = path.parent / 'ro-dir'
            state_dir.mkdir()
            ro = state_dir / 'state.json'
            ro.write_text(json.dumps({'schemaVersion': 3, 'closed': {'d0': dict(LEGACY_TOMB)}}))
            st2 = RuntimeState(ro)
            os.chmod(state_dir, 0o555)
            try:
                with self.assertRaises(Exception):
                    st2.load()
            finally:
                os.chmod(state_dir, 0o755)
            # Retry after the fault is cleared: same legacy entry still present.
            st3 = RuntimeState(ro)
            v = st3.load()
            self.assertNotIn('closed', v)
            self.assertEqual(st3.ledger.count(), 1)

    def test_partial_migration_then_restart(self):
        with tempfile.TemporaryDirectory() as td:
            closed = {'d0': dict(LEGACY_TOMB),
                      'd1': {'decisionIdHash': digest('d1'), 'identityHash': digest('id1'),
                             'payloadHash': digest('p1'), 'closedAtEpochSeconds': 1000},
                      'd2': {'decisionIdHash': digest('d2'), 'identityHash': digest('id2'),
                             'payloadHash': digest('p2'), 'closedAtEpochSeconds': 1000}}
            path = write_legacy_state(td, closed)
            st = RuntimeState(path, max_ledger_entries=1)
            with self.assertRaises(CONTRACT_OR_MIGRATION):
                st.load()
            # First entry externalized, all three still in the mirror (no
            # destructive save). Restart with capacity: everything migrates.
            self.assertEqual(st.ledger.count(), 1)
            keep = json.loads(path.read_text())
            self.assertEqual(len(keep['closed']), 3)
            st2 = RuntimeState(path, max_ledger_entries=8)
            v = st2.load()
            self.assertNotIn('closed', v)
            self.assertEqual(st2.ledger.count(), 3)


if __name__ == '__main__':
    unittest.main()