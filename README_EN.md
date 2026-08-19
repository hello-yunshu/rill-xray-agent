# RillML Xray Agent 0.1.0

> A local-first, fail-closed operational observation and decision-support agent for Xray management scripts.
> Ships the portable Runtime, restricted Agent, audit chain, state and transaction recovery, backup safety, systemd units, Xray host integration files, tests and release gates.
>
> Short name: **Rill Xray Agent**.

[中文](./README.md) · [Docs](./docs/)

## What it is

RillML Xray Agent (short name: Rill Xray Agent) is a local observation and decision-support agent for Xray management scripts. It does not take ownership of Xray configuration; it provides observation, audit, and restricted decision-support so you get traceable, rollback-capable, auditable operation records on an Xray host.

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

CLI examples (default socket `/run/rill-xray-agent/runtime.sock`):

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

**Rill Xray Agent 0.1.0** (stable).

- Portable Python Runtime is the supported runtime; Native Rust remains experimental / unsupported (`nativeRuntimeSupported=false`).
- Default `observe-only`; Route Assist OFF; bounded auto OFF; local-only.
- Docker qualification completed (fresh 20/20, Debian 12 / Ubuntu 24.04 systemd PID1, five-mode, deterministic A/B, bootstrap delivery).
- Real bare-metal / VM qualification: **NOT RUN** (deferred by owner release policy; not claimed as PASS).
- Known governance item: legacy public prompt orphan objects remain DEFERRED / STILL OPEN; they do not block 0.1.0.

## License

[MIT](./LICENSE-MIT)