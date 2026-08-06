# Lifecycle contract

- Default mode is `observe-only`.
- Route Assist and bounded automatic execution remain disabled.
- Before host reconfiguration, switch the agent to maintenance/observe-only and snapshot its mode.
- Commit a new observation only after the host transaction passes its own validation.
- Preserve the host transaction return code.
- Whole-host uninstall uses prepare -> host uninstall -> agent purge. A failed host uninstall must retain agent diagnostics.
- Host updates must validate the integration schema before replacing the running script.
