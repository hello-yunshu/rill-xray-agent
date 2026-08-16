"""RouteTopologyProjection: safe, secret-free projection of Xray routing.

The projection must never leak UUID / privateKey / shortId / Reality material /
proxy URLs / VLESS links / raw config bodies. Selector values are persisted as
digests or non-sensitive enums only. Managed-rule ownership detection must work
across insert / restart / update.
"""
import unittest

from rill_xray_agent.route_topology import RouteTopologyProjection


SECRET_RULE = {
    'id': 'a92f8c9f-0f4f-4b7c-9d3a-7f8a9b0c1d2e',
    'domain': ['example.com'],
    'outboundTag': 'proxy',
    'tag': 'rill-managed-abc123',
}
REALITY_CONFIG_RULE = {
    'privateKey': '6KzhM9OBsZ0T9c7Vhx4N2mFpR1QvJ5tW8yXbL3eDcG',
    'shortId': 'abcdef0123456789',
    'protocol': 'reality',
    'tag': 'rill-managed-def456',
}
VLESS_RULE = {
    'type': 'field',
    'domain': ['vless://user@example.com:443?encryption=none'],
    'outboundTag': 'direct',
}


def sample_routing():
    return {
        'rules': [
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'proxy'},
            SECRET_RULE,
            {'type': 'field', 'ip': ['0.0.0.0/0'], 'outboundTag': 'direct'},
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'other',
             'tag': 'rill-managed-xyz789'},
        ]
    }


