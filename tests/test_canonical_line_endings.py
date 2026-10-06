import unittest

from scripts.build_canonical_manifest import canonical_content, sha_bytes


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


if __name__ == "__main__":
    unittest.main()
