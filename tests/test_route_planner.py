"""RoutePlanner: deterministic, declarative, schema-valid, managed-scope-only.

A plan must be byte-stable for the same topology + operations (determinism),
must reject any non-allowlisted op / unsafe character / arbitrary path, must
bind sourceConfigSha256 / planSha256, and must never produce shell/argv/code.
"""
import unittest

from rill_xray_agent.canonical import canonical_bytes
from rill_xray_agent.route_planner import (
    ALLOWED_OPS, RoutePlanner)
from rill_xray_agent.route_topology import RouteTopologyProjection


def make_topology(routing=None, generation=2, digest_sha=None):
    routing = routing if routing is not None else {
        'rules': [
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'proxy'},
            {'tag': 'rill-managed-aaa111', 'type': 'field', 'domain': ['x.com'],
             'outboundTag': 'proxy'},
        ]}
    proj = RouteTopologyProjection(
        routing, config_generation=generation,
        whole_config_safe_digest=digest_sha or ('cd' * 32),
        captured_at_epoch_seconds=1000).project()
    proj['configurationGeneration'] = generation
    return proj


def planner(**kw):
    return RoutePlanner(make_topology(), **kw)


INSERT = {'op': 'routingRule.insert',
          'params': {'position': 1, 'selectorType': 'domain',
                     'selectorValue': ['new.example.com'], 'outboundTag': 'proxy'}}


