import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Tests(unittest.TestCase):
    def test_identity(self):
        self.assertEqual((ROOT / "VERSION").read_text().strip(), "0.1.0-rc.1")
        self.assertTrue((ROOT / "bin/rill-xray-agent").is_file())
        self.assertTrue((ROOT / "python/rill_xray_agent/runtime_service.py").is_file())

    def test_default_is_fail_closed(self):
        data = json.loads((ROOT / "config/default.json").read_text())
        self.assertEqual(data["mode"], "observe-only")
        self.assertFalse(data["routeAssistEnabled"])
        self.assertFalse(data["boundedAutoAllowed"])

    def test_forbidden_identity_is_absent(self):
        token = "i" + "d" + "l" + "e" + "l" + "e" + "o"
        for path in ROOT.rglob("*"):
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            self.assertNotIn(token, path.as_posix().lower())
            if path.is_file() and path.name != "PACKAGE_SHA256SUMS":
                self.assertNotIn(token, path.read_text(errors="ignore").lower(), str(path))


if __name__ == "__main__":
    unittest.main()
