import unittest

from rill_xray_agent.doctor import Doctor


def _obs(**kw):
    base = {
        'capturedAtEpochSeconds': 1000,
        'xrayConfig': {'present': True, 'safe': True, 'sha256': 'a' * 64},
        'nginxConfig': {'present': True, 'safe': True, 'treeSha256': 'b' * 64, 'files': 2},
        'installConfig': {'present': True, 'safe': True, 'sha256': 'c' * 64},
        'xrayValidation': {'ok': True, 'returnCode': 0},
        'nginxValidation': {'ok': True, 'returnCode': 0},
        'services': {'xray': {'ok': True, 'returnCode': 0}, 'nginx': {'ok': True, 'returnCode': 0}},
    }
    base.update(kw)
    return base


# Deterministic clock: the observation is captured at 1000; diagnosing with
# an injected now in the same window keeps evidence fresh and correlation
# windows stable regardless of wall-clock time.
NOW = 1000


def _evt(event_type, component='xray', at=NOW):
    return {'schemaVersion': 1, 'eventType': event_type, 'component': component,
            'facts': {}, 'capturedAtEpochSeconds': at}


def _doctor(**kw):
    kw.setdefault('now', NOW)
    kw.setdefault('health', {'canRecommend': True})
    return Doctor(**kw)


