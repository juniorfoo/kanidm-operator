import asyncio
from unittest.mock import MagicMock, patch

import kopf
import pytest

from kanidm_operator.deploy.kanidm import (
    on_update_kanidms,
    spec_needs_reconcile,
    validate_spec_version_upgrade,
)


@pytest.fixture(autouse=True)
def _mock_deployment_replica_status():
    with patch(
        "kanidm_operator.deploy.kanidm_status.get_deployment_replica_status",
        return_value={
            "image": "kanidm/server:1.10.5",
            "readyReplicas": 1,
            "availableReplicas": 1,
        },
    ):
        yield


def test_spec_needs_reconcile_detects_version_change() -> None:
    old = {"version": "1.10.3", "webPort": 8443}
    new = {"version": "1.10.5", "webPort": 8443}
    assert spec_needs_reconcile(old, new) is True


def test_spec_needs_reconcile_ignores_unrelated_changes() -> None:
    old = {"version": "1.10.5", "webPort": 8443}
    new = {"version": "1.10.5", "webPort": 8443}
    assert spec_needs_reconcile(old, new) is False


def test_validate_spec_version_upgrade_refuses_downgrade() -> None:
    logger = MagicMock()
    with patch(
        "kanidm_operator.deploy.kanidm.get_deployed_server_image",
        return_value="kanidm/server:1.10.5",
    ):
        with pytest.raises(kopf.PermanentError):
            validate_spec_version_upgrade("kanidm", "1.10.3", logger)


def test_on_update_skips_when_spec_unchanged() -> None:
    spec = {"version": "1.10.5", "webPort": 8443}
    old = {"spec": spec}
    logger = MagicMock()

    async def run() -> None:
        with patch(
            "kanidm_operator.deploy.kanidm.deploy_kanidm_reconciled_resources"
        ) as reconcile:
            await on_update_kanidms(
                spec=spec,
                old=old,
                name="kanidm-instance",
                namespace="kanidm",
                logger=logger,
                patch={},
                meta={"generation": 1},
            )
            reconcile.assert_not_called()

    asyncio.run(run())
