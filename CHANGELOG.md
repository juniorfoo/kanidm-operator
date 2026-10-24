# Changelog

## 1.10.5-op.2 (unreleased)

- Reconcile `Kanidm` CR updates: changing `spec.version` (and ports or other rendered fields) patches the server `Deployment`, `ConfigMap`, and related child resources.
- On operator resume, detect Deployment image drift versus `spec.version` and roll the server without requiring a CR spec change (covers clusters already at the target version in GitOps/kopf state).
- Server `Deployment` strategy is `Recreate` for ReadWriteOnce database volumes.
- Refuse unsupported `spec.version` changes (downgrades or skipping minor versions) with a clear operator error.

## 1.10.5-op.1

- Kanidm 1.10.x support: config version 2, password recovery parsing, resource limits, and documentation.
