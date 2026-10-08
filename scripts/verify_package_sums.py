#!/usr/bin/env python3
from pathlib import Path
import hashlib

root = Path(__file__).resolve().parents[1]
sums = root / "PACKAGE_SHA256SUMS"


def content_digest(raw: bytes) -> str:
    """Hash text consistently across CRLF and LF checkouts; preserve binaries."""
    if b"\0" not in raw:
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def verify() -> int:
    expected = {}
    for line in sums.read_text().splitlines():
        digest, rel = line.split("  ", 1)
        expected[rel] = digest
    actual = {
        path.relative_to(root).as_posix(): content_digest(path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
        and path != sums
        and not path.name.endswith(".pyc")
        and not (path.relative_to(root).parts and path.relative_to(root).parts[0] == ".git")
        and not any(part in {"__pycache__", ".pytest_cache", "target"} for part in path.relative_to(root).parts)
    }
    if expected != actual:
        print("missing/extra", sorted(set(expected) ^ set(actual))[:20])
        return 1
    print(f"package sums passed ({len(actual)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(verify())
