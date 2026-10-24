from unittest.mock import patch

from kanidm_operator.deploy.kanidm_status import (
    clear_legacy_kopf_annotations,
    write_kanidm_status,
)


def test_clear_legacy_kopf_annotations() -> None:
    patch_body: dict = {}
    annotations = {
        "kopf.zalando.org/on_resume_kanidms": '{"failure": true}',
        "kanidm.github.io/processed": "true",
    }
    clear_legacy_kopf_annotations(patch_body, annotations)
    assert patch_body["metadata"]["annotations"] == {
        "kopf.zalando.org/on_resume_kanidms": None,
    }


def test_write_kanidm_status_ready_on_success() -> None:
    patch_body: dict = {}
    meta = {
        "generation": 3,
        "annotations": {"kopf.zalando.org/on_update_kanidms": "stale"},
    }
    spec = {"version": "1.10.5"}
    with patch(
        "kanidm_operator.deploy.kanidm_status.get_deployment_replica_status",
        return_value={
            "image": "kanidm/server:1.10.5",
            "readyReplicas": 1,
            "availableReplicas": 1,
        },
    ):
        write_kanidm_status(
            patch_body,
            meta=meta,
            spec=spec,
            namespace="kanidm",
            trigger="resume",
            reconcile_result="Success",
        )

    status = patch_body["status"]
    assert status["version"] == "1.10.5"
    assert status["image"] == "kanidm/server:1.10.5"
    assert status["readyReplicas"] == 1
    assert status["lastReconcileResult"] == "Success"
    assert status["lastReconcileTrigger"] == "resume"
    ready = next(c for c in status["conditions"] if c["type"] == "Ready")
    degraded = next(c for c in status["conditions"] if c["type"] == "Degraded")
    assert ready["status"] == "True"
    assert degraded["status"] == "False"
    assert patch_body["metadata"]["annotations"][
        "kopf.zalando.org/on_update_kanidms"
    ] is None


def test_write_kanidm_status_degraded_on_failure() -> None:
    patch_body: dict = {}
    meta = {"generation": 1}
    spec = {"version": "1.10.5"}
    with patch(
        "kanidm_operator.deploy.kanidm_status.get_deployment_replica_status",
        return_value={
            "image": "kanidm/server:1.10.3",
            "readyReplicas": 1,
            "availableReplicas": 1,
        },
    ):
        write_kanidm_status(
            patch_body,
            meta=meta,
            spec=spec,
            namespace="kanidm",
            trigger="update",
            reconcile_result="Failed",
            reconcile_error=RuntimeError("422 Unprocessable Entity"),
        )

    degraded = next(
        c for c in patch_body["status"]["conditions"] if c["type"] == "Degraded"
    )
    assert degraded["status"] == "True"
    assert "422" in patch_body["status"]["lastReconcileMessage"]
