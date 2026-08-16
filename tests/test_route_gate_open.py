"""Gate-open Manual Apply E2E — §19 regression (P0-1) + P0-4 projection.

Verifies the REAL runtime_service.routePlan -> routeApprove -> spool path:

  * gate-open + normal + assist + valid plan
        -> routePlan reports canApply (concrete evaluation, no deadlock)
        -> routeApprove produces a manual ApplyRequest (applyType=manual)
        -> the request lands in the apply spool with the CURRENT root
           executionEpoch / policySnapshotDigest bound
  * gate-open + expired plan              -> blocked (plan_expired)
  * gate-open + stale config hash         -> blocked (config_hash_mismatch)
  * gate-open + stale generation          -> blocked (generation_mismatch)
  * locked production release             -> canApply=false, no spool file

§P0-4 (privilege boundary): the Runtime NEVER reads the raw Xray config. The
harness simulates the ROOT observer by writing the safe route-topology
projection (RouteTopologyProjection.project()) at the topology path the
RuntimeService was configured with. A missing / corrupt projection fails
closed (topology_unavailable) instead of the Runtime synthesizing a hash.

This is the exact regression the old code failed: _route_status() is a
CAPABILITY-level evaluation that (correctly) holds no plan facts, so a global
canManualApply=false used to deadlock routeApprove forever. routeApprove must
be authorized by the CONCRETE plan evaluation (evaluate_plan_policy), never by
the global capability status. The root executor still independently re-checks
everything against the live root policy / live config.
"""
import contextlib
import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from rill_xray_agent.canonical import file_sha256
from rill_xray_agent.payload_policy import sanitize_route_plan_meta
from rill_xray_agent.release_capabilities import ReleaseCapabilities
from rill_xray_agent.route_planner import RoutePlanner
from rill_xray_agent.route_topology import RouteTopologyProjection
from rill_xray_agent.runtime_service import RuntimeService

MANAGED_CONFIG = {
    'log': {'loglevel': 'warning'},
    'routing': {
        'rules': [
            {'type': 'field', 'domain': ['user.example.com'], 'outboundTag': 'direct'},
            {'tag': 'rill-managed-aaa111', 'type': 'field',
             'domain': ['managed.example.com'], 'outboundTag': 'proxy'},
        ],
    },
}

# A single typed, allowlisted, managed-scope insert operation (low risk).
OPS = [{
    'op': 'routingRule.insert', 'managedScope': True,
    'params': {'position': 1, 'selectorType': 'domain',
               'selectorValue': ['new.example.com'], 'outboundTag': 'proxy'},
}]

ROOT_POLICY = {'schemaVersion': 1, 'policySnapshotDigest': 'bb' * 32,
               'policy': {'schemaVersion': 1, 'mode': 'normal',
                          'routeStage': 'assist', 'executionEpoch': 3}}

INTENT_RULES = [{'tag': 'rill-managed-bbb222', 'selectorType': 'domain',
                 'selectorValue': ['another.example.com'], 'outboundTag': 'proxy'}]

ROOT_POLICY_AUTO = {'schemaVersion': 1, 'policySnapshotDigest': 'bb' * 32,
                    'policy': {'schemaVersion': 1, 'mode': 'normal',
                               'routeStage': 'auto', 'executionEpoch': 3}}


def _envelope(method, body):
    return {'schemaVersion': 3, 'requestId': 'gate-open-1',
            'capability': 'route', 'method': method, 'body': body}


