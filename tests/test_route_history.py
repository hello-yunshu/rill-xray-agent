"""RouteHistory: bounded, secret-free, thread-safe, prune-on-overflow.

Every entry is validated against a strict scalar allowlist. Forbidden fields
(UUID, privateKey, shortId, proxy URLs, vless/vmess/trojan links) are
rejected. The history prunes to max_entries when the cap is exceeded.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.route_history import RouteHistory


def plan_entry(overrides=None):
    e = {
        'id': 'plan:rec-001',
        'eventType': 'plan',
        'createdAtEpochSeconds': 1000,
        'expiresAtEpochSeconds': 2000,
        'recommendationId': 'rec-001',
        'planSha256': 'aa' * 32,
        'sourceConfigSha256': 'bb' * 32,
        'configurationGeneration': 3,
        'risk': 'low',
        'reasonCode': 'managed-route-plan:routingRule.insert',
        'operationCount': 1,
        'operationKinds': ['routingRule.insert'],
        'operationsDigest': 'cc' * 32,
    }
    if overrides:
        e.update(overrides)
    return e


class RouteHistoryTest(unittest.TestCase):
    def test_append_and_read(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            entry = plan_entry()
            h.append(entry)
            entries = h.read()
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['id'], 'plan:rec-001')

    def test_read_empty(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'missing.jsonl')
            self.assertEqual(h.read(), [])

    def test_forbidden_fields_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            for token in ('vless://', 'vmess://', 'trojan://', 'ssh://',
                          'privatekey', 'publickey', 'shortid', '-----begin '):
                with self.assertRaises(ValueError, msg=f'token={token}'):
                    h.append(plan_entry({'reasonCode': token}))

    def test_forbidden_fields_in_operation_kinds(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            with self.assertRaises(ValueError):
                h.append(plan_entry({'operationKinds': ['routingRule.insert', 'vless://x']}))

    def test_unknown_field_dropped(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            entry = plan_entry({'rawConfig': '{"privateKey":"x"}', 'nested': {'a': 1}})
            safe = h.append(entry)
            self.assertNotIn('rawConfig', safe)
            self.assertNotIn('nested', safe)

    def test_missing_required_field_fails(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            with self.assertRaises(ValueError):
                h.append({'eventType': 'plan', 'createdAtEpochSeconds': 1})
            with self.assertRaises(ValueError):
                h.append({'id': 'x', 'eventType': 'plan'})

    def test_oversized_entry_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            with self.assertRaises(ValueError):
                h.append(plan_entry({'reasonCode': 'x' * 5000}))

    def test_invalid_event_type_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            with self.assertRaises(ValueError):
                h.append({'id': 'x', 'eventType': 'hack', 'createdAtEpochSeconds': 1})

    def test_prune_on_overflow(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl', max_entries=5)
            for i in range(10):
                h.append(plan_entry({'id': f'plan:rec-{i:03d}',
                                     'recommendationId': f'rec-{i:03d}'}))
            entries = h.read(limit=100)
            self.assertEqual(len(entries), 5)
            self.assertEqual(entries[0]['id'], 'plan:rec-005')

    def test_get_by_id(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            h.append(plan_entry({'id': 'plan:rec-001'}))
            h.append(plan_entry({'id': 'plan:rec-002'}))
            found = h.get('plan:rec-001')
            self.assertIsNotNone(found)
            self.assertEqual(found['id'], 'plan:rec-001')
            self.assertIsNone(h.get('nonexistent'))

    def test_approve_reject_types(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            for et in ('approve', 'reject'):
                h.append({'id': f'{et}:x', 'eventType': et,
                          'createdAtEpochSeconds': 1000,
                          'recommendationId': 'x', 'applied': True,
                          'wouldReject': False, 'blockedBy': [],
                          'mode': 'normal', 'releaseReleased': False})
            self.assertEqual(len(h.read()), 2)

    def test_auto_status_type(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            h.append({'id': 'auto:x', 'eventType': 'auto-status',
                      'createdAtEpochSeconds': 1000,
                      'effectiveStage': 'observe', 'wouldApply': False,
                      'blockedBy': ['feature_not_released']})
            self.assertEqual(len(h.read()), 1)

    def test_int_field_validation(self):
        with tempfile.TemporaryDirectory() as td:
            h = RouteHistory(Path(td) / 'history.jsonl')
            for bad in (True, '1', 1.5, [1]):
                with self.assertRaises(ValueError):
                    h.append(plan_entry({'configurationGeneration': bad}))


if __name__ == '__main__':
    unittest.main()