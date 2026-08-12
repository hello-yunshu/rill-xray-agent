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

# ---------------------------------------------------------------------------
# Qualification provenance metadata (independent, auditable header).
# Evidence metadata only; NOT part of the deterministic subject identity.
# ---------------------------------------------------------------------------
emit_metadata() {
    local repo="${REPO_NAME:-rill-xray-agent}"
    local vy="${VERSION:-1.0.0}"
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
    echo "version=$vy"
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

echo "=== bootstrap delivery: 1.0.0 (real Xray bootstrap + bundle asset) ==="
echo "--- identity ---"
echo "bootstrap file: $(basename "$Bootstrap")"
echo "bootstrap EXPECTED_SHA256: $(sed -n 's/^EXPECTED_SHA256=//p' "$Bootstrap")"
echo "bundle sha256: $(sha256sum "$Bundle" | awk '{print $1}')"

check "bootstrap EXPECTED_SHA256 == 14371ba7" \
    bash -c "grep -q 'EXPECTED_SHA256=14371ba7d078e849f5dd3648624da05c8e9e23c599edaf834af73463d8dfb9ac' '$Bootstrap'"
check "bundle sha == 14371ba7" \
    bash -c "[ \"\$(sha256sum '$Bundle' | awk '{print \$1}')\" == '14371ba7d078e849f5dd3648624da05c8e9e23c599edaf834af73463d8dfb9ac' ]"

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