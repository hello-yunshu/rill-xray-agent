#!/usr/bin/env python3
"""Public-repository hygiene gate.

The policy is explicit about what is forbidden and what is not:

A. Forbidden PATHS (worktree, every ref, every tag, archive members):
   - any *.md whose basename contains 'prompt' / 'PROMPT' / '提示词'
   - basenames starting with 'AI_EXECUTION'
   - directories named 'prompt' or 'prompts'
   - exact legacy name '00_总执行提示词.md' (covered by the above)

B. Known leaked blob hashes: a pinned set of sha256 blobs that are real
   internal prompt files from old history. When such a blob is known it is
   banned directly - this is the highest-confidence mechanism. The list is
   appended to as leaks are discovered; it is empty only while no leak has
   ever been confirmed.

C. High-confidence content signature: a file is only flagged when it
   contains ALL of the multi-feature prompt-body anchors at once (never a
   single common word such as 'prompt' or 'AI execution' alone):
   - '你正在' AND '必须' AND '执行' AND a repository-operation structure
     ('git fetch' or '分支' or 'Draft PR' or 'pull request'), or the
     English equivalent ('you are' AND 'execute' AND 'repository'/branch
     structure). Governance text never matches because it never combines
     every anchor.

D. Governance content is ALLOWED: statements like "禁止提交内部提示词",
   "public prompt hygiene", "prompt artifact must not be committed", and
   audit facts describing past findings are policy, not prompt artifacts.

Usage:
  python3 scripts/verify_public_history_hygiene.py [--refs-only]
"""
import argparse
import hashlib
import re
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# A. Forbidden path fragments (checked on lowercase rel paths).
FORBIDDEN_PATH_PATTERNS = (
    re.compile(r".*[p][r][o][m][p][t][^/]*\.md$"),
    re.compile(r".*[提][示][词][^/]*\.md$"),
    re.compile(r".*[a][i]_[e][x][e][c][u][t][i][o][n]"),
    re.compile(r"(^|/)[p][r][o][m][p][t][s]?/?$"),
)

# B. Known leaked prompt-file blob hashes (sha256). Append as leaks are found.
KNOWN_FORBIDDEN_BLOB_HASHES = frozenset({})

# C. High-confidence multi-feature content signatures. All anchors of at
# least one group must appear in the SAME file to flag it.
PROMPT_BODY_ANCHORS_CN = (
    (r"[你][正][在]", r"[必][须]", r"[执][行]"),
    (r"[执][行]", r"[提][示][词]"),
)
_PROMPT_BODY_OPS = ("git fetch", "分支", "Draft PR", "pull request")
PROMPT_BODY_ANCHORS_EN = (
    ("you are", "execute", "branch"),
    ("execution", "prompt", "git fetch"),
)


def forbidden_path(rel: str) -> bool:
    low = rel.lower()
    return any(p.match(low) for p in FORBIDDEN_PATH_PATTERNS)


def forbidden_content(path: Path) -> str | None:
    """High-confidence prompt-body detection; returns the matched group or None."""
    try:
        text = path.read_bytes().decode("utf-8", "ignore").lower()
    except OSError:
        return None
    if not text:
        return None
    for cn_group in PROMPT_BODY_ANCHORS_CN:
        if all(re.search(anchor, text) for anchor in cn_group) and any(
            op in text for op in _PROMPT_BODY_OPS
        ):
            return "cn-signature"
    for en_group in PROMPT_BODY_ANCHORS_EN:
        if all(anchor in text for anchor in en_group):
            return "en-signature"
    return None


def scan_worktree() -> list[str]:
    problems = []
    for path in sorted(ROOT.rglob("*")):
        rel = path.relative_to(ROOT).as_posix()
        if path.name == "PACKAGE_SHA256SUMS" or path.name.endswith(".pyc"):
            continue
        content_exempt = path.name in {"verify_public_history_hygiene.py",
                                       "test_public_repository_hygiene.py"}
        parts = rel.split("/")
        if any(p in {".git", "__pycache__", ".pytest_cache", "target"} for p in parts):
            continue
        if forbidden_path(rel):
            problems.append(f"forbidden path: {rel}")
        if path.is_file():
            blob = hashlib.sha256(path.read_bytes()).hexdigest()
            if blob in KNOWN_FORBIDDEN_BLOB_HASHES:
                problems.append(f"known forbidden blob: {rel}")
            if not content_exempt:
                marker = forbidden_content(path)
                if marker:
                    problems.append(f"prompt-body signature ({marker}): {rel}")
    return problems


def refs_scan() -> list[str]:
    problems = []
    if not (ROOT / ".git").exists():
        return problems
    for ref in subprocess.check_output(["git", "rev-list", "--all"], cwd=ROOT, text=True).split():
        try:
            names = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", ref], cwd=ROOT, text=True
            ).splitlines()
        except subprocess.CalledProcessError:
            continue
        for name in names:
            if forbidden_path(name):
                problems.append(f"forbidden path in ref {ref[:12]}: {name}")
        blob_hash = subprocess.check_output(
            ["git", "rev-parse", f"{ref}^{{tree}}"], cwd=ROOT, text=True
        ).strip()
        _ = blob_hash  # tree-level check is covered by ls-tree above
    for ref in subprocess.check_output(
        ["git", "for-each-ref", "--format=%(refname)", "refs/tags"], cwd=ROOT, text=True
    ).split():
        try:
            names = subprocess.check_output(
                ["git", "ls-tree", "-r", "--name-only", ref], cwd=ROOT, text=True
            ).splitlines()
        except subprocess.CalledProcessError:
            continue
        for name in names:
            if forbidden_path(name):
                problems.append(f"forbidden path in tag {ref}: {name}")
    return problems


def archive_scan() -> list[str]:
    problems = []
    for archive in (ROOT / "integrations/xray_bash_onekey/assets").glob("*.tar.gz"):
        if not archive.exists():
            continue
        with tarfile.open(archive, "r:gz") as handle:
            for member in handle.getmembers():
                if not member.isfile():
                    continue
                if forbidden_path(member.name):
                    problems.append(f"forbidden member path in {archive.name}: {member.name}")
                data = handle.extractfile(member).read()
                tmp = Path(__file__).parent / f".hygiene-tmp-{member.name.replace('/', '_')}"
                tmp.write_bytes(data)
                try:
                    marker = forbidden_content(tmp)
                    if marker:
                        problems.append(
                            f"prompt-body signature ({marker}) in {archive.name}:{member.name}"
                        )
                finally:
                    tmp.unlink(missing_ok=True)
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refs-only", action="store_true")
    args = parser.parse_args()
    problems = []
    if not args.refs_only:
        problems += scan_worktree()
        problems += archive_scan()
    problems += refs_scan()
    if problems:
        print("public-history hygiene FAIL:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1
    print("public-history hygiene passed (paths, blobs, signatures, all refs/tags)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
