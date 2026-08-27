#!/usr/bin/env python3
"""Remote RillML stable-index consumer gate (real network, real artifact).

Spec §45 / §46: this gate is the *remote* counterpart to the offline unit
tests. It runs inside GitHub Actions and genuinely:

  1. fetches the audited immutable ``v1.5.3/stable-index.json``,
  2. verifies the Ed25519 signature (pure stdlib verifier),
  3. asserts schema v3 + channel stable,
  4. resolves the runner's Linux x86_64 GNU (or musl in Alpine) artifact,
  5. downloads the REAL release binary,
  6. re-verifies size + SHA-256 from the signed index,
  7. executes a controlled lightweight probe.

Nothing is compiled here, ever (§1/§73). The only trust root is the signed
index; HTTPS transport is defence-in-depth, never a signature substitute.

``--expect-libc gnu|musl`` asserts the detected host ABI so the GNU and musl
matrix entries genuinely exercise the intended selection path (an Alpine
runner that accidentally reports gnu would fail the gate instead of passing).

Exit 0 with a structured JSON summary on success; non-zero otherwise.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))

from rill_xray_agent.rillml_artifact import (  # noqa: E402
    detect_platform,
    fetch_release_index,
    load_expected_release_version,
    parse_release_index,
    select_runtime_artifact,
    verify_artifact_file,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-libc", choices=("gnu", "musl"),
                        help="required detected host libc/ABI")
    parser.add_argument("--index-url", default=None,
                        help="override the stable-index URL (default: prod)")
    args = parser.parse_args()

    platform_ = detect_platform()
    expected_release = load_expected_release_version()
    summary = {"platform": platform_, "channel": "stable", "schemaVersion": None,
               "publisherKeyId": None, "runtimeApiVersion": None,
               "expectedReleaseVersion": expected_release,
               "selectedReleaseVersion": None, "artifact": None,
               "download": None, "probe": None}

    if args.expect_libc:
        if platform_["os"] != "linux" or platform_["libc"] != args.expect_libc:
            print(f"FAIL: expected libc={args.expect_libc} but host is "
                  f"os={platform_['os']} arch={platform_['arch']} "
                  f"libc={platform_['libc']}", file=sys.stderr)
            return 2

    text = fetch_release_index(args.index_url).decode("utf-8")
    payload = parse_release_index(text, channel="stable")
    if payload.get("schemaVersion") != 3:
        print(f"FAIL: stable-index schemaVersion={payload.get('schemaVersion')!r} "
              "!= 3", file=sys.stderr)
        return 2
    summary["schemaVersion"] = payload.get("schemaVersion")
    summary["publisherKeyId"] = payload.get("publisherKeyId")

    artifact = select_runtime_artifact(
        payload, target_os=platform_["os"], target_arch=platform_["arch"],
        libc=platform_["libc"], api_version=2, channel="stable")
    if artifact["version"] != expected_release:
        print(f"FAIL: selected stable release {artifact['version']!r} != "
              f"audited expected release {expected_release!r}", file=sys.stderr)
        return 2
    summary["selectedReleaseVersion"] = artifact["version"]
    summary["artifact"] = {
        "id": artifact["id"], "version": artifact["version"],
        "targetOs": artifact.get("targetOs"), "targetArch": artifact.get("targetArch"),
        "targetLibc": artifact.get("targetLibc"),
        "runtimeApiVersion": artifact.get("runtimeApiVersion"),
        "size": artifact["size"], "sha256": artifact["sha256"],
        "url": artifact["url"],
    }
    summary["runtimeApiVersion"] = artifact.get("runtimeApiVersion")

    # Download the REAL binary to a scratch root (never activates anything on
    # the runner; download_artifact re-verifies size + SHA from the index).
    with tempfile.TemporaryDirectory() as scratch:
        # Scratch root only; download_artifact re-verifies size + SHA from the
        # index (same code path install() uses). Nothing is activated here.
        dest = Path(scratch) / "staging"
        dest.mkdir(parents=True, exist_ok=True)
        from rill_xray_agent.rillml_artifact import download_artifact
        binary = download_artifact(artifact, dest)
        verify_artifact_file(artifact, binary)
        summary["download"] = {
            "path": str(binary),
            "sizeBytes": binary.stat().st_size,
            "sha256": verify_artifact_file(artifact, binary),
        }

        # Controlled lightweight probe (--help). A real startup probe would need
        # model/handler packs from the signed index (handshake path); the
        # lightweight probe proves execution + ABI compatibility for the gate.
        from rill_xray_agent.rillml_artifact import probe_runtime
        probe = probe_runtime(binary, expected_version=artifact["version"])
        summary["probe"] = probe

    print(json.dumps(summary, sort_keys=True, indent=2))
    ok = (summary["schemaVersion"] == 3
          and summary["runtimeApiVersion"] == 2
          and summary["download"]["sha256"] == artifact["sha256"]
          and summary["probe"].get("executes") is True)
    if not ok:
        print("FAIL: one or more consumer invariants did not hold", file=sys.stderr)
        return 1
    print(f"PASS: real stable-index v3 + {platform_['os']}/{platform_['arch']}/"
          f"{platform_['libc']} prebuilt {artifact['version']} consumed "
          f"({artifact['sha256'][:12]}…)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
