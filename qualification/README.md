# 2026-08-09 R4 Docker-only qualification (frozen heads)

SHA pins and image digests; full run logs in this directory.

## Frozen heads
- Rill final HEAD: `0a0ab2bde9ffe2354aa3dc2db8e839fbea2e3a08`
- Xray final HEAD: `6233c3f5db303f8b0ad8e561ad152e444893b2aa`

## Docker images
| image | digest | distro | PID1 |
|---|---|---|---|
| rill-gates:local | 1d0cfdd683abac3aa7375d7bc282f8adcb7a3d13c1177fe26b072fd74193bb88 | python:3.12-bookworm (Debian 12) | n/a (source gates) |
| rill-debian-systemd:r4 | 10453735f21c678e27785b4623fe096548372289f6b9a99757829762ab1850c5 | Debian 12 (bookworm) | systemd 252 |
| rill-ubuntu-systemd:r4 | 9ef5189be24f0850c1a58c9fc99703aee1c5e8dcdecab4ad973 | Ubuntu 24.04 (noble) | systemd 255 |

uname -m: arm64 (OrbStack, Darwin host). Docker Server 29.4.0.

## Results
- Docker source qualification (fresh non-root container, frozen Rill tree, full
  gate set incl. shellcheck + ResourceWarning unittest suite): PASS
- Debian 12 systemd PID1 (mode lifecycle 6-step, RuntimeDirectory retention,
  runtime.sock/agent.sock live probes, durable uninstall intent): 39/39 PASS
- Ubuntu 24.04 systemd PID1 (same suite): 39/39 PASS
- Five-mode matrix (fresh container per mode; install -> agent install ->
  mode lifecycle -> formal verify -> standalone two-phase uninstall ->
  cleanup verify -> destroy): PASS each (xtls_only, reality_nginx,
  ws_grpc_xhttp, tls, reality)
- Fresh 20/20 (RILL_GATE_ORDER_SEED=1..20, fresh container per round, frozen
  Rill source, full run_all_checks + explicit unittest list): 20/20 PASS
- Deterministic build (fresh container A/B, full sync->manifest->sums pipeline
  from frozen source): identical bundle/manifest/sums/bootstrap/uninstall bytes
  (see deterministic-A.sha256 vs deterministic-B.sha256)

## Logs
- round-01..20.log              - fresh 20/20 rounds
- five-mode-*.log              - per-mode install+lifecycle runs
- (PID1 details per run command in repo harness; uninstall fault matrix logs
  kept operationally, not checked into the public tree)