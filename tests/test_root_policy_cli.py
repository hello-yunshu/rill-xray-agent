"""rill-xray-agent-root-policy helper CLI (root_policy_cli).

The helper is the one-shot root control surface (§17) for the ROOT execution
policy: confirm/revoke auto, acknowledge fuse, safe-disable, mode, route-stage,
reset, status. It must be enum-only (no arbitrary paths/shell/service), atomic,
epoch-bumping, audited, projection-refreshing, and fail closed on corruption.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.root_policy import DEFAULT_EXECUTION_POLICY_PATH
from rill_xray_agent import root_policy_cli


def run_cli(td, *argv):
    """Run the helper against a temp root/projection; return (rc, parsed_json)."""
    root = Path(td) / 'root'
    proj = Path(td) / 'proj' / 'execution-policy.json'
    full = ['--root-dir', str(root), '--projection', str(proj), *argv]
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = root_policy_cli.main(full)
    return rc, json.loads(buf.getvalue())


class RootPolicyCliTest(unittest.TestCase):
    def test_status_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = run_cli(td, 'status')
            self.assertEqual(rc, 0)
            self.assertTrue(out['ok'])
            self.assertEqual(out['command'], 'status')
            self.assertEqual(out['policy']['mode'], 'observe-only')
            # status must not create root policy files.
            self.assertFalse((Path(td) / 'root' / 'execution-policy.json').exists())

    def test_confirm_auto_sets_state_audits_and_projects(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = run_cli(td, 'confirm-auto')
            self.assertEqual(rc, 0)
            self.assertTrue(out['ok'])
            self.assertTrue(out['policy']['autoConfirmed'])
            self.assertEqual(out['policy']['executionEpoch'], 1)
            self.assertIsNotNone(out['auditEventHash'])
            # Projection was written and binds the snapshot digest.
            proj = Path(td) / 'proj' / 'execution-policy.json'
            self.assertTrue(proj.is_file())
            data = json.loads(proj.read_text())
            self.assertEqual(data['policy']['autoConfirmed'], True)
            # Root-owned audit log recorded the transition.
            audit = Path(td) / 'root' / 'audit' / 'events-000001.jsonl'
            self.assertTrue(audit.is_file())
            event = json.loads(audit.read_text().splitlines()[0])
            self.assertEqual(event['eventType'], 'policy.auto_confirm')
            self.assertEqual(event['actorType'], 'operator')

    def test_revoke_auto_bumps_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            run_cli(td, 'confirm-auto')
            rc, out = run_cli(td, 'revoke-auto')
            self.assertEqual(rc, 0)
            self.assertFalse(out['policy']['autoConfirmed'])
            self.assertEqual(out['policy']['executionEpoch'], 2)

    def test_safe_disable(self):
        with tempfile.TemporaryDirectory() as td:
            run_cli(td, 'confirm-auto')
            rc, out = run_cli(td, 'safe-disable')
            self.assertEqual(rc, 0)
            self.assertEqual(out['policy']['mode'], 'safe-disabled')
            self.assertFalse(out['policy']['autoConfirmed'])
            self.assertGreaterEqual(out['policy']['executionEpoch'], 2)

    def test_mode_transition(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = run_cli(td, 'mode', 'normal')
            self.assertEqual(rc, 0)
            self.assertEqual(out['policy']['mode'], 'normal')
            self.assertEqual(out['policy']['executionEpoch'], 1)

    def test_route_stage_transition(self):
        with tempfile.TemporaryDirectory() as td:
            rc, out = run_cli(td, 'route-stage', 'auto')
            self.assertEqual(rc, 0)
            self.assertEqual(out['policy']['routeStage'], 'auto')
            self.assertEqual(out['policy']['executionEpoch'], 1)

    def test_reset_clears_confirmation_and_bumps_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            run_cli(td, 'confirm-auto')
            rc, out = run_cli(td, 'reset')
            self.assertEqual(rc, 0)
            self.assertFalse(out['policy']['autoConfirmed'])
            self.assertGreaterEqual(out['policy']['executionEpoch'], 2)

    def test_illegal_enum_rejected_by_argparse(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                root_policy_cli.main(['--root-dir', str(Path(td) / 'root'),
                                      'mode', 'not-a-mode'])
            with self.assertRaises(SystemExit):
                root_policy_cli.main(['--root-dir', str(Path(td) / 'root'),
                                      'route-stage', 'sideways'])

    def test_corrupt_policy_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'root'
            root.mkdir(exist_ok=True)
            (root / 'execution-policy.json').write_text('{bad')
            rc, out = run_cli(td, 'confirm-auto')
            self.assertEqual(rc, 1)
            self.assertFalse(out['ok'])
            self.assertEqual(out['error']['code'], 'root_policy_corrupt')
            # Never reset to a fresh default.
            self.assertEqual((root / 'execution-policy.json').read_text(), '{bad')

    def test_noop_transition_does_not_bump_epoch(self):
        with tempfile.TemporaryDirectory() as td:
            rc1, _ = run_cli(td, 'mode', 'observe-only')  # default mode already
            self.assertEqual(rc1, 0)
            # No-op: epoch stays 0.
            rc2, out = run_cli(td, 'status')
            self.assertEqual(out['policy']['executionEpoch'], 0)

    @unittest.skipIf(os.geteuid() == 0, 'root guard not applicable as root')
    def test_mutating_production_path_requires_root(self):
        with tempfile.TemporaryDirectory() as td:
            # Point at the production default root (guard triggers on path,
            # before any filesystem write) via a harmless temp projection.
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = root_policy_cli.main([
                    '--root-dir', str(DEFAULT_EXECUTION_POLICY_PATH.parent),
                    '--projection', str(Path(td) / 'p.json'),
                    'confirm-auto'])
            self.assertEqual(rc, 1)
            out = json.loads(buf.getvalue())
            self.assertEqual(out['error']['code'], 'root_required')
            # status is read-only and allowed even as non-root.
            rc2 = root_policy_cli.main([
                '--root-dir', str(DEFAULT_EXECUTION_POLICY_PATH.parent),
                'status'])
            self.assertEqual(rc2, 0)


if __name__ == '__main__':
    unittest.main()
