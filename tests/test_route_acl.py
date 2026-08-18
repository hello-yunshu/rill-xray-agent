"""Agent ACL / API surface: deliberate method categorization.

Route APIs are categorized READ_ONLY / OPERATOR / ROOT_ONLY. Read-only methods
(routeStatus / routeHistory / autoStatus) must never require write privilege
and must never mutate state; write methods (routeStage / routePlan / routeApprove
/ routeReject / autoConfirm) require a privileged peer. mode is ROOT_ONLY.
"""
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.agent_service import (
    OPERATOR, READ_ONLY, ROOT_ONLY, ROUTE_METHODS)
from rill_xray_agent.runtime_service import RuntimeService


def _envelope(method, body):
    return {'schemaVersion': 3, 'requestId': 'acl-1', 'capability': 'route',
            'method': method, 'body': body}


def _make_service(td, allowed_uids=(0,)):
    return RuntimeService(Path(td) / 'state', Path(td) / 'tx',
                          allowed_uids=list(allowed_uids))


class AgentAclMappingTest(unittest.TestCase):
    def test_route_methods_are_categorized(self):
        for m in ROUTE_METHODS:
            self.assertIn(m, READ_ONLY | OPERATOR | ROOT_ONLY, m)
        # No overlap: each method has exactly one category.
        self.assertTrue(READ_ONLY.isdisjoint(OPERATOR))
        self.assertTrue(READ_ONLY.isdisjoint(ROOT_ONLY))
        self.assertTrue(OPERATOR.isdisjoint(ROOT_ONLY))

    def test_read_only_contains_route_queries(self):
        self.assertIn('routeStatus', READ_ONLY)
        self.assertIn('routeHistory', READ_ONLY)
        self.assertIn('autoStatus', READ_ONLY)

    def test_operator_contains_route_mutations(self):
        for m in ('routeStage', 'routePlan', 'routeApprove', 'routeReject',
                  'autoConfirm'):
            self.assertIn(m, OPERATOR)

    def test_root_only_contains_mode(self):
        self.assertIn('mode', ROOT_ONLY)
        self.assertNotIn('routeStage', ROOT_ONLY)
        self.assertNotIn('routeApprove', ROOT_ONLY)


class AgentAclRuntimeTest(unittest.TestCase):
    def test_read_only_route_status_works_for_non_operator(self):
        # routeStatus must not require operator privilege.
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=(0, 1000))
            out = svc.handle(_envelope('routeStatus', {}), peer_uid=1000)
            self.assertTrue(out['ok'], out)
            self.assertIn('supported', out['result'])

    def test_route_stage_requires_privileged_peer(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=(0,))
            out = svc.handle(_envelope('routeStage', {'stage': 'assist'}),
                             peer_uid=9999)
            self.assertFalse(out['ok'])
            self.assertIn('privileged', str(out['error']['message']))

    def test_route_stage_works_for_privileged_peer(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=(0,))
            out = svc.handle(_envelope('routeStage', {'stage': 'assist'}), peer_uid=0)
            self.assertTrue(out['ok'], out)
            # The op wrapper carries the audit trail; the stored preference is
            # inside result.result, and effective reflects the release gate.
            self.assertEqual(out['result']['result']['routeStage'], 'assist')
            self.assertEqual(out['result']['effective'], 'observe')

    def test_route_reject_requires_privileged_peer(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=(0,))
            out = svc.handle(_envelope('routeReject', {'recommendationId': 'x'}),
                             peer_uid=9999)
            self.assertFalse(out['ok'])

    def test_auto_confirm_requires_privileged_peer(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=(0,))
            out = svc.handle(_envelope('autoConfirm', {}), peer_uid=9999)
            self.assertFalse(out['ok'])

    def test_mode_root_only(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=(0,))
            out = svc.handle(_envelope('mode', {'mode': 'safe-disabled'}), peer_uid=1000)
            self.assertFalse(out['ok'])
            out2 = svc.handle(_envelope('mode', {'mode': 'safe-disabled'}), peer_uid=0)
            self.assertTrue(out2['ok'])

    def test_empty_allowlist_denies_everyone(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=())
            out = svc.handle(_envelope('routeStage', {'stage': 'assist'}), peer_uid=0)
            self.assertFalse(out['ok'])

    def test_route_history_readonly_no_mutation(self):
        with tempfile.TemporaryDirectory() as td:
            svc = _make_service(td, allowed_uids=(0,))
            svc.handle(_envelope('routePlan', {'operations': []}), peer_uid=0)
            hist_before = len(svc.handle(_envelope('routeHistory', {}), peer_uid=0)['result']['entries'])
            # Reading history must not add entries.
            svc.handle(_envelope('routeHistory', {}), peer_uid=0)
            hist_after = len(svc.handle(_envelope('routeHistory', {}), peer_uid=0)['result']['entries'])
            self.assertEqual(hist_before, hist_after)


if __name__ == '__main__':
    unittest.main()