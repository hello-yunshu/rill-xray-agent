"""RoutePolicy invariants: supported != released; locked release never allows
apply; safe-disabled overrides; recovery/plan/generation/hash failures all
fail closed; auto requires every gate simultaneously.

Runtime invariants are carried over from the pre-release hard invariant suite:
a legacy persisted routeAssistEnabled=true must normalize to observe on load
with durable write-back, the mode command never resurrects effective
enablement, config/snapshot report the release-gated effective state, and a
restart never re-enables a locked feature.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.release_capabilities import ReleaseCapabilities
from rill_xray_agent.route_policy import RoutePolicy
from rill_xray_agent.runtime_service import RuntimeService

READY_HEALTH = {'status': 'ready'}


def locked_caps(td):
    return ReleaseCapabilities(Path(td) / 'missing.json')


def open_caps(td):
    caps = locked_caps(td)
    caps = caps.with_released('routeAssist', True)
    caps = caps.with_released('boundedAuto', True)
    return caps


def policy(caps, mode='normal', stage='observe', **kw):
    defaults = dict(mode=mode, configured_stage=stage, release_capabilities=caps,
                    health=READY_HEALTH, recovery_required=False,
                    observation_fresh=True, observation_integrity_valid=True,
                    timeline_integrity_valid=True)
    defaults.update(kw)
    return RoutePolicy(**defaults)


class RoutePolicyInvariant(unittest.TestCase):
    def test_supported_locked_blocks_assist(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, mode='normal', stage='assist').evaluate()
            self.assertFalse(d['canManualApply'])
            self.assertFalse(d['canAutoApply'])
            self.assertEqual(d['effectiveStage'], 'observe')
            self.assertIn('feature_not_released', d['blockedBy'])

    def test_supported_locked_blocks_auto(self):
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, mode='normal', stage='auto').evaluate()
            self.assertFalse(d['canAutoApply'])
            self.assertFalse(d['canManualApply'])
            self.assertEqual(d['effectiveStage'], 'observe')
            self.assertIn('feature_not_released', d['blockedBy'])

    def test_safe_disabled_overrides_everything(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='safe-disabled', stage='auto').evaluate()
            self.assertFalse(d['canPlan'])
            self.assertFalse(d['canManualApply'])
            self.assertFalse(d['canAutoApply'])
            self.assertEqual(d['effectiveStage'], 'disabled')
            self.assertIn('mode_safe_disabled', d['blockedBy'])

    def test_recovery_required_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='normal', stage='assist', recovery_required=True).evaluate()
            self.assertFalse(d['canManualApply'])
            self.assertIn('recovery_required', d['blockedBy'])

    def test_stale_plan_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='normal', stage='assist', plan_valid=False).evaluate()
            self.assertFalse(d['canManualApply'])
            self.assertIn('plan_invalid', d['blockedBy'])
            d2 = policy(caps, mode='normal', stage='assist', plan_not_expired=False).evaluate()
            self.assertFalse(d2['canManualApply'])
            self.assertIn('plan_expired', d2['blockedBy'])

    def test_generation_and_hash_mismatch_block(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='normal', stage='assist', generation_match=False).evaluate()
            self.assertFalse(d['canManualApply'])
            self.assertIn('generation_mismatch', d['blockedBy'])
            d2 = policy(caps, mode='normal', stage='assist', config_hash_match=False).evaluate()
            self.assertFalse(d2['canManualApply'])
            self.assertIn('config_hash_mismatch', d2['blockedBy'])

    def test_manual_apply_allowed_when_released_assist(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='normal', stage='assist').evaluate()
            self.assertTrue(d['canPlan'])
            self.assertTrue(d['canManualApprove'])
            self.assertTrue(d['canManualApply'])
            self.assertFalse(d['canAutoApply'])
            self.assertEqual(d['effectiveStage'], 'assist')

    def test_auto_requires_all_gates(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='normal', stage='auto').evaluate()
            self.assertTrue(d['canAutoApply'])
            self.assertEqual(d['effectiveStage'], 'auto')
            for kw in ({'observation_fresh': False}, {'fusible_open': False},
                       {'rate_limit_ok': False}, {'cooldown_ok': False},
                       {'plan_valid': False}, {'generation_match': False},
                       {'config_hash_match': False}, {'recovery_required': True},
                       {'timeline_integrity_valid': False},
                       {'observation_integrity_valid': False},
                       {'health': {'status': 'recovery-required'}}):
                d2 = policy(caps, mode='normal', stage='auto', **kw).evaluate()
                self.assertFalse(d2['canAutoApply'], kw)
                self.assertNotEqual(d2['effectiveStage'], 'auto')

    def test_observe_only_no_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            caps = open_caps(td)
            d = policy(caps, mode='observe-only', stage='auto').evaluate()
            self.assertFalse(d['canAutoApply'])
            self.assertFalse(d['canManualApply'])
            self.assertEqual(d['effectiveStage'], 'observe')
            self.assertIn('mode_observe_only', d['blockedBy'])

    def test_shadow_would_apply_available_while_locked(self):
        # Locked release: shadow evaluation may run (planning/canPlan) but
        # actual host mutation stays blocked with feature_not_released.
        with tempfile.TemporaryDirectory() as td:
            caps = locked_caps(td)
            d = policy(caps, mode='normal', stage='auto').evaluate()
            self.assertTrue(d['canPlan'])
            self.assertFalse(d['canManualApply'])
            self.assertFalse(d['canAutoApply'])
            self.assertEqual(d['effectiveStage'], 'observe')
            self.assertIn('feature_not_released', d['blockedBy'])


def _envelope(method, body, cap='route'):
    return {'schemaVersion': 3, 'requestId': 'x1', 'capability': cap,
            'method': method, 'body': body}


def _make_service(td, mode=None, seed_route_assist=False, uid=None):
    state_root = Path(td) / 'state'
    state_path = state_root / 'runtime-state.json'
    if mode is not None:
        state_root.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps({
            'schemaVersion': 3, 'mode': mode,
            'routeAssistEnabled': bool(seed_route_assist),
            'pending': {}, 'completed': {}, 'restartCount': 0}, sort_keys=True))
    return RuntimeService(state_root, Path(td) / 'tx',
                          allowed_uids=[uid] if uid is not None else [0])


class RouteRuntimeInvariant(unittest.TestCase):
    """Runtime-level locked-release invariants carried over from the old
    permanent-OFF suite: the migration, mode, config/snapshot and restart
    behaviors must all keep the production release gate effectively locked."""

    def test_legacy_true_normalized_on_load(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, mode='normal', seed_route_assist=True)
            state = svc.state.load()
            self.assertFalse(state['routeAssistEnabled'], 'must normalize on load')
            self.assertEqual(state['routeStage'], 'observe')
            persisted = json.loads((svc.state_root / 'runtime-state.json').read_text())
            self.assertFalse(persisted['routeAssistEnabled'], 'normalized value persisted')

    def test_mode_command_never_resurrects_effective(self):
        for mode, expect in (('normal', 'observe'), ('observe-only', 'observe'),
                             ('safe-disabled', 'disabled')):
            with tempfile.TemporaryDirectory() as td:
                svc = _make_service(td)
                out = svc.handle(_envelope('mode', {'mode': mode}), peer_uid=0)
                self.assertTrue(out['ok'], (mode, out))
                state = svc.state.load()
                self.assertFalse(state['routeAssistEnabled'])
                self.assertFalse(state['boundedAutoAllowed'])
                status = svc.handle(_envelope('routeStatus', {}))['result']
                self.assertEqual(status['released'], False)
                self.assertEqual(status['effectiveStage'], expect)

    def test_config_and_snapshot_report_locked_effective(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td)
            for mode in ('normal', 'observe-only', 'safe-disabled'):
                svc.handle(_envelope('mode', {'mode': mode}), peer_uid=0)
                cfg = svc.handle(_envelope('config', {}))['result']
                self.assertEqual(cfg['routeAssistEnabled'], False)
                self.assertEqual(cfg['boundedAutoAllowed'], False)
                snap = svc.handle(_envelope('snapshot', {}))['result']
                self.assertEqual(snap['routeAssistEnabled'], False)
                self.assertEqual(snap['boundedAutoAllowed'], False)

    def test_restart_keeps_locked(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td)
            svc.handle(_envelope('mode', {'mode': 'normal'}), peer_uid=0)
            svc2 = _make_service(td)
            self.assertFalse(svc2.state.load()['routeAssistEnabled'])
            cfg = svc2.handle(_envelope('config', {}))['result']
            self.assertEqual(cfg['routeAssistEnabled'], False)

    def test_legacy_true_through_full_cycle(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, mode='observe-only', seed_route_assist=True)
            svc.handle(_envelope('mode', {'mode': 'normal'}), peer_uid=0)
            svc2 = _make_service(td)
            state = svc2.state.load()
            self.assertEqual(state['mode'], 'normal')
            self.assertFalse(state['routeAssistEnabled'])

    def test_configured_auto_never_effective_while_locked(self):
        # Setting routeStage=auto is a preference; it must never become an
        # effective enablement while the production release gate is locked.
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td)
            svc.handle(_envelope('mode', {'mode': 'normal'}), peer_uid=0)
            out = svc.handle(_envelope('routeStage', {'stage': 'auto'}), peer_uid=0)
            self.assertTrue(out['ok'])
            self.assertEqual(out['result']['effective'], 'observe')
            status = svc.handle(_envelope('routeStatus', {}))['result']
            self.assertEqual(status['configuredStage'], 'auto')
            self.assertEqual(status['effectiveStage'], 'observe')
            self.assertFalse(status['canAutoApply'])
            self.assertIn('feature_not_released', status['blockedBy'])


if __name__ == '__main__':
    unittest.main()
