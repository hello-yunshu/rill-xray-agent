import unittest
import importlib.util
import tempfile
from pathlib import Path

from scripts.build_canonical_manifest import ROOT, canonical_content, sha_bytes

SPEC = importlib.util.spec_from_file_location(
    "verify_xray_payload", ROOT / "integrations/xray_bash_onekey/tools/verify_xray_payload.py"
)
VERIFY_XRAY_PAYLOAD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY_XRAY_PAYLOAD)


class CanonicalLineEndingTests(unittest.TestCase):
    def test_text_hash_is_stable_across_lf_and_crlf(self):
        lf = b"first\nsecond\n"
        crlf = b"first\r\nsecond\r\n"
        self.assertEqual(canonical_content(lf), canonical_content(crlf))
        self.assertEqual(sha_bytes(lf), sha_bytes(crlf))

    def test_binary_hash_keeps_raw_bytes(self):
        lf = b"\0first\nsecond\n"
        crlf = b"\0first\r\nsecond\r\n"
        self.assertNotEqual(canonical_content(lf), canonical_content(crlf))
        self.assertNotEqual(sha_bytes(lf), sha_bytes(crlf))

    def test_xray_verifier_accepts_text_checkouts_with_different_endings(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "payload.txt"
            path.write_bytes(b"first\nsecond\n")
            lf_sha = VERIFY_XRAY_PAYLOAD.sha(path)
            path.write_bytes(b"first\r\nsecond\r\n")
            self.assertEqual(VERIFY_XRAY_PAYLOAD.sha(path), lf_sha)


if __name__ == "__main__":
    unittest.main()
