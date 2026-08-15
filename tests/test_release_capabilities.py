"""Release capability manifest: supported vs released separation.

The production manifest is root-owned and runtime read-only. Effective
enablement requires BOTH supported and released. Missing/corrupt manifests
fail closed to the locked default (SUPPORTED_LOCKED), never to open.
"""
import json
import tempfile
import unittest
from pathlib import Path

from rill_xray_agent.release_capabilities import ReleaseCapabilities, ReleaseCapabilityStatus


def write_manifest(td, features):
    path = Path(td) / 'release-capabilities.json'
    path.write_text(json.dumps({'schemaVersion': 1, 'features': features}, sort_keys=True))
    return path


class ReleaseCapabilitiesTest(unittest.TestCase):
    def test_default_is_locked(self):
        with tempfile.TemporaryDirectory() as td:
            caps = ReleaseCapabilities(Path(td) / 'missing.json')
            self.assertTrue(caps.is_supported('routeAssist'))
            self.assertFalse(caps.is_released('routeAssist'))
            self.assertTrue(caps.is_supported('boundedAuto'))
            self.assertFalse(caps.is_released('boundedAuto'))

    def test_corrupt_manifest_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'release-capabilities.json'
            p.write_text('{not json')
            caps = ReleaseCapabilities(p)
            self.assertFalse(caps.is_released('routeAssist'))
            self.assertFalse(caps.is_released('boundedAuto'))

    def test_released_opens_evaluation(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(td, {'routeAssist': {'supported': True, 'released': True},
                                    'boundedAuto': {'supported': True, 'released': False}})
            caps = ReleaseCapabilities(p)
            self.assertTrue(caps.is_released('routeAssist'))
            self.assertFalse(caps.is_released('boundedAuto'))
            self.assertEqual(caps.evaluate('routeAssist', 'assist'),
                             ReleaseCapabilityStatus.AVAILABLE_ENABLED)
            self.assertEqual(caps.evaluate('boundedAuto', 'auto'),
                             ReleaseCapabilityStatus.SUPPORTED_LOCKED)

    def test_unsupported_feature(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(td, {'routeAssist': {'supported': False, 'released': False},
                                    'boundedAuto': {'supported': True, 'released': False}})
            caps = ReleaseCapabilities(p)
            self.assertEqual(caps.evaluate('routeAssist', 'assist'),
                             ReleaseCapabilityStatus.UNSUPPORTED)

    def test_with_released_injection(self):
        with tempfile.TemporaryDirectory() as td:
            caps = ReleaseCapabilities(Path(td) / 'missing.json')
            open_caps = caps.with_released('routeAssist', True)
            self.assertTrue(open_caps.is_released('routeAssist'))
            self.assertFalse(caps.is_released('routeAssist'))  # original unchanged
            with self.assertRaises(Exception):
                caps.with_released('nope', True)

    def test_evaluate_stage_semantics(self):
        with tempfile.TemporaryDirectory() as td:
            p = write_manifest(td, {'routeAssist': {'supported': True, 'released': True},
                                    'boundedAuto': {'supported': True, 'released': True}})
            caps = ReleaseCapabilities(p)
            # routeAssist: assist/auto configured -> enabled; observe -> disabled
            self.assertEqual(caps.evaluate('routeAssist', 'assist'),
                             ReleaseCapabilityStatus.AVAILABLE_ENABLED)
            self.assertEqual(caps.evaluate('routeAssist', 'auto'),
                             ReleaseCapabilityStatus.AVAILABLE_ENABLED)
            self.assertEqual(caps.evaluate('routeAssist', 'observe'),
                             ReleaseCapabilityStatus.AVAILABLE_DISABLED)
            # boundedAuto: only auto configured -> enabled
            self.assertEqual(caps.evaluate('boundedAuto', 'auto'),
                             ReleaseCapabilityStatus.AVAILABLE_ENABLED)
            self.assertEqual(caps.evaluate('boundedAuto', 'assist'),
                             ReleaseCapabilityStatus.AVAILABLE_DISABLED)
            self.assertEqual(caps.evaluate('boundedAuto', 'observe'),
                             ReleaseCapabilityStatus.AVAILABLE_DISABLED)

    def test_releaseCapabilities_projection(self):
        with tempfile.TemporaryDirectory() as td:
            caps = ReleaseCapabilities(Path(td) / 'missing.json')
            proj = caps.releaseCapabilities('assist')
            self.assertEqual(proj['schemaVersion'], 1)
            self.assertEqual(proj['features']['routeAssist']['released'], False)
            self.assertEqual(proj['features']['routeAssist']['status'], 'supported_locked')
            self.assertEqual(proj['features']['boundedAuto']['status'], 'supported_locked')


if __name__ == '__main__':
    unittest.main()
