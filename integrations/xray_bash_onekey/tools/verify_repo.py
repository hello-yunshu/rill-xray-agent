#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path

EXPECTED = "e3ba5d7474498fbb556b0cae741a629ebb3bf1cd"
parser = argparse.ArgumentParser()
parser.add_argument("repo", type=Path)
parser.add_argument("--post-integration", action="store_true")
args = parser.parse_args()
repo = args.repo.resolve()
head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
text = (repo / "install.sh").read_text()
if not args.post_integration:
    assert head == EXPECTED
    assert "menu_read menu_num 8" in text
    assert "RILL_XRAY_AGENT_INTEGRATION_SCHEMA" not in text
else:
    for token in (
        "RILL_XRAY_AGENT_INTEGRATION_SCHEMA=1",
        'menu_item 9 "Rill Xray Agent"',
        "9) rxa_menu ;;",
        "--rill-agent-status",
        "--rill-agent-safe-disable",
        "--rill-agent-verify",
        "--rill-agent-uninstall",
    ):
        assert token in text, token
print(json.dumps({"ok": True, "head": head, "postIntegration": args.post_integration}, sort_keys=True))