class RoutePlannerTest(unittest.TestCase):
    def test_allowed_ops_exact(self):
        self.assertEqual(ALLOWED_OPS, {
            'routingRule.insert', 'routingRule.removeManaged',
            'routingRule.replaceManaged', 'routingRule.moveManaged'})

    def test_plan_schema_fields(self):
        p = planner().plan([INSERT])
        self.assertEqual(p['schemaVersion'], 1)
        self.assertEqual(set(p), {'schemaVersion', 'recommendationId',
                                  'createdAtEpochSeconds', 'expiresAtEpochSeconds',
                                  'configurationGeneration', 'sourceConfigSha256',
                                  'topologySha256', 'risk', 'reasonCode',
                                  'operations', 'preconditions', 'verification',
                                  'managedScopeOnly', 'planSha256'})
        self.assertEqual(p['configurationGeneration'], 2)
        self.assertEqual(p['sourceConfigSha256'], 'cd' * 32)
        self.assertEqual(p['managedScopeOnly'], True)
        self.assertEqual(p['expiresAtEpochSeconds'],
                         p['createdAtEpochSeconds'] + p['createdAtEpochSeconds'] - p['createdAtEpochSeconds'] + 300)

    def test_determinism_same_input_same_plan(self):
        p1 = planner().plan([INSERT], now=123)
        p2 = planner().plan([INSERT], now=123)
        self.assertEqual(canonical_bytes(p1), canonical_bytes(p2))
        self.assertEqual(p1['planSha256'], p2['planSha256'])
        self.assertEqual(p1['recommendationId'], p2['recommendationId'])

    def test_determinism_stable_across_planner_instances(self):
        a = RoutePlanner(make_topology()).plan([INSERT], now=5)
        b = RoutePlanner(make_topology()).plan([INSERT], now=5)
        self.assertEqual(a['recommendationId'], b['recommendationId'])
        self.assertEqual(a['planSha256'], b['planSha256'])

    def test_plan_digest_binds_operations(self):
        p = planner().plan([INSERT], now=123)
        from rill_xray_agent.route_planner import plan_digest
        # planSha256 must equal the canonical digest of the plan body (the
        # self-referential field is excluded from its own digest).
        self.assertEqual(p['planSha256'], plan_digest(p))
        # The digest is stable for identical plans.
        self.assertEqual(p['planSha256'], planner().plan([INSERT], now=123)['planSha256'])

    def test_unknown_operation_rejected(self):
        with self.assertRaises(ValueError):
            planner().plan([{'op': 'routingRule.sedEdit',
                             'params': {'command': 's/foo/bar/'}}])

    def test_arbitrary_path_rejected(self):
        with self.assertRaises(ValueError):
            planner().plan([{'op': 'routingRule.insert',
                             'params': {'position': 0, 'selectorType': 'domain',
                                        'selectorValue': ['/etc/passwd'],
                                        'outboundTag': '/tmp/x'}}])

    def test_shell_metacharacters_rejected(self):
        for bad in ['; rm -rf /', '$(id)', '`id`', 'a"b', "a'b", 'a\\b', 'a\nb']:
            with self.assertRaises(ValueError):
                planner().plan([{'op': 'routingRule.insert',
                                 'params': {'position': 0, 'selectorType': 'domain',
                                            'selectorValue': [bad], 'outboundTag': 'x'}}])

    def test_managed_scope_always_true(self):
        ops = RoutePlanner.canonicalize_operations([INSERT])
        self.assertTrue(all(o['managedScope'] is True for o in ops))

    def test_index_must_be_non_negative_int(self):
        for bad in (-1, '1', 1.5, True, None):
            with self.assertRaises(ValueError):
                RoutePlanner.canonicalize_operations([{'op': 'routingRule.removeManaged',
                                                       'params': {'ruleIndex': bad}}])

    def test_unknown_params_rejected(self):
        with self.assertRaises(ValueError):
            RoutePlanner.canonicalize_operations([{'op': 'routingRule.insert',
                                                   'params': {'position': 0, 'selectorType': 'domain',
                                                              'selectorValue': ['x.com'],
                                                              'outboundTag': 'proxy', 'shell': 'rm -rf'}}])

    def test_operations_digest_stable(self):
        a = RoutePlanner.canonicalize_operations([INSERT])
        b = RoutePlanner.canonicalize_operations([INSERT])
        from rill_xray_agent.canonical import digest
        self.assertEqual(digest({'operations': a}), digest({'operations': b}))

    def test_risk_low_for_insert_end(self):
        p = RoutePlanner(make_topology()).plan([
            {'op': 'routingRule.insert',
             'params': {'position': 99, 'selectorType': 'domain',
                        'selectorValue': ['z.com'], 'outboundTag': 'proxy'}}], now=1)
        self.assertEqual(p['risk'], 'low')

    def test_risk_medium_for_replace_selector_type_change(self):
        p = RoutePlanner(make_topology()).plan([
            {'op': 'routingRule.replaceManaged',
             'params': {'ruleIndex': 1, 'selectorType': 'ip',
                        'selectorValue': ['1.2.3.4/32'], 'outboundTag': 'proxy'}}], now=1)
        self.assertEqual(p['risk'], 'medium')

    def test_reason_code_and_preconditions(self):
        p = planner().plan([INSERT], now=1)
        self.assertEqual(p['reasonCode'], 'managed-route-plan:routingRule.insert')
        self.assertIn('source-config-sha256-unchanged', p['preconditions'])

    def test_no_code_or_shell_fields(self):
        p = planner().plan([INSERT], now=1)
        blob = repr(p)
        for token in ('shell', 'command', 'exec', 'eval', 'subprocess', 'argv',
                      'system(', 'os.system'):
            self.assertNotIn(token, blob)

    def test_accepts_whole_config_sha_alias(self):
        topo = make_topology()
        topo.pop('wholeConfigSha256', None)
        topo['sourceConfigSha256'] = 'ef' * 32
        p = RoutePlanner(topo).plan([INSERT], now=1)
        self.assertEqual(p['sourceConfigSha256'], 'ef' * 32)

    def test_empty_operations_plan(self):
        p = planner().plan([], now=1)
        self.assertEqual(p['operations'], [])
        self.assertEqual(p['risk'], 'low')
        self.assertEqual(p['reasonCode'], 'no-operations')


if __name__ == '__main__':
    unittest.main()
