#!/usr/bin/env python3
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parents[1] / "PROJECT_MEMORY"
chain = json.loads((root / "history_chain.json").read_text())
previous = "0" * 64
for item in chain["records"]:
    path = root / item["path"]
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != item["sha256"] or item["previousSha256"] != previous:
        raise SystemExit("memory chain invalid")
    previous = digest
state = json.loads((root / "project_state.json").read_text())
if state["latestHistorySha256"] != previous:
    raise SystemExit("memory head mismatch")
print(f"project memory passed ({len(chain['records'])} records)")