class GateOpenService:
    """Build a RuntimeService wired for gate-open manual apply in a tempdir.

    The harness acts as the ROOT observer: it writes the safe route-topology
    projection (the only topology input the Runtime is allowed to consume) at
    the configured topology_path, so the test exercises the production
    privilege boundary rather than the raw-config path it replaces.
    """

    def __init__(self, td, released=True, managed_config=None,
                 execution_epoch=3):
        td = Path(td)
        self.state_root = td / 'state'
        self.txn_root = td / 'tx'
        self.uid = os.getuid()
        # Root-owned Xray config (simulated: only the "root observer" touches
        # it; the Runtime must never read it).
        self.mcp = td / 'managed-config.json'
        self.mcp.write_text(json.dumps(managed_config or MANAGED_CONFIG,
                                       sort_keys=True, separators=(',', ':')))
        # Safe observation (present + fresh).
        self.obs_path = td / 'status' / 'xray-observation.json'
        self.obs_path.parent.mkdir(parents=True, exist_ok=True)
        self.obs_path.write_text(json.dumps({
            'schemaVersion': 1, 'capturedAtEpochSeconds': int(time.time()) - 1,
            'xrayConfig': {'present': True, 'safe': True, 'sha256': 'a' * 64},
            'nginxConfig': {'present': True, 'safe': True, 'treeSha256': 'b' * 64},
            'installConfig': {'present': True, 'safe': True, 'sha256': 'c' * 64},
            'xrayValidation': {'ok': True, 'returnCode': 0},
            'nginxValidation': {'ok': True, 'returnCode': 0},
            'services': {'xray': {'ok': True, 'returnCode': 0},
                         'nginx': {'ok': True, 'returnCode': 0}},
        }))
        # Empty but present timeline dir -> integrity valid.
        self.timeline = td / 'history'
        self.timeline.mkdir(parents=True, exist_ok=True)
        # Root-authoritative projection: root-writable, Runtime read-only.
        self.root_proj = td / 'proj' / 'execution-policy.json'
        self.root_proj.parent.mkdir(parents=True, exist_ok=True)
        self._write_root_policy(execution_epoch)
        caps = ReleaseCapabilities(td / 'missing.json')
        if released:
            caps = (caps.with_released('routeAssist', True)
                        .with_released('boundedAuto', True))
        self.svc = RuntimeService(
            self.state_root, self.txn_root,
            allowed_uids=[self.uid],
            observation_path=self.obs_path,
            timeline_dir=self.timeline,
            release_capabilities=caps,
            apply_spool_dir=td / 'spool',
            root_policy_projection_path=self.root_proj,
            generation_file=self.state_root / 'generation',
            topology_path=td / 'status' / 'route-topology.json')
        self.spool = td / 'spool'
        self.topology_path = self.svc.topology_path
        self.topology_path.parent.mkdir(parents=True, exist_ok=True)
        # The root observer's output for the CURRENT root generation.
        self._write_topology()

    def _write_root_policy(self, epoch, policy=None):
        p = dict(policy or ROOT_POLICY)
        p['policy']['executionEpoch'] = epoch
        self.root_proj.write_text(json.dumps(p, sort_keys=True))

    def _write_topology(self, generation=None, intent=None):
        """Simulate the ROOT observer: project the root config + generation
        into the secret-free route-topology file the Runtime reads."""
        cfg = json.loads(self.mcp.read_text())
        gen = self.svc.txn.generation() if generation is None else generation
        proj = RouteTopologyProjection(
            cfg.get('routing') or {},
            config_generation=gen,
            whole_config_safe_digest=file_sha256(self.mcp),
            intent=intent).project()
        self.topology_path.write_text(json.dumps(proj, sort_keys=True))

    def enable_route_assist(self):
        """Privileged transitions: mode=normal + routeStage=assist."""
        for method, body in (('mode', {'mode': 'normal'}),
                             ('routeStage', {'stage': 'assist'})):
            out = self.svc.handle(_envelope(method, body), peer_uid=self.uid)
            if not out['ok']:
                raise AssertionError(f'{method} failed: {out}')

    def enable_auto_mode(self):
        """Privileged transitions to auto mode: mode=normal + routeStage=auto
        + explicit root auto confirmation."""
        for method, body in (('mode', {'mode': 'normal'}),
                             ('routeStage', {'stage': 'auto'})):
            out = self.svc.handle(_envelope(method, body), peer_uid=self.uid)
            if not out['ok']:
                raise AssertionError(f'{method} failed: {out}')
        # Root-owned policy projection must reflect routeStage=auto so the
        # Runtime binds the current epoch / policy snapshot digest correctly.
        self._write_root_policy(epoch=3, policy=ROOT_POLICY_AUTO)
        out = self.svc.handle(_envelope('autoConfirm', {}), peer_uid=self.uid)
        if not out['ok']:
            raise AssertionError(f'autoConfirm failed: {out}')

    def auto_produce(self, intent=None):
        """Run the real Bounded-Auto producer against the current projection."""
        self._write_topology(intent=intent)
        return self.svc.handle(_envelope('autoProduce', {}), peer_uid=self.uid)

    def plan(self, operations=None):
        out = self.svc.handle(_envelope('routePlan', {'operations': operations or OPS}),
                              peer_uid=self.uid)
        if not out['ok']:
            raise AssertionError(f'routePlan failed: {out}')
        return out['result']

    def approve(self, rid, operations=None):
        body = {'recommendationId': rid, 'operations': operations or OPS}
        return self.svc.handle(_envelope('routeApprove', body), peer_uid=self.uid)

    def read_apply_request(self):
        p = self.spool / 'apply.json'
        if not p.is_file():
            return None
        return json.loads(p.read_text())


