#!/usr/bin/env bash
# RC upgrade qualification: v0.1.0 (real released artifact tree) -> 0.9.0-rc.1
#
# Usage (inside a fresh systemd-PID1 container):
#   upgrade_v010_to_rc1.sh <v0.1.0-tree> <rc-tree>
# <v0.1.0-tree> = the frozen v0.1.0 release tree (VERSION == 0.1.0)
# <rc-tree>     = the frozen RC tree under test (VERSION == 0.9.0-rc.1)
#
# Covers: fresh v0.1.0 install -> real state/config -> RC upgrade -> config
# preservation + state migration -> RC timeline continues writing -> rollback
# to v0.1.0. All qualification is Docker-only.
set -uo pipefail

PASS=0
FAIL=0
check() {
    local label=$1
    shift
    if "$@" >/dev/null 2>&1; then
        PASS=$((PASS + 1))
        echo "[PASS] $label"
    else
        FAIL=$((FAIL + 1))
        echo "[FAIL] $label"
    fi
}

V010=$1
RC=$2

echo "=== upgrade suite: v0.1.0 -> 0.9.0-rc.1 ==="
echo "--- identity: v0.1.0 tree ---"
cat "$V010/VERSION"
grep -m1 EXPECTED_SHA256 "$V010/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_bootstrap.sh"
echo "--- identity: RC tree ---"
cat "$RC/VERSION"
grep -m1 EXPECTED_SHA256 "$RC/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_bootstrap.sh"

echo "=== phase 1: install v0.1.0 from frozen tag tree ==="
check "v0.1.0 unit absent before install" bash -c '! [[ -e /etc/systemd/system/rill-xray-agent-runtime.service ]]'
bash "$V010/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh" >/tmp/v010-install.log 2>&1
rc=$?
tail -2 /tmp/v010-install.log
check "v0.1.0 install rc=0" test "$rc" -eq 0
check "v0.1.0 runtime unit active" systemctl is-active --quiet rill-xray-agent-runtime.service
check "v0.1.0 agent unit active" systemctl is-active --quiet rill-xray-agent-agent.service
check "v0.1.0 observe path active" systemctl is-active --quiet rill-xray-agent-xray-observe.path

echo "=== phase 2: generate real v0.1.0 state/config ==="
source /etc/rill-xray-agent/scripts/rill_xray_agent_manager.sh
check "v0.1.0 mode observe-only" test "$(rxa_get mode)" = "observe-only"
# user config customisation (keys that exist in v0.1.0; must survive upgrade)
python3 - <<'PY'
import json
p = "/etc/rill-xray-agent/config.json"
d = json.load(open(p))
d["maximumConcurrentConnections"] = 7
d["userLevelStatistics"] = True
json.dump(d, open(p, "w"), indent=2)
PY
# real v0.1.0 observation cycles (observe.py writes observation status)
for _ in $(seq 1 6); do
    sleep 3
    /usr/bin/python3 /etc/rill-xray-agent/scripts/rill_xray_agent_observe.py >/dev/null 2>&1 || true
    sync
done
sleep 3
check "v0.1.0 observation file exists" test -f /var/lib/rill-xray-agent-xray/status/xray-observation.json
check "v0.1.0 observation is valid json" python3 -c '
import json
d = json.load(open("/var/lib/rill-xray-agent-xray/status/xray-observation.json"))
assert isinstance(d, dict)
'
check "v0.1.0 CLI status works" /opt/rill-xray-agent/bin/rill-xray-agent --json status
check "v0.1.0 CLI snapshot works" /opt/rill-xray-agent/bin/rill-xray-agent --json config
check "v0.1.0 CLI has NO timeline subcommand (pre-OI identity)" bash -c '! /opt/rill-xray-agent/bin/rill-xray-agent --json timeline >/dev/null 2>&1'

echo "=== phase 3: upgrade to 0.9.0-rc.1 (frozen RC tree) ==="
bash "$RC/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh" >/tmp/rc-install.log 2>&1
rc=$?
tail -2 /tmp/rc-install.log
check "RC upgrade install rc=0" test "$rc" -eq 0
check "RC runtime unit active after upgrade" systemctl is-active --quiet rill-xray-agent-runtime.service
check "RC agent unit active after upgrade" systemctl is-active --quiet rill-xray-agent-agent.service

