import unittest

from rill_xray_agent.payload_policy import sanitize_doctor_feedback, sanitize_payload


class DoctorFeedbackPolicyTests(unittest.TestCase):
    def test_valid_feedback_accepted(self):
        out = sanitize_doctor_feedback({
            'decisionId': 'd1', 'capability': 'doctor', 'modelGeneration': 1,
            'createdAtEpochSeconds': 1, 'outcome': 'resolved',
            'helpful': True, 'diagnosisCorrect': True,
        })
        self.assertEqual(out['outcome'], 'resolved')
        self.assertIs(out['helpful'], True)

    def test_invalid_outcome_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_doctor_feedback({'decisionId': 'd1', 'capability': 'doctor',
                                      'modelGeneration': 1, 'createdAtEpochSeconds': 1,
                                      'outcome': 'maybe'})

    def test_non_boolean_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_doctor_feedback({'decisionId': 'd1', 'capability': 'doctor',
                                      'modelGeneration': 1, 'createdAtEpochSeconds': 1,
                                      'outcome': 'resolved', 'helpful': 'yes'})

    def test_free_text_comment_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_doctor_feedback({'decisionId': 'd1', 'capability': 'doctor',
                                      'modelGeneration': 1, 'createdAtEpochSeconds': 1,
                                      'outcome': 'resolved', 'comment': 'my private key is...'})

    def test_config_body_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_doctor_feedback({'decisionId': 'd1', 'capability': 'doctor',
                                      'modelGeneration': 1, 'createdAtEpochSeconds': 1,
                                      'outcome': 'resolved', 'inbounds': []})

    def test_nested_payload_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_doctor_feedback({'decisionId': 'd1', 'capability': 'doctor',
                                      'modelGeneration': 1, 'createdAtEpochSeconds': 1,
                                      'outcome': 'resolved', 'nested': {'a': 1}})

    def test_secret_material_rejected(self):
        with self.assertRaises(ValueError):
            sanitize_doctor_feedback({'decisionId': 'd1', 'capability': 'doctor',
                                      'modelGeneration': 1, 'createdAtEpochSeconds': 1,
                                      'outcome': 'resolved', 'helpful': True,
                                      'diagnosisCorrect': 'vless://secret'})

    def test_sanitize_payload_redacts_free_text(self):
        # sanitize_payload (the generic allowlist) must not leak doctor free text
        out = sanitize_payload({'decisionId': 'd1', 'capability': 'doctor',
                                'modelGeneration': 1, 'createdAtEpochSeconds': 1,
                                'outcome': 'resolved', 'helpful': True})
        self.assertNotIn('outcome', out)
        self.assertNotIn('helpful', out)


if __name__ == '__main__':
    unittest.main()