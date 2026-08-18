"""AutoPolicy: cooldown, rate limit, consecutive-rollback fuse.

All functions are implemented and tested. Shadow evaluation (evaluate()) never
mutates state. record_apply()/record_rollback() require the release-gated
executor path. The fuse is persistent (survives restarts).
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.auto_policy import AutoPolicy


def make_policy(td, now=1000, **kw):
    return AutoPolicy(Path(td) / 'auto-policy.json', now=now, **kw)


class AutoPolicyTest(unittest.TestCase):
    def test_default_initial_state(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td)
            s = p.snapshot()
            self.assertFalse(s['fuseOpen'])
            self.assertFalse(s['fuseAcknowledged'])
            self.assertEqual(s['consecutiveRollbacks'], 0)
            self.assertEqual(s['autoMutationsLastHour'], 0)
            self.assertEqual(s['globalCooldownRemainingSeconds'], 0)

    def test_evaluate_allows_when_cold(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            allowed, blocked = p.evaluate('rec-001')
            self.assertTrue(allowed)
            self.assertEqual(blocked, [])

    def test_same_recommendation_cooldown(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            allowed, blocked = p.evaluate('rec-001')
            self.assertFalse(allowed)
            self.assertIn('same_recommendation_cooldown', blocked)

    def test_global_cooldown(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            allowed, blocked = p.evaluate('rec-002')
            self.assertFalse(allowed)
            self.assertIn('auto_global_cooldown', blocked)

    def test_global_cooled_down(self):
        with tempfile.TemporaryDirectory() as td:
            # apply at 1000, then 6 min later -> cooldown (5 min) expired
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            p2 = make_policy(td, now=1000 + 361)
            allowed, _ = p2.evaluate('rec-002')
            self.assertTrue(allowed)

    def test_rate_limit(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            # 3 mutations in 1 hour -> max allowed = 3 -> next blocked
            for i in range(3):
                p.record_apply(f'rec-{i:03d}')
            allowed, blocked = p.evaluate('rec-004')
            self.assertFalse(allowed)
            self.assertIn('auto_rate_limited', blocked)

    def test_rate_limit_expires(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            for i in range(3):
                p.record_apply(f'rec-{i:03d}')
            # 1 hour later -> no mutations in window
            p2 = make_policy(td, now=1000 + 3600)
            allowed, _ = p2.evaluate('rec-004')
            self.assertTrue(allowed)

    def test_rollback_opens_fuse_at_limit(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            p.record_rollback()
            self.assertFalse(p.snapshot()['fuseOpen'])
            p.record_rollback()
            s = p.snapshot()
            self.assertTrue(s['fuseOpen'])
            self.assertEqual(s['consecutiveRollbacks'], 2)
            self.assertFalse(s['fuseAcknowledged'])
            # Fuse blocks auto
            allowed, blocked = p.evaluate('rec-002')
            self.assertFalse(allowed)
            self.assertIn('fusible_closed', blocked)

    def test_acknowledge_fuse_rearms(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            p.record_rollback()
            p.record_rollback()  # 2 consecutive rollbacks -> fuse opens
            self.assertTrue(p.snapshot()['fuseOpen'])
            p.acknowledge_fuse(True)
            s = p.snapshot()
            self.assertTrue(s['fuseAcknowledged'])
            self.assertEqual(s['consecutiveRollbacks'], 0)
            # After acknowledge, evaluate passes (cooldown may still apply)
            p2 = make_policy(td, now=1000 + 361)
            allowed, _ = p2.evaluate('rec-002')
            self.assertTrue(allowed)

    def test_fuse_survives_restart(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            p.record_rollback()
            p.record_rollback()  # 2 consecutive rollbacks -> fuse opens
            # Restart: fuse persists
            p2 = make_policy(td, now=9999)
            s = p2.snapshot()
            self.assertTrue(s['fuseOpen'])
            self.assertFalse(s['fuseAcknowledged'])

    def test_restart_never_resets_fuse(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            p.record_rollback()
            p.record_rollback()  # 2 consecutive rollbacks -> fuse opens
            # Simulate a restart that would silently re-enable auto if fuse
            # were not persistent.
            p2 = make_policy(td, now=9999)
            allowed, _ = p2.evaluate('rec-002')
            self.assertFalse(allowed)

    def test_successful_apply_resets_rollback_counter(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_rollback()
            self.assertEqual(p.snapshot()['consecutiveRollbacks'], 1)
            p.record_apply('rec-001')
            self.assertEqual(p.snapshot()['consecutiveRollbacks'], 0)

    def test_successful_apply_does_not_clear_open_fuse(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=1000)
            p.record_apply('rec-001')
            p.record_rollback()
            p.record_rollback()  # 2 consecutive rollbacks -> fuse opens
            p.record_apply('rec-002')
            self.assertTrue(p.snapshot()['fuseOpen'])

    def test_evaluate_never_mutates_state(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'auto-policy.json'
            p = make_policy(td, now=1000)
            # Record one apply, then shadow-evaluate (no mutation).
            p.record_apply('rec-001')
            before = path.read_bytes()
            p.evaluate('rec-001')
            self.assertEqual(path.read_bytes(), before)

    def test_persistent_mutation_times_pruned(self):
        with tempfile.TemporaryDirectory() as td:
            p = make_policy(td, now=0)
            for i in range(5):
                p.record_apply(f'rec-{i:03d}')
            # After 1h, mutations are pruned
            p2 = make_policy(td, now=3600)
            self.assertEqual(p2.snapshot()['autoMutationsLastHour'], 0)

    def test_corrupt_policy_file_blocks_auto(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'auto-policy.json'
            path.write_text('{not json')
            p = AutoPolicy(path)
            s = p.snapshot()
            self.assertEqual(s['integrity'], 'invalid')
            self.assertFalse(s['canAutoApply'])
            self.assertIsNotNone(s['corruptReason'])
            # Never silently reset: a corrupt policy must not look fresh.
            allowed, blocked = p.evaluate('rec-001')
            self.assertFalse(allowed)
            self.assertIn('policy_corrupt', blocked)
            # Mutating a corrupt policy must fail closed.
            from rill_xray_agent.auto_policy import AutoPolicyIntegrityError
            with self.assertRaises(AutoPolicyIntegrityError):
                p.record_apply('rec-001')
            with self.assertRaises(AutoPolicyIntegrityError):
                p.record_rollback()
            with self.assertRaises(AutoPolicyIntegrityError):
                p.acknowledge_fuse(True)

    def test_malformed_policy_values_block_auto(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'auto-policy.json'
            path.write_text(json.dumps({
                'fuseOpen': 'yes', 'consecutiveRollbacks': 'many',
                'mutationTimes': 'not-a-list', 'lastByRecommendation': 'x',
                'fuseAcknowledged': 1}))
            p = AutoPolicy(path)
            s = p.snapshot()
            self.assertEqual(s['integrity'], 'invalid')
            self.assertFalse(s['canAutoApply'])
            allowed, blocked = p.evaluate('rec-001')
            self.assertFalse(allowed)
            self.assertIn('policy_corrupt', blocked)

    def test_missing_policy_file_is_fresh_and_valid(self):
        with tempfile.TemporaryDirectory() as td:
            p = AutoPolicy(Path(td) / 'auto-policy.json')
            s = p.snapshot()
            self.assertEqual(s['integrity'], 'valid')
            self.assertTrue(s['canAutoApply'])
            allowed, _ = p.evaluate('rec-001')
            self.assertTrue(allowed)

    def test_symlink_policy_file_blocks_auto(self):
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / 'target.json'
            target.write_text(json.dumps({
                'lastAutoAtEpochSeconds': 0, 'lastByRecommendation': {},
                'mutationTimes': [], 'consecutiveRollbacks': 0,
                'fuseOpen': False, 'fuseOpenedAtEpochSeconds': None,
                'fuseAcknowledged': False}))
            link = Path(td) / 'auto-policy.json'
            link.symlink_to(target.name)
            p = AutoPolicy(link)
            s = p.snapshot()
            self.assertEqual(s['integrity'], 'invalid')
            self.assertFalse(s['canAutoApply'])
            self.assertIn('symlink', s['corruptReason'])

    def test_dangling_symlink_policy_file_blocks_auto(self):
        # A dangling symlink fails exists() but is still a symlink: it must
        # never be treated as a fresh install (§15 fail-closed).
        with tempfile.TemporaryDirectory() as td:
            link = Path(td) / 'auto-policy.json'
            link.symlink_to('does-not-exist.json')
            p = AutoPolicy(link)
            s = p.snapshot()
            self.assertEqual(s['integrity'], 'invalid')
            self.assertFalse(s['canAutoApply'])
            self.assertIn('symlink', s['corruptReason'])
            with self.assertRaises(Exception):
                p.record_apply('rec-001')

    def test_world_writable_policy_file_blocks_auto(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'auto-policy.json'
            path.write_text(json.dumps({
                'lastAutoAtEpochSeconds': 0, 'lastByRecommendation': {},
                'mutationTimes': [], 'consecutiveRollbacks': 0,
                'fuseOpen': False, 'fuseOpenedAtEpochSeconds': None,
                'fuseAcknowledged': False}))
            path.chmod(0o666)
            p = AutoPolicy(path)
            s = p.snapshot()
            self.assertEqual(s['integrity'], 'invalid')
            self.assertFalse(s['canAutoApply'])

    def test_valid_policy_with_extra_keys_tolerated(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / 'auto-policy.json'
            path.write_text(json.dumps({
                'lastAutoAtEpochSeconds': 0, 'lastByRecommendation': {},
                'mutationTimes': [], 'consecutiveRollbacks': 0,
                'fuseOpen': False, 'fuseOpenedAtEpochSeconds': None,
                'fuseAcknowledged': False, 'futureField': 'x'}))
            p = AutoPolicy(path)
            s = p.snapshot()
            self.assertEqual(s['integrity'], 'valid')
            self.assertTrue(s['canAutoApply'])


if __name__ == '__main__':
    unittest.main()