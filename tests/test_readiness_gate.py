"""Tests for Kanidm CLI readiness gating."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import kopf
import pytest

from kanidm_operator.deploy.readiness import require_kanidm_cli_ready


def test_require_kanidm_cli_ready_missing_cr() -> None:
    with patch(
        "kanidm_operator.deploy.readiness.find_kanidm_cr",
        return_value=None,
    ):
        with pytest.raises(kopf.TemporaryError, match="No Kanidm configuration"):
            require_kanidm_cli_ready("kanidm-instance", "kanidm")


def test_require_kanidm_cli_ready_missing_secret() -> None:
    cr = {"metadata": {"name": "kanidm-instance", "namespace": "kanidm"}}
    with patch(
        "kanidm_operator.deploy.readiness.find_kanidm_cr",
        return_value=cr,
    ):
        with patch(
            "kanidm_operator.deploy.readiness._idm_admin_secret_exists",
            return_value=False,
        ):
            with pytest.raises(kopf.TemporaryError, match="not ready for identity"):
                require_kanidm_cli_ready("kanidm-instance", "kanidm")


def test_require_kanidm_cli_ready_ok() -> None:
    cr = {"metadata": {"name": "kanidm-instance", "namespace": "kanidm"}}
    with patch(
        "kanidm_operator.deploy.readiness.find_kanidm_cr",
        return_value=cr,
    ):
        with patch(
            "kanidm_operator.deploy.readiness._idm_admin_secret_exists",
            return_value=True,
        ):
            require_kanidm_cli_ready("kanidm-instance", "kanidm")
