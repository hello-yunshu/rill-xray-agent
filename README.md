# Rill Xray Agent

Rill Xray Agent is a local-first, fail-closed operational observation and decision-support agent for Xray management scripts. This package contains the actual Portable Runtime, restricted Agent, audit chain, state and transaction recovery, backup safety, systemd units, Xray host integration files, tests, release gates and one AI execution prompt.

## Safety defaults

- `observe-only` by default
- Route Assist disabled
- bounded automatic execution disabled
- no upload of Xray configuration or user secrets
- Xray remains the sole owner of configuration validation, reload, rollback and service lifecycle

## Verify locally

```bash
python3 scripts/verify_package_tree.py
python3 scripts/verify_package_sums.py
python3 scripts/verify_project_memory.py
python3 scripts/run_all_checks.py
```

## Create the repository

Extract the package, enter `rill-xray-agent`, initialize Git and push it to `hello-yunshu/rill-xray-agent`. Then create a clean Xray integration branch at the commit recorded in `integrations/xray_bash_onekey/UPSTREAM_ANCHOR.json`.

This is a complete source candidate, not a public release. Real-host systemd, Xray/Nginx/Fail2ban, ShellCheck and repository CI remain mandatory before a pre-release.
