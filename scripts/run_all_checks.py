#!/usr/bin/env python3
from __future__ import annotations

import os
import random
import shutil
import signal
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = dict(os.environ)
ENV["PYTHONDONTWRITEBYTECODE"] = "1"
ENV["PYTHONHASHSEED"] = "0"
ENV["PYTHONPATH"] = str(ROOT / "python") + ((":" + ENV["PYTHONPATH"]) if ENV.get("PYTHONPATH") else "")

commands = [
    ([sys.executable, "scripts/validate_schemas.py"], 30),
    ([sys.executable, "scripts/run_python_tests.py"], 180),
    ([sys.executable, "scripts/verify_xray_integration.py"], 90),
    ([sys.executable, "scripts/rust_static_sanity.py"], 30),
    ([sys.executable, "scripts/verify_no_build_gate.py", "--root", "."], 30),
    ([sys.executable, "scripts/verify_project_memory.py"], 30),
    ([sys.executable, "scripts/verify_package_tree.py"], 30),
    ([sys.executable, "scripts/verify_package_sums.py"], 30),
    ([sys.executable, "scripts/build_canonical_manifest.py", "--check"], 30),
]
seed = int(os.environ.get("RILL_GATE_ORDER_SEED", "0"))
head = commands[:-1]
if seed:
    random.Random(seed).shuffle(head)
commands = head + [commands[-1]]


def cleanup() -> None:
    for path in list(ROOT.rglob("__pycache__")):
        if path.exists():
            shutil.rmtree(path)
    for path in list(ROOT.rglob("*.pyc")):
        path.unlink(missing_ok=True)


for command, timeout in commands:
    print("+", " ".join(command), f"(timeout={timeout}s)", flush=True)
    process = subprocess.Popen(command, cwd=ROOT, env=ENV, start_new_session=True)
    try:
        returncode = process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=3)
        raise SystemExit(124)
    cleanup()
    if returncode:
        raise SystemExit(returncode)
print(f"all source/process gates passed; seed={seed}; real-host gates remain open")
