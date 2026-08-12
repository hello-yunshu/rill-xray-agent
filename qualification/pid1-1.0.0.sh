#!/usr/bin/env bash
# PID1 full-critical suite for the frozen 1.0.0 canonical identity.
# Run INSIDE a fresh systemd-PID1 container. The canonical payload is mounted
# read-only at /src (repository_files). All qualification is Docker-only.
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

SRC=${SRC:-/src}
# Source helper functions from the CANONICAL payload (/src), which is mounted
# read-only and becomes the installed /etc/rill-xray-agent on install. The
# installed copies are byte-identical (canonical), so sourcing from /src works
# on a FRESH container before install has run.

# ---------------------------------------------------------------------------
# Qualification provenance metadata (independent, auditable header).
# Emitted FIRST so a log proves its runtime environment + exact subject.
# These are evidence metadata only; they are NOT part of the deterministic
# production subject identity (subjectId is computed without executedAt).
# ---------------------------------------------------------------------------
emit_metadata() {
    local repo="${REPO_NAME:-rill-xray-agent}"
    local vy="${VERSION:-1.0.0}"
    local rill_src="${RILL_SOURCE_COMMIT:-97d3c14540318268d0275d33a5649e58ff8f4c50}"
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
    echo "rillSourceCommit=$rill_src"
    echo "rillCanonicalCommit=$rill_canon"
    echo "xrayCommit=$xray"
    echo "bundleSha256=$bundle"
    echo "qualificationSubjectId=$subj"
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        echo "osId=${ID:-}"
        echo "osVersion=${VERSION_ID:-}"
        echo "osPrettyName=${PRETTY_NAME:-}"
    else
        echo "osId=unknown"
        echo "osVersion=unknown"
        echo "osPrettyName=unknown"
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

Manager="$SRC/scripts/rill_xray_agent_manager.sh"
UninstallScript="$SRC/scripts/rill_xray_agent_uninstall.sh"
RUNTIME_SOCK=/run/rill-xray-agent/runtime.sock
AGENT_SOCK=/run/rill-xray-agent/agent.sock
INTENT=/var/lib/rill-xray-agent-runtime/uninstall.intent.json
CFG=/etc/rill-xray-agent/config.json

# Load manager helpers (rxa_get, rxa_apply_mode, rxa_socket_connectable, ...).
# shellcheck disable=SC1090
source "$Manager"
# Load uninstall phase functions WITHOUT running the script's main block:
# strip the set -e header and only source the function definitions (lines 1-209,
# before the --purge / standalone main). Prepares/abort/commit are then callable.
# shellcheck disable=SC1090
source <(sed -n '1,209p' "$UninstallScript" | grep -v '^set -euo pipefail$')

cfg() { RILL_XRAY_AGENT_CONFIG="$CFG" python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get(sys.argv[2]))' "$CFG" "$1"; }

# Poll a unix socket until the runtime/agent actually accepts a connect (up to
# ~5s). The RFC runtime/agent sockets need a moment after a restart or mode
# switch before they are listening; a poll avoids false harness negatives.
wait_sock() {
    local sock=$1
    for _ in $(seq 1 20); do
        rxa_socket_connectable "$sock" && return 0
        sleep 0.25
    done
    return 1
}

# Run the CLI against the runtime socket with a short retry (same timing guard).
wait_runtime_cli() {
    for _ in $(seq 1 20); do
        RILL_XRAY_AGENT_CONFIG="$CFG" /opt/rill-xray-agent/bin/rill-xray-agent --json config >/dev/null 2>&1 && return 0
        sleep 0.25
    done
    return 1
}

# Uninstall phase helpers must run in THIS shell (the rxa_* functions are
# sourced here, not in a bash -c subshell). Each wrapper returns the phase's
# real result so the check() harness sees the true product behavior.
uninstall_prepare_then_test() { rxa_uninstall_prepare; [[ -f "$INTENT" ]]; }
uninstall_abort_nz() { ! rxa_uninstall_abort; }
uninstall_commit() { rxa_uninstall_commit; }

echo "=== PID1 suite ==="
check "PID1 is systemd" bash -c '[[ "$(ps -p 1 -o comm=)" == "systemd" ]]'

echo "--- identity: canonical payload EXPECTED_SHA256 == 14371ba7 ---"
check "source bundle EXPECTED_SHA256 == 14371ba7" bash -c "grep -q 'EXPECTED_SHA256=14371ba7d078e849f5dd3648624da05c8e9e23c599edaf834af73463d8dfb9ac' '$SRC/scripts/rill_xray_agent_bootstrap.sh'"

echo "=== phase 0: fresh install from canonical payload ==="
check "unit absent before install" bash -c '! [[ -e /etc/systemd/system/rill-xray-agent-runtime.service ]]'
bash "$SRC/scripts/rill_xray_agent_install.sh" >/tmp/install.log 2>&1
rc=$?
tail -2 /tmp/install.log
check "install rc=0" test "$rc" -eq 0

echo "=== static install sanity ==="
check "manager present" test -f /etc/rill-xray-agent/scripts/rill_xray_agent_manager.sh
check "config present" test -f /etc/rill-xray-agent/config.json
check "runtime binary present" test -x /opt/rill-xray-agent/bin/rill-xray-agent-runtime
check "agent binary present" test -x /opt/rill-xray-agent/bin/rill-xray-agent-agent
check "runtime unit present" test -f /etc/systemd/system/rill-xray-agent-runtime.service
check "agent unit present" test -f /etc/systemd/system/rill-xray-agent-agent.service
check "config defaults routeAssist=false" test "$(cfg routeAssistEnabled)" = "False"
check "config defaults boundedAuto=false" test "$(cfg boundedAutoAllowed)" = "False"
check "config defaults candidate=1.0.0" test "$(cfg candidate)" = "1.0.0"
check "config defaults localOnly=true" test "$(cfg localOnly)" = "True"
check "config mode=observe-only" test "$(cfg mode)" = "observe-only"
check "installed version == 1.0.0" python3 -c 'import sys; sys.path.insert(0,"/opt/rill-xray-agent/python"); import rill_xray_agent as m; assert m.__version__=="1.0.0", m.__version__'

echo "=== fresh observe-only ==="
check "runtime unit active" systemctl is-active --quiet rill-xray-agent-runtime.service
check "agent unit active" systemctl is-active --quiet rill-xray-agent-agent.service
check "observe path active" systemctl is-active --quiet rill-xray-agent-xray-observe.path
check "runtime.sock connects (real connect)" wait_sock "$RUNTIME_SOCK"
check "agent.sock connects (real connect)" wait_sock "$AGENT_SOCK"

echo "=== RuntimeDirectory retention while observe-only ==="
check "/run/rill-xray-agent exists" test -d /run/rill-xray-agent

echo "=== observation freshness (fresh observe holds valid JSON) ==="
check "observe refresh runs" rxa_observe_fresh
check "observe valid (structure+fresh)" python3 -c '
import json,time
d=json.load(open("/var/lib/rill-xray-agent-xray/status/xray-observation.json"))
assert isinstance(d,dict) and "capturedAtEpochSeconds" in d, list(d.keys())
assert time.time()-d["capturedAtEpochSeconds"] < 300, d
'

echo "=== switch safe-disabled ==="
check "apply safe-disabled" rxa_apply_mode safe-disabled
check "config mode=safe-disabled" test "$(cfg mode)" = "safe-disabled"
check "runtime unit still active" systemctl is-active --quiet rill-xray-agent-runtime.service
check "agent unit inactive" bash -c '! systemctl is-active --quiet rill-xray-agent-agent.service'
check "observe path inactive" bash -c '! systemctl is-active --quiet rill-xray-agent-xray-observe.path'
check "routeAssist stays false in runtime" test "$(cfg routeAssistEnabled)" = "False"
check "boundedAuto stays false in runtime" test "$(cfg boundedAutoAllowed)" = "False"

echo "--- safe-disabled socket semantics ---"
check "runtime.sock still connects" wait_sock "$RUNTIME_SOCK"

echo "=== RuntimeDirectory retention while safe-disabled ==="
check "/run/rill-xray-agent still exists" test -d /run/rill-xray-agent

echo "=== switch back observe-only ==="
check "apply observe-only" rxa_apply_mode observe-only
check "config mode=observe-only" test "$(cfg mode)" = "observe-only"
check "agent unit active again" systemctl is-active --quiet rill-xray-agent-agent.service
check "runtime.sock connects again" wait_sock "$RUNTIME_SOCK"
check "agent.sock connects again" wait_sock "$AGENT_SOCK"

echo "=== switch normal ==="
check "apply normal" rxa_apply_mode normal
check "config mode=normal" test "$(cfg mode)" = "normal"
check "agent unit active in normal" systemctl is-active --quiet rill-xray-agent-agent.service
check "runtime.sock connects in normal" wait_sock "$RUNTIME_SOCK"
check "agent.sock connects in normal" wait_sock "$AGENT_SOCK"

echo "=== switch safe-disabled again ==="
check "apply safe-disabled (2)" rxa_apply_mode safe-disabled
check "config mode=safe-disabled (2)" test "$(cfg mode)" = "safe-disabled"
check "agent unit inactive (2)" bash -c '! systemctl is-active --quiet rill-xray-agent-agent.service'

echo "=== switch observe-only again ==="
check "apply observe-only (2)" rxa_apply_mode observe-only
check "config mode=observe-only (2)" test "$(cfg mode)" = "observe-only"

echo "=== formal verify ==="
check "runtime answers config" wait_runtime_cli
check "diagnose canApply=false" bash -c '/opt/rill-xray-agent/bin/rill-xray-agent --json diagnose 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); assert not d.get(\"canApply\", False), d"'
check "verify.sh runtime path exits 0" bash /etc/rill-xray-agent/scripts/rill_xray_agent_verify.sh runtime

echo "=== agent restart recovery while observe-only ==="
systemctl restart rill-xray-agent-agent.service
check "agent unit active after restart" systemctl is-active --quiet rill-xray-agent-agent.service
check "agent.sock connects after restart" wait_sock "$AGENT_SOCK"
check "runtime.sock connects after restart" wait_sock "$RUNTIME_SOCK"

echo "=== observation freshness after restart ==="
check "observation valid after restart" rxa_observe_fresh

echo "=== agent restart recovery assert socket is listening (true reconnect) ==="
check "agent.sock still accepted (post-restart)" wait_sock "$AGENT_SOCK"

echo "=== uninstall intent: prepared persisted before host removal ==="
check "prepare writes intent" uninstall_prepare_then_test
check "intent file exists" test -f "$INTENT"
check "intent JSON parseable + phase=prepared" python3 -c "import json; d=json.load(open('$INTENT')); assert d.get('phase')=='prepared', d"
check "no agent removal before committed" systemctl is-active --quiet rill-xray-agent-runtime.service

echo "=== uninstall abort keeps host failure + persists aborted ==="
check "abort returns nonzero with host rc" uninstall_abort_nz
check "abort marker persisted" python3 -c "import json; d=json.loads(open('$INTENT').read().strip().splitlines()[-1]); assert d.get('phase')=='aborted', d"
check "runtime still active after abort" systemctl is-active --quiet rill-xray-agent-runtime.service

echo "=== uninstall commit (host purge) ==="
check "commit returns zero (purge runs)" uninstall_commit
check "runtime unit removed by purge" bash -c '! test -e /etc/systemd/system/rill-xray-agent-runtime.service'
check "no agent unit remains" bash -c '! test -e /etc/systemd/system/rill-xray-agent-agent.service'
check "opt rill payload removed" bash -c '! test -e /opt/rill-xray-agent'

echo "=== totals ==="
echo "PID1 suite: r=$PASS PASS, r=$FAIL FAIL"
if ((FAIL == 0)); then
    echo "PID1 SUITE ALL PASS"
    exit 0
else
    echo "PID1 SUITE FAILURES"
    exit 1
fi