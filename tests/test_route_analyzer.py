"""RouteAnalyzer: deterministic recommendations + semantic fingerprint.

A recommendation id must be a SEMANTIC fingerprint: the same semantic problem
must not produce a fresh id merely because the capture timestamp changed. The
analyzer only classifies; it never emits operations, shell, argv or paths.
"""
import unittest

from rill_xray_agent.route_analyzer import (RouteAnalyzer, auto_eligible,
                                            semantic_fingerprint)
from rill_xray_agent.route_topology import RouteTopologyProjection


def projection(rules, generation=3, digest_sha='ab' * 32, captured=1000):
    return RouteTopologyProjection(
        {'rules': rules}, config_generation=generation,
        whole_config_safe_digest=digest_sha,
        captured_at_epoch_seconds=captured).project()


MANAGED = {'type': 'field', 'tag': 'rill-managed-aaa111',
           'domain': ['x.com'], 'outboundTag': 'proxy'}


class RouteAnalyzerTest(unittest.TestCase):
    def test_no_recommendation_when_no_managed_shadow(self):
        topo = projection([
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'proxy'},
            MANAGED,
        ])
        rec = RouteAnalyzer(topo).analyze()
        self.assertEqual(rec['recommendationType'], 'no-recommendation')
        self.assertEqual(rec['risk'], 'low')
        self.assertEqual(rec['confidenceBand'], 'high')

    def test_shadowed_managed_rule_detected(self):
        topo = projection([
            {'type': 'field', 'domain': ['x.com'], 'outboundTag': 'a'},
            MANAGED,  # same predicate, later -> shadowed
        ])
        rec = RouteAnalyzer(topo).analyze()
        self.assertEqual(rec['recommendationType'], 'managed-rule-shadowed')
        self.assertEqual(rec['risk'], 'low')
        self.assertEqual(rec['shadowing'], {1: 0})

    def test_semantic_fingerprint_stable_across_capture(self):
        # Same semantic situation at different capture timestamps -> same id.
        t1 = RouteAnalyzer(projection([
            {'type': 'field', 'domain': ['x.com'], 'outboundTag': 'a'},
            MANAGED], captured=1000)).analyze()
        t2 = RouteAnalyzer(projection([
            {'type': 'field', 'domain': ['x.com'], 'outboundTag': 'a'},
            MANAGED], captured=99999)).analyze()
        self.assertEqual(t1['semanticFingerprint'], t2['semanticFingerprint'])
        self.assertEqual(t1['recommendationId'], t2['recommendationId'])

    def test_semantic_fingerprint_differs_on_semantic_change(self):
        # Different selector semantics -> different fingerprint.
        t1 = RouteAnalyzer(projection([
            {'type': 'field', 'domain': ['x.com'], 'outboundTag': 'a'},
            MANAGED])).analyze()
        t2 = RouteAnalyzer(projection([
            {'type': 'field', 'domain': ['y.com'], 'outboundTag': 'a'},
            MANAGED])).analyze()
        self.assertNotEqual(t1['semanticFingerprint'], t2['semanticFingerprint'])

    def test_evidence_digest_binds_recommendation(self):
        rec = RouteAnalyzer(projection([
            {'type': 'field', 'domain': ['x.com'], 'outboundTag': 'a'},
            MANAGED])).analyze()
        self.assertEqual(len(rec['evidenceDigest']), 64)
        self.assertTrue(rec['evidenceDigest'])

    def test_analyzer_never_emits_operations(self):
        rec = RouteAnalyzer(projection([
            {'type': 'field', 'domain': ['x.com'], 'outboundTag': 'a'},
            MANAGED])).analyze()
        for token in ('shell', 'argv', 'command', 'operations', 'systemctl',
                      'subprocess', '/etc/'):
            self.assertNotIn(token, repr(rec), f'analyzer emitted {token}')

    def test_analyzer_rejects_invalid_input(self):
        with self.assertRaises(ValueError):
            RouteAnalyzer({'nope': 1}).analyze()

    def test_semantic_fingerprint_function(self):
        a = semantic_fingerprint('managed-rule-shadowed',
                                 {'managedShadowed': [[1, 0]]})
        b = semantic_fingerprint('managed-rule-shadowed',
                                 {'managedShadowed': [[1, 0]]})
        self.assertEqual(a, b)
        self.assertNotEqual(
            a, semantic_fingerprint('no-recommendation', {'x': 1}))

    def test_auto_eligible_allowlist(self):
        good = {'recommendationType': 'managed-rule-shadowed', 'risk': 'low'}
        bad_risk = {'recommendationType': 'managed-rule-shadowed', 'risk': 'high'}
        bad_type = {'recommendationType': 'unreachable-rule', 'risk': 'low'}
        self.assertTrue(auto_eligible(good))
        self.assertFalse(auto_eligible(bad_risk))
        self.assertFalse(auto_eligible(bad_type))


if __name__ == '__main__':
    unittest.main()
