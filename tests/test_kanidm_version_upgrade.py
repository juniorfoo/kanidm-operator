import os
import subprocess

import kopf.testing
import pytest

from tests.helpers import (
    KANIDM_NAMESPACE,
    assert_kanidm_deployment,
    deployment_image_version,
    kubectl,
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


def test_patch_version_upgrade_rollout():
    settings = kopf.OperatorSettings()
    settings.watching.server_timeout = 10

    subprocess.run(
        f"kubectl apply -f {os.path.join(example, 'namespace.yaml')}",
        shell=True,
        check=True,
        timeout=30,
        capture_output=True,
    )

    with kopf.testing.KopfRunner(
        ["run", "--all-namespaces", "--standalone", "-m", "kanidm_operator"],
        timeout=900,
        settings=settings,
    ) as runner:
        subprocess.run(
            f"kubectl apply -f {os.path.join(fixtures, 'kanidm-1.10.3.yaml')}",
            shell=True,
            check=True,
            timeout=30,
            capture_output=True,
        )
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

        for _ in range(60):
            if deployment_image_version() == "1.10.5":
                break
            subprocess.run(["sleep", "5"], check=True)
        else:
            raise AssertionError(
                f"deployment image did not reach 1.10.5, still {deployment_image_version()}"
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

    assert runner.exception is None
    assert runner.exit_code == 0
