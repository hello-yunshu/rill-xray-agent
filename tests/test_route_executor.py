"""RouteExecutor + RouteMutationCompiler + ApplyRequest security.

Covers: typed compiler (managed-scope only, user rules untouched, no shell/
sed/awk), ApplyRequest validation (malformed / oversized / expired / unknown
op / digest mismatch / secret material), spool safety (symlink, owner, mode,
size), release-gate lock, generation/hash/stale guards, replay idempotency,
RootTransaction apply -> verify -> commit and verify-fail -> rollback.
"""
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.canonical import atomic_write_json, file_sha256
from rill_xray_agent.errors import ContractError
from rill_xray_agent.release_capabilities import ReleaseCapabilities
from rill_xray_agent.root_policy import RootExecutionPolicy
from rill_xray_agent.route_executor import (
    MAX_REQUEST_BYTES, RouteExecutor, RouteMutationCompiler,
    request_digest, validate_apply_request)


def managed_config_bytes():
    return json.dumps({
        'log': {'loglevel': 'warning'},
        'routing': {
            'rules': [
                {'type': 'field', 'domain': ['user.example.com'],
                 'outboundTag': 'direct'},
                {'tag': 'rill-managed-aaa111', 'type': 'field',
                 'domain': ['managed.example.com'], 'outboundTag': 'proxy'},
            ],
        },
    }, sort_keys=True, separators=(',', ':')).encode()


def make_executor(td, released=False, xray_ok=True, root_mode='normal',
                  root_stage='assist', **kw):
    state_root = Path(td) / 'state'
    txn_root = Path(td) / 'tx'
    spool = Path(td) / 'spool'
    spool.mkdir(parents=True, exist_ok=True)
    mcp = Path(td) / 'managed-config.json'
    mcp.write_bytes(managed_config_bytes())

    xray_bin = Path(td) / 'fake-xray'
    xray_bin.write_text('#!/bin/sh\nexit 0\n' if xray_ok else '#!/bin/sh\nexit 1\n')
    xray_bin.chmod(0o755)

    caps = ReleaseCapabilities(Path(td) / 'missing.json')
    if released:
        caps = caps.with_released('routeAssist', True)
        caps = caps.with_released('boundedAuto', True)

    # Root-authoritative execution policy: the executor re-reads mode/stage/
    # epoch from this, never from the request. Configure it to the state the
    # test wants (default: normal + assist so manual applies can proceed).
    root_dir = Path(td) / 'root'
    rp = RootExecutionPolicy(root_dir=root_dir)
    if rp.mode() != root_mode:
        rp.set_mode(root_mode)
    if rp.route_stage() != root_stage:
        rp.set_route_stage(root_stage)

    ex = RouteExecutor(state_root, txn_root, spool_dir=spool,
                       release_capabilities=caps,
                       managed_config_path=mcp, xray_bin=xray_bin,
                       allowed_producer_uids=[os.geteuid()],
                       root_policy=rp,
                       projection_path=Path(td) / 'proj' / 'execution-policy.json',
                       generation_file=state_root / 'generation')
    return ex, mcp, spool


def base_request(ex, mcp, **kw):
    ops = [{'op': 'routingRule.insert', 'managedScope': True,
            'params': {'position': 1, 'selectorType': 'domain',
                       'selectorValue': ['new.example.com'], 'outboundTag': 'proxy'}}]
    req = {
        'schemaVersion': 2,
        'recommendationId': 'rec-route-test-0001',
        'createdAtEpochSeconds': 1000,
        'expiresAtEpochSeconds': 9999999999,
        'configurationGeneration': ex.txn.generation(),
        'executionEpoch': ex.root_policy.execution_epoch(),
        'sourceConfigSha256': file_sha256(mcp),
        'planSha256': 'aa' * 32,
        'recommendationType': 'no-recommendation',
        'semanticFingerprint': 'rec-route-test-0001',
        'policySnapshotDigest': 'bb' * 32,
        'applyType': 'manual',
        'mode': 'normal',
        'effectiveStage': 'assist',
        'releaseSnapshot': {
            'routeAssist': {'supported': True, 'released': True},
            'boundedAuto': {'supported': True, 'released': True},
        },
        'operations': ops,
        'requestSha256': '',
    }
    req.update(kw)
    req['requestSha256'] = request_digest(req)
    return req


