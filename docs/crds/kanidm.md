# Kanidm custom resource

Deploys a Kanidm server and the Kubernetes objects it needs: PVCs, TLS certificate, ingress, configmap, and admin credential secrets.

```yaml
apiVersion: kanidm.github.io/v1alpha1
kind: Kanidm
metadata:
  name: kanidm-instance
  namespace: kanidm
spec:
  version: 1.10.5
  domain: idm.example.com
  certificate:
    issuer: letsencrypt-prod
  database:
    fsType: other
    storageClass: standard
    storageSize: 1Gi
    arcSize: 2048
  backup:
    enabled: true
    schedule: "0 9 * * *"
    versions: 7
    storageClass: standard
    storageSize: 7Gi
  webPort: 8443
  ldapPort: 3890
  logLevel: info
  highAvailability:
    enabled: false
    replicas: 1
  ingress:
    enabled: true
    ingressClassName: nginx
    trustXForwardedFor: true
    annotations:
      nginx.ingress.kubernetes.io/backend-protocol: HTTPS
      cert-manager.io/cluster-issuer: letsencrypt-prod
```

## Key fields

| Field | Description |
|-------|-------------|
| `version` | Kanidm server image tag (`kanidm/server:{version}`) |
| `domain` | DNS name and Kanidm `domain` / WebAuthn origin |
| `certificate.issuer` | cert-manager `ClusterIssuer` name for the server TLS cert |
| `database.*` | PVC for the Kanidm database |
| `backup.*` | Online backup PVC and schedule |
| `ingress.*` | Ingress resource; defaults to `ingressClassName: nginx`; set `trustXForwardedFor` when behind a reverse proxy |
| `highAvailability` | Not yet implemented — keep `enabled: false` |

## Status

The `Kanidm` CR exposes a `.status` subresource. The operator updates it on every create, update, and resume reconcile with the live server image, replica counts, and standard conditions:

```yaml
status:
  observedGeneration: 1
  version: 1.10.5
  image: kanidm/server:1.10.5
  readyReplicas: 1
  availableReplicas: 1
  lastReconcileTime: "2026-10-24T12:00:00Z"
  lastReconcileResult: Success
  lastReconcileTrigger: create
  conditions:
    - type: Ready
      status: "True"
      reason: ReconcileSuccessful
    - type: Degraded
      status: "False"
      reason: NotDegraded
```

When provisioning completes, the operator also sets `metadata.annotations.kanidm.github.io/processed: "true"` and creates `admin-credentials` and `idm-admin-credentials` secrets in the Kanidm namespace.

Kopf handler progress is stored under `status.kopf` (not in annotations), so stale failure annotations from older operator builds are cleared after a successful reconcile.

## Example

See [`manifests/example/kanidm.yaml`](https://github.com/juniorfoo/kanidm-operator/blob/master/manifests/example/kanidm.yaml).
