#!/usr/bin/env python3
"""Byte-verify an Xray clone's installed payload against the Rill canonical
manifest pinned at a specific Rill commit.

The Xray repo mirrors repository_files as: rill_payload/, scripts/, systemd/,
assets/ and .github/test/. Each Xray file is compared by SHA-256 against the
hash recorded in the canonical manifest; the assets bundle sha and the
bootstrap EXPECTED_SHA256 anchor must match too.

Usage:
  python3 verify_xray_payload.py <xray-repo> <canonical-manifest.json>
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# mapping: repository_files top -> Xray repo top
# .github is deliberately NOT mapped: workflows and GitHub CI orchestration
# on the Xray consumer are host-owned. Verifying them byte-identically would
# create a self-reference (the workflow pins Rill's commit, which owns the
# manifest). Xray's own workflow checks out the pinned Rill commit and
# verifies the stable payload against that commit's canonical manifest.
TOP_TO_XRAY = {
    "rill_payload": "rill_payload",
    "scripts": "scripts",
    "systemd": "systemd",
    "assets": "assets",
}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(xray: Path, manifest: Path, allow_missing_github: bool = True,
           expected_canonical_digest: str | None = None) -> int:
    m = json.loads(manifest.read_text())
    assert m.get("schemaVersion") == 1, "unsupported manifest schema"
    assert isinstance(m.get("canonicalDigest"), str), "canonical digest missing"
    if expected_canonical_digest is not None:
        assert m["canonicalDigest"] == expected_canonical_digest, (
            "canonical digest does not match the Xray pin"
        )
    # No sourceCommit in the manifest: provenance is anchored by the consumer
    # workflow's RILL_CANONICAL_COMMIT pin, not embedded in-file.
    checked = 0
    for rel, expected in m["files"].items():
        if not rel.startswith("repository_files/"):
            continue  # source/* entries are Rill-side only
        sub = rel[len("repository_files/"):]
        top, rest = sub.split("/", 1)
        if top not in TOP_TO_XRAY:
            print(f"skip {rel}: no consumer mapping for top '{top}'")
            continue
        xray_path = xray / TOP_TO_XRAY[top] / rest
        if not xray_path.exists():
            # .github mirror is optional on a bare clone.
            if top == ".github" and allow_missing_github:
                continue
            print(f"MISSING {rel} -> {xray_path}", file=sys.stderr)
            return 1
        if sha(xray_path) != expected:
            print(f"DRIFT {rel} (sha {sha(xray_path)} != {expected})", file=sys.stderr)
            return 1
        checked += 1

    # Bundle + bootstrap pin.
    bundle = xray / "assets" / (ASSETS_BUNDLE := "rill-xray-agent-xray-bundle.tar.gz")
    if not bundle.is_file():
        print(f"MISSING bundle {bundle}", file=sys.stderr)
        return 1
    bundle_sha = sha(bundle)
    if bundle_sha != m["bundleSha256"]:
        print(f"DRIFT bundle {bundle_sha} != {m['bundleSha256']}", file=sys.stderr)
        return 1
    bootstrap = xray / "scripts" / "rill_xray_agent_bootstrap.sh"
    text = bootstrap.read_text()
    match = re.search(r"^EXPECTED_SHA256=([0-9a-f]{64})$", text, flags=re.M)
    if not match or match.group(1) != m["bundleSha256"]:
        print(
            f"MISSING/DRIFT bootstrap EXPECTED_SHA256 on {xray}",
            file=sys.stderr,
        )
        return 1
    print(
        f"xray payload matches canonical manifest {manifest.parent.name}/"
        f"{manifest.name}: {checked} files, "
        f"bundle {bundle_sha[:12]}"
    )
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("xray_repo", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--expected-canonical-digest")
    args = parser.parse_args()
    raise SystemExit(verify(args.xray_repo.resolve(), args.manifest.resolve(),
                            expected_canonical_digest=args.expected_canonical_digest))
