#!/usr/bin/env python3
"""Verify the declared host-owned Xray install surface at its reviewed commit."""

from __future__ import annotations

import hashlib
import json
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROVENANCE = ROOT / "PROVENANCE" / "upstream.json"


def main() -> int:
    data = json.loads(PROVENANCE.read_text())
    anchor = data["xray"]
    commit = anchor["reviewedCommit"]
    path = anchor["reviewedInstallScriptPath"]
    expected = anchor["reviewedInstallScriptBlob"]
    if len(commit) != 40 or len(expected) != 40 or not path:
        raise SystemExit("invalid Xray host-surface provenance anchor")
    url = f"https://raw.githubusercontent.com/{anchor['repository']}/{commit}/{path}"
    request = urllib.request.Request(url, headers={"User-Agent": "rill-xray-agent-provenance/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            blob = response.read()
            # reviewedInstallScriptBlob is a Git blob object ID, not a raw
            # SHA-1 of the HTTP response bytes.
            actual = hashlib.sha1(
                f"blob {len(blob)}\0".encode() + blob
            ).hexdigest()
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SystemExit(f"unable to verify Xray host-surface blob: {exc}") from exc
    if actual != expected:
        raise SystemExit(
            f"Xray host-surface blob drift: {path}@{commit} has {actual}, expected {expected}"
        )
    print(json.dumps({"repository": anchor["repository"], "commit": commit,
                      "path": path, "blob": actual}, sort_keys=True))
    print("PASS: reviewed Xray host-owned install surface is byte-anchored")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
