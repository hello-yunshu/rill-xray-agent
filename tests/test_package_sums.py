import unittest

from scripts.verify_package_sums import content_digest


class PackageSumLineEndingTests(unittest.TestCase):
    def test_text_digest_is_stable_across_lf_and_crlf(self):
        self.assertEqual(content_digest(b"first\nsecond\n"), content_digest(b"first\r\nsecond\r\n"))

    def test_binary_digest_preserves_crlf_bytes(self):
        self.assertNotEqual(content_digest(b"\x00first\nsecond\n"), content_digest(b"\x00first\r\nsecond\r\n"))


if __name__ == "__main__":
    unittest.main()
