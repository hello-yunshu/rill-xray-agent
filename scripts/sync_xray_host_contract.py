#!/usr/bin/env python3
"""Apply a changed Xray Host Contract to the Agent integration.

The Xray full commit is recorded only as audit metadata.  Runtime config and
canonical identity consume the independently verified Host Contract digest.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ANCHOR = ROOT / "integrations/xray_bash_onekey/UPSTREAM_ANCHOR.json"
CONFIG = ROOT / "config/default.json"
PROVENANCE = ROOT / "PROVENANCE/upstream.json"
BEGIN = b"# BEGIN RILL XRAY AGENT INTEGRATION"
END = b"# END RILL XRAY AGENT INTEGRATION"


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"invalid JSON {path}: {exc}") from exc


def write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def git_output(xray: Path, *args: str) -> str:
    return subprocess.check_output(("git", "-C", str(xray), *args), text=True).strip()


def host_surface(blob: bytes) -> bytes:
    start = blob.find(BEGIN)
    end_marker = END + b"\n"
    end = blob.find(end_marker, start)
    if start < 0 or end < 0:
        raise SystemExit("Xray install.sh host integration markers are missing")
    return blob[start : end + len(end_marker)]


def package_sums() -> None:
    sums = ROOT / "PACKAGE_SHA256SUMS"
    rows = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or path == sums or path.name.endswith(".pyc"):
            continue
        rel = path.relative_to(ROOT)
        if ".git" in rel.parts or "__pycache__" in rel.parts or ".pytest_cache" in rel.parts or "target" in rel.parts:
            continue
        rows.append((rel.as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
    sums.write_text("".join(f"{digest}  {rel}\n" for rel, digest in rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--xray", type=Path, required=True)
    parser.add_argument("--xray-sha", required=True)
    parser.add_argument("--reviewed-at")
    parser.add_argument("--github-output", type=Path)
    args = parser.parse_args()
    xray = args.xray.resolve()
    contract = load(xray / "repository_files/rill_integration/HOST_CONTRACT.json")
    digest = contract.get("digest")
    if contract.get("schemaVersion") != 1 or contract.get("semanticVersion") != 1:
        raise SystemExit("unsupported Xray Host Contract")
    if not isinstance(digest, str) or len(digest) != 64:
        raise SystemExit("invalid Xray Host Contract digest")
    expected_surface_sha = contract.get("hostOwnedFiles", {}).get(
        "install.sh#RILL_XRAY_AGENT_INTEGRATION"
    )
    actual_surface_sha = hashlib.sha256(host_surface((xray / "install.sh").read_bytes())).hexdigest()
    if expected_surface_sha != actual_surface_sha:
        raise SystemExit("Xray Host Contract does not match install.sh")

    anchor = load(ANCHOR)
    before = anchor.get("hostContractDigest")
    output = args.github_output.resolve() if args.github_output else None
    if before == digest:
        print("NO_CHANGE")
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            with output.open("a") as handle:
                handle.write("changed=false\n")
                handle.write(f"host_contract_digest={digest}\n")
        return 0

    reviewed_at = args.reviewed_at or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    reviewed_blob = git_output(xray, "hash-object", "install.sh")
    anchor.update({
        "hostContractDigest": digest,
        "hostContractSchema": contract["schemaVersion"],
        "reviewedAt": reviewed_at,
        "reviewedCommit": args.xray_sha,
        "reviewedInstallScriptBlob": reviewed_blob,
    })
    write(ANCHOR, anchor)

    config = load(CONFIG)
    integration = config.setdefault("xrayIntegration", {})
    integration.pop("reviewedCommit", None)
    integration.update({
        "enabled": False,
        "observeOnly": True,
        "hostContractSchema": contract["schemaVersion"],
        "hostContractDigest": digest,
        "upstreamRepository": contract["repository"],
    })
    write(CONFIG, config)

    provenance = load(PROVENANCE)
    provenance_xray = provenance.setdefault("xray", {})
    provenance_xray.update({
        "hostContractDigest": digest,
        "hostContractSchema": contract["schemaVersion"],
        "reviewedAt": reviewed_at,
        "reviewedCommit": args.xray_sha,
        "reviewedInstallScriptBlob": reviewed_blob,
        "reviewedInstallScriptPath": "install.sh",
        "releaseRule": "The reviewed host-owned install.sh surface is identified by the independently verified Host Contract digest; full commit and blob values remain audit metadata only.",
    })
    write(PROVENANCE, provenance)

    subprocess.run((sys.executable, "scripts/sync_xray_payload.py"), cwd=ROOT, check=True)
    subprocess.run((sys.executable, "scripts/build_canonical_manifest.py"), cwd=ROOT, check=True)
    package_sums()
    print(f"UPDATED host contract {before or '<missing>'} -> {digest}")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("a") as handle:
            handle.write("changed=true\n")
            handle.write(f"old_host_contract_digest={before or 'missing'}\n")
            handle.write(f"host_contract_digest={digest}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