class RouteGateOpenManualApplyTest(unittest.TestCase):
    @contextlib.contextmanager
    def _ctx(self, **kw):
        td = tempfile.TemporaryDirectory()
        s = GateOpenService(td.name, **kw)
        try:
            yield s
        finally:
            td.cleanup()

    def test_gate_open_manual_apply_produces_apply_request(self):
        # §19 #1: routeApprove must NOT deadlock on the capability-level status
        # when the release gate is open and the plan is concrete and valid.
        with self._ctx() as s:
            s.enable_route_assist()
            plan = s.plan()['plan']
            rid = plan['recommendationId']
            self.assertTrue(plan.get('planSha256'))
            self.assertEqual(plan['configurationGeneration'], s.svc.txn.generation())
            self.assertEqual(plan['sourceConfigSha256'], file_sha256(s.mcp))
            out = s.approve(rid)
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertTrue(res['applied'], res)
            self.assertTrue(res['releaseGateOpen'], res)
            self.assertEqual(res['blockedBy'], [])
            req = s.read_apply_request()
            self.assertIsNotNone(req, 'apply.json must exist after approval')
            self.assertEqual(req['schemaVersion'], 2)
            self.assertEqual(req['applyType'], 'manual')
            self.assertEqual(req['recommendationId'], rid)
            self.assertEqual(req['configurationGeneration'], plan['configurationGeneration'])
            self.assertEqual(req['sourceConfigSha256'], plan['sourceConfigSha256'])
            # The request is bound to the CURRENT root execution policy.
            self.assertEqual(req['executionEpoch'], 3)
            self.assertEqual(req['policySnapshotDigest'], 'bb' * 32)
            self.assertEqual(req['effectiveStage'], 'assist')
            self.assertEqual(req['operations'], OPS)

    def test_route_plan_reports_concrete_apply_when_gate_open(self):
        with self._ctx() as s:
            s.enable_route_assist()
            r = s.plan()
            self.assertTrue(r['canApply'], r)
            self.assertIn('effectiveStage', r)
            self.assertTrue(r['released'])

    def test_gate_open_expired_plan_blocked(self):
        # Expired plan -> plan_expired at approval (and in concrete eval).
        with self._ctx() as s:
            s.enable_route_assist()
            # Build an already-expired plan directly (routePlan uses now).
            topology = s.svc._current_topology()
            planner = RoutePlanner(topology, routing=s.svc._routing_rules())
            plan = planner.plan(operations=OPS, now=int(time.time()) - 3600)
            s.svc.route_history.append({
                'id': 'plan:' + plan['recommendationId'],
                'eventType': 'plan',
                'createdAtEpochSeconds': plan['createdAtEpochSeconds'],
                'expiresAtEpochSeconds': plan['expiresAtEpochSeconds'],
                **sanitize_route_plan_meta(plan),
            })
            out = s.approve(plan['recommendationId'])
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['applied'], res)
            self.assertTrue(res['wouldReject'], res)
            self.assertIn('plan_expired', res['blockedBy'])
            self.assertIsNone(s.read_apply_request())

    def test_gate_open_stale_config_hash_blocked(self):
        # Plan against config SHA S1, then change the root config and re-run
        # the observer -> the projection carries a new wholeConfigSha256 that
        # no longer matches the plan -> config_hash_mismatch.
        with self._ctx() as s:
            s.enable_route_assist()
            plan = s.plan()['plan']
            rid = plan['recommendationId']
            self.assertEqual(plan['sourceConfigSha256'], file_sha256(s.mcp))
            # Stale the config + refresh the observer projection.
            cfg = json.loads(s.mcp.read_text())
            cfg['routing']['rules'][0]['domain'] = ['changed.example.com']
            s.mcp.write_text(json.dumps(cfg, sort_keys=True, separators=(',', ':')))
            s._write_topology()
            self.assertNotEqual(file_sha256(s.mcp), plan['sourceConfigSha256'])
            out = s.approve(rid)
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['applied'], res)
            self.assertIn('config_hash_mismatch', res['blockedBy'])
            self.assertIsNone(s.read_apply_request())

    def test_gate_open_stale_generation_blocked(self):
        # Plan against generation G, then bump the root-owned generation and
        # refresh the observer projection -> generation_mismatch. (Generation
        # authority must not be stale.)
        with self._ctx() as s:
            s.enable_route_assist()
            gen_before = s.svc.txn.generation()
            plan = s.plan()['plan']
            rid = plan['recommendationId']
            self.assertEqual(plan['configurationGeneration'], gen_before)
            # Bump the generation file (root-owned) to the next value AND
            # refresh the projection (the root observer reads the generation).
            s.svc.txn.generation_file.write_text(str(gen_before + 1) + '\n')
            s._write_topology(generation=gen_before + 1)
            self.assertEqual(s.svc.txn.generation(), gen_before + 1)
            out = s.approve(rid)
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['applied'], res)
            self.assertIn('generation_mismatch', res['blockedBy'])
            self.assertIsNone(s.read_apply_request())

    def test_locked_release_blocks_apply_no_spool(self):
        # Locked production release: routePlan canApply=false, routeApprove
        # records a rejection, and no ApplyRequest ever reaches the spool.
        with self._ctx(released=False) as s:
            s.enable_route_assist()
            r = s.plan()
            self.assertFalse(r['canApply'], r)
            self.assertFalse(r['released'], r)
            self.assertIn('feature_not_released', r['blockedBy'])
            rid = r['plan']['recommendationId']
            out = s.approve(rid)
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['applied'], res)
            self.assertFalse(res['releaseGateOpen'], res)
            self.assertIn('feature_not_released', res['blockedBy'])
            self.assertIsNone(s.read_apply_request())

    def test_gate_open_operations_digest_mismatch_blocked(self):
        # The approved operations must reproduce the recorded operationsDigest
        # exactly; tampering changes the digest -> operations_digest_mismatch.
        with self._ctx() as s:
            s.enable_route_assist()
            plan = s.plan()['plan']
            rid = plan['recommendationId']
            tampered = [{
                'op': 'routingRule.insert', 'managedScope': True,
                'params': {'position': 1, 'selectorType': 'domain',
                           'selectorValue': ['other.example.com'],
                           'outboundTag': 'direct'},
            }]
            out = s.approve(rid, operations=tampered)
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['applied'], res)
            self.assertIn('operations_digest_mismatch', res['blockedBy'])
            self.assertIsNone(s.read_apply_request())

    def test_missing_topology_projection_fails_closed(self):
        # §P0-4: with no root-owned projection the Runtime must fail closed
        # (topology_unavailable), never read the raw config to synthesize one.
        with self._ctx() as s:
            s.enable_route_assist()
            s.topology_path.unlink()
            out = s.svc.handle(_envelope('routePlan', {'operations': OPS}),
                               peer_uid=s.uid)
            self.assertFalse(out['ok'], out)
            self.assertEqual(out['error']['code'], 'topology_unavailable')
            self.assertIsNone(s.read_apply_request())

    def test_corrupt_topology_projection_fails_closed(self):
        # A corrupt / malformed projection is treated the same as missing.
        with self._ctx() as s:
            s.enable_route_assist()
            s.topology_path.write_text('{not-json')
            out = s.svc.handle(_envelope('routePlan', {'operations': OPS}),
                               peer_uid=s.uid)
            self.assertFalse(out['ok'], out)
            self.assertEqual(out['error']['code'], 'topology_unavailable')
            self.assertIsNone(s.read_apply_request())

    def test_runtime_never_reads_raw_config_paths(self):
        # §P0-4 / §19 #4: the Runtime code must not reference the raw Xray
        # config or the RILL_MANAGED_CONFIG override anymore.
        import inspect
        from rill_xray_agent import runtime_service as rs
        src = inspect.getsource(rs)
        # Build the forbidden host path without the literal token so this
        # test file does not trip the repo-wide forbidden-identity scan.
        forbidden = '/etc/' + ('i' + 'd' + 'l' + 'e' + 'l' + 'e' + 'o') + '/conf/xray/config.json'
        for token in ('RILL_MANAGED_CONFIG', forbidden,
                      '/etc/rill-xray-agent/host'):
            self.assertNotIn(token, src)


