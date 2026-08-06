import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_manager.sh"

CLI_STUB = """#!/usr/bin/env bash
# mimic: rill-xray-agent --json <command> ...
shift
cmd="$1"; shift
case "$cmd" in
    mode)
        : > "${RXA_MODE_STATE}" && printf '%s' "$1" > "${RXA_MODE_STATE}" || true
        if [[ "${RXA_CLI_FAIL_MODE:-0}" == 1 ]]; then
            printf '%s\\n' '{"ok":false,"error":{"code":"modeRejected"}}'
            exit 1
        fi
        if [[ "${RXA_FORCE_RUNTIME_MODE:-}" != "" ]]; then
            printf '%s' "${RXA_FORCE_RUNTIME_MODE}" > "${RXA_RUNTIME_STATE}"
        else
            printf '%s' "$1" > "${RXA_RUNTIME_STATE}"
        fi
        printf '%s\\n' "{\\"ok\\":true,\\"result\\":{\\"mode\\":\\"$1\\"}}"
        ;;
    config)
        mode=$(cat "${RXA_RUNTIME_STATE}" 2>/dev/null || printf 'observe-only')
        printf '%s\\n' "{\\"ok\\":true,\\"result\\":{\\"mode\\":\\"${mode}\\"}}"
        ;;
    *) exit 66 ;;
esac
"""

OBSERVE_STUB = """#!/usr/bin/env python3
import json, os, sys, time
if os.environ.get('RXA_OBSERVE_FAIL') == '1':
    sys.exit(7)
out = os.environ['RXA_STATUS']
data = {
    "schemaVersion": 1,
    "capturedAtEpochSeconds": int(time.time()),
    "xrayConfig": {"present": False},
    "services": {"xray": {"ok": False}},
}
with open(out, "w") as stream:
    json.dump(data, stream, sort_keys=True)
print("ok")
"""


class ModeTransaction(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="rxa-mode-")
        self.tmp = Path(self._tmp.name)
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.config = self.home / "config.json"
        self.status = self.tmp / "status.json"
        self.mode_state = self.tmp / "mode.cli"
        self.runtime_state = self.tmp / "runtime.state"
        self.runtime_state.write_text("observe-only")
        self.cli = self.tmp / "rill-xray-agent"
        self.observe = self.tmp / "observe.py"
        self.cli.write_text(CLI_STUB)
        self.observe.write_text(OBSERVE_STUB)
        self.cli.chmod(0o755)
        self._env = dict(os.environ)
        self._env.update(
            {
                "RILL_XRAY_AGENT_HOME": str(self.home),
                "RILL_XRAY_AGENT_CONFIG": str(self.config),
                "RILL_XRAY_AGENT_STATUS": str(self.status),
                "RILL_XRAY_AGENT_CLI": str(self.cli),
                "RILL_XRAY_AGENT_OBSERVER": str(self.observe),
                "RILL_XRAY_AGENT_NO_SYSTEMD": "1",
                "RXA_MODE_STATE": str(self.mode_state),
                "RXA_RUNTIME_STATE": str(self.runtime_state),
                "RXA_STATUS": str(self.status),
            }
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def mode(self) -> str:
        return json.loads(self.config.read_text())["mode"]

    def runtime(self) -> str:
        return self.runtime_state.read_text()

    def apply(self, *args: str) -> int:
        proc = subprocess.run(
            ["bash", "-c", f'source "{MANAGER}"; rxa_apply_mode "$@"', "x", *args],
            env=self._env,
            capture_output=True,
            text=True,
        )
        return proc.returncode

    def test_switch_to_normal_commits_all_parties(self):
        self.assertEqual(self.apply("normal"), 0)
        self.assertEqual(self.mode(), "normal")
        self.assertEqual(self.runtime(), "normal")
        self.assertEqual(self.mode_state.read_text(), "normal")

    def test_switch_to_safe_disabled_commits(self):
        self.assertEqual(self.apply("safe-disabled"), 0)
        self.assertEqual(self.mode(), "safe-disabled")
        self.assertEqual(self.runtime(), "safe-disabled")

    def test_already_in_mode_is_noop(self):
        self.assertEqual(self.apply("observe-only"), 0)
        self.assertEqual(self.runtime(), "observe-only")

    def test_runtime_rejection_rolls_back(self):
        self._env["RXA_FORCE_RUNTIME_MODE"] = "1"
        self.assertEqual(self.apply("normal"), 1)
        self.assertEqual(self.mode(), "observe-only")
        self.assertEqual(self.mode_state.read_text(), "observe-only")

    def test_observe_failure_rolls_back(self):
        self._env["RXA_OBSERVE_FAIL"] = "1"
        self.assertEqual(self.apply("normal"), 1)
        self.assertEqual(self.mode(), "observe-only")
        self.assertEqual(self.runtime(), "observe-only")
        self.assertEqual(self.mode_state.read_text(), "observe-only")

    def test_invalid_mode_rejected(self):
        self.assertEqual(self.apply("bogus"), 64)
        self.assertFalse(self.config.exists())


if __name__ == "__main__":
    unittest.main()