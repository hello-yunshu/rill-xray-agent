# Architecture

`rill-xray-agent-runtime` owns local state, audit and the decision lifecycle. `rill-xray-agent-agent` exposes a restricted Unix-socket method set. The Xray adapter emits only hashes, sizes, validation return codes and service states. Root configuration changes remain owned by the host Xray project.
