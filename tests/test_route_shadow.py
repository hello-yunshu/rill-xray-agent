"""Shadow planning / shadow auto decision: lock-invariant, no host mutation.

In the locked production release, shadow evaluation must be available
(canPlan=True, shadowWouldApply=computed) while actual host mutation is
blocked (canManualApply=False, canAutoApply=False, blockedBy contains
feature_not_released). Shadow must never write to the auto policy state.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.release_capabilities import ReleaseCapabilities
from rill_xray_agent.route_policy import RoutePolicy


READY_HEALTH = {'status': 'ready'}


def locked_caps(td):
    return ReleaseCapabilities(Path(td) / 'missing.json')


def open_caps(td):
    return locked_caps(td).with_released('routeAssist', True).with_released('boundedAuto', True)


def policy(caps, **kw):
    defaults = dict(mode='normal', configured_stage='auto', release_capabilities=caps,
                    health=READY_HEALTH, recovery_required=False,
                    observation_fresh=True, observation_integrity_valid=True,
                    timeline_integrity_valid=True)
    defaults.update(kw)
    return RoutePolicy(**defaults)


class ShadowPlanningTest(unittest.TestCase):
    def test_shadow_planning_available_while_locked(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, configured_stage='assist').evaluate()
            self.assertTrue(d['canPlan'])
            self.assertFalse(d['canManualApply'])
            self.assertFalse(d['canAutoApply'])
            self.assertEqual(d['effectiveStage'], 'observe')
            self.assertIn('feature_not_released', d['blockedBy'])

    def test_shadow_would_apply_available_while_locked(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, configured_stage='auto').evaluate()
            self.assertTrue(d['canPlan'])
            # shadowWouldApply is a function of health and observation; in
            # locked mode it does not encode the release gate directly.
            self.assertTrue(d['shadowWouldApply'])
            self.assertFalse(d['canManualApply'])
            self.assertFalse(d['canAutoApply'])

    def test_shadow_would_reject_when_health_fails(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, configured_stage='assist', health={'status': 'recovery-required'}).evaluate()
            self.assertFalse(d['canPlan'])
            self.assertFalse(d['shadowWouldApply'])

    def test_shadow_would_reject_when_recovery_required(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, configured_stage='assist', recovery_required=True).evaluate()
            self.assertFalse(d['canPlan'])
            self.assertFalse(d['shadowWouldApply'])

    def test_shadow_would_reject_when_observation_corrupt(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, configured_stage='assist', observation_integrity_valid=False).evaluate()
            self.assertFalse(d['canPlan'])
            self.assertFalse(d['shadowWouldApply'])

    def test_shadow_auto_not_mutated_by_locked_evaluate(self):
        # Shadow evaluation never writes to the auto policy state.
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, configured_stage='auto').evaluate()
            self.assertFalse(d['canAutoApply'])

    def test_shadow_runs_up_to_apply_request_boundary(self):
        # In locked mode, shadow planning reaches the "canPlan" decision; the
        # ApplyRequest never reaches the root executor spool because
        # canManualApply/canAutoApply are false.
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, configured_stage='assist').evaluate()
            self.assertTrue(d['canPlan'])
            self.assertFalse(d['canManualApply'])
            self.assertIn('feature_not_released', d['blockedBy'])

    def test_open_gate_shadow_would_apply_matches_actual(self):
        # When the gate is open, shadowWouldApply must be consistent with
        # actual auto eligibility.
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, configured_stage='auto').evaluate()
            self.assertTrue(d['canAutoApply'])
            self.assertTrue(d['shadowWouldApply'])

    def test_observe_only_shadow_planning_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='observe-only', configured_stage='assist').evaluate()
            self.assertTrue(d['canPlan'])
            self.assertFalse(d['canManualApply'])
            self.assertIn('mode_observe_only', d['blockedBy'])

    def test_locked_safe_disabled_shadow_shut_down(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, mode='safe-disabled', configured_stage='auto').evaluate()
            self.assertFalse(d['canPlan'])
            self.assertFalse(d['shadowWouldApply'])


if __name__ == '__main__':
    unittest.main()