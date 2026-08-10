#!/usr/bin/env python3
"""Build or verify the canonical cross-repo sync manifest.

Single source of truth is this Rill repository. The manifest pins every
payload file Xray consumes (payload mirrors, repository_files scripts,
systemd units, bundle copies) plus the reproducible bundle digest, so a
consumer (Xray CI) can byte-verify its installed tree against a pinned
Rill commit.

Run: python3 scripts/build_canonical_manifest.py          # (re)write manifest
     python3 scripts/build_canonical_manifest.py --check  # verify tree matches
"""
import argparse
import gzip
import hashlib
import io
import json
import re
import subprocess
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "integrations" / "xray_bash_onekey"
REPO_FILES = INTEGRATION / "repository_files"
ASSETS_DIR = INTEGRATION / "assets"
BUNDLE_NAME = "rill-xray-agent-xray-bundle.tar.gz"
MANIFEST = INTEGRATION / "CANONICAL_MANIFEST.json"
BUNDLE_EXCLUDE = {"rill_xray_agent_bootstrap.sh"}
BUNDLE_TOPS = ("rill_payload", "scripts", "systemd")

# Top-level source dirs that must be byte-identical to their payload mirrors.
MIRROR_PAIRS = [
    (ROOT / "python/rill_xray_agent", REPO_FILES / "rill_payload/python/rill_xray_agent"),
    (ROOT / "bin", REPO_FILES / "rill_payload/bin"),
    (ROOT / "config", REPO_FILES / "rill_payload/config"),
    (ROOT / "systemd", REPO_FILES / "rill_payload/systemd"),
]

# Top-level files pinned as-is (schema/version metadata, no payload mirror).
PINNED_SOURCES = [
    ROOT / "schemas",
    ROOT / "VERSION",
]


def sha_bytes(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def subprocess_check(argv: list[str]) -> str:
    return subprocess.run(argv, cwd=ROOT, check=True, capture_output=True, text=True).stdout.strip()


def build_bundle() -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for top in BUNDLE_TOPS:
            base = REPO_FILES / top
            files = sorted(
                p for p in base.rglob("*")
                if p.is_file()
                and p.name not in BUNDLE_EXCLUDE
                and ".git" not in p.relative_to(base).parts
                and "__pycache__" not in p.relative_to(base).parts
            )
            for p in files:
                rel = p.relative_to(base).as_posix()
                data = p.read_bytes()
                info = tarfile.TarInfo(f"{top}/{rel}")
                info.size = len(data)
                info.mtime = 0
                info.mode = p.stat().st_mode & 0o7777
                info.uid = info.gid = 0
                tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", compresslevel=9, mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def hash_tree(root: Path, key_prefix: str, out: dict[str, str]) -> None:
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if "__pycache__" in p.parts or p.name.endswith(".pyc"):
            continue
        out[f"{key_prefix}{p.relative_to(root).as_posix()}"] = sha_bytes(p.read_bytes())


def compute_manifest() -> dict:
    files: dict[str, str] = {}
    # Mirror sources first (authoritative originals).
    for src, dst in MIRROR_PAIRS:
        if not src.is_dir():
            raise SystemExit(f"missing source dir {src}")
        if not dst.is_dir():
            raise SystemExit(f"missing mirror dir {dst}")
        src_map: dict[str, str] = {}
        hash_tree(src, "", src_map)
        dst_map: dict[str, str] = {}
        hash_tree(dst, "", dst_map)
        if src_map != dst_map:
            drift = {k for k in set(src_map) | set(dst_map) if src_map.get(k) != dst_map.get(k)}
            raise SystemExit(f"mirror drift {src} vs {dst}: {sorted(drift)[:10]}")
        for k, v in src_map.items():
            files[f"source/{src.relative_to(ROOT).as_posix()}/{k}"] = v
    for pinned in PINNED_SOURCES:
        if pinned.is_dir():
            hash_tree(pinned, f"source/{pinned.relative_to(ROOT).as_posix()}/", files)
        else:
            files[f"source/{pinned.relative_to(ROOT).as_posix()}"] = sha_bytes(pinned.read_bytes())
    # repository_files payload/scripts/systemd/assets (+.github for the mirror).
    # .github is deliberately EXCLUDED from the canonical byte scope: it holds
    # the Xray-consumer workflow whose RILL_CANONICAL_COMMIT pin would make the
    # manifest self-referential (pinning the commit that contains the pin).
    # Xray host-owned CI orchestration is verified by the consuming workflow
    # against the manifest, never mirrored back as canonical payload.
    for top in ("rill_payload", "scripts", "systemd", "assets"):
        base = REPO_FILES / top
        if not base.exists():
            continue
        hash_tree(base, f"repository_files/{top}/", files)
    bundle = build_bundle()
    return {
        "schemaVersion": 1,
        # No sourceCommit here: provenance is anchored externally by the Xray
        # consumer workflow's RILL_CANONICAL_COMMIT pin (the commit that owns
        # this manifest). Embedding it would be stale or self-referential.
        "bundleSha256": sha_bytes(bundle),
        "files": dict(sorted(files.items())),
    }


def manifest_entry_path(rel: str) -> Path:
    if rel.startswith("source/"):
        return ROOT / rel[len("source/"):]
    if rel.startswith("repository_files/"):
        return REPO_FILES / rel[len("repository_files/"):]
    raise SystemExit(f"unexpected manifest key {rel}")


def check_bootstrap_pin(bundle_sha: str) -> None:
    bootstrap = REPO_FILES / "scripts/rill_xray_agent_bootstrap.sh"
    text = bootstrap.read_text()
    match = re.search(r"^EXPECTED_SHA256=([0-9a-f]{64})$", text, flags=re.M)
    if not match:
        raise SystemExit("bootstrap EXPECTED_SHA256 missing")
    if match.group(1) != bundle_sha:
        raise SystemExit("bootstrap EXPECTED_SHA256 != canonical bundleSha256")


def check_bundle_copies(bundle_sha: str) -> None:
    copies = [
        ASSETS_DIR / BUNDLE_NAME,
        REPO_FILES / "assets" / BUNDLE_NAME,
    ]
    blobs = []
    for path in copies:
        if not path.is_file():
            raise SystemExit(f"bundle missing: {path}")
        blobs.append(path.read_bytes())
    if blobs[0] != blobs[1]:
        raise SystemExit("two bundle copies differ (assets/ vs repository_files/assets/)")
    if sha_bytes(blobs[0]) != bundle_sha:
        raise SystemExit("bundle sha != canonical manifest bundleSha256")


def verify() -> int:
    if not MANIFEST.is_file():
        raise SystemExit(f"missing {MANIFEST}")
    committed = json.loads(MANIFEST.read_text())
    current = compute_manifest()
    drift = {k for k in set(committed["files"]) | set(current["files"])
             if committed["files"].get(k) != current["files"].get(k)}
    if drift:
        raise SystemExit(f"payload drift vs canonical manifest: {sorted(drift)[:10]}")
    if committed["bundleSha256"] != current["bundleSha256"]:
        raise SystemExit("bundle drift vs canonical manifest")
    check_bundle_copies(committed["bundleSha256"])
    check_bootstrap_pin(committed["bundleSha256"])
    print(f"canonical payload sync passed: {len(committed['files'])} files, "
          f"bundle {committed['bundleSha256'][:12]}")
    return 0


def build() -> None:
    manifest = compute_manifest()
    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    print(f"wrote {MANIFEST} (files={len(manifest['files'])}, "
          f"bundle={manifest['bundleSha256'][:12]})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        raise SystemExit(verify())
    build()