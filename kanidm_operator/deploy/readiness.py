"""Fast Kubernetes checks before Kanidm CLI reconciliation."""

from __future__ import annotations

import os

import kopf
from kubernetes import client as kube_client, config
from kubernetes.client.models.v1_secret_list import V1SecretList

from kanidm_operator.deployer import slugify

_IDM_ADMIN = "idm_admin"


def _load_kube_config() -> None:
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        config.load_incluster_config()
    else:
        config.load_kube_config()


def find_kanidm_cr(kanidm_name: str) -> dict | None:
    _load_kube_config()
    customapi = kube_client.CustomObjectsApi()
    kanidms = customapi.list_cluster_custom_object(
        "kanidm.github.io",
        version="v1alpha1",
        plural="kanidms",
    )
    for item in kanidms["items"]:
        if item["metadata"]["name"] == kanidm_name:
            return item
    return None


def _idm_admin_secret_exists(kanidm_cr: dict, namespace: str) -> bool:
    coreapi = kube_client.CoreV1Api()
    selector = f"kanidm.github.io/credentials-for={slugify(_IDM_ADMIN)}"
    for ns in (namespace, kanidm_cr["metadata"]["namespace"]):
        secrets: V1SecretList = coreapi.list_namespaced_secret(ns, label_selector=selector)
        for secret in secrets.items:
            if secret.data and "password" in secret.data:
                return True
    return False


def require_kanidm_cli_ready(kanidm_name: str, namespace: str) -> None:
    """
    Fail fast (with retry) when the Kanidm instance is not ready for CLI calls.

    Dependent User/Group/OAuth2 handlers call this before constructing
    ``KanidmCLIClient``, so bulk resume work does not block thread-pool slots on
    login timeouts while the Kanidm instance handler is still deploying secrets.
    """
    kanidm_cr = find_kanidm_cr(kanidm_name)
    if kanidm_cr is None:
        raise kopf.TemporaryError(
            f"No Kanidm configuration named {kanidm_name} found",
            delay=10,
        )
    if not _idm_admin_secret_exists(kanidm_cr, namespace):
        raise kopf.TemporaryError(
            f"Kanidm instance {kanidm_name} is not ready for identity reconciliation "
            "(waiting for idm_admin credentials)",
            delay=5,
        )
