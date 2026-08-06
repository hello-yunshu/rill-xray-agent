import json
import tarfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_NAMES = (
    "master execution instruction",
    "execution instruction",
    "SCANNER_TOKEN",
    "SCANNER_TOKEN",
    "INSTRUCTION.md",
    "INSTRUCTION_",
    "instruction.md",
)

FORBIDDEN_CONTENT = (
    "master execution instruction",
    "execution instruction",
    "AI execution instructions",
    "AI execution prompt",
    "you are an ai",
    "system prompt",
)

PACKAGE_ARCHIVES = (
    ROOT / "integrations/xray_bash_onekey/assets/rill-xray-agent-xray-bundle.tar.gz",
)


class Tests(unittest.TestCase):
    def scan_tree(self, root: Path):
        problems = []
        for path in sorted(root.rglob("*")):
            if any(part in {".git", "__pycache__", ".pytest_cache", "target"} for part in path.relative_to(root).parts):
                continue
            rel = path.relative_to(root).as_posix()
            low = rel.lower()
            for name in FORBIDDEN_NAMES:
                if name.lower() in low:
                    problems.append(f"forbidden prompt file name: {rel}")
            if path.is_file() and path.name != "PACKAGE_SHA256SUMS":
                text = path.read_bytes().decode("utf-8", "ignore")
                low_text = text.lower()
                for marker in FORBIDDEN_CONTENT:
                    if marker.lower() in low_text:
                        problems.append(f"forbidden prompt content in {rel}: {marker}")
        return problems

    def test_no_prompt_files_anywhere(self):
        problems = self.scan_tree(ROOT)
        self.assertEqual(problems, [])

    def test_worktree_no_prompt_paths(self):
            self.assertEqual(list(ROOT.glob(pattern)), [])

    def test_required_delivery_paths_still_present(self):
        for rel in (
            "README.md",
            "README_EN.md",
            "VERSION",
            "PACKAGE_SHA256SUMS",
            "scripts/verify_package_tree.py",
            "scripts/verify_package_sums.py",
            "scripts/verify_project_memory.py",
            "PROJECT_MEMORY/project_state.json",
            "PROJECT_MEMORY/history_chain.json",
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_archive_members_have_no_prompt_material(self):
        for archive in PACKAGE_ARCHIVES:
            if not archive.exists():
                continue
            with tarfile.open(archive, "r:gz") as handle:
                for member in handle.getmembers():
                    if not member.isfile():
                        continue
                    low = member.name.lower()
                    for name in FORBIDDEN_NAMES:
                        if name.lower() in low:
                            self.fail(f"forbidden member name in {archive.name}: {member.name}")
                    content = handle.extractfile(member).read().decode("utf-8", "ignore")
                    for marker in FORBIDDEN_CONTENT:
                        if marker.lower() in content.lower():
                            self.fail(f"forbidden content in {archive.name}:{member.name} -> {marker}")

    def test_project_memory_has_no_prompt_body(self):
        memory = ROOT / "PROJECT_MEMORY"
        problems = self.scan_tree(memory)
        self.assertEqual(problems, [])


if __name__ == "__main__":
    unittest.main()