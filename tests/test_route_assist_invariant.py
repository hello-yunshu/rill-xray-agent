"""P0-4: Route Assist must be a hard Runtime invariant: OFF in every mode.

Any persisted true is normalized to false on load (with durable write-back),
the mode command never resurrects it (including the 'normal' mode), the
config response always reports false, snapshots report false, and a restart
keeps it false.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.runtime_service import RuntimeService


def envelope(method, body, cap='route'):
    return {'schemaVersion': 3, 'requestId': 'x1', 'capability': cap,
            'method': method, 'body': body}


def make_service(td, mode=None, seed_route_assist=False, uid=None):
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


class RouteAssistInvariant(unittest.TestCase):
    def test_legacy_true_normalized_on_load(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td, mode='normal', seed_route_assist=True)
            state = svc.state.load()
            self.assertFalse(state['routeAssistEnabled'], 'must normalize on load')
            persisted = json.loads((svc.state_root / 'runtime-state.json').read_text())
            self.assertFalse(persisted['routeAssistEnabled'], 'normalized value persisted')

    def test_mode_command_never_resurrects(self):
        for mode in ('normal', 'observe-only', 'safe-disabled'):
            with tempfile.TemporaryDirectory() as td:
                svc = make_service(td)
                out = svc.handle(envelope('mode', {'mode': mode}), peer_uid=0)
                self.assertTrue(out['ok'], (mode, out))
                self.assertFalse(svc.state.load()['routeAssistEnabled'])

    def test_config_and_snapshot_always_false(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            for mode in ('normal', 'observe-only', 'safe-disabled'):
                svc.handle(envelope('mode', {'mode': mode}), peer_uid=0)
                cfg = svc.handle(envelope('config', {}))['result']
                self.assertEqual(cfg['routeAssistEnabled'], False)
                self.assertEqual(cfg['boundedAutoAllowed'], False)
                snap = svc.handle(envelope('snapshot', {}))['result']
                self.assertEqual(snap['routeAssistEnabled'], False)
                self.assertEqual(snap['boundedAutoAllowed'], False)

    def test_restart_keeps_false(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td)
            svc.handle(envelope('mode', {'mode': 'normal'}), peer_uid=0)
            svc2 = make_service(td)
            self.assertFalse(svc2.state.load()['routeAssistEnabled'])
            cfg = svc2.handle(envelope('config', {}))['result']
            self.assertEqual(cfg['routeAssistEnabled'], False)

    def test_legacy_true_through_full_cycle(self):
        with tempfile.TemporaryDirectory() as td:
            svc = make_service(td, mode='observe-only', seed_route_assist=True)
            svc.handle(envelope('mode', {'mode': 'normal'}), peer_uid=0)
            svc2 = make_service(td)
            state = svc2.state.load()
            self.assertEqual(state['mode'], 'normal')
            self.assertFalse(state['routeAssistEnabled'])


if __name__ == '__main__':
    unittest.main()