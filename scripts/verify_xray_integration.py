#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import re
import subprocess
import tarfile

root = Path(__file__).resolve().parents[1]
integration = root / "integrations/xray_bash_onekey"
repository_files = integration / "repository_files"
anchor = json.loads((integration / "UPSTREAM_ANCHOR.json").read_text())
assert len(anchor["reviewedCommit"]) == 40
required = [
    "repository_files/scripts/rill_xray_agent_manager.sh",
    "repository_files/scripts/rill_xray_agent_install.sh",
    "repository_files/scripts/rill_xray_agent_verify.sh",
    "repository_files/scripts/rill_xray_agent_uninstall.sh",
    "repository_files/scripts/rill_xray_agent_observe.py",
    "repository_files/systemd/rill-xray-agent-runtime.service",
    "assets/rill-xray-agent-xray-bundle.tar.gz",
    "tools/apply_to_repo.py",
    "tools/verify_repo.py",
]
for rel in required:
    assert (integration / rel).is_file(), rel
for path in (repository_files / "scripts").glob("*.sh"):
    assert subprocess.run(["bash", "-n", str(path)]).returncode == 0, path

bundle_path = integration / "assets/rill-xray-agent-xray-bundle.tar.gz"
with tarfile.open(bundle_path, "r:gz") as archive:
    for member in archive.getmembers():
        assert not member.issym() and not member.islnk()
        assert not member.name.startswith("/")
        assert ".." not in Path(member.name).parts

source_py = root / "python/rill_xray_agent"
payload_py = repository_files / "rill_payload/python/rill_xray_agent"
source_files = {p.name: p.read_bytes() for p in source_py.glob("*.py") if p.name.endswith(".py")}
for name, blob in source_files.items():
    payload_file = payload_py / name
    assert payload_file.is_file(), f"payload missing {name}"
    assert payload_file.read_bytes() == blob, f"payload drift: {name}"
for p in payload_py.glob("*.py"):
    assert p.name in source_files, f"stale payload file {p.name}"

config_src = root / "config/default.json"
config_dst = repository_files / "rill_payload/config/default.json"
assert config_dst.is_file(), "payload config missing"
assert config_dst.read_bytes() == config_src.read_bytes(), "payload config drift: default.json"

expected_re = re.compile(r"^EXPECTED_SHA256=([0-9a-f]{64})$", re.M)
bootstrap = (repository_files / "scripts/rill_xray_agent_bootstrap.sh").read_text()
match = expected_re.search(bootstrap)
assert match, "bootstrap EXPECTED_SHA256 missing"
assert hashlib.sha256(bundle_path.read_bytes()).hexdigest() == match.group(1), "bundle sha != bootstrap EXPECTED_SHA256"

init_blob = (source_py / "__init__.py").read_text()
m_version = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init_blob)
assert m_version, "no package __version__"
version = (root / "VERSION").read_text().strip()
assert version == m_version.group(1), f"VERSION {version} != __version__"
candidate = json.loads((repository_files / "rill_payload/config/default.json").read_text())["candidate"]
assert candidate == m_version.group(1), f"payload candidate {candidate} != {m_version.group(1)}"

with tarfile.open(bundle_path, "r:gz") as archive:
    names = {member.name for member in archive.getmembers()}
tops = {n.split("/", 1)[0] for n in names}
assert tops == {"rill_payload", "scripts", "systemd"}, tops
for top in ("rill_payload", "scripts", "systemd"):
    base = repository_files / top
    expected = {f"{top}/{p.relative_to(base).as_posix()}" for p in base.rglob("*") if p.is_file()
                and p.name != "rill_xray_agent_bootstrap.sh"}
    missing = expected - names
    assert not missing, f"bundle missing {sorted(missing)[:5]}"

print(f"xray integration passed ({len(required)} required paths; source/payload/bundle/version drift-free)")