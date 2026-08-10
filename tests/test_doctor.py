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


def _evt(event_type, component='xray'):
    return {'schemaVersion': 1, 'eventType': event_type, 'component': component, 'facts': {}}


class DoctorTests(unittest.TestCase):
    def test_healthy(self):
        result = Doctor(observation=_obs(), events=[], health={'canRecommend': True}).diagnose()
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['diagnosisCode'], 'HEALTHY')
        self.assertFalse(result['canApply'])

    def test_config_changed_everything_healthy_is_not_fault(self):
        # The most important false-positive guard: config change + healthy is
        # informational, NOT a fault.
        result = Doctor(observation=_obs(),
                        events=[_evt('xray_config_changed')],
                        health={'canRecommend': True}).diagnose()
        self.assertEqual(result['status'], 'healthy')
        self.assertEqual(result['diagnosisCode'], 'CONFIG_CHANGED_HEALTHY')
        self.assertEqual(result['severity'], 'info')

    def test_xray_validation_failed_after_change(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        result = Doctor(observation=obs,
                        events=[_evt('xray_config_changed')],
                        health={'canRecommend': True}).diagnose()
        self.assertEqual(result['diagnosisCode'], 'XRAY_VALIDATION_FAILED_AFTER_CHANGE')
        self.assertEqual(result['confidenceBand'], 'high')
        self.assertEqual(result['recommendations'][0]['code'], 'CHECK_RECENT_XRAY_CHANGE')
        self.assertFalse(result['recommendations'][0]['executionAllowed'])

    def test_xray_service_down_without_change_lower_confidence(self):
        obs = _obs(services={'xray': {'ok': False, 'returnCode': 3}, 'nginx': {'ok': True}})
        result = Doctor(observation=obs, events=[], health={'canRecommend': True}).diagnose()
        self.assertEqual(result['diagnosisCode'], 'XRAY_SERVICE_DOWN')
        self.assertEqual(result['confidenceBand'], 'low')

    def test_both_services_down_without_change_host_issue(self):
        obs = _obs(services={'xray': {'ok': False, 'returnCode': 3}, 'nginx': {'ok': False, 'returnCode': 3}})
        result = Doctor(observation=obs, events=[], health={'canRecommend': True}).diagnose()
        self.assertEqual(result['diagnosisCode'], 'BOTH_SERVICES_DOWN')
        self.assertIn('host', result['inferences'][0].lower())

    def test_missing_observation_insufficient_evidence(self):
        result = Doctor(observation=None, events=[], health={'canRecommend': True}).diagnose()
        self.assertEqual(result['status'], 'insufficient-evidence')
        self.assertEqual(result['confidenceBand'], 'insufficient-evidence')

    def test_unsafe_path_degraded_no_actionable_beyond_inspection(self):
        obs = _obs(xrayConfig={'present': True, 'safe': False})
        result = Doctor(observation=obs, events=[], health={'canRecommend': True}).diagnose()
        self.assertEqual(result['diagnosisCode'], 'UNSAFE_PATH')
        self.assertEqual(result['recommendations'][0]['code'], 'SAFE_INSPECTION')

    def test_recovery_required_suppresses_normal_recommendation(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        result = Doctor(observation=obs,
                        events=[_evt('xray_config_changed')],
                        health={'canRecommend': False}).diagnose()
        self.assertEqual(result['diagnosisCode'], 'RECOVERY_REQUIRED')
        self.assertEqual(result['recommendations'][0]['code'], 'RUN_RECOVERY')

    def test_deterministic_diagnosis_id(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        events = [_evt('xray_config_changed')]
        a = Doctor(observation=obs, events=events, health={'canRecommend': True}).diagnose()
        b = Doctor(observation=obs, events=events, health={'canRecommend': True}).diagnose()
        self.assertEqual(a['diagnosisId'], b['diagnosisId'])

    def test_changed_evidence_new_diagnosis_id(self):
        obs = _obs(xrayValidation={'ok': False, 'returnCode': 1})
        a = Doctor(observation=obs, events=[_evt('xray_config_changed')], health={'canRecommend': True}).diagnose()
        b = Doctor(observation=obs, events=[], health={'canRecommend': True}).diagnose()
        self.assertNotEqual(a['diagnosisId'], b['diagnosisId'])

    def test_can_apply_always_false(self):
        for obs, events in [(_obs(), []),
                            (_obs(xrayService={'ok': False} if False else None), [])]:
            result = Doctor(observation=obs, events=events, health={'canRecommend': True}).diagnose()
            self.assertFalse(result['canApply'])


if __name__ == '__main__':
    unittest.main()