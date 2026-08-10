import json
import os
import subprocess
import tempfile
import time
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
        printf '%s\n' "{\\"ok\\":true,\\"result\\":{\\"mode\\":\\"${mode}\\",\\"routeAssistEnabled\\":false,\\"boundedAutoAllowed\\":false}}"
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

SYSCTL_STUB = """#!/usr/bin/env bash
# Fake systemctl used by same-mode repair tests. Unit state is tracked by
# files under RXA_SYS_STATE: active/<unit> and enabled/<unit>.
STATE="${RXA_SYS_STATE}"
cmd="$1"; shift
fail() {
    local u
    for u in $RXA_SYSCTL_FAIL_UNITS; do
        [[ "$1" == "$u" ]] && return 0
    done
    return 1
}
case "$cmd" in
    enable)
        now=0
        [[ "$1" == "--now" ]] && { now=1; shift; }
        for u in "$@"; do
            if fail "$u"; then
                echo "enable $u failed" >&2
                exit 1
            fi
            mkdir -p "$STATE/enabled"
            touch "$STATE/enabled/$u"
            (( now )) && { mkdir -p "$STATE/active"; touch "$STATE/active/$u"; }
        done
        exit 0
        ;;
    disable)
        now=0
        [[ "$1" == "--now" ]] && { now=1; shift; }
        for u in "$@"; do
            if fail "$u"; then
                echo "disable $u failed" >&2
                exit 1
            fi
            rm -f "$STATE/enabled/$u"
            (( now )) && rm -f "$STATE/active/$u"
        done
        exit 0
        ;;
    is-active)
        quiet=0
        [[ "$1" == "--quiet" ]] && { quiet=1; shift; }
        if [[ -e "$STATE/active/$1" ]]; then
            [[ $quiet -eq 0 ]] && echo active
            exit 0
        fi
        [[ $quiet -eq 0 ]] && echo inactive
        exit 3
        ;;
    is-enabled)
        quiet=0
        [[ "$1" == "--quiet" ]] && { quiet=1; shift; }
        if [[ -e "$STATE/enabled/$1" ]]; then
            [[ $quiet -eq 0 ]] && echo enabled
            exit 0
        fi
        [[ $quiet -eq 0 ]] && echo disabled
        exit 1
        ;;
    daemon-reload) exit 0 ;;
    *) exit 0 ;;
esac
"""

