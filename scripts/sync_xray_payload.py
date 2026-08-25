#!/usr/bin/env python3
"""Sync Rill source (config + Python payload) into the Xray integration
payload, rebuild the bundle, and pin the bootstrap SHA. Reproducible output:
fixed mtime, sorted entries. config/default.json mirrors byte-identically
into rill_payload/config/default.json; stale payload config entries fail.
Integration systemd units are intentionally NOT mirrored from standalone."""
import hashlib
import io
import shutil
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG = ROOT / 'config' / 'default.json'
SOURCE_PROVENANCE = ROOT / 'PROVENANCE' / 'upstream.json'
SOURCE_PY = ROOT / 'python' / 'rill_xray_agent'
REPO_FILES = ROOT / 'integrations' / 'xray_bash_onekey' / 'repository_files'
PAYLOAD_CONFIG_DIR = REPO_FILES / 'rill_payload' / 'config'
PAYLOAD_CONFIG = PAYLOAD_CONFIG_DIR / 'default.json'
PAYLOAD_PROVENANCE_DIR = REPO_FILES / 'rill_payload' / 'PROVENANCE'
PAYLOAD_PROVENANCE = PAYLOAD_PROVENANCE_DIR / 'upstream.json'
PAYLOAD_PY = REPO_FILES / 'rill_payload' / 'python' / 'rill_xray_agent'
ASSETS = ROOT / 'integrations' / 'xray_bash_onekey' / 'assets'
BOOTSTRAP = REPO_FILES / 'scripts' / 'rill_xray_agent_bootstrap.sh'
BUNDLE_NAME = 'rill-xray-agent-xray-bundle.tar.gz'
BUNDLE_TOPS = ('rill_payload', 'scripts', 'systemd')
BUNDLE_EXCLUDE = {'rill_xray_agent_bootstrap.sh'}


def sync_config() -> list[str]:
    """Mirror the root config/default.json into the canonical Xray payload.

    Byte-identical, deterministic, change-reported. The payload mirror must
    never silently diverge: any file left over from an earlier source state
    is a fail (not silently preserved).
    """
    if not SOURCE_CONFIG.is_file():
        raise SystemExit(f'missing source config: {SOURCE_CONFIG}')
    changed = []
    if not PAYLOAD_CONFIG.exists() or PAYLOAD_CONFIG.read_bytes() != SOURCE_CONFIG.read_bytes():
        PAYLOAD_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_CONFIG, PAYLOAD_CONFIG)
        changed.append('config: default.json')
    stale = [p.name for p in sorted(PAYLOAD_CONFIG_DIR.glob('*.json'))
             if p.name != 'default.json' and not (ROOT / 'config' / p.name).exists()]
    if stale:
        raise SystemExit(f'stale payload config entries (failing closed): {", ".join(stale)}')
    return changed


def sync_provenance() -> list[str]:
    """Ship the audited release identity with the installed payload."""
    if not SOURCE_PROVENANCE.is_file():
        raise SystemExit(f'missing source provenance: {SOURCE_PROVENANCE}')
    if (not PAYLOAD_PROVENANCE.exists()
            or PAYLOAD_PROVENANCE.read_bytes() != SOURCE_PROVENANCE.read_bytes()):
        PAYLOAD_PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SOURCE_PROVENANCE, PAYLOAD_PROVENANCE)
        return ['provenance: upstream.json']
    return []


def sync_payload() -> list[str]:
    changed = []
    PAYLOAD_PY.mkdir(parents=True, exist_ok=True)
    for src in sorted(SOURCE_PY.glob('*.py')):
        dst = PAYLOAD_PY / src.name
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            shutil.copy2(src, dst)
            changed.append(f'payload: {src.name}')
    for stale in sorted(PAYLOAD_PY.glob('*.py')):
        if not (SOURCE_PY / stale.name).exists():
            stale.unlink()
            changed.append(f'payload-remove: {stale.name}')
    return changed


def build_bundle() -> bytes:
    import gzip
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.GNU_FORMAT) as tar:
        for top in BUNDLE_TOPS:
            base = REPO_FILES / top
            files = sorted(p for p in base.rglob('*') if p.is_file()
                           and p.name not in BUNDLE_EXCLUDE
                           and not any(v in {'.git', '__pycache__'} for v in p.relative_to(base).parts))
            for p in files:
                rel = p.relative_to(base).as_posix()
                data = p.read_bytes()
                info = tarfile.TarInfo(f'{top}/{rel}')
                info.size = len(data)
                info.mtime = 0
                info.mode = p.stat().st_mode & 0o7777
                info.uid = info.gid = 0
                tar.addfile(info, io.BytesIO(data))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode='wb', compresslevel=9, mtime=0) as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


def pin_bundle() -> str:
    """The bundle embeds the bootstrap script whose EXPECTED_SHA256 references the
    bundle's own digest, so iterate to the fixed point where they agree."""
    import re
    for _ in range(16):
        blob = build_bundle()
        digest = hashlib.sha256(blob).hexdigest()
        text = BOOTSTRAP.read_text()
        current = re.search(r'^EXPECTED_SHA256=([0-9a-f]{64})$', text, flags=re.M)
        if current and current.group(1) == digest:
            break
        text, n = re.subn(r'^EXPECTED_SHA256=([0-9a-f]{64})$', f'EXPECTED_SHA256={digest}',
                          text, count=1, flags=re.M)
        if n != 1:
            raise SystemExit('bootstrap EXPECTED_SHA256 anchor not found')
        BOOTSTRAP.write_text(text)
    for path in (ASSETS / BUNDLE_NAME, REPO_FILES / 'assets' / BUNDLE_NAME):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    return digest


def main() -> None:
    changed = sync_config()
    changed += sync_provenance()
    changed += sync_payload()
    digest = pin_bundle()
    print('synced payload:')
    for c in changed:
        print('  ', c)
    print(f'bundle: {ASSETS / BUNDLE_NAME} -> {digest}')


if __name__ == '__main__':
    main()
