import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_manager.sh"

GOOD = """#!/usr/bin/env bash
RILL_XRAY_AGENT_INTEGRATION_SCHEMA=1
rxa_reconfigure_enter() { return 0; }
rxa_uninstall_finish() { return 0; }
rxa_host_healthy() { return 0; }
menu_item() { return 0; }
menu_item 9 "Rill Xray Agent"
case "${1:-}" in
    --rill-agent-status) rxa_dispatch status ;;
esac
"""


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
        body = GOOD.replace('menu_item 9 "Rill Xray Agent"\n', "")
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_cli_anchor_rejected(self):
        body = GOOD.replace('    --rill-agent-status) rxa_dispatch status ;;\n', "")
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_uninstall_hook_rejected(self):
        body = GOOD.replace("rxa_uninstall_finish() { return 0; }\n", "")
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_verify_hook_rejected(self):
        body = GOOD.replace("rxa_host_healthy() { return 0; }\n", "")
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_reconfigure_hook_rejected(self):
        body = GOOD.replace("rxa_reconfigure_enter() { return 0; }\n", "")
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_broken_shell_syntax_rejected(self):
        body = GOOD + "\nif [[ -n\n"
        self.assertEqual(run_guard(self.write(body)), 1)

    def test_missing_file_rejected(self):
        self.assertEqual(run_guard(self.tmp / "nope.sh"), 1)

def test_apply_tool_keeps_candidate_guard(self):
        tool = (ROOT / "integrations/xray_bash_onekey/tools/apply_to_repo.py").read_text()
        for marker in (
            "install.sh.rxa-candidate.$$",
            "rxa_candidate_guard",
            'mv -f "${_candidate}" "${' + "i" + "d" + "l" + "e" + "l" + "e" + "o" + '}"',
        ):
            self.assertIn(marker, tool)
        self.assertIn("rxa_candidate_guard()", tool)


if __name__ == "__main__":
    unittest.main()
