#!/usr/bin/env bash
# Upgrade qualification: SOURCE (real released artifact tree) -> TARGET release
# tree. SOURCE_VERSION is read from <source-tree>/VERSION, TARGET_VERSION from
# <target-tree>/VERSION. For the 1.0.0 qualification this is v0.1.0 -> 1.0.0.
#
# Usage (inside a fresh systemd-PID1 container):
#   upgrade_v010_to_rc1.sh <source-tree> <target-tree>
# <source-tree> = the frozen SOURCE release tree (e.g. VERSION == 0.1.0)
# <target-tree> = the frozen release tree under test (e.g. VERSION == 1.0.0)
#
# Covers: fresh SOURCE install -> real state/config -> upgrade -> config
# preservation + state migration -> timeline continues writing -> rollback
# to SOURCE. All qualification is Docker-only.
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

SOURCE=$1
TARGET=$2
SOURCE_VERSION=$(cat "$SOURCE/VERSION")
TARGET_VERSION=$(cat "$TARGET/VERSION")

# ---------------------------------------------------------------------------
# Qualification provenance metadata (independent, auditable header).
# Evidence metadata only; NOT part of the deterministic subject identity.
# The 1.0.0 qualification runs SOURCE_VERSION=0.1.0, TARGET_VERSION=1.0.0.
# ---------------------------------------------------------------------------
emit_metadata() {
    local repo="${REPO_NAME:-rill-xray-agent}"
    local rill_canon="${RILL_CANONICAL_COMMIT:-97d3c14540318268d0275d33a5649e58ff8f4c50}"
    local xray="${XRAY_COMMIT:-2ab36c00f274f4fbe92a1c22d4d26122046d859d}"
    local bundle="${BUNDLE_SHA256:-14371ba7d078e849f5dd3648624da05c8e9e23c599edaf834af73463d8dfb9ac}"
    local subj="${SUBJECT_ID:-16b3e43d0fd99162ca62a95a3bb509350c11b45869ab552e7da3ac10784c06fa}"
    local img="${CONTAINER_IMAGE:-$repo-docker}"
    local harness="${HARNESS_SHA256:-$( (sha256sum "$0" 2>/dev/null || shasum -a 256 "$0" 2>/dev/null) | awk '{print $1}')}"
    local pid1="$(ps -p 1 -o comm= 2>/dev/null)"
    local sysd="$(systemctl --version 2>/dev/null | head -1)"
    echo "QUALIFICATION_METADATA_BEGIN"
    echo "repository=$repo"
    echo "version=$TARGET_VERSION"
    echo "rillSourceCommit=$rill_canon"
    echo "rillCanonicalCommit=$rill_canon"
    echo "xrayCommit=$xray"
    echo "bundleSha256=$bundle"
    echo "qualificationSubjectId=$subj"
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "osId=${ID:-}"
        echo "osVersion=${VERSION_ID:-}"
        echo "osPrettyName=${PRETTY_NAME:-}"
    fi
    echo "containerRuntime=docker"
    echo "containerImage=$img"
    echo "pid1=$pid1"
    echo "systemdVersion=${sysd:-}"
    echo "harnessSha256=$harness"
    echo "executedAtUTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "QUALIFICATION_METADATA_END"
}
emit_metadata

echo "=== upgrade suite: v$SOURCE_VERSION -> v$TARGET_VERSION ==="
echo "--- identity: SOURCE tree ---"
cat "$SOURCE/VERSION"
grep -m1 EXPECTED_SHA256 "$SOURCE/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_bootstrap.sh"
echo "--- identity: TARGET tree ---"
cat "$TARGET/VERSION"
grep -m1 EXPECTED_SHA256 "$TARGET/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_bootstrap.sh"

echo "=== phase 1: install v$SOURCE_VERSION from frozen tag tree ==="
check "v$SOURCE_VERSION unit absent before install" bash -c '! [[ -e /etc/systemd/system/rill-xray-agent-runtime.service ]]'
bash "$SOURCE/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh" >/tmp/v010-install.log 2>&1
rc=$?
tail -2 /tmp/v010-install.log
check "v$SOURCE_VERSION install rc=0" test "$rc" -eq 0
check "v$SOURCE_VERSION runtime unit active" systemctl is-active --quiet rill-xray-agent-runtime.service
check "v$SOURCE_VERSION agent unit active" systemctl is-active --quiet rill-xray-agent-agent.service
check "v$SOURCE_VERSION observe path active" systemctl is-active --quiet rill-xray-agent-xray-observe.path

echo "=== phase 2: generate real v$SOURCE_VERSION state/config ==="
source /etc/rill-xray-agent/scripts/rill_xray_agent_manager.sh
check "v$SOURCE_VERSION mode observe-only" test "$(rxa_get mode)" = "observe-only"
# user config customisation (keys that exist in v$SOURCE_VERSION; must survive upgrade)
python3 - <<'PY'
import json
p = "/etc/rill-xray-agent/config.json"
d = json.load(open(p))
d["maximumConcurrentConnections"] = 7
d["userLevelStatistics"] = True
json.dump(d, open(p, "w"), indent=2)
PY
# real v$SOURCE_VERSION observation cycles (observe.py writes observation status)
for _ in $(seq 1 6); do
    sleep 3
    /usr/bin/python3 /etc/rill-xray-agent/scripts/rill_xray_agent_observe.py >/dev/null 2>&1 || true
    sync
