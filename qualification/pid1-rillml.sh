#!/usr/bin/env bash
# PID1 full-critical suite for the RillML-integrated 1.0.0 canonical payload.
# Run INSIDE a fresh systemd-PID1 container with the rill-xray-agent checkout
# mounted read-only. SRC must point at the canonical repository_files dir
# (defaults to /src). All qualification is Docker-only. Nothing is compiled.
#
# In addition to the frozen 1.0.0 critical suite (install / services / mode
# lifecycle / sockets / uninstall durability) this suite adds the Batch D
# RillML prebuilt-runtime checks: the best-effort install from the signed
# stable index must actually land a verified native runtime, and the read-only
# IPC surface must reflect it (active / verified).
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
VERSION=${VERSION:-1.0.0}

# ---------------------------------------------------------------------------
# Qualification provenance metadata (independent, auditable header).
# Emitted FIRST so a log proves its runtime environment + exact subject.
# These are evidence metadata only; they are NOT part of the deterministic
# production subject identity.
# ---------------------------------------------------------------------------
emit_metadata() {
    local repo="${REPO_NAME:-rill-xray-agent}"
    local vy="${VERSION:-1.0.0}"
    local img="${CONTAINER_IMAGE:-$repo-docker}"
    local pid1="$(ps -p 1 -o comm= 2>/dev/null)"
    local sysd="$(systemctl --version 2>/dev/null | head -1)"
    local bundle="$SRC/assets/rill-xray-agent-xray-bundle.tar.gz"
    local bundle_sha="$( (sha256sum "$bundle" 2>/dev/null || shasum -a 256 "$bundle" 2>/dev/null) | awk '{print $1}')"
    echo "QUALIFICATION_METADATA_BEGIN"
    echo "repository=$repo"
    echo "version=$vy"
    echo "src=$SRC"
    echo "bundleSha256=${bundle_sha:-unavailable}"
    if [[ -f /etc/os-release ]]; then
        # Parse without sourcing: `os-release` defines VERSION/VERSION_ID which
        # would clobber this suite's own VERSION variable.
        echo "osId=$(sed -n 's/^ID=//p' /etc/os-release)"
        echo "osVersion=$(sed -n 's/^VERSION_ID=//p' /etc/os-release)"
        echo "osPrettyName=$(sed -n 's/^PRETTY_NAME=//p' /etc/os-release)"
    else
        echo "osId=unknown"
        echo "osVersion=unknown"
        echo "osPrettyName=unknown"
    fi
    echo "containerRuntime=docker"
    echo "containerImage=$img"
    echo "pid1=$pid1"
    echo "systemdVersion=${sysd:-}"
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
RILLML_ROOT=/var/lib/rill-xray-agent-rillml

# Load manager helpers (rxa_get, rxa_apply_mode, rxa_socket_connectable, ...).
# shellcheck disable=SC1090
source "$Manager"
# Load uninstall phase functions WITHOUT running the script's main block.
# The main block begins at the `--purge` dispatch; everything from that exact
# line to EOF is dropped so sourcing cannot trigger any side effects.
# shellcheck disable=SC1090
source <(sed '/^if \[\[ ${1:-} == --purge \]\]; then/,$d' "$UninstallScript" \
        | grep -v '^set -euo pipefail$')

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

# RillML helpers (root CLI is authoritative and offline for status).
# The CLI prints the bare `result` dict (no ok/result envelope) on success;
# accept both that and the wrapped form so the suite is not format-fragile.
rillml_status_json() { rxa_rillml status 2>/dev/null; }
rillml_available() {
    rillml_status_json | python3 -c 'import json,sys
d=json.load(sys.stdin); r=d.get("result") or d
assert r.get("supported") and r.get("available"), r
assert r.get("current") and r.get("current",{}).get("version"), r
print(r["current"]["version"])'
}
EXPECTED_RILL_VERSION=${RILLML_EXPECTED_VERSION:-1.5.1}
rillml_version_ok() {
    rillml_status_json | EXPECTED_RILL_VERSION="$EXPECTED_RILL_VERSION" python3 -c 'import json,os,sys
d=json.load(sys.stdin); r=d.get("result") or d
assert r["current"]["version"] == os.environ["EXPECTED_RILL_VERSION"], r'
}
rillml_ipc_active() {
    rxa_runtime rillml-status 2>/dev/null | python3 -c 'import json,sys
d=json.load(sys.stdin); d=d.get("result") or d
nr=d.get("nativeRuntime") or {}
assert nr.get("status") == "active" and nr.get("verified") is True, nr'
}

echo "=== PID1 suite ==="
check "PID1 is systemd" bash -c '[[ "$(ps -p 1 -o comm=)" == "systemd" ]]'

echo "--- identity: canonical bundle self-consistency (no stale pin) ---"
bundle_sha=$(sha256sum "$SRC/assets/rill-xray-agent-xray-bundle.tar.gz" | awk '{print $1}')
expected_sha=$(sed -n 's/^EXPECTED_SHA256=//p' "$SRC/scripts/rill_xray_agent_bootstrap.sh")
check "bootstrap EXPECTED_SHA256 == bundle sha (drift fails closed)" \
    bash -c "test -n \"$expected_sha\" && test \"$bundle_sha\" = \"$expected_sha\""

echo "=== phase 0: fresh install from canonical payload ==="
check "unit absent before install" bash -c '! [[ -e /etc/systemd/system/rill-xray-agent-runtime.service ]]'
bash "$SRC/scripts/rill_xray_agent_install.sh" >/tmp/install.log 2>&1
rc=$?
tail -3 /tmp/install.log
check "install rc=0" test "$rc" -eq 0
check "install log reports RillML (native enabled or best-effort fallback)" \
    bash -c 'grep -q "RillML" /tmp/install.log'

echo "=== static install sanity ==="
check "manager present" test -f /etc/rill-xray-agent/scripts/rill_xray_agent_manager.sh
check "config present" test -f /etc/rill-xray-agent/config.json
check "runtime binary present" test -x /opt/rill-xray-agent/bin/rill-xray-agent-runtime
check "agent binary present" test -x /opt/rill-xray-agent/bin/rill-xray-agent-agent
check "runtime unit present" test -f /etc/systemd/system/rill-xray-agent-runtime.service
check "agent unit present" test -f /etc/systemd/system/rill-xray-agent-agent.service
check "config defaults routeAssist=false" test "$(cfg routeAssistEnabled)" = "False"
check "config defaults boundedAuto=false" test "$(cfg boundedAutoAllowed)" = "False"
check "config defaults localOnly=true" test "$(cfg localOnly)" = "True"
check "config mode=observe-only" test "$(cfg mode)" = "observe-only"
check "installed version == ${VERSION}" python3 -c 'import sys; sys.path.insert(0,"/opt/rill-xray-agent/python"); import rill_xray_agent as m; assert m.__version__==sys.argv[1], m.__version__' "$VERSION"

echo "=== RillML prebuilt native runtime (Batch D) ==="
check "RillML root current tree + state present" bash -c 'test -d "$1/current" && test -f "$1/state.json"' _ "$RILLML_ROOT"
check "RillML native binary executable" test -x "$RILLML_ROOT/current/rill-runtime"
check "rillml status ok + supported + available + version (root CLI)" rillml_available
check "rillml status version matches ${EXPECTED_RILL_VERSION}" rillml_version_ok
check "rillml IPC surface active + verified (read-only)" rillml_ipc_active

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

echo "=== RillML read-only IPC still consistent after restart ==="
check "rillml IPC active after restart" rillml_ipc_active

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

echo "=== PID1 still systemd at end ==="
check "PID1 still systemd" bash -c '[[ "$(ps -p 1 -o comm=)" == "systemd" ]]'

echo "=== totals ==="
echo "PID1 suite: $PASS PASS, $FAIL FAIL"
if ((FAIL == 0)); then
    echo "PID1 SUITE ALL PASS"
    exit 0
else
    echo "PID1 SUITE FAILURES"
    exit 1
fi
