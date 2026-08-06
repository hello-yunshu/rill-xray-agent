#!/usr/bin/env python3
from pathlib import Path
import hashlib
import sys

root = Path(__file__).resolve().parents[1]
sums = root / "PACKAGE_SHA256SUMS"
expected = {}
for line in sums.read_text().splitlines():
    digest, rel = line.split("  ", 1)
    expected[rel] = digest
actual = {
    path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in root.rglob("*")
    if path.is_file()
    and path != sums
    and not path.name.endswith(".pyc")
    and not any(part in {"__pycache__", ".pytest_cache", "target"} for part in path.relative_to(root).parts)
}
if expected != actual:
    print("missing/extra", sorted(set(expected) ^ set(actual))[:20])
    sys.exit(1)
print(f"package sums passed ({len(actual)})")
