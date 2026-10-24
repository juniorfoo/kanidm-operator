import os
import subprocess

import kopf.testing
import pytest

from tests.helpers import (
    KANIDM_NAMESPACE,
    assert_kanidm_cr_status,
    assert_kanidm_deployment,
    deployment_image_version,
    kubectl,
    stamp_kopf_failure_annotation,
    stamp_kopf_last_handled_configuration,
    wait_processed,
)
from tests.test_kanidm_operator import crd_yaml, example, fixtures


@pytest.fixture(autouse=True)
def crd_exists():
    from tests.test_kanidm_operator import _clear_kanidm_namespace

    _clear_kanidm_namespace()
    subprocess.run(
        f"kubectl apply -k {crd_yaml}",
        check=True,
        timeout=10,
        capture_output=True,
        shell=True,
    )


def test_resume_heals_version_drift_with_stale_last_handled():
    """
    Simulate Joe's cluster: CR and kopf last-handled already at 1.10.5 while the
    Deployment still runs 1.10.3. Operator restart must roll the server via resume.
    """
    settings = kopf.OperatorSettings()
    settings.watching.server_timeout = 10

    subprocess.run(
        f"kubectl apply -f {os.path.join(example, 'namespace.yaml')}",
        shell=True,
        check=True,
        timeout=30,
        capture_output=True,
    )

    subprocess.run(
        f"kubectl apply -f {os.path.join(fixtures, 'kanidm-1.10.3.yaml')}",
        shell=True,
        check=True,
        timeout=30,
        capture_output=True,
    )

    with kopf.testing.KopfRunner(
        ["run", "--all-namespaces", "--standalone", "-m", "kanidm_operator"],
        timeout=600,
        settings=settings,
    ) as bootstrap_runner:
        wait_processed("kanidm", "kanidm-instance", timeout="300s")
        kubectl(
            "wait",
            "--for=condition=Available",
            "deployment",
            "kanidm",
            "-n",
            KANIDM_NAMESPACE,
            "--timeout=300s",
        )
        assert_kanidm_deployment(version="1.10.3")

    assert bootstrap_runner.exception is None
    assert bootstrap_runner.exit_code == 0

    kubectl(
        "patch",
        "kanidm",
        "kanidm-instance",
        "-n",
        KANIDM_NAMESPACE,
        "--type=merge",
        "-p",
        '{"spec":{"version":"1.10.5"}}',
    )
    stamp_kopf_last_handled_configuration("kanidm", "kanidm-instance")
    stamp_kopf_failure_annotation(
        "on_update_kanidms",
        "422 Client Error: Unprocessable Entity for url: .../deployments/kanidm",
    )
    assert deployment_image_version() == "1.10.3"

    with kopf.testing.KopfRunner(
        ["run", "--all-namespaces", "--standalone", "-m", "kanidm_operator"],
        timeout=900,
        settings=settings,
    ) as resume_runner:
        for _ in range(60):
            if deployment_image_version() == "1.10.5":
                break
            subprocess.run(["sleep", "5"], check=True)
        else:
            raise AssertionError(
                f"resume did not roll deployment, still {deployment_image_version()}"
            )

        kubectl(
            "wait",
            "--for=condition=Available",
            "deployment",
            "kanidm",
            "-n",
            KANIDM_NAMESPACE,
            "--timeout=300s",
        )
        assert_kanidm_deployment(version="1.10.5")
        assert_kanidm_cr_status(version="1.10.5")

    assert resume_runner.exception is None
    assert resume_runner.exit_code == 0
