# Changelog

## 1.10.5-op.4 (unreleased)

- Clear stale `spec.strategy.rollingUpdate` when patching the server `Deployment` to `Recreate`, fixing 422 reconcile loops on clusters upgraded from older operator builds that used `RollingUpdate`.

## 1.10.5-op.3

- Grant `get`, `list`, and `watch` on `apps/deployments` in the operator ClusterRole so in-cluster reconciliation can read the live server image (fixes 403 on `on_resume` / `on_update` version drift handling).
- Remove dead ClusterRole rules: admission webhook configs (invalid `admissionregistration.k8s.io/v1` apiGroups and unused in `--standalone` kopf) and `extensions`/`batch` CronJobs (no CronJob templates; backups are in-server `online_backup`).
- Add `tests/test_operator_rbac.py` to assert the shipped ServiceAccount can perform every verb in `manifests/operator/cluster-role.yaml`.

## 1.10.5-op.2

- Reconcile `Kanidm` CR updates: changing `spec.version` (and ports or other rendered fields) patches the server `Deployment`, `ConfigMap`, and related child resources.
- On operator resume, detect Deployment image drift versus `spec.version` and roll the server without requiring a CR spec change (covers clusters already at the target version in GitOps/kopf state).
- Server `Deployment` strategy is `Recreate` for ReadWriteOnce database volumes.
- Refuse unsupported `spec.version` changes (downgrades or skipping minor versions) with a clear operator error.

## 1.10.5-op.1

- Kanidm 1.10.x support: config version 2, password recovery parsing, resource limits, and documentation.
