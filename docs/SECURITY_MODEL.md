# Security model

The agent is local-only and fail-closed. It does not own Xray configuration. It never stores raw user identities, private keys or share links. Audit records redact sensitive keys and values. Backup extraction rejects traversal, symlinks and decompression-limit violations. Root transactions use a durable commit bundle.