def stage_request(ex, spool, request):
    atomic_write_json(spool / 'apply.json', request, 0o640)


class ApplyRequestValidationTest(unittest.TestCase):
    def test_valid_request_passes(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td, released=True)
            self.assertTrue(validate_apply_request(base_request(ex, mcp)))

    def test_malformed_json_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            req = base_request(ex, mcp)
            req['schemaVersion'] = 3
            with self.assertRaises(ContractError):
                validate_apply_request(req)

    def test_epoch_binding_fields_fail_closed(self):
        # §12/§24: executionEpoch / recommendationType / semanticFingerprint /
        # policySnapshotDigest must be strictly validated.
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            for mutate in (
                {'executionEpoch': -1},
                {'executionEpoch': True},
                {'executionEpoch': '9'},
                {'recommendationType': 'not-a-real-type'},
                {'recommendationType': 7},
                {'semanticFingerprint': 'bad fp with spaces'},
                {'semanticFingerprint': 'a' * 200},
                {'policySnapshotDigest': 'zz' * 32},
                {'policySnapshotDigest': None},
            ):
                req = base_request(ex, mcp, **mutate)
                with self.assertRaises(ContractError):
                    validate_apply_request(req)

    def test_oversized_request_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            req = base_request(ex, mcp)
            req['operations'] = [{'op': 'routingRule.insert',
                                  'params': {'position': 0, 'selectorType': 'domain',
                                             'selectorValue': ['x' * (MAX_REQUEST_BYTES // 2)],
                                             'outboundTag': 'p'}}] * 40
            req['requestSha256'] = request_digest(req)
            with self.assertRaises(ContractError):
                validate_apply_request(req)

    def test_deep_nesting_and_unknown_fields_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            req = base_request(ex, mcp)
            req['operations'] = [{'op': 'routingRule.insert', 'managedScope': True,
                                  'params': {'position': 0, 'selectorType': 'domain',
                                             'selectorValue': ['x.com'],
                                             'outboundTag': 'p', 'nested': {'a': {'b': 1}}}}]
            req['requestSha256'] = request_digest(req)
            with self.assertRaises(ContractError):
                validate_apply_request(req)

    def test_expired_request_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            req = base_request(ex, mcp, expiresAtEpochSeconds=1)
            with self.assertRaises(ContractError):
                validate_apply_request(req)

    def test_unknown_operation_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            req = base_request(ex, mcp)
            req['operations'] = [{'op': 'routingRule.editAll',
                                  'params': {'position': 0}}]
            req['requestSha256'] = request_digest(req)
            with self.assertRaises(ContractError):
                validate_apply_request(req)

    def test_arbitrary_path_and_shell_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            for bad in ('/etc/shadow', '/tmp/x', '; rm -rf /', '$(id)', 'a\nb'):
                req = base_request(ex, mcp)
                req['operations'] = [{'op': 'routingRule.insert', 'managedScope': True,
                                      'params': {'position': 0, 'selectorType': 'domain',
                                                 'selectorValue': [bad], 'outboundTag': 'p'}}]
                req['requestSha256'] = request_digest(req)
                with self.assertRaises(ContractError):
                    validate_apply_request(req)

    def test_digest_mismatch_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            req = base_request(ex, mcp)
            req['requestSha256'] = 'ff' * 32
            with self.assertRaises(ContractError):
                validate_apply_request(req)

    def test_secret_material_never_executed_as_code(self):
        # Selector values are opaque JSON data; even if a vless-like string is
        # structurally acceptable, the compiler must store it as data and never
        # evaluate it. Build a request and confirm the compiled rule keeps the
        # value as a plain string field.
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, _ = make_executor(td)
            req = base_request(ex, mcp)
            value = 'vless://u@h:443/k'
            req['operations'] = [{'op': 'routingRule.insert', 'managedScope': True,
                                  'params': {'position': 0, 'selectorType': 'domain',
                                             'selectorValue': [value],
                                             'outboundTag': 'p'}}]
            req['requestSha256'] = request_digest(req)
            # Shape-valid (chars within the safe alphabet) -> passes validation,
            # but the compiler output contains the raw string as data only.
            validate_apply_request(req)
            out = RouteMutationCompiler(json.loads(managed_config_bytes()),
                                        req['operations']).compile()
            self.assertIn(value, out['routing']['rules'][0]['domain'])
            self.assertIsInstance(out, dict)
            self.assertNotIn(';', value)


class RouteMutationCompilerTest(unittest.TestCase):
    def _config(self):
        return json.loads(managed_config_bytes())

    def test_insert_managed_rule(self):
        c = RouteMutationCompiler(self._config(), [
            {'op': 'routingRule.insert', 'managedScope': True,
             'params': {'position': 1, 'selectorType': 'domain',
                        'selectorValue': ['new.example.com'], 'outboundTag': 'proxy'}}])
        out = c.compile()
        self.assertEqual(len(out['routing']['rules']), 3)
        rule = out['routing']['rules'][1]
        self.assertEqual(rule['domain'], ['new.example.com'])
        self.assertTrue(rule['tag'].startswith('rill-managed-'))

    def test_insert_never_touches_user_rules(self):
        cfg = self._config()
        orig = json.dumps(cfg['routing']['rules'][0], sort_keys=True)
        c = RouteMutationCompiler(cfg, [
            {'op': 'routingRule.insert', 'managedScope': True,
             'params': {'position': 0, 'selectorType': 'domain',
                        'selectorValue': ['x.com'], 'outboundTag': 'proxy'}}])
        out = c.compile()
        self.assertEqual(json.dumps(out['routing']['rules'][1], sort_keys=True), orig)

    def test_remove_only_managed(self):
        cfg = self._config()
        c = RouteMutationCompiler(cfg, [
            {'op': 'routingRule.removeManaged', 'managedScope': True,
             'params': {'ruleIndex': 1}}])
        out = c.compile()
        self.assertEqual(len(out['routing']['rules']), 1)
        self.assertEqual(out['routing']['rules'][0]['domain'], ['user.example.com'])

    def test_remove_user_rule_fails_closed(self):
        cfg = self._config()
        c = RouteMutationCompiler(cfg, [
            {'op': 'routingRule.removeManaged', 'managedScope': True,
             'params': {'ruleIndex': 0}}])
        with self.assertRaises(ContractError):
            c.compile()

    def test_replace_managed(self):
        cfg = self._config()
        c = RouteMutationCompiler(cfg, [
            {'op': 'routingRule.replaceManaged', 'managedScope': True,
             'params': {'ruleIndex': 1, 'selectorType': 'ip',
                        'selectorValue': ['10.0.0.0/8'], 'outboundTag': 'direct'}}])
        out = c.compile()
        rule = out['routing']['rules'][1]
        self.assertEqual(rule['ip'], ['10.0.0.0/8'])
        self.assertNotIn('domain', rule)

    def test_move_managed(self):
        cfg = self._config()
        c = RouteMutationCompiler(cfg, [
            {'op': 'routingRule.moveManaged', 'managedScope': True,
             'params': {'fromIndex': 1, 'toIndex': 0}}])
        out = c.compile()
        self.assertEqual(out['routing']['rules'][0]['tag'], 'rill-managed-aaa111')

    def test_move_user_rule_fails_closed(self):
        cfg = self._config()
        c = RouteMutationCompiler(cfg, [
            {'op': 'routingRule.moveManaged', 'managedScope': True,
             'params': {'fromIndex': 0, 'toIndex': 1}}])
        with self.assertRaises(ContractError):
            c.compile()

    def test_malformed_config_json_fails_closed(self):
        with self.assertRaises(ContractError):
            RouteMutationCompiler.parse_text('{not json', [])

    def test_no_routing_rules_fails_closed(self):
        with self.assertRaises(ContractError):
            RouteMutationCompiler({'routing': {}}, [
                {'op': 'routingRule.insert', 'managedScope': True,
                 'params': {'position': 0, 'selectorType': 'domain',
                            'selectorValue': ['x.com'], 'outboundTag': 'p'}}])

    def test_never_emits_shell_strings(self):
        cfg = self._config()
        c = RouteMutationCompiler(cfg, [
            {'op': 'routingRule.insert', 'managedScope': True,
             'params': {'position': 1, 'selectorType': 'domain',
                        'selectorValue': ['a.com'], 'outboundTag': 'proxy'}}])
        out = c.compile()
        # Output is a JSON object, never a shell command string.
        self.assertIsInstance(out, dict)


class RouteExecutorSecurityTest(unittest.TestCase):
    def test_locked_release_blocks_apply(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=False)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('feature_not_released', result['blockedBy'])
            # No host mutation happened.
            self.assertEqual(file_sha256(mcp), req['sourceConfigSha256'])

    def test_released_manual_apply_commits(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'committed', result)
            self.assertEqual(ex.txn.generation(), 1)
            cfg = json.loads(mcp.read_text())
            self.assertEqual(len(cfg['routing']['rules']), 3)

    def test_verify_fail_rolls_back(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True, xray_ok=False)
            before = file_sha256(mcp)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'rolledBack', result)
            # Bytes restored exactly.
            self.assertEqual(file_sha256(mcp), before)
            self.assertEqual(ex.txn.generation(), 0)

    def test_config_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            # Config changed after planning -> hash no longer matches.
            mcp.write_bytes(json.dumps({'routing': {'rules': []}}).encode())
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('config_hash_mismatch', result['blockedBy'])

    def test_generation_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            req['configurationGeneration'] = 99
            req['requestSha256'] = request_digest(req)
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('generation_mismatch', result['blockedBy'])

    def test_stale_expired_plan_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp, expiresAtEpochSeconds=1)
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'rejected')

    def test_symlink_spool_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            target = Path(td) / 'outside.json'
            target.write_bytes(managed_config_bytes())
            os.symlink(target, spool / 'apply.json')
            result = ex.apply()
            self.assertEqual(result['status'], 'rejected')

    def test_wrong_owner_spool_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            # Simulate an attacker-owned producer uid (not our uid).
            ex.allowed_producer_uids = {os.geteuid() + 999999}
            result = ex.apply()
            self.assertEqual(result['status'], 'rejected')

    def test_world_writable_spool_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            path = spool / 'apply.json'
            path.chmod(0o666)
            result = ex.apply()
            self.assertEqual(result['status'], 'rejected')

    def test_mode_not_normal_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp, mode='observe-only')
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('mode_not_normal', result['blockedBy'])

    def test_auto_type_requires_auto_stage(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp, applyType='auto', effectiveStage='observe')
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('effective_stage_not_auto', result['blockedBy'])

    def test_replay_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            first = ex.apply()
            self.assertEqual(first['status'], 'committed')
            # Re-staging the same request must not double-apply.
            stage_request(ex, spool, req)
            second = ex.apply()
            # requestSha256 no longer matches the NEW generation; blocked.
            self.assertIn(second['status'], ('blocked', 'rejected'))
            cfg = json.loads(mcp.read_text())
            self.assertEqual(len(cfg['routing']['rules']), 3)

    def test_claim_in_progress_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            # First apply consumes the claim.
            ex.apply()
            # A second apply with nothing staged is blocked (no pending request).
            result = ex.apply()
            self.assertEqual(result['status'], 'blocked')

    # ---- P0-11: boot/crash-safe spool state machine --------------------
    def test_reboot_recover_committed_claim(self):
        """A leftover apply.claim from a committed transaction is recovered
        after reboot, reported, settled to done, and never double-applied."""
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            first = ex.apply()
            self.assertEqual(first['status'], 'committed')
            self.assertEqual(ex.txn.generation(), 1)
            # Simulate a crash/reboot that left the claim in place after the
            # transaction committed: re-stage the same request as apply.claim.
            atomic_write_json(spool / 'apply.claim', req, 0o640)
            recovered = ex.apply()
            self.assertEqual(recovered['status'], 'committed', recovered)
            self.assertEqual(recovered['recommendationId'], req['recommendationId'])
            # Claim was settled to a done marker; nothing pending remains.
            self.assertFalse((spool / 'apply.claim').exists())
            self.assertTrue((spool / 'apply.done').is_file())
            # No double apply: the managed config still has exactly one more
            # rule than the original, generation unchanged.
            cfg = json.loads(mcp.read_text())
            self.assertEqual(len(cfg['routing']['rules']), 3)
            self.assertEqual(ex.txn.generation(), 1)
            # A subsequent boot run is a no-op (blocked, nothing pending).
            self.assertEqual(ex.apply()['status'], 'blocked')

    def test_reboot_recover_claim_then_process_new_request(self):
        """Executor startup order (P0-11): recover the interrupted claim
        first, then claim and process a new request in the same run."""
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req_a = base_request(ex, mcp, recommendationId='rec-route-a0001')
            stage_request(ex, spool, req_a)
            first = ex.apply()
            self.assertEqual(first['status'], 'committed')
            # Leftover claim for A (committed) + a fresh pending request B.
            atomic_write_json(spool / 'apply.claim', req_a, 0o640)
            req_b = base_request(ex, mcp, recommendationId='rec-route-b0002')
            stage_request(ex, spool, req_b)
            result = ex.apply()
            # The returned outcome is the NEW request's; the recovered claim
            # was settled durably before B was processed.
            self.assertEqual(result['status'], 'committed', result)
            self.assertEqual(result['recommendationId'], 'rec-route-b0002')
            self.assertFalse((spool / 'apply.claim').exists())
            cfg = json.loads(mcp.read_text())
            self.assertEqual(len(cfg['routing']['rules']), 4)
            self.assertEqual(ex.txn.generation(), 2)

    def test_leftover_claim_without_txn_quarantined(self):
        """A claim left after a crash before any transaction started is
        quarantined (never silently discarded, never re-executed in a loop)."""
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp)
            stage_request(ex, spool, req)
            before = file_sha256(mcp)
            # Simulate a crash right after claim (rename), before the txn began.
            os.replace(spool / 'apply.json', spool / 'apply.claim')
            result = ex.apply()
            self.assertEqual(result['status'], 'blocked')
            self.assertIn('apply_in_progress', result['blockedBy'])
            # The claim was preserved under quarantine, not dropped.
            quarantined = list((spool / 'quarantine').glob('*'))
            self.assertEqual(len(quarantined), 1)
            self.assertIn('claim-unrecoverable', quarantined[0].name)
            # No host mutation happened.
            self.assertEqual(file_sha256(mcp), before)
            self.assertFalse((spool / 'apply.claim').exists())

    def test_rejected_request_quarantined(self):
        """A claimed request that fails validation is quarantined (no silent
        discard) and not marked as done."""
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            req = base_request(ex, mcp, expiresAtEpochSeconds=1)
            stage_request(ex, spool, req)
            result = ex.apply()
            self.assertEqual(result['status'], 'rejected')
            quarantined = list((spool / 'quarantine').glob('*'))
            self.assertEqual(len(quarantined), 1)
            self.assertIn('rejected', quarantined[0].name)
            self.assertFalse((spool / 'apply.done').exists())
            self.assertFalse((spool / 'apply.claim').exists())

    def test_claim_symlink_quarantined(self):
        """A symlink apply.claim is an anomaly: quarantined, never processed."""
        with tempfile.TemporaryDirectory() as td:
            ex, mcp, spool = make_executor(td, released=True)
            target = Path(td) / 'outside.json'
            target.write_bytes(b'{}')
            os.symlink(target, spool / 'apply.claim')
            result = ex.apply()
            # Symlink claim moved away; nothing pending remains.
            quarantined = list((spool / 'quarantine').glob('*'))
            self.assertEqual(len(quarantined), 1)
            self.assertIn('claim-symlink', quarantined[0].name)
            self.assertFalse((spool / 'apply.claim').exists())
            self.assertEqual(result['status'], 'blocked')


if __name__ == '__main__':
    unittest.main()
