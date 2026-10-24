# Developing

## Local operator run

You need:

- A Kubernetes cluster and kubeconfig
- Network access to the Kanidm HTTPS endpoint (for example via ingress and `/etc/hosts`)
- The `kanidm` CLI matching your server version

Install Python dependencies:

```bash
poetry install
```

Install CRDs but **not** the in-cluster operator deployment:

```bash
kubectl apply -k manifests/crds
```

Run the operator locally:

```bash
export KANIDM_EXEC=kanidm   # or $PWD/.bin/kanidm when using the Docker wrapper
poetry run kopf run --standalone --all-namespaces -m kanidm_operator
```

See the [Dockerfile](https://github.com/juniorfoo/kanidm-operator/blob/master/Dockerfile) for how the container image installs dependencies and the Kanidm CLI.

## Tests

The project has two test layers:

| Test file | Purpose |
|-----------|---------|
| `tests/test_server_config.py` | Unit tests for `server.toml` rendering and password parsing |
| `tests/test_kanidm_operator.py` | End-to-end test against a real KIND cluster |
| `tests/test_operator_rbac.py` | Shipped ClusterRole vs operator ServiceAccount (`kubectl auth can-i`) |

### End-to-end coverage

The e2e test verifies:

- Kubernetes resources: deployment image, configmap, ingress, admin secrets
- HTTPS reachability through ingress
- Kanidm server state via CLI: user, group membership, OAuth2 client
- Kubernetes OAuth2 secret matches `kanidm system oauth2 show-basic-secret`

### Run unit tests only

```bash
poetry run pytest -v tests/test_server_config.py
```

### Run the full suite locally

Follow the cluster setup in [Upgrading to Kanidm 1.10](upgrading/kanidm-1.10.md#running-tests-locally), then:

```bash
poetry run pytest -v
```

CI runs the same tests on every pull request (see `.github/workflows/dockerhub-cd.yaml`).

### How e2e runs the operator

End-to-end tests start the operator with `kopf.testing.KopfRunner` on the test runner host, using the default kubeconfig (cluster-admin on the KIND cluster). They do **not** deploy `manifests/operator` or run the operator pod under `kanidm-operator-account`, so RBAC gaps in the shipped ClusterRole are invisible to those tests. `tests/test_operator_rbac.py` applies the operator kustomize overlay and checks that the ServiceAccount may perform every verb declared in `manifests/operator/cluster-role.yaml`.

## Documentation

Build the site locally:

```bash
poetry install --with docs
poetry run mkdocs serve
```

Strict build (matches CI):

```bash
poetry run mkdocs build --strict
```

Output is written to `site/`.

## Releases and Docker images

Images are built and pushed to Docker Hub by [`.github/workflows/dockerhub-cd.yaml`](https://github.com/juniorfoo/kanidm-operator/blob/master/.github/workflows/dockerhub-cd.yaml) when changes merge to `master` or when a `v*` git tag is pushed.

| Trigger | Image |
|---------|-------|
| Push to `master` | `juniorfoo/kanidm-operator:latest` (and branch/SHA tags) |
| Git tag `v1.10.5-op.5` | `juniorfoo/kanidm-operator:1.10.5-op.5` |

The operator version in `pyproject.toml` (for example `1.10.5+5`) tracks the supported Kanidm release. Tag git releases as `v1.10.5-op.5` for Docker-friendly version tags.

To cut a release:

```bash
git tag v1.10.5-op.1
git push origin v1.10.5-op.1
```

Pin a cluster to that image by setting `newTag` in `manifests/operator/kustomization.yaml`.