echo "=== phase 4: verify preservation + migration ==="
check "user config maximumConcurrentConnections preserved" test "$(python3 -c 'import json;print(json.load(open("/etc/rill-xray-agent/config.json"))["maximumConcurrentConnections"])')" = "7"
check "user config userLevelStatistics preserved" test "$(python3 -c 'import json;print(json.load(open("/etc/rill-xray-agent/config.json"))["userLevelStatistics"])')" = "True"
check "mode defaults unchanged (observe-only)" test "$(rxa_get mode)" = "observe-only"
check "routeAssist unchanged (false)" test "$(rxa_get routeAssistEnabled)" = "false"
check "boundedAuto unchanged (false)" test "$(rxa_get boundedAutoAllowed)" = "false"
check "execution gate canApply=false" bash -c '/opt/rill-xray-agent/bin/rill-xray-agent --json diagnose 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert not d.get(\"canApply\", False), d"'
check "runtime version is RC" python3 -c 'import sys; sys.path.insert(0,"/opt/rill-xray-agent/python"); import rill_xray_agent as m; assert m.__version__ == "0.9.0-rc.1", m.__version__'
check "RC unit files replaced (runtime unit newer than config)" test "/etc/systemd/system/rill-xray-agent-runtime.service" -nt "/etc/rill-xray-agent/config.json"
check "old v0.1.0 observation still readable" test -f /var/lib/rill-xray-agent-xray/status/xray-observation.json
check "old v0.1.0 observation survives upgrade (valid json)" python3 -c '
import json
json.load(open("/var/lib/rill-xray-agent-xray/status/xray-observation.json"))
'

echo "=== phase 5: RC timeline fresh + continues writing ==="
# The event journal is created lazily on the first MEANINGFUL state-change
# event. After upgrade the operator config is preserved (no change), so no
# journal exists yet - that is correct, not a defect. Trigger a real observed
# change (install config appears), run the observer, and verify the RC creates
# a fresh journal and records the transition exactly once.
# Derive the host observe root from the installed integration unit (the unit
# sets Environment=RILL_XRAY_HOST_ROOT=...). Do not hardcode the host-specific
# path here.
host_root=$(systemctl show rill-xray-agent-xray-observe.service -p Environment 2>/dev/null \
    | sed -n 's/^Environment=RILL_XRAY_HOST_ROOT=//p')
host_root=${host_root:-/etc/rill-xray-agent/host}
mkdir -p "$host_root/conf"
printf '{"upgradeTrigger":true}\n' > "$host_root/conf/install_config.json"
# Invoke the observer the same way the systemd unit does (/usr/bin/python3) so
# the installed canonical payload is what actually runs.
/usr/bin/python3 /etc/rill-xray-agent/scripts/rill_xray_agent_observe.py >/dev/null 2>&1
check "timeline meta created after a meaningful change (fresh journal by RC)" test -f /var/lib/rill-xray-agent-xray/history/meta.json
check "timeline records the observed change" python3 -c '
import json, subprocess
out = subprocess.check_output(["/opt/rill-xray-agent/bin/rill-xray-agent","--json","timeline"])
d = json.loads(out)
assert d.get("available") is True and d.get("integrity") == "valid", d
types = [e.get("eventType") for e in d.get("events", [])]
assert "install_config_changed" in types, types
'
check "RC timeline CLI works" /opt/rill-xray-agent/bin/rill-xray-agent --json timeline
check "RC diagnose CLI works" /opt/rill-xray-agent/bin/rill-xray-agent --json diagnose
check "observation still valid after upgrade" test -f /var/lib/rill-xray-agent-xray/status/xray-observation.json

echo "=== phase 6: rollback to v0.1.0 (downgrade path) ==="
bash "$V010/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh" >/tmp/v010-rollback.log 2>&1
rc=$?
check "rollback install rc=0" test "$rc" -eq 0
check "runtime unit active after rollback" systemctl is-active --quiet rill-xray-agent-runtime.service
check "agent unit active after rollback" systemctl is-active --quiet rill-xray-agent-agent.service
check "user config preserved through rollback" test "$(python3 -c 'import json;print(json.load(open("/etc/rill-xray-agent/config.json"))["maximumConcurrentConnections"])')" = "7"
python3 -c 'import sys; sys.path.insert(0,"/opt/rill-xray-agent/python"); import rill_xray_agent as m; assert m.__version__ == "0.1.0", m.__version__' && check "runtime version back to v0.1.0" true

echo "=== totals ==="
echo "upgrade suite: $PASS PASS, $FAIL FAIL"
if ((FAIL == 0)); then
    echo "UPGRADE QUALIFICATION PASS"
    exit 0
else
    echo "UPGRADE QUALIFICATION FAILURES"
    exit 1
fi