class DoctorTests(unittest.TestCase):
    def test_healthy(self):
        result = _doctor(observation=_obs(), events=[]).diagnose()
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['diagnosisCode'], 'HEALTHY')
        self.assertFalse(result['canApply'])

    def test_config_changed_everything_healthy_is_not_fault(self):
        # The most important false-positive guard: config change + healthy is
        # informational, NOT a fault.
        result = _doctor(observation=_obs(),
                         events=[_evt('xray_config_changed')]).diagnose()
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['diagnosisCode'], 'CONFIG_CHANGED_HEALTHY')
        self.assertEqual(result['severity'], 'info')

    def test_xray_validation_failed_after_change(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        result = _doctor(observation=obs,
                         events=[_evt('xray_config_changed')]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'XRAY_VALIDATION_FAILED_AFTER_CHANGE')
        self.assertEqual(result['confidenceBand'], 'high')
        self.assertEqual(result['recommendations'][0]['code'], 'CHECK_RECENT_XRAY_CHANGE')
        self.assertFalse(result['recommendations'][0]['executionAllowed'])

    def test_xray_service_down_without_change_lower_confidence(self):
        obs = _obs(services={'xray': {'ok': False, 'returnCode': 3}, 'nginx': {'ok': True}})
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'XRAY_SERVICE_DOWN')
        self.assertEqual(result['confidenceBand'], 'low')

    def test_both_services_down_without_change_host_issue(self):
        obs = _obs(services={'xray': {'ok': False, 'returnCode': 3}, 'nginx': {'ok': False, 'returnCode': 3}})
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'BOTH_SERVICES_DOWN')
        self.assertIn('host', result['inferences'][0].lower())

    def test_missing_observation_insufficient_evidence(self):
        result = _doctor(observation=None, events=[]).diagnose()
        self.assertEqual(result['status'], 'insufficient-evidence')
        self.assertEqual(result['confidenceBand'], 'insufficient-evidence')

    def test_unsafe_path_degraded_no_actionable_beyond_inspection(self):
        obs = _obs(xrayConfig={'present': True, 'safe': False})
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'UNSAFE_PATH')
        self.assertEqual(result['recommendations'][0]['code'], 'SAFE_INSPECTION')

    def test_recovery_required_suppresses_normal_recommendation(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        result = _doctor(observation=obs,
                         events=[_evt('xray_config_changed')],
                         health={'canRecommend': False}).diagnose()
        self.assertEqual(result['diagnosisCode'], 'RECOVERY_REQUIRED')
        self.assertEqual(result['recommendations'][0]['code'], 'RUN_RECOVERY')

    def test_deterministic_diagnosis_id(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        events = [_evt('xray_config_changed')]
        a = _doctor(observation=obs, events=events).diagnose()
        b = _doctor(observation=obs, events=events).diagnose()
        self.assertEqual(a['diagnosisId'], b['diagnosisId'])

    def test_changed_evidence_new_diagnosis_id(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        a = _doctor(observation=obs, events=[_evt('xray_config_changed')]).diagnose()
        b = _doctor(observation=obs, events=[]).diagnose()
        self.assertNotEqual(a['diagnosisId'], b['diagnosisId'])

    def test_can_apply_always_false(self):
        for obs, events in [(_obs(), []),
                            (_obs(xrayService={'ok': False} if False else None), [])]:
            result = _doctor(observation=obs, events=events).diagnose()
            self.assertFalse(result['canApply'])

    # -- 15.1 evidence quality boundary matrix ---------------------------

    def test_stale_observation_insufficient_evidence(self):
        # observation captured at NOW-FRESHNESS-1s relative to injected now
        obs = _obs(capturedAtEpochSeconds=NOW - 601)
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'STALE_OBSERVATION')
        self.assertEqual(result['status'], 'insufficient-evidence')

    def test_freshness_exact_boundary(self):
        # at the boundary (age == threshold) it is still fresh
        fresh = _doctor(observation=_obs(capturedAtEpochSeconds=NOW - 600)).diagnose()
        self.assertEqual(fresh['status'], 'healthy')
        # just past the boundary it is stale
        stale = _doctor(observation=_obs(capturedAtEpochSeconds=NOW - 601)).diagnose()
        self.assertEqual(stale['diagnosisCode'], 'STALE_OBSERVATION')

    def test_future_observation_invalid(self):
        obs = _obs(capturedAtEpochSeconds=NOW + 1000)
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'INVALID_OBSERVATION_TIME')
        self.assertEqual(result['status'], 'insufficient-evidence')

    def test_missing_validation_evidence_not_healthy(self):
        obs = _obs(xrayValidation=None, nginxValidation=None)
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['status'], 'insufficient-evidence')
        self.assertEqual(result['diagnosisCode'], 'INSUFFICIENT_EVIDENCE')

    def test_missing_service_evidence_not_healthy(self):
        obs = _obs(services={'xray': None, 'nginx': {'ok': True}})
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['status'], 'insufficient-evidence')

    def test_nginx_validation_failure_without_change(self):
        obs = _obs(nginxValidation={'ok': False, 'returnCode': 1})
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'NGINX_VALIDATION_FAILED')
        self.assertEqual(result['recommendations'][0]['code'], 'CHECK_NGINX_VALIDATION')
        self.assertEqual(result['recommendations'][0]['reasonCode'], 'NGINX_VALIDATION_FAILED')

    def test_xray_validation_failure_without_change(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        result = _doctor(observation=obs, events=[]).diagnose()
        self.assertEqual(result['diagnosisCode'], 'XRAY_VALIDATION_FAILED')
        self.assertEqual(result['recommendations'][0]['code'], 'CHECK_XRAY_VALIDATION')

    def test_correlation_inside_window(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        events = [_evt('xray_config_changed', at=NOW - 1)]
        result = _doctor(observation=obs, events=events).diagnose()
        self.assertEqual(result['diagnosisCode'], 'XRAY_VALIDATION_FAILED_AFTER_CHANGE')
        self.assertEqual(result['confidenceBand'], 'high')

    def test_correlation_outside_window_not_recent(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        events = [_evt('xray_config_changed', at=NOW - 601)]
        result = _doctor(observation=obs, events=events).diagnose()
        # the change is outside the window -> NOT "recent", so the plain
        # validation-failed diagnosis applies.
        self.assertEqual(result['diagnosisCode'], 'XRAY_VALIDATION_FAILED')
        self.assertNotEqual(result['confidenceBand'], 'high')

    def test_intentionally_absent_optional_nginx_not_fault(self):
        # Nginx-free single-binary install: no nginxConfig present -> not required
        obs = _obs(nginxConfig={'present': False},
                   nginxValidation={'ok': False, 'returnCode': 66},
                   services={'xray': {'ok': True, 'returnCode': 0},
                             'nginx': {'ok': False, 'returnCode': 4}})
        result = _doctor(observation=obs, events=[]).diagnose()
        # xray is healthy; intentionally absent nginx is NOT a failure
        self.assertEqual(result['status'], 'healthy')

    def test_timeline_unavailable_validation_failure_no_false_recent(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        result = _doctor(observation=obs, events=[], timeline_status='corrupt').diagnose()
        self.assertEqual(result['diagnosisCode'], 'XRAY_VALIDATION_FAILED')
        # must never claim "no recent change": only that evidence is unavailable
        self.assertIn('unavailable', result['inferences'][0])
        self.assertIn('corrupt', result['limitations'][0])

    def test_timeline_unavailable_healthy_lower_confidence(self):
        result = _doctor(observation=_obs(), events=[],
                         timeline_status='missing').diagnose()
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['confidenceBand'], 'medium')
        self.assertTrue(any('unavailable' in l for l in result['limitations']))


if __name__ == '__main__':
    unittest.main()