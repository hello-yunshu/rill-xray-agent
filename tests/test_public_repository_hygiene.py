import hashlib
import subprocess
import sys
import tarfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scripts/verify_public_history_hygiene.py"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGE_ARCHIVES = (
    ROOT / "integrations/xray_bash_onekey/assets/rill-xray-agent-xray-bundle.tar.gz",
)

GOVERNANCE_SNIPPETS = (
    "禁止提交内部提示词",
    "public prompt hygiene",
    "prompt artifact must not be committed",
    "execution prompt material is permanently forbidden",
)


class Tests(unittest.TestCase):
    def test_no_prompt_files_anywhere(self):
        out = subprocess.run(
            [sys.executable, str(SCANNER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_worktree_no_prompt_paths(self):
        # Path-based forbiddance must hold even if the shared scanner changes.
        from scripts.verify_public_history_hygiene import forbidden_path
        for path in ROOT.rglob("*"):
            rel = path.relative_to(ROOT).as_posix()
            if any(p in {".git", "__pycache__", ".pytest_cache", "target"} for p in rel.split("/")):
                continue
            self.assertFalse(forbidden_path(rel), rel)

    def test_governance_text_is_allowed(self):
        # Governance statements are policy, not prompt artifacts. The gate
        # must never flag them: audit history that references the hygiene
        # rule is real audit fact and is preserved verbatim.
        from scripts.verify_public_history_hygiene import forbidden_content
        from pathlib import Path as _P
        for i, snippet in enumerate(GOVERNANCE_SNIPPETS):
            tmp = _P(__file__).parent / f".governance-tmp-{i}.txt"
            tmp.write_text(snippet + "\n")
            try:
                self.assertIsNone(forbidden_content(tmp), snippet)
            finally:
                tmp.unlink(missing_ok=True)

    def test_required_delivery_paths_still_present(self):
        for rel in (
            "README.md",
            "README_EN.md",
            "VERSION",
            "PACKAGE_SHA256SUMS",
            "scripts/verify_package_tree.py",
            "scripts/verify_package_sums.py",
            "scripts/verify_project_memory.py",
            "scripts/verify_public_history_hygiene.py",
            "PROJECT_MEMORY/project_state.json",
            "PROJECT_MEMORY/history_chain.json",
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_archive_members_have_no_prompt_material(self):
        from scripts.verify_public_history_hygiene import forbidden_path
        for archive in PACKAGE_ARCHIVES:
            if not archive.exists():
                continue
            with tarfile.open(archive, "r:gz") as handle:
                for member in handle.getmembers():
                    if not member.isfile():
                        continue
                    self.assertFalse(forbidden_path(member.name), member.name)

    def test_project_memory_has_no_prompt_body(self):
        # Memory must not embed prompt bodies, but audit facts that name the
        # policy are allowed. The shared scanner enforces the signature-based
        # rule; this test re-checks memory specifically.
        from scripts.verify_public_history_hygiene import forbidden_content
        for path in (ROOT / "PROJECT_MEMORY").rglob("*"):
            if path.is_file() and not path.name.endswith(".pyc"):
                self.assertIsNone(forbidden_content(path), str(path))


if __name__ == "__main__":
    unittest.main()
