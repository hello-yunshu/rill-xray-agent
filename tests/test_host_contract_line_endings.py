import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.sync_xray_host_contract import host_surface


class HostContractLineEndingTests(unittest.TestCase):
    def test_lf_and_crlf_checkouts_have_the_same_surface(self):
        lf = (
            b"before\n# BEGIN RILL XRAY AGENT INTEGRATION\n"
            b"function body\n# END RILL XRAY AGENT INTEGRATION\nafter\n"
        )
        self.assertEqual(host_surface(lf.replace(b"\n", b"\r\n")), host_surface(lf))


if __name__ == "__main__":
    unittest.main()
