#!/usr/bin/env python3
from __future__ import annotations
import os,random,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
mods=sorted(p.stem for p in (ROOT/'tests').glob('test_*.py'))
seed=int(os.environ.get('RILL_TEST_ORDER_SEED','0'))
if seed:random.Random(seed).shuffle(mods)
env=dict(os.environ);env['PYTHONDONTWRITEBYTECODE']='1';env['PYTHONPATH']=str(ROOT/'python')+((':'+env['PYTHONPATH']) if env.get('PYTHONPATH') else '')
count=0
for mod in mods:
 command=[sys.executable,'-m','unittest','-v',mod]
 print('+',' '.join(command),flush=True)
 with tempfile.NamedTemporaryFile(prefix=f'{mod}.',suffix='.log',delete=False) as stream:
  log_path=Path(stream.name)
  try:
   result=subprocess.run(command,cwd=ROOT/'tests',env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=240)
  except subprocess.TimeoutExpired:
   stream.flush();print(log_path.read_text(errors='replace'),end='');raise
 print(log_path.read_text(errors='replace'),end='');log_path.unlink(missing_ok=True)
 if result.returncode:raise SystemExit(result.returncode)
 count+=1
print(f'isolated Python test modules passed ({count}; seed={seed})')
