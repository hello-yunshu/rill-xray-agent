#!/usr/bin/env python3
from pathlib import Path
import json
from jsonschema import Draft202012Validator
r=Path(__file__).resolve().parents[1];n=0
for p in (r/'schemas').glob('*.json'):Draft202012Validator.check_schema(json.loads(p.read_text()));n+=1
print(f'schemas passed ({n})')
