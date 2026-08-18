"""RootExecutionPolicy: root-owned execution policy + auto ledger.

The unprivileged Runtime may write its own state-root, so Runtime state can
never be the final authority. This module owns executionEpoch, mode, routeStage,
auto confirmation, and the cooldown/rate/fuse ledger at the ROOT path, and
publishes a secret-free projection the Runtime only reads.

Invariants under test:
  - every authorization-relevant transition bumps executionEpoch (§12);
  - no-op transitions never bump the epoch;
  - corruption / symlink / bad permissions fail closed and NEVER reset to a
    fresh default (§15);
  - evaluate() recomputes auto eligibility root-side (epoch, confirmation,
    mode, cooldown/rate/fuse, risk, op allowlist) and never mutates (§16/§19);
  - the projection binds the exact policy snapshot digest.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.root_policy import (
    DEFAULT_EXECUTION_POLICY, RootExecutionPolicy, RootPolicyIntegrityError)


def make_policy(td, now=1000, **kw):
    root = Path(td) / 'root'
    root.mkdir(exist_ok=True)
    return RootExecutionPolicy(root_dir=root, now=now, **kw)


# A low-risk, auto-allowlisted operation (insert at/after the rule list end).
LOW_INSERT = {'op': 'routingRule.insert',
              'params': {'position': 5, 'selectorType': 'domain',
                         'selectorValue': ['x.example.com'],
                         'outboundTag': 'proxy'}}
# A manual-only operation (not in the auto allowlist).
REMOVE = {'op': 'routingRule.removeManaged', 'params': {'ruleIndex': 0}}
# A medium-risk replace (selectorType differs from the current rule).
MEDIUM_REPLACE = {'op': 'routingRule.replaceManaged',
                  'params': {'ruleIndex': 0, 'selectorType': 'ip',
                             'selectorValue': ['1.2.3.4'],
                             'outboundTag': 'proxy'}}


class RootPolicyCoreTest(unittest.TestCase):
    def test_default_state(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            self.assertTrue(p.integrity_valid)
            self.assertEqual(p.execution_epoch(), 0)
            self.assertFalse(p.is_auto_confirmed())
            self.assertEqual(p.mode(), 'observe-only')
            self.assertEqual(p.route_stage(), 'observe')

    def test_missing_policy_file_is_fresh_and_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            self.assertEqual(p.snapshot()['integrity'], 'valid')

    # ---- epoch bump matrix (§12) -------------------------------------
    def test_mode_change_bumps_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            self.assertTrue(p.set_mode('normal'))
            self.assertEqual(p.execution_epoch(), 1)
            self.assertEqual(p.mode(), 'normal')

    def test_route_stage_change_bumps_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            self.assertTrue(p.set_route_stage('assist'))
            self.assertEqual(p.execution_epoch(), 1)
            self.assertEqual(p.route_stage(), 'assist')

    def test_noop_transition_never_bumps_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            # observe-only -> observe-only is a no-op.
            self.assertFalse(p.set_mode('observe-only'))
            self.assertFalse(p.set_route_stage('observe'))
            self.assertEqual(p.execution_epoch(), 0)
            # confirm then re-confirm: only the first bumps.
            self.assertTrue(p.set_auto_confirmed(True))
            self.assertFalse(p.set_auto_confirmed(True))
            self.assertEqual(p.execution_epoch(), 1)

    def test_safe_disable_bumps_epoch_and_revokes_confirmation(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            p.set_auto_confirmed(True)
            epoch = p.execution_epoch()
            p.safe_disable()
            self.assertEqual(p.execution_epoch(), epoch + 1)
            self.assertEqual(p.mode(), 'safe-disabled')
            self.assertFalse(p.is_auto_confirmed())
            self.assertIsNone(p.snapshot()['autoConfirmedAtEpochSeconds'])

    def test_auto_confirm_and_revoke_bump_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            p.set_auto_confirmed(True)
            self.assertTrue(p.is_auto_confirmed())
            self.assertEqual(p.execution_epoch(), 1)
            p.set_auto_confirmed(False)
            self.assertFalse(p.is_auto_confirmed())
            self.assertEqual(p.execution_epoch(), 2)

    def test_fuse_transition_and_ack_bump_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            p.record_apply('rec-001')
            epoch = p.execution_epoch()
            p.record_rollback()  # 1
            p.record_rollback()  # 2 -> fuse opens, epoch bump
            self.assertTrue(p.snapshot()['fuseOpen'])
            self.assertEqual(p.execution_epoch(), epoch + 1)
            ack_epoch = p.execution_epoch()
            p.acknowledge_fuse(True)
            self.assertTrue(p.snapshot()['fuseAcknowledged'])
            self.assertEqual(p.execution_epoch(), ack_epoch + 1)

    def test_reset_bumps_epoch_and_clears_confirmation(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            p.set_auto_confirmed(True)
            epoch = p.execution_epoch()
            p.reset_policy()
            self.assertEqual(p.execution_epoch(), epoch + 1)
            self.assertFalse(p.is_auto_confirmed())

    # ---- corruption / fail-closed (§15) -------------------------------
    def test_corrupt_policy_blocks_mutations(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'root'
            root.mkdir(exist_ok=True)
            (root / 'execution-policy.json').write_text('{not json')
            p = make_policy(td)
            self.assertFalse(p.integrity_valid)
            self.assertIn('unparseable', p.corrupt_reason)
            # Never reset to a fresh default: epoch/mode stay pristine.
            self.assertEqual(p.snapshot()['mode'], 'observe-only')
            for call in (lambda: p.set_mode('normal'),
                         lambda: p.set_route_stage('auto'),
                         lambda: p.safe_disable(),
                         lambda: p.set_auto_confirmed(True),
                         lambda: p.reset_policy(),
                         lambda: p.bump_execution_epoch('mode-change'),
                         lambda: p.record_apply('rec-001'),
                         lambda: p.record_rollback(),
                         lambda: p.acknowledge_fuse(True)):
                with self.assertRaises(RootPolicyIntegrityError):
                    call()

    def test_corrupt_ledger_blocks_mutations(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'root'
            root.mkdir(exist_ok=True)
            (root / 'auto-execution-ledger.json').write_text('[1,2,3]')
            p = make_policy(td)
            self.assertFalse(p.integrity_valid)
            self.assertIn('auto ledger', p.corrupt_reason)
            with self.assertRaises(RootPolicyIntegrityError):
                p.set_mode('normal')

    def test_symlink_policy_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'root'
            root.mkdir(exist_ok=True)
            target = Path(td) / 'target.json'
            target.write_text(json.dumps(DEFAULT_EXECUTION_POLICY))
            (root / 'execution-policy.json').symlink_to(target.name)
            p = make_policy(td)
            self.assertFalse(p.integrity_valid)
            self.assertIn('symlink', p.corrupt_reason)

    def test_world_writable_policy_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'root'
            root.mkdir(exist_ok=True)
            path = root / 'execution-policy.json'
            path.write_text(json.dumps(DEFAULT_EXECUTION_POLICY))
            path.chmod(0o666)
            p = make_policy(td)
            self.assertFalse(p.integrity_valid)
            self.assertIn('writable', p.corrupt_reason)

    # ---- root-side auto evaluation (§16/§19) --------------------------
    def _ready_policy(self, td, now=1000):
        p = make_policy(td, now=now)
        p.set_mode('normal')
        p.set_route_stage('auto')
        p.set_auto_confirmed(True)
        return p

    def test_evaluate_allows_when_everything_green(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            allowed, blocked = p.evaluate('rec-001', p.execution_epoch(),
                                          'low', [LOW_INSERT])
            self.assertTrue(allowed)
            self.assertEqual(blocked, [])

    def test_evaluate_blocks_stale_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            allowed, blocked = p.evaluate('rec-001', p.execution_epoch() - 1,
                                          'low', [LOW_INSERT])
            self.assertFalse(allowed)
            self.assertIn('execution_epoch_mismatch', blocked)

    def test_evaluate_blocks_when_not_confirmed(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            p.set_auto_confirmed(False)
            allowed, blocked = p.evaluate('rec-001', p.execution_epoch(),
                                          'low', [LOW_INSERT])
            self.assertFalse(allowed)
            self.assertIn('auto_requires_confirmation', blocked)

    def test_evaluate_blocks_safe_disabled(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            p.safe_disable()
            allowed, blocked = p.evaluate('rec-001', p.execution_epoch(),
                                          'low', [LOW_INSERT])
            self.assertFalse(allowed)
            self.assertIn('mode_safe_disabled', blocked)

    def test_evaluate_blocks_medium_risk(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            # replaceManaged is auto-allowlisted, but the root re-evaluation
            # (against the live rules) classifies this specific replace as
            # medium (selectorType changes) -> not auto-eligible.
            allowed, blocked = p.evaluate('rec-001', p.execution_epoch(),
                                          'medium', [MEDIUM_REPLACE])
            self.assertFalse(allowed)
            self.assertIn('auto_risk_not_eligible', blocked)

    def test_evaluate_blocks_non_allowlisted_op(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            allowed, blocked = p.evaluate('rec-001', p.execution_epoch(),
                                          'low', [REMOVE])
            self.assertFalse(allowed)
            self.assertIn('auto_op_not_allowlisted', blocked)

    def test_evaluate_blocks_auto_cooldown(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            p.record_apply('rec-001')
            allowed, blocked = p.evaluate('rec-001', p.execution_epoch(),
                                          'low', [LOW_INSERT])
            self.assertFalse(allowed)
            self.assertIn('same_recommendation_cooldown', blocked)

    def test_evaluate_blocks_fuse_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            p.record_apply('rec-000')
            p.record_rollback()
            p.record_rollback()  # fuse opens
            allowed, blocked = p.evaluate('rec-002', p.execution_epoch(),
                                          'low', [LOW_INSERT])
            self.assertFalse(allowed)
            self.assertIn('fusible_closed', blocked)

    def test_evaluate_blocks_corrupt_policy(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'root'
            root.mkdir(exist_ok=True)
            (root / 'execution-policy.json').write_text('{bad')
            p = make_policy(td)
            allowed, blocked = p.evaluate('rec-001', 0, 'low', [LOW_INSERT])
            self.assertFalse(allowed)
            self.assertIn('policy_corrupt', blocked)

    def test_evaluate_never_mutates(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            # Materialize the root ledger so both files exist to compare bytes.
            p.record_apply('rec-000')
            pol_before = (Path(td) / 'root' / 'execution-policy.json').read_bytes()
            led_before = (Path(td) / 'root' / 'auto-execution-ledger.json').read_bytes()
            p.evaluate('rec-001', p.execution_epoch(), 'low', [LOW_INSERT])
            self.assertEqual((Path(td) / 'root' / 'execution-policy.json').read_bytes(),
                             pol_before)
            self.assertEqual((Path(td) / 'root' / 'auto-execution-ledger.json').read_bytes(),
                             led_before)

    # ---- projection / digest ------------------------------------------
    def test_projection_binds_policy_snapshot_digest(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            proj = Path(td) / 'proj' / 'execution-policy.json'
            p.write_projection(proj)
            data = json.loads(proj.read_text())
            self.assertEqual(data['schemaVersion'], 1)
            self.assertEqual(data['policySnapshotDigest'],
                             p.policy_snapshot_digest())
            self.assertEqual(data['policy'], p.snapshot())
            self.assertEqual(proj.stat().st_mode & 0o777, 0o640)

    def test_projection_epoch_moves_with_policy(self):
        with tempfile.TemporaryDirectory() as td:
            p = self._ready_policy(td)
            proj = Path(td) / 'proj' / 'execution-policy.json'
            p.write_projection(proj)
            before = json.loads(proj.read_text())['policy']['executionEpoch']
            p.set_mode('observe-only')  # bump epoch
            p.write_projection(proj)
            after = json.loads(proj.read_text())['policy']['executionEpoch']
            self.assertEqual(after, before + 1)

    def test_record_apply_persists_to_root_ledger(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            p2 = make_policy(td, now=1000)
            self.assertEqual(p2.snapshot()['lastAutoAtEpochSeconds'], 1000)


if __name__ == '__main__':
    unittest.main()
