#!/usr/bin/env python3
from pathlib import Path
import json
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
with tarfile.open(integration / "assets/rill-xray-agent-xray-bundle.tar.gz", "r:gz") as archive:
    for member in archive.getmembers():
        assert not member.issym() and not member.islnk()
        assert not member.name.startswith("/")
        assert ".." not in Path(member.name).parts
print(f"xray integration passed ({len(required)} required paths)")
