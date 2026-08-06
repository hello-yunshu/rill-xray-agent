# Xray_bash_onekey integration

This directory contains the complete host-repository implementation set for Rill Xray Agent. It is pinned to the reviewed upstream commit in `UPSTREAM_ANCHOR.json`.

Run `tools/verify_repo.py <repo>` before applying. Run `tools/apply_to_repo.py <repo>` only on a clean integration branch. The tool adds the status header, menu item 9, offline commands and the complete payload. Host reinstall, update and whole-uninstall coordination must be reviewed in the pull request before release.
