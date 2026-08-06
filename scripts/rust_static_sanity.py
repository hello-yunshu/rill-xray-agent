#!/usr/bin/env python3
from pathlib import Path
import sys
r=Path(__file__).resolve().parents[1];f=list(r.glob('crates/**/src/*.rs'));errors=[]
for p in f:
 t=p.read_text()
 if 'unsafe {' in t:errors.append(str(p))
for x in ['crates/rill-xray-agent-runtime/src/main.rs','crates/rill-xray-agent-agent/src/main.rs']:
 t=(r/x).read_text()
 if 'set_read_timeout' not in t or 'thread::spawn' not in t:errors.append(x)
for manifest in r.glob('crates/*/Cargo.toml'):
 if 'publish=false' not in manifest.read_text().replace(' ',''):
  errors.append(f'experimental crate is publishable: {manifest}')
if errors:print(errors);sys.exit(1)
print(f'Rust experimental source sanity passed ({len(f)} files; publish=false; NOT compiled or supported)')