UNITS = (
    "rill-xray-agent-runtime.service",
    "rill-xray-agent-agent.service",
    "rill-xray-agent-xray-observe.path",
    "rill-xray-agent-xray-observe.timer",
)


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
        self.sys_state = self.tmp / "sys"
        (self.sys_state / "active").mkdir(parents=True)
        (self.sys_state / "enabled").mkdir(parents=True)
        self.cli = self.tmp / "rill-xray-agent"
        self.observe = self.tmp / "observe.py"
        self.sysctl = self.tmp / "systemctl"
        self.cli.write_text(CLI_STUB)
        self.observe.write_text(OBSERVE_STUB)
        self.sysctl.write_text(SYSCTL_STUB)
        self.cli.chmod(0o755)
        self.observe.chmod(0o755)
        self.sysctl.chmod(0o755)
        self._env = dict(os.environ)
        self._env.update(
            {
                "RILL_XRAY_AGENT_HOME": str(self.home),
                "RILL_XRAY_AGENT_CONFIG": str(self.config),
                "RILL_XRAY_AGENT_STATUS": str(self.status),
                "RILL_XRAY_AGENT_CLI": str(self.cli),
                "RILL_XRAY_AGENT_OBSERVER": str(self.observe),
                "RILL_XRAY_AGENT_NO_SYSTEMD": "0",
                "PATH": f"{self.tmp}:/usr/bin:/bin",
                "RXA_MODE_STATE": str(self.mode_state),
                "RXA_RUNTIME_STATE": str(self.runtime_state),
                "RXA_STATUS": str(self.status),
                "RXA_SYS_STATE": str(self.sys_state),
            }
        )

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def mode(self) -> str:
        return json.loads(self.config.read_text())["mode"]

    def runtime(self) -> str:
        return self.runtime_state.read_text()

    def active(self, unit: str) -> bool:
        return (self.sys_state / "active" / unit).exists()

    def apply(self, *args: str) -> int:
        proc = subprocess.run(
            ["bash", "-c", f'source "{MANAGER}"; rxa_apply_mode "$@"', "x", *args],
            env=self._env,
            capture_output=True,
            text=True,
        )
        return proc.returncode

    def seed_ready_observe(self, mode: str = "observe-only") -> None:
        """Bring config, Runtime and all units/observation into a converged state."""
        self.config.write_text(
            json.dumps({"schemaVersion": 1, "mode": mode, "routeAssistEnabled": False,
                        "boundedAutoAllowed": False, "routeStage": "observe"})
        )
        self.runtime_state.write_text(mode)
        for u in UNITS:
            (self.sys_state / "active" / u).touch()
            (self.sys_state / "enabled" / u).parent.mkdir(exist_ok=True)
            (self.sys_state / "enabled" / u).touch()
        data = {"schemaVersion": 1, "capturedAtEpochSeconds": int(time.time()),
                "xrayConfig": {"present": False}, "services": {"xray": {"ok": False}}}
        self.status.write_text(json.dumps(data))
        return mode

    def test_fresh_install_observe_only_enables_all_units(self):
        # Fresh install: config defaults to observe-only (written by
        # rxa_config_init), Runtime follows through the WAL transaction, and
        # every unit must actually be brought active -- not short-circuited.
        self.assertEqual(self.apply("observe-only"), 0)
        self.assertEqual(self.mode(), "observe-only")
        self.assertEqual(self.runtime(), "observe-only")
        for u in UNITS:
            self.assertTrue(self.active(u), u)
            self.assertTrue((self.sys_state / "enabled" / u).exists(), u)
        self.assertTrue(self.active("rill-xray-agent-runtime.service"))

    def test_same_mode_agent_stopped_is_repaired(self):
        self.seed_ready_observe()
        (self.sys_state / "active" / "rill-xray-agent-agent.service").unlink()
        self.assertEqual(self.apply("observe-only"), 0)
        self.assertTrue(self.active("rill-xray-agent-agent.service"))

    def test_same_mode_observe_path_disabled_is_repaired(self):
        self.seed_ready_observe()
        (self.sys_state / "active" / "rill-xray-agent-xray-observe.path").unlink()
        (self.sys_state / "enabled" / "rill-xray-agent-xray-observe.path").unlink()
        self.assertEqual(self.apply("observe-only"), 0)
        self.assertTrue(self.active("rill-xray-agent-xray-observe.path"))

    def test_same_mode_observe_timer_disabled_is_repaired(self):
        self.seed_ready_observe()
        (self.sys_state / "active" / "rill-xray-agent-xray-observe.timer").unlink()
        (self.sys_state / "enabled" / "rill-xray-agent-xray-observe.timer").unlink()
        self.assertEqual(self.apply("observe-only"), 0)
        self.assertTrue(self.active("rill-xray-agent-xray-observe.timer"))

    def test_same_mode_stale_observation_refreshed(self):
        self.seed_ready_observe()
        stale = {"schemaVersion": 1, "capturedAtEpochSeconds": int(time.time()) - 7200,
                 "xrayConfig": {"present": False}, "services": {"xray": {"ok": False}}}
        self.status.write_text(json.dumps(stale))
        self.assertEqual(self.apply("observe-only"), 0)
        fresh = json.loads(self.status.read_text())
        self.assertGreaterEqual(fresh["capturedAtEpochSeconds"], int(time.time()) - 60)

    def test_same_mode_runtime_drift_repaired(self):
        self.seed_ready_observe()
        self.runtime_state.write_text("normal")
        self.assertEqual(self.apply("observe-only"), 0)
        self.assertEqual(self.runtime(), "observe-only")

    def test_safe_disabled_repeat_converges_and_stays_disabled(self):
        self.seed_ready_observe("safe-disabled")
        for u in ("rill-xray-agent-agent.service", "rill-xray-agent-xray-observe.path",
                  "rill-xray-agent-xray-observe.timer"):
            (self.sys_state / "active" / u).unlink()
        self.assertEqual(self.apply("safe-disabled"), 0)
        self.assertFalse(self.active("rill-xray-agent-agent.service"))
        self.assertFalse(self.active("rill-xray-agent-xray-observe.path"))
        self.assertFalse(self.active("rill-xray-agent-xray-observe.timer"))
        self.assertEqual(self.apply("safe-disabled"), 0)
        self.assertEqual(self.mode(), "safe-disabled")

    def test_switch_to_normal_commits_all_parties(self):
        self.assertEqual(self.apply("normal"), 0)
        self.assertEqual(self.mode(), "normal")
        self.assertEqual(self.runtime(), "normal")
        self.assertEqual(self.mode_state.read_text(), "normal")

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

    def test_same_mode_unit_activation_failure_rolls_back(self):
        self.seed_ready_observe()
        (self.sys_state / "active" / "rill-xray-agent-agent.service").unlink()
        self._env["RXA_SYSCTL_FAIL_UNITS"] = "rill-xray-agent-agent.service rill-xray-agent-xray-observe.path rill-xray-agent-xray-observe.timer"
        self.assertNotEqual(self.apply("observe-only"), 0)
        self.assertEqual(self.mode(), "observe-only")


if __name__ == "__main__":
    unittest.main()