done
sleep 3
check "v$SOURCE_VERSION observation file exists" test -f /var/lib/rill-xray-agent-xray/status/xray-observation.json
check "v$SOURCE_VERSION observation is valid json" python3 -c '
import json
d = json.load(open("/var/lib/rill-xray-agent-xray/status/xray-observation.json"))
assert isinstance(d, dict)
'
check "v$SOURCE_VERSION CLI status works" /opt/rill-xray-agent/bin/rill-xray-agent --json status
check "v$SOURCE_VERSION CLI snapshot works" /opt/rill-xray-agent/bin/rill-xray-agent --json config
check "v$SOURCE_VERSION CLI has NO timeline subcommand (pre-OI identity)" bash -c '! /opt/rill-xray-agent/bin/rill-xray-agent --json timeline >/dev/null 2>&1'

echo "=== phase 3: upgrade to v$TARGET_VERSION (frozen TARGET tree) ==="
bash "$TARGET/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh" >/tmp/rc-install.log 2>&1
rc=$?
tail -2 /tmp/rc-install.log
check "TARGET upgrade install rc=0" test "$rc" -eq 0
check "TARGET runtime unit active after upgrade" systemctl is-active --quiet rill-xray-agent-runtime.service
check "TARGET agent unit active after upgrade" systemctl is-active --quiet rill-xray-agent-agent.service

echo "=== phase 4: verify preservation + migration ==="
check "user config maximumConcurrentConnections preserved" test "$(python3 -c 'import json;print(json.load(open("/etc/rill-xray-agent/config.json"))["maximumConcurrentConnections"])')" = "7"
check "user config userLevelStatistics preserved" test "$(python3 -c 'import json;print(json.load(open("/etc/rill-xray-agent/config.json"))["userLevelStatistics"])')" = "True"
check "mode defaults unchanged (observe-only)" test "$(rxa_get mode)" = "observe-only"
check "routeAssist unchanged (false)" test "$(rxa_get routeAssistEnabled)" = "false"
check "boundedAuto unchanged (false)" test "$(rxa_get boundedAutoAllowed)" = "false"
check "execution gate canApply=false" bash -c '/opt/rill-xray-agent/bin/rill-xray-agent --json diagnose 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert not d.get(\"canApply\", False), d"'
# Derive the TARGET version from the tree under test (single source) so the
# same harness serves any rc/stable without hardcoding a version string.
check "runtime version is target (v$TARGET_VERSION)" python3 -c 'import sys; sys.path.insert(0,"/opt/rill-xray-agent/python"); import rill_xray_agent as m; assert m.__version__ == "'"$TARGET_VERSION"'", m.__version__'
check "TARGET unit files replaced (runtime unit newer than config)" test "/etc/systemd/system/rill-xray-agent-runtime.service" -nt "/etc/rill-xray-agent/config.json"
check "old v$SOURCE_VERSION observation still readable" test -f /var/lib/rill-xray-agent-xray/status/xray-observation.json
check "old v$SOURCE_VERSION observation survives upgrade (valid json)" python3 -c '
import json
json.load(open("/var/lib/rill-xray-agent-xray/status/xray-observation.json"))
'

echo "=== phase 5: TARGET timeline fresh + continues writing ==="
# The event journal is created lazily on the first MEANINGFUL state-change
# event. After upgrade the operator config is preserved (no change), so no
# journal exists yet - that is correct, not a defect. Trigger a real observed
# change (install config appears), run the observer, and verify the TARGET
# creates a fresh journal and records the transition exactly once.
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
check "timeline meta created after a meaningful change (fresh journal by TARGET)" test -f /var/lib/rill-xray-agent-xray/history/meta.json
check "timeline records the observed change" python3 -c '
import json, subprocess
out = subprocess.check_output(["/opt/rill-xray-agent/bin/rill-xray-agent","--json","timeline"])
d = json.loads(out)
assert d.get("available") is True and d.get("integrity") == "valid", d
types = [e.get("eventType") for e in d.get("events", [])]
assert "install_config_changed" in types, types
'
check "TARGET timeline CLI works" /opt/rill-xray-agent/bin/rill-xray-agent --json timeline
check "TARGET diagnose CLI works" /opt/rill-xray-agent/bin/rill-xray-agent --json diagnose
check "observation still valid after upgrade" test -f /var/lib/rill-xray-agent-xray/status/xray-observation.json

echo "=== phase 6: rollback to v$SOURCE_VERSION (downgrade path) ==="
bash "$SOURCE/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_install.sh" >/tmp/v010-rollback.log 2>&1
rc=$?
check "rollback install rc=0" test "$rc" -eq 0
check "runtime unit active after rollback" systemctl is-active --quiet rill-xray-agent-runtime.service
check "agent unit active after rollback" systemctl is-active --quiet rill-xray-agent-agent.service
check "user config preserved through rollback" test "$(python3 -c 'import json;print(json.load(open("/etc/rill-xray-agent/config.json"))["maximumConcurrentConnections"])')" = "7"
check "runtime version back to v$SOURCE_VERSION" python3 -c 'import sys; sys.path.insert(0,"/opt/rill-xray-agent/python"); import rill_xray_agent as m; assert m.__version__ == "'"$SOURCE_VERSION"'", m.__version__'

echo "=== totals ==="
echo "upgrade suite: $PASS PASS, $FAIL FAIL"
if ((FAIL == 0)); then
    echo "UPGRADE QUALIFICATION PASS"
    exit 0
else
    echo "UPGRADE QUALIFICATION FAILURES"
    exit 1
fi