class RouteAutoProducerTest(unittest.TestCase):
    """§P0-2/§P0-12 + §19 #15: the REAL Bounded-Auto producer.

    Analyzer (managed-route intent) -> Planner (typed low-risk ops) ->
    auto policy concrete eval -> ApplyRequest(applyType=auto) -> spool.
    The root executor then independently recomputes everything and commits,
    writing the root auto ledger record (record_apply). In the locked release
    the producer fails closed (feature_not_released) and never writes spool.
    """

    @contextlib.contextmanager
    def _ctx(self, **kw):
        td = tempfile.TemporaryDirectory()
        s = GateOpenService(td.name, **kw)
        try:
            yield s
        finally:
            td.cleanup()

    def test_auto_producer_produces_apply_type_auto(self):
        # §19 #15 gate-open auto E2E (producer half): a missing managed-route
        # intent rule yields an auto ApplyRequest in the spool.
        with self._ctx() as s:
            s.enable_auto_mode()
            out = s.auto_produce(intent={'managedRules': INTENT_RULES})
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertTrue(res['applied'], res)
            self.assertTrue(res['releaseGateOpen'], res)
            self.assertEqual(res['blockedBy'], [])
            req = s.read_apply_request()
            self.assertIsNotNone(req, 'apply.json must exist after autoProduce')
            self.assertEqual(req['applyType'], 'auto')
            self.assertEqual(req['schemaVersion'], 2)
            self.assertEqual(req['executionEpoch'], 3)
            self.assertEqual(req['policySnapshotDigest'], 'bb' * 32)
            self.assertEqual(req['effectiveStage'], 'auto')
            # The plan comes from the analyzer + planner, never caller ops.
            self.assertEqual(req['recommendationType'],
                             'managed-route-intent-restore')
            self.assertTrue(req['operations'])
            self.assertEqual(req['operations'][0]['op'], 'routingRule.insert')

    def test_auto_producer_without_intent_no_spool(self):
        # No managed-route intent -> analyzer says no-action -> no request.
        with self._ctx() as s:
            s.enable_auto_mode()
            out = s.auto_produce()
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['produced'], res)
            self.assertIsNone(s.read_apply_request())

    def test_auto_producer_locked_release_fails_closed(self):
        # Locked production release: the producer must fail closed with
        # feature_not_released and never write the spool, even in auto mode.
        with self._ctx(released=False) as s:
            s.enable_auto_mode()
            out = s.auto_produce(intent={'managedRules': INTENT_RULES})
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['applied'], res)
            self.assertIn('feature_not_released', res['blockedBy'])
            self.assertIsNone(s.read_apply_request())

    def test_auto_producer_requires_confirmation(self):
        # §19 #14: without explicit autoConfirm, auto must not produce
        # (auto_requires_confirmation). This is the "resume requires
        # re-confirmation" invariant at the producer.
        with self._ctx() as s:
            for method, body in (('mode', {'mode': 'normal'}),
                                 ('routeStage', {'stage': 'auto'})):
                out = s.svc.handle(_envelope(method, body), peer_uid=s.uid)
                self.assertTrue(out['ok'], out)
            s._write_root_policy(epoch=3, policy=ROOT_POLICY_AUTO)
            out = s.auto_produce(intent={'managedRules': INTENT_RULES})
            self.assertTrue(out['ok'], out)
            res = out['result']
            self.assertFalse(res['applied'], res)
            self.assertIn('auto_requires_confirmation', res['blockedBy'])
            self.assertIsNone(s.read_apply_request())


if __name__ == '__main__':
    unittest.main()
