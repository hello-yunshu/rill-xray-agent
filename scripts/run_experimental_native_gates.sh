#!/usr/bin/env bash
set -euo pipefail
command -v cargo >/dev/null || { echo 'cargo required' >&2; exit 2; }
cargo fmt --all --check
cargo check --workspace --all-targets
cargo test --workspace --all-targets
