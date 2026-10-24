"""Shipped CRDs must expose status subresources for kopf status persistence."""

from __future__ import annotations

from pathlib import Path

import yaml

CRD_DIR = Path(__file__).resolve().parents[1] / "manifests" / "crds"

_EXPECT_STATUS = (
    "kanidm.yaml",
    "user.yaml",
    "group.yaml",
    "oauth2-client.yaml",
)


def _load_crd(name: str) -> dict:
    return yaml.safe_load((CRD_DIR / name).read_text(encoding="utf-8"))


def test_kopf_managed_crds_define_status_subresource() -> None:
    for filename in _EXPECT_STATUS:
        crd = _load_crd(filename)
        version = crd["spec"]["versions"][0]
        assert version.get("subresources", {}).get("status") == {}, filename
        status_schema = version["schema"]["openAPIV3Schema"]["properties"]["status"]
        assert "kopf" in status_schema["properties"], filename
