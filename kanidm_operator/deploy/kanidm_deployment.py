"""Helpers for reading the Kanidm server Deployment in the cluster."""

from kubernetes import client
import kubernetes.client.exceptions as k8s_exceptions

KANIDM_DEPLOYMENT_NAME = "kanidm"


def get_deployed_server_image(namespace: str) -> str | None:
    apps = client.AppsV1Api()
    try:
        deployment = apps.read_namespaced_deployment(KANIDM_DEPLOYMENT_NAME, namespace)
    except k8s_exceptions.ApiException as exc:
        if exc.status == 404:
            return None
        raise
    containers = deployment.spec.template.spec.containers
    if not containers:
        return None
    return containers[0].image