class TopologyProjectionTest(unittest.TestCase):
    def _project(self, routing=None, generation=3):
        return RouteTopologyProjection(
            routing if routing is not None else sample_routing(),
            config_generation=generation,
            whole_config_safe_digest='ab' * 32,
            captured_at_epoch_seconds=1000).project()

    def test_projection_shape(self):
        p = self._project()
        self.assertEqual(p['schemaVersion'], 2)
        self.assertEqual(p['configurationGeneration'], 3)
        self.assertNotIn('configGeneration', p)
        self.assertEqual(p['routingRulesCount'], 4)
        self.assertEqual(len(p['rules']), 4)
        self.assertEqual(p['wholeConfigSha256'], 'ab' * 32)
        self.assertEqual(p['wholeConfigSafeDigest'], 'ab' * 32)
        self.assertEqual(p['capturedAtEpochSeconds'], 1000)

    def test_no_secret_material_in_projection(self):
        p = self._project()
        blob = repr(p)
        for token in ('a92f8c9f', 'privateKey', 'shortId', '6KzhM9OB',
                      'vless://', 'user@example.com', '0.0.0.0/0',
                      'encryption=none', 'example.com'):
            self.assertNotIn(token, blob, f'projection leaked {token}')

    def test_rule_entries_are_metadata_only(self):
        p = self._project()
        for rule in p['rules']:
            base = {'ruleIndex', 'ruleKind',
                    'selectorTypes', 'selectorDigests',
                    'predicateDigest', 'outboundTag',
                    'isManaged', 'hasCatchAll', 'position'}
            expected = base | ({'managedId'} if rule['isManaged'] else set())
            self.assertEqual(set(rule), expected)
            self.assertNotIn('domain', rule)
            self.assertNotIn('ip', rule)
            self.assertNotIn('privateKey', rule)

    def test_managed_rule_has_managed_id(self):
        # Managed rules expose a secret-free managedId (digest of the tag);
        # unmanaged rules must NOT carry it.
        p = self._project()
        for rule in p['rules']:
            self.assertEqual('managedId' in rule, rule['isManaged'])
        managed_ids = [r['managedId'] for r in p['rules'] if r['isManaged']]
        self.assertEqual(len(managed_ids), 2)
        self.assertEqual(len(set(managed_ids)), 2)
        self.assertTrue(all(len(i) == 64 for i in managed_ids))

    def test_selector_value_is_digested(self):
        p = self._project()
        rule0 = p['rules'][0]
        self.assertEqual(rule0['selectorTypes'], ['domain'])
        self.assertNotIn('example.com', rule0['selectorDigests']['domain'])
        self.assertEqual(len(rule0['selectorDigests']['domain']), 64)  # sha256 hex
        self.assertEqual(len(rule0['predicateDigest']), 64)

    def test_multi_selector_predicate(self):
        # A rule with multiple selectors must record ALL of them (§10).
        p = RouteTopologyProjection({'rules': [
            {'type': 'field', 'domain': ['example.com'], 'port': '443',
             'inboundTag': ['foo'], 'outboundTag': 'proxy'},
        ]}).project()
        rule = p['rules'][0]
        self.assertEqual(rule['selectorTypes'], ['domain', 'port', 'inboundTag'])
        self.assertEqual(set(rule['selectorDigests']),
                         {'domain', 'port', 'inboundTag'})
        for field in ('domain', 'port', 'inboundTag'):
            self.assertEqual(len(rule['selectorDigests'][field]), 64)
        self.assertEqual(len(rule['predicateDigest']), 64)

    def test_multi_selector_not_shadowed_by_single_selector(self):
        # Full-predicate comparison: a single-selector rule must NOT shadow a
        # rule that additionally constrains by port.
        single = RouteTopologyProjection({'rules': [
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'a'},
            {'type': 'field', 'domain': ['example.com'], 'port': '443',
             'outboundTag': 'b'},
        ]}).unreachable_rules()
        self.assertEqual(single, {})

    def test_multi_selector_exact_duplicate_shadowed(self):
        dup = RouteTopologyProjection({'rules': [
            {'type': 'field', 'domain': ['example.com'], 'port': '443',
             'outboundTag': 'a'},
            {'type': 'field', 'port': '443', 'domain': ['example.com'],
             'outboundTag': 'b'},
        ]}).unreachable_rules()
        # Same full predicate (order of fields normalised) -> shadowed.
        self.assertIn(1, dup)

    def test_managed_ownership_detection(self):
        p = self._project()
        managed = [r['ruleIndex'] for r in p['rules'] if r['isManaged']]
        # SECRET_RULE tag rill-managed-abc123 and rill-managed-xyz789
        self.assertEqual(managed, [1, 3])

    def test_managed_rules_after_simulated_restart_update(self):
        # Ownership must survive restart / Xray update: same tag prefix.
        p1 = self._project(sample_routing(), generation=1)
        p2 = self._project(sample_routing(), generation=5)
        self.assertEqual([r['ruleIndex'] for r in p1['rules'] if r['isManaged']],
                         [r['ruleIndex'] for r in p2['rules'] if r['isManaged']])

    def test_user_rule_not_managed(self):
        # The first rule has no rill-managed tag -> isManaged False.
        p = self._project()
        self.assertFalse(p['rules'][0]['isManaged'])

    def test_unreachable_shadowing_detection(self):
        p = RouteTopologyProjection({'rules': [
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'a'},
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'b'},
            {'type': 'field', 'ip': ['1.2.3.4/32'], 'outboundTag': 'c'},
        ]}).project()
        self.assertEqual(p['rules'][0]['position'], 0)
        # unreachable_rules reports shadowed indexes with duplicate selector
        dup = RouteTopologyProjection({'rules': [
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'a'},
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'b'},
        ]}).unreachable_rules()
        self.assertIn(1, dup)

    def test_empty_routing(self):
        p = self._project({})
        self.assertEqual(p['routingRulesCount'], 0)
        self.assertEqual(p['rules'], [])

    def test_non_dict_routing_is_safe(self):
        p = RouteTopologyProjection(None).project()
        self.assertEqual(p['rules'], [])

    def test_catch_all_detection(self):
        p = RouteTopologyProjection({'rules': [
            {'type': 'field', 'outboundTag': 'direct'},
            {'type': 'field', 'domain': ['example.com'], 'outboundTag': 'proxy'},
        ]}).project()
        self.assertTrue(p['rules'][0]['hasCatchAll'])
        self.assertFalse(p['rules'][1]['hasCatchAll'])

    def test_reality_secret_rule_still_metadata_only(self):
        p = RouteTopologyProjection({'rules': [REALITY_CONFIG_RULE]}).project()
        blob = repr(p)
        for token in ('privateKey', 'shortId', '6KzhM9OB', 'abcdef0123456789'):
            self.assertNotIn(token, blob)
        self.assertEqual(p['rules'][0]['selectorTypes'], ['protocol'])
        self.assertEqual(len(p['rules'][0]['selectorDigests']['protocol']), 64)

    def test_vless_url_never_persisted(self):
        p = RouteTopologyProjection({'rules': [VLESS_RULE]}).project()
        blob = repr(p)
        for token in ('vless://', 'user@example.com', 'encryption=none'):
            self.assertNotIn(token, blob)


if __name__ == '__main__':
    unittest.main()
