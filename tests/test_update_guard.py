import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_manager.sh"
APPLY = ROOT / "integrations/xray_bash_onekey/tools/apply_to_repo.py"


def canonical_block() -> str:
    src = APPLY.read_text()
    m = re.search(r"BLOCK = r'''(.*?)'''", src, re.S)
    if not m:
        raise AssertionError("canonical BLOCK not found in apply_to_repo.py")
    return m.group(1)


def build(custom_block: str | None = None) -> str:
    block = canonical_block() if custom_block is None else custom_block
    return (
        "#!/usr/bin/env bash\n"
        "RILL_XRAY_AGENT_INTEGRATION_SCHEMA=1\n"
        'menu_item() { :; }\n'
        'menu_item 9 "Rill Xray Agent"\n'
        'case "${1:-}" in\n'
        "    9) rxa_menu ;;\n"
        "    --rill-agent-status) rxa_dispatch status ;;\n"
        "esac\n"
        + block
        + "\n"
    )


GOOD = build()


def run_guard(candidate: Path) -> int:
    proc = subprocess.run(
        ["bash", "-c", f'source "{MANAGER}"; rxa_candidate_guard "$1"', "guard", str(candidate)],
        capture_output=True,
        text=True,
    )
    return proc.returncode


class Tests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="rxa-guard-")
        self.tmp = Path(self._tmp.name)
        self.candidate = self.tmp / "install.sh"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def write(self, body: str) -> Path:
        self.candidate.write_text(body)
        return self.candidate

    def test_good_candidate_passes(self):
        self.assertEqual(run_guard(self.write(GOOD)), 0)

    def test_missing_schema_marker_rejected(self):
        body = GOOD.replace("RILL_XRAY_AGENT_INTEGRATION_SCHEMA=1\n", "")
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_menu_entry_rejected(self):
        # Remove the exact wrapper line the guard anchors on (case 9 dispatch).
        body = GOOD.replace("    9) rxa_menu ;;\n", "")
        self.assertNotEqual(run_guard(self.write(body)), 0)

    def test_missing_cli_anchor_rejected(self):
        body = GOOD.replace("    --rill-agent-status) rxa_dispatch status ;;\n", "")
        self.assertNotEqual(run_guard(self.write(body)), 0)

    def test_comment_only_functions_rejected(self):
        # Strings in comments are not acceptable; the runtime probe requires
        # real function definitions (declare -F), not grep matches.
        block = canonical_block()
        stripped = "\n".join(
            "# " + line if re.match(r'^\s*rxa_\w+\(\)', line) else line
            for line in block.splitlines()
        )
        body = build(stripped)
        self.assertNotEqual(run_guard(self.write(body)), 0)

    def test_missing_uninstall_hook_rejected(self):
        block = canonical_block()
        body = build(re.sub(r"rxa_uninstall_finish\(\) \{.*?\n\}", "", block, count=1, flags=re.S))
        # keep the END marker (produced by the sub) intact
        self.assertNotEqual(run_guard(self.write(body)), 0)

    def test_missing_verify_hook_rejected(self):
        block = canonical_block()
        body = build(re.sub(r"rxa_host_healthy\(\) \{.*?\n\}", "", block, count=1, flags=re.S))
        self.assertNotEqual(run_guard(self.write(body)), 0)

    def test_missing_reconfigure_hook_rejected(self):
        block = canonical_block()
        body = build(re.sub(r"rxa_reconfigure_enter\(\) \{.*?\n\}", "", block, count=1, flags=re.S))
        self.assertNotEqual(run_guard(self.write(body)), 0)

    def test_broken_shell_syntax_rejected(self):
        body = GOOD + "\nif [[ -n\n"
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_block_markers_rejected(self):
        block = canonical_block().replace("# BEGIN RILL XRAY AGENT INTEGRATION\n", "")
        body = build(block)
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_file_rejected(self):
        self.assertEqual(run_guard(self.tmp / "nope.sh"), 1)

    def test_apply_tool_keeps_candidate_guard(self):
        tool = APPLY.read_text()
        for marker in (
            "install.sh.rxa-candidate.$$",
            "rxa_candidate_guard",
            'mv -f "${_candidate}" "${' + "i" + "d" + "l" + "e" + "l" + "e" + "o" + '}"',
            "rxa_postreplace_selfcheck",
        ):
            self.assertIn(marker, tool)
        self.assertIn("rxa_candidate_guard()", tool)


if __name__ == "__main__":
    unittest.main()