from unittest.mock import MagicMock, patch

import kopf
import pytest

from kanidm_operator.deploy.kanidm import (
    deployment_version_drifts_from_spec,
    on_resume_kanidms,
)

_DEPLOYMENT_STATUS = {
    "image": "kanidm/server:1.10.5",
    "readyReplicas": 1,
    "availableReplicas": 1,
}


@pytest.fixture(autouse=True)
def _mock_deployment_replica_status():
    with (
        patch(
            "kanidm_operator.deploy.kanidm_status.get_deployment_replica_status",
            return_value=_DEPLOYMENT_STATUS,
        ),
        patch(
            "kanidm_operator.deploy.kanidm.get_deployment_replica_status",
            return_value=_DEPLOYMENT_STATUS,
        ),
    ):
        yield


def test_deployment_version_drifts_from_spec_detects_mismatch() -> None:
    with patch(
        "kanidm_operator.deploy.kanidm.get_deployed_server_image",
        return_value="kanidm/server:1.10.3",
    ):
        assert deployment_version_drifts_from_spec("kanidm", "1.10.5") is True


def test_deployment_version_drifts_from_spec_no_drift() -> None:
    with patch(
        "kanidm_operator.deploy.kanidm.get_deployed_server_image",
        return_value="kanidm/server:1.10.5",
    ):
        assert deployment_version_drifts_from_spec("kanidm", "1.10.5") is False


def test_on_resume_skips_without_drift() -> None:
    spec = {"version": "1.10.5"}
    logger = MagicMock()

    with patch(
        "kanidm_operator.deploy.kanidm.deployment_version_drifts_from_spec",
        return_value=False,
    ):
        with patch(
            "kanidm_operator.deploy.kanidm.deploy_kanidm_version_drift_resources"
        ) as reconcile:
            on_resume_kanidms(
                spec=spec,
                name="kanidm-instance",
                namespace="kanidm",
                logger=logger,
                patch={},
                meta={"generation": 1},
            )
            reconcile.assert_not_called()


def test_on_resume_reconciles_drift() -> None:
    spec = {"version": "1.10.5", "highAvailability": {"enabled": False}}
    logger = MagicMock()

    with patch(
        "kanidm_operator.deploy.kanidm.deployment_version_drifts_from_spec",
        return_value=True,
    ):
        with patch(
            "kanidm_operator.deploy.kanidm.validate_spec_version_upgrade"
        ) as validate:
            with patch("kanidm_operator.deploy.kanidm.Deployer") as deployer_cls:
                with patch(
                    "kanidm_operator.deploy.kanidm.deploy_kanidm_version_drift_resources"
                ) as reconcile:
                    on_resume_kanidms(
                        spec=spec,
                        name="kanidm-instance",
                        namespace="kanidm",
                        logger=logger,
                        patch={},
                        meta={"generation": 1},
                    )
                    validate.assert_called_once_with("kanidm", "1.10.5", logger)
                    reconcile.assert_called_once()
                    deployer_cls.assert_called_once_with("kanidm", "1.10.5", logger)


def test_on_resume_refuses_downgrade_drift() -> None:
    spec = {"version": "1.10.3"}
    logger = MagicMock()

    with patch(
        "kanidm_operator.deploy.kanidm.deployment_version_drifts_from_spec",
        return_value=True,
    ):
        with patch(
            "kanidm_operator.deploy.kanidm.validate_spec_version_upgrade",
            side_effect=kopf.PermanentError("downgrade"),
        ):
            with patch(
                "kanidm_operator.deploy.kanidm.deploy_kanidm_version_drift_resources"
            ) as reconcile:
                with pytest.raises(kopf.PermanentError):
                    on_resume_kanidms(
                        spec=spec,
                        name="kanidm-instance",
                        namespace="kanidm",
                        logger=logger,
                        patch={},
                        meta={"generation": 1},
                    )
                reconcile.assert_not_called()
