"""Status helpers for the Kanidm custom resource."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from kubernetes import client
import kubernetes.client.exceptions as k8s_exceptions

from kanidm_operator.deploy.kanidm_deployment import (
    KANIDM_DEPLOYMENT_NAME,
    get_deployed_server_image,
)

ReconcileResult = Literal["Success", "Failed", "InProgress"]
ReconcileTrigger = Literal["create", "update", "resume"]

KOPF_ANNOTATION_PREFIX = "kopf.zalando.org"


def _now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def get_deployment_replica_status(namespace: str) -> dict[str, Any]:
    """Read the live server Deployment image and replica counts."""
    image = get_deployed_server_image(namespace)
    ready_replicas = 0
    available_replicas = 0
    apps = client.AppsV1Api()
    try:
        deployment = apps.read_namespaced_deployment(KANIDM_DEPLOYMENT_NAME, namespace)
    except k8s_exceptions.ApiException as exc:
        if exc.status != 404:
            raise
    else:
        status = deployment.status
        if status is not None:
            ready_replicas = status.ready_replicas or 0
            available_replicas = status.available_replicas or 0
    return {
        "image": image,
        "readyReplicas": ready_replicas,
        "availableReplicas": available_replicas,
    }


def clear_legacy_kopf_annotations(
    patch: dict[str, Any],
    annotations: dict[str, str] | None,
) -> None:
    """Remove kopf progress annotations left from releases before the status subresource."""
    if not annotations:
        return
    ann_patch = patch.setdefault("metadata", {}).setdefault("annotations", {})
    for key in annotations:
        if key.startswith(f"{KOPF_ANNOTATION_PREFIX}/"):
            ann_patch[key] = None


def _condition(
    *,
    condition_type: str,
    status: str,
    reason: str,
    message: str,
    previous: dict[str, Any] | None,
) -> dict[str, str]:
    last_transition = _now_iso()
    if (
        previous is not None
        and previous.get("status") == status
        and previous.get("reason") == reason
        and previous.get("message") == message
    ):
        last_transition = previous.get("lastTransitionTime", last_transition)
    return {
        "type": condition_type,
        "status": status,
        "reason": reason,
        "message": message,
        "lastTransitionTime": last_transition,
    }


def _index_conditions(
    conditions: list[dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if not conditions:
        return {}
    return {item["type"]: item for item in conditions if "type" in item}


def write_kanidm_status(
    patch: dict[str, Any],
    *,
    meta: dict[str, Any],
    spec: dict[str, Any],
    namespace: str,
    trigger: ReconcileTrigger,
    reconcile_result: ReconcileResult,
    reconcile_message: str = "",
    reconcile_error: BaseException | None = None,
    existing_status: dict[str, Any] | None = None,
) -> None:
    """Populate .status on the Kanidm CR from the cluster and the last reconcile outcome."""
    deployment = get_deployment_replica_status(namespace)
    image = deployment["image"] or f"kanidm/server:{spec['version']}"
    ready_replicas = deployment["readyReplicas"]
    available_replicas = deployment["availableReplicas"]

    failed = reconcile_result == "Failed" or reconcile_error is not None
    in_progress = reconcile_result == "InProgress"
    workload_ready = available_replicas >= 1 and ready_replicas >= 1
    ready = not failed and not in_progress and workload_ready

    if reconcile_error is not None and not reconcile_message:
        reconcile_message = str(reconcile_error)
    elif not reconcile_message and failed:
        reconcile_message = "Kanidm reconciliation failed"
    elif not reconcile_message and in_progress:
        reconcile_message = "Kanidm reconciliation in progress"
    elif not reconcile_message and ready:
        reconcile_message = "Kanidm server is running and reconciled"
    elif not reconcile_message and not workload_ready:
        reconcile_message = "Waiting for Kanidm Deployment to become ready"

    previous = _index_conditions((existing_status or {}).get("conditions"))

    ready_reason = "ReconcileSuccessful"
    if failed:
        ready_reason = "ReconcileFailed"
    elif in_progress:
        ready_reason = "Reconciling"
    elif not workload_ready:
        ready_reason = "DeploymentNotReady"

    conditions = [
        _condition(
            condition_type="Ready",
            status="True" if ready else "False",
            reason=ready_reason,
            message=reconcile_message,
            previous=previous.get("Ready"),
        ),
        _condition(
            condition_type="Degraded",
            status="True" if failed else "False",
            reason="ReconcileError" if failed else "NotDegraded",
            message=reconcile_message if failed else "",
            previous=previous.get("Degraded"),
        ),
    ]

    status_patch = patch.setdefault("status", {})
    status_patch.update(
        {
            "observedGeneration": meta.get("generation"),
            "version": spec["version"],
            "image": image,
            "readyReplicas": ready_replicas,
            "availableReplicas": available_replicas,
            "lastReconcileTime": _now_iso(),
            "lastReconcileResult": reconcile_result,
            "lastReconcileMessage": reconcile_message,
            "lastReconcileTrigger": trigger,
            "conditions": conditions,
        }
    )

    clear_legacy_kopf_annotations(patch, meta.get("annotations"))
