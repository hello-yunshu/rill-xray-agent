# Usage

Rill Xray Agent 0.1.0 is a local-first observation and decision-support agent
for Xray hosts. This document is the user-facing manual; the developer
integration workflow is covered in [Developer / integration](#developer--integration).

## Install / integration entry

On an Xray host running the Xray Bash Onekey project, the agent is delivered
through the Xray-tied bootstrap and installer:

```bash
bash scripts/rill_xray_agent_bootstrap.sh
```

After installation the following paths exist:

| Path | Purpose |
| --- | --- |
| `/etc/rill-xray-agent/config.json` | committed host config (installed from the canonical `default.json`) |
| `/etc/rill-xray-agent/scripts/` | manager, install, verify, uninstall, observe, bootstrap scripts |
| `/opt/rill-xray-agent/` | Runtime, Agent and CLI payload |
| `/etc/systemd/system/rill-xray-agent-*.{service,path,timer}` | systemd units |
| `/run/rill-xray-agent/runtime.sock` | Runtime socket (operator-facing) |
| `/run/rill-xray-agent/agent.sock` | Agent socket (restricted method set) |
| `/var/lib/rill-xray-agent-xray/status/xray-observation.json` | sanitized observation snapshot |

Integration entry from the Xray script: main menu item `9)` opens the Rill
submenu; non-interactive flags are `--rill-agent`, `--rill-agent-status`,
`--rill-agent-safe-disable`, `--rill-agent-verify` and
`--rill-agent-uninstall`.

## Status

```bash
rill-xray-agent --json status
```

Returns mode, Runtime/Agent service activity, route stage and the safety
flags (`routeAssistEnabled=false`, `boundedAutoAllowed=false`).

## Health

```bash
rill-xray-agent --json health
```

Runtime health including WAL / audit / recovery state. Either the CLI or the
manager route `rxa_health` can be used for live checks.

## Snapshot

```bash
rill-xray-agent --json snapshot
```

Current decision lifecycle snapshot (pending / completed / closed ledger
summaries and audit head).

## Modes

```bash
rill-xray-agent mode observe-only   # default
rill-xray-agent mode normal
rill-xray-agent mode safe-disabled
```

Mode switching is a four-party transaction (config, Runtime WAL, systemd
units, observation snapshot) with rollback on any failure. `routeAssistEnabled`
stays false in every mode. In `safe-disabled` the Agent and observation units
are stopped; the Runtime stays up for live verification.

## Verify

```bash
rill-xray-agent --json health && /etc/rill-xray-agent/scripts/rill_xray_agent_verify.sh
```

or from the Xray menu (`--rill-agent-verify`). Verification covers config
defaults, Runtime WAL mode vs config mode, per-mode unit states, observation
freshness and per-mode socket rules.

## Uninstall

```bash
--rill-agent-uninstall
```

Durable two-phase uninstall: `prepare` persists an intent file, `abort`
keeps the host intact with a persisted aborted marker, `commit` writes a
durable `committed` marker before the purge removes the Runtime, units and
payload.

## Safe-disabled

`rill-xray-agent mode safe-disabled` stops the Agent and observer while the
Runtime remains active so the runtime state can be verified live. The agent
socket is refused while present (stale inode must never pass); the runtime
socket still connects.

## Paths

See the table in [Install / integration entry](#install--integration-entry).
State and audit live under `/var/lib/rill-xray-agent-runtime` (owned by the
Runtime) and `/var/lib/rill-xray-agent-root/transactions` (root-owned
transactions). `/var/lib/rill-xray-agent-xray/status` holds the sanitized
observation snapshot.

## Known limitations

- Real bare-metal / VM qualification: **NOT RUN**. Docker-only qualification
  was completed; no real-host claim is made.
- Native Rust runtime is experimental and unsupported
  (`nativeRuntimeSupported=false`); the supported runtime is Portable Python.
- Public prompt orphan objects in upstream history are a known governance
  item (deferred by owner policy, not resolved).
- The agent never executes mode changes or Xray lifecycle actions beyond the
  explicit installed contract; configuration validation, reload, rollback and
  service lifecycle remain owned by the Xray host project.

## Developer / integration

For Xray repository integration, the `integrations/xray_bash_onekey/tools/`
tooling applies the canonical payload:

```bash
python3 /path/to/rill-xray-agent/integrations/xray_bash_onekey/tools/verify_repo.py .
python3 /path/to/rill-xray-agent/integrations/xray_bash_onekey/tools/apply_to_repo.py .
python3 /path/to/rill-xray-agent/integrations/xray_bash_onekey/tools/verify_repo.py . --post-integration
```

These are developer tools; end users do not run them on hosts.