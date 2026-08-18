#!/usr/bin/env python3
"""No-downstream-build gate: RillML / rill-runtime must never be compiled here.

Spec §1 / §44 / §44.1 / §73: the downstream consumers (hello-yunshu/rill-xray-agent
and hello-yunshu/Xray_bash_onekey) are forbidden from compiling Rill-ML /
rill-runtime in any code path - install scripts, upgrade scripts, GitHub
Actions, Dockerfiles, fallback paths, packaging. The only delivery channel is
the signed stable-index + prebuilt release binary
(resolve/download/verify/probe/activate/fallback, never build).

This gate scans text files for forbidden *build commands* and fails closed on
the first match. It deliberately does not flag:

  * prose that merely names the tooling - the consumer docstring asserts "no
    Cargo / zigbuild happens here", which is the negation of a build and is
    explicitly allowed,
  * builds of rill-xray-agent's own crates (allowed, spec §44.1),
  * the gate's own source file (its purpose is scanning other files).

Forbidden command shapes are assembled from fragments so the gate can never
match its own source text even if it were scanned: cargo build/zigbuild of a
rill-ml workspace crate, cross-compile invocations targeting rill, in-place
model/handler pack creation, and docker builds that package a rill runtime.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SELF = Path(__file__).resolve()

_SP = r"\s+"


def _pat(*fragments: str) -> re.Pattern[str]:
    return re.compile("".join(fragments))


# Build-command shapes (not bare tool names): each requires a real invocation
# context so prose that only names a tool cannot trip the gate.
FORBIDDEN: tuple[re.Pattern[str], ...] = (
    # cargo build/zigbuild of the rill-ml workspace crates
    _pat(r"cargo", _SP, r"build", r"[^\n]*?(?:-p|--package)", _SP,
         r"rill-(?:ml|runtime|handler-api|runtime-protocol)\b"),
    _pat(r"cargo", _SP, r"zigbuild\b"),
    _pat(r"cargo", "-zigbuild\b"),
    # cross-compile invocations targeting a rill target
    _pat(r"\bcross", _SP, r"build", r"[^\n]*(?:rill|--target)"),
    # in-place model/handler pack creation (never built on user hosts)
    _pat(r"rill", "-pack", _SP, r"create\b"),
    _pat(r"cargo", _SP, r"run", r"[^\n]*rill-(?:pack|handler)\b"),
    # docker build that packages a rill runtime
    _pat(r"docker", _SP, r"build", r"[^\n]*(?:rill-runtime|rill-ml)\b"),
)

# The consumer asserts its own zero-build posture in a docstring; that
# negation line is explicitly allowed (and is the only known mention).
_ALLOW_NEGATION = re.compile(r"No Cargo / \S+zigbuild / cross-compile happens here")

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".tox", ".venv", ".eggs"}
_SKIP_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".webp", ".pdf", ".gz", ".tgz",
    ".tar", ".zip", ".woff", ".woff2", ".ttf", ".pyc", ".otf", ".eot",
}


def _iter_text_files(root: Path):
    root = root.resolve()
    for path in root.rglob("*"):
        # is_symlink() does not follow, so dangling links are skipped cleanly
        # (fail closed: the gate never scans an out-of-tree target).
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        if path.resolve() == SELF:
            continue  # the gate never scans itself
        rel = path.relative_to(root)
        if any(part in _SKIP_DIRS or part.endswith(".pyc") for part in rel.parts):
            continue
        if path.suffix.lower() in _SKIP_SUFFIXES:
            continue
        yield path


def _scan(root: Path) -> list[str]:
    hits: list[str] = []
    for path in _iter_text_files(root):
        try:
            with path.open("rb") as handle:
                head = handle.read(8192)
            if b"\x00" in head:
                continue  # binary file
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if _ALLOW_NEGATION.search(line):
                continue
            for pattern in FORBIDDEN:
                if pattern.search(line):
                    hits.append(f"{path}:{number}: {line.strip()[:160]}")
                    break
    return hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="fail closed if any downstream code path compiles RillML")
    parser.add_argument("--root", action="append", required=True,
                        help="repository root to scan (repeatable)")
    args = parser.parse_args(argv)

    failed = False
    for root in args.root:
        root_path = Path(root)
        if not root_path.is_dir():
            print(f"FAIL: scan root not found: {root_path}", file=sys.stderr)
            failed = True
            continue
        hits = _scan(root_path)
        if hits:
            failed = True
            print(f"FAIL: no-downstream-build gate violated under {root_path}",
                  file=sys.stderr)
            for hit in hits:
                print(f"  forbidden: {hit}", file=sys.stderr)
        else:
            print(f"PASS: no RillML build command under {root_path}")
    if failed:
        return 1
    print("no-downstream-build gate passed (RillML is consumed, never compiled)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
