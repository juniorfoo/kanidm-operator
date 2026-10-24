"""Verify the shipped ClusterRole grants every API access the operator uses."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

from tests.helpers import KANIDM_NAMESPACE, kubectl

OPERATOR_KUSTOMIZE = Path(__file__).resolve().parents[1] / "manifests" / "operator"
CLUSTER_ROLE_PATH = OPERATOR_KUSTOMIZE / "cluster-role.yaml"
OPERATOR_SA = "system:serviceaccount:kanidm-system:kanidm-operator-account"

# Cluster-scoped API objects in the shipped ClusterRole (kubectl auth can-i: no --namespace).
_CLUSTER_SCOPED = {
    ("", "namespaces"),
    ("apiextensions.k8s.io", "customresourcedefinitions"),
}


def _kubectl_reachable() -> bool:
    try:
        kubectl("cluster-info", check=False)
        return kubectl("cluster-info").returncode == 0
    except (FileNotFoundError, subprocess.SubprocessError):
        return False


def _resource_for_can_i(api_group: str, resource: str) -> str:
    if "/" in resource:
        return resource
    if api_group:
        return f"{resource}.{api_group}"
    return resource


def _iter_cluster_role_checks():
    role = yaml.safe_load(CLUSTER_ROLE_PATH.read_text(encoding="utf-8"))
    for rule in role["rules"]:
        for api_group in rule["apiGroups"]:
            for resource in rule["resources"]:
                for verb in rule["verbs"]:
                    yield api_group, resource, verb


@pytest.fixture(scope="module")
def operator_rbac_applied():
    if not _kubectl_reachable():
        pytest.skip("kubectl cluster not available")
    kubectl("apply", "-k", str(OPERATOR_KUSTOMIZE))
    yield
    kubectl("delete", "-k", str(OPERATOR_KUSTOMIZE), "--ignore-not-found", check=False)


_CLUSTER_ROLE_CHECKS = list(_iter_cluster_role_checks())


@pytest.mark.parametrize(
    ("api_group", "resource", "verb"),
    _CLUSTER_ROLE_CHECKS,
    ids=[
        f"{verb}_{resource}_{api_group or 'core'}"
        for api_group, resource, verb in _CLUSTER_ROLE_CHECKS
    ],
)
def test_operator_service_account_can_use_shipped_cluster_role(
    operator_rbac_applied, api_group: str, resource: str, verb: str
):
    """Each verb in manifests/operator/cluster-role.yaml must be allowed for the operator SA."""
    resource_name = _resource_for_can_i(api_group, resource)
    args = [
        "auth",
        "can-i",
        verb,
        resource_name,
        f"--as={OPERATOR_SA}",
    ]
    if (api_group, resource) not in _CLUSTER_SCOPED:
        args.extend(["--namespace", KANIDM_NAMESPACE])
    result = kubectl(*args, check=False)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "yes", (
        f"operator SA cannot {verb} {resource_name} "
        f"(apiGroup={api_group!r}): {result.stdout.strip()}"
    )
