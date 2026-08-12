#!/usr/bin/env bash
# Bootstrap delivery qualification for the frozen 1.0.0 canonical identity.
# Run INSIDE a fresh systemd-PID1 container with the 1.0.0 tree mounted at
# /repo (read-only). Uses the committed bundle asset via
# RILL_XRAY_AGENT_BUNDLE_FILE so no network download is needed (Docker-only).
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

REPO=${REPO:-/repo}
Bootstrap="$REPO/integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_bootstrap.sh"
Bundle="$REPO/integrations/xray_bash_onekey/assets/rill-xray-agent-xray-bundle.tar.gz"
CFG=/etc/rill-xray-agent/config.json

echo "=== bootstrap delivery: 1.0.0 (real Xray bootstrap + bundle asset) ==="
echo "--- identity ---"
echo "bootstrap file: $(basename "$Bootstrap")"
echo "bootstrap EXPECTED_SHA256: $(sed -n 's/^EXPECTED_SHA256=//p' "$Bootstrap")"
echo "bundle sha256: $(sha256sum "$Bundle" | awk '{print $1}')"

check "bootstrap EXPECTED_SHA256 == 434fd20f" \
    bash -c "grep -q 'EXPECTED_SHA256=434fd20fff899f363c70185932528f2be9acb88f6bf8a83d5d958522324d3b1f' '$Bootstrap'"
check "bundle sha == 434fd20f" \
    bash -c "[ \"\$(sha256sum '$Bundle' | awk '{print \$1}')\" == '434fd20fff899f363c70185932528f2be9acb88f6bf8a83d5d958522324d3b1f' ]"

echo "=== run 1: fresh bootstrap+install (real paths, no DESTDIR) ==="
check "unit absent before bootstrap" bash -c '! [[ -e /etc/systemd/system/rill-xray-agent-runtime.service ]]'
RILL_XRAY_AGENT_BUNDLE_FILE="$Bundle" bash "$Bootstrap" >/tmp/bs-install.log 2>&1
rc=$?
tail -2 /tmp/bs-install.log
check "bootstrap+installer exit 0" test "$rc" -eq 0

echo "--- installed default config invariants ---"
cfg() { python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2]))' "$CFG" "$1"; }
check "mode=observe-only" test "$(cfg mode)" = "observe-only"
check "routeAssistEnabled=False" test "$(cfg routeAssistEnabled)" = "False"
check "boundedAutoAllowed=False" test "$(cfg boundedAutoAllowed)" = "False"
check "localOnly=True" test "$(cfg localOnly)" = "True"
check "candidate=1.0.0" test "$(cfg candidate)" = "1.0.0"

echo "--- installed systemd units ---"
check "runtime unit present" test -f /etc/systemd/system/rill-xray-agent-runtime.service
check "agent unit present" test -f /etc/systemd/system/rill-xray-agent-agent.service
check "runtime unit active" systemctl is-active --quiet rill-xray-agent-runtime.service
check "agent unit active" systemctl is-active --quiet rill-xray-agent-agent.service

echo "=== run 2: repeat bootstrap (must remain idempotent) ==="
RILL_XRAY_AGENT_BUNDLE_FILE="$Bundle" bash "$Bootstrap" >/tmp/bs-repeat.log 2>&1
rc=$?
check "repeat bootstrap exit 0 (idempotent)" test "$rc" -eq 0
check "runtime unit still active after repeat" systemctl is-active --quiet rill-xray-agent-runtime.service
check "config candidate still 1.0.0 after repeat" test "$(cfg candidate)" = "1.0.0"

echo "=== totals ==="
echo "bootstrap suite: $PASS PASS, $FAIL FAIL"
if ((FAIL == 0)); then
    echo "BOOTSTRAP DELIVERY 1.0.0: PASS"
    exit 0
else
    echo "BOOTSTRAP DELIVERY 1.0.0: FAILURES"
    exit 1
fi