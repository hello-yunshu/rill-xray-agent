#!/usr/bin/env python3
from pathlib import Path
import stat,sys,zipfile
r=Path(sys.argv[1]).resolve();out=Path(sys.argv[2]);epoch=(2026,8,4,0,0,0)
with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
 for p in sorted(x for x in r.rglob('*') if x.is_file() and not x.name.endswith('.pyc') and not any(v in {'.git','__pycache__','.pytest_cache','target'} for v in x.relative_to(r).parts)):
  i=zipfile.ZipInfo(f'{r.name}/{p.relative_to(r).as_posix()}',epoch);i.external_attr=((stat.S_IFREG|stat.S_IMODE(p.stat().st_mode))&0xffff)<<16;i.create_system=3;i.compress_type=zipfile.ZIP_DEFLATED;z.writestr(i,p.read_bytes(),compress_type=zipfile.ZIP_DEFLATED,compresslevel=9)
