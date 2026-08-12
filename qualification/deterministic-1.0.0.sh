#!/usr/bin/env bash
# Deterministic build A/B: rebuild the canonical bundle from two clean
# checkouts of the frozen 1.0.0 source and confirm byte-identical artifacts.
set -euo pipefail

A=/tmp/rxa-det-A
B=/tmp/rxa-det-B
ASSET=integrations/xray_bash_onekey/assets/rill-xray-agent-xray-bundle.tar.gz
REPO_ASSET=integrations/xray_bash_onekey/repository_files/assets/rill-xray-agent-xray-bundle.tar.gz

build() {
    local root=$1
    # Remove the committed bundle so we genuinely rebuild it from source.
    rm -f "$root/$ASSET" "$root/$REPO_ASSET"
    (cd "$root" && python3 scripts/sync_xray_payload.py 2>&1 | sed -n 's/.*-> \([0-9a-f]\{64\}\)$/\1/p' | head -1)
    # Return the critical artifact hashes (relative paths -> identical across A/B).
    (cd "$root" && sha256sum \
        "$ASSET" \
        integrations/xray_bash_onekey/CANONICAL_MANIFEST.json \
        integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_bootstrap.sh \
        integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_uninstall.sh)
}

echo "=== deterministic build A ==="
build "$A" > /tmp/rxa-qual/det-A.out
cat /tmp/rxa-qual/det-A.out
echo "=== deterministic build B ==="
build "$B" > /tmp/rxa-qual/det-B.out
cat /tmp/rxa-qual/det-B.out

echo "=== compare A vs B hashes ==="
if diff /tmp/rxa-qual/det-A.out /tmp/rxa-qual/det-B.out; then
    echo "DETERMINISTIC BUILD A/B: BYTE-IDENTICAL"
    echo "rebuilt bundle: $(awk 'NR==1{print $1}' /tmp/rxa-qual/det-A.out)"
    exit 0
else
    echo "DETERMINISTIC BUILD A/B: MISMATCH"
    exit 1
fi