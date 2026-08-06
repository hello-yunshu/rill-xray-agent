# Rill Xray Agent

> A local-first, fail-closed operational observation and decision-support agent for Xray management scripts.
> Ships the portable Runtime, restricted Agent, audit chain, state and transaction recovery, backup safety, systemd units, Xray host integration files, tests and release gates.

[中文](./README.md) · [Docs](./docs/)

## What it is

Rill Xray Agent is a local observation and decision-support agent for Xray management scripts. It does not take ownership of Xray configuration; it provides observation, audit, and restricted decision-support so you get traceable, rollback-capable, auditable operation records on an Xray host.

## Safety defaults

- `observe-only` mode by default
- Route Assist disabled
- bounded automatic execution disabled
- no upload of Xray configuration, no collection of user secrets
- configuration validation, reload, rollback, and service lifecycle remain owned by the Xray host project

## Components

| Component | Description |
| --- | --- |
| `rill-xray-agent-runtime` | Owns local state, the audit chain and the decision lifecycle |
| `rill-xray-agent-agent` | Exposes a restricted method set over a Unix socket |
| Xray adapter | Emits only hashes, sizes, validation return codes and service states |
| Python CLI | Provides `status` / `health` / `metrics` / `config` / `snapshot` / `mode` / `inspect` commands |

## Getting started

Verify the source package locally:

```bash
python3 scripts/verify_package_tree.py
python3 scripts/verify_package_sums.py
python3 scripts/verify_project_memory.py
python3 scripts/run_all_checks.py
```

CLI examples (default socket `/run/rill-xray-agent/agent.sock`):

```bash
rill-xray-agent --json status
rill-xray-agent --json snapshot
rill-xray-agent mode observe-only
```

## Documentation

- [Architecture](./docs/ARCHITECTURE.md)
- [Security model](./docs/SECURITY_MODEL.md)
- [Usage](./docs/USAGE.md)
- [Release gates](./docs/RELEASE_GATES.md)
- [Project memory / state](./PROJECT_MEMORY/01_CURRENT_STATE.md)

## Status

Currently in **Alpha audit-repair phase** (baseline `v0.1.0-rc.1`). Release qualification has been revoked by the joint review: `preReleaseAllowed=false`, `sourceProcessQualified=false`, `stableAllowed=false`. A `v0.1.0-rc.2` tag and Pre-release are only allowed after all P0 items are closed, merged main CI is green and real PID1/systemd gates pass. Real-host systemd and Xray/Nginx/Fail2ban verification remain open items.

## License

[MIT](./LICENSE-MIT)