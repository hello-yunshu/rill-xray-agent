#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
errors: list[str] = []
required = [
    "README.md",
    "VERSION",
    "LICENSE-MIT",
    "config/default.json",
    "python/rill_xray_agent/runtime_service.py",
    "bin/rill-xray-agent",
    "systemd/rill-xray-agent-runtime.service",
    "integrations/xray_bash_onekey/UPSTREAM_ANCHOR.json",
    "integrations/xray_bash_onekey/tools/apply_to_repo.py",
    "integrations/xray_bash_onekey/repository_files/scripts/rill_xray_agent_manager.sh",
    "integrations/xray_bash_onekey/assets/rill-xray-agent-xray-bundle.tar.gz",
    "PROJECT_MEMORY/project_state.json",
    "PROJECT_MEMORY/history_chain.json",
    ".github/workflows/source-gates.yml",
]
for rel in required:
    path = root / rel
    if not path.is_file() or path.is_symlink() or path.stat().st_size == 0:
        errors.append(f"missing/unsafe {rel}")
for path in root.rglob("*"):
    rel = path.relative_to(root)
    if rel.parts and rel.parts[0] == ".git":
        continue
    if path.is_symlink():
        errors.append(f"symlink forbidden: {rel}")
    if any(part in {".git", "__pycache__", ".pytest_cache", "target"} for part in rel.parts):
        errors.append(f"cache/build path forbidden: {rel}")
    forbidden = "i" + "d" + "l" + "e" + "l" + "e" + "o"
    if forbidden in rel.as_posix().lower():
        errors.append(f"forbidden identity in path: {rel}")
    if path.is_file() and path.name != "PACKAGE_SHA256SUMS":
        if forbidden in path.read_text(errors="ignore").lower():
            errors.append(f"forbidden identity in content: {rel}")
if (root / "Cargo.lock").exists():
    errors.append("unreviewed Cargo.lock forbidden")
if errors:
    print("\n".join(errors))
    sys.exit(1)
print(f"package tree passed ({len(required)} required paths; identity clean)")