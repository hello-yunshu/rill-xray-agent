import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.sync_xray_host_contract import reviewed_install_blob


class ReviewedInstallBlobTests(unittest.TestCase):
    def test_requires_full_commit_sha(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(SystemExit, "full 40-character SHA"):
                reviewed_install_blob(Path(td), "1234abc")

    def test_records_blob_from_exact_commit(self):
        with tempfile.TemporaryDirectory() as td:
            repo = Path(td)
            subprocess.run(["git", "init", "--quiet", str(repo)], check=True)
            (repo / "install.sh").write_text("#!/bin/sh\n")
            subprocess.run(["git", "-C", str(repo), "add", "install.sh"], check=True)
            subprocess.run([
                "git", "-C", str(repo), "-c", "user.name=Test",
                "-c", "user.email=test@example.invalid", "commit", "--quiet", "-m", "fixture",
            ], check=True)
            commit = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
            resolved, blob = reviewed_install_blob(repo, commit)
            self.assertEqual(resolved, commit)
            self.assertEqual(blob, subprocess.check_output(
                ["git", "-C", str(repo), "rev-parse", f"{commit}:install.sh"], text=True
            ).strip())


if __name__ == "__main__":
    unittest.main()
