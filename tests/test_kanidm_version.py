import pytest

from kanidm_operator.deploy.version import (
    KanidmVersion,
    VersionUpgradeError,
    parse_server_image,
    validate_version_upgrade,
)


def test_parse_server_image() -> None:
    assert parse_server_image("kanidm/server:1.10.3") == KanidmVersion(1, 10, 3)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("1.10.3", "1.10.5"),
        ("1.10.3", "1.10.3"),
        ("1.9.5", "1.10.0"),
        ("1.10.5", "1.11.0"),
        ("1.10.3", "1.11.2"),
        ("1.10.5", "2.0.0"),
    ],
)
def test_validate_version_upgrade_allows(current: str, target: str) -> None:
    validate_version_upgrade(
        KanidmVersion.parse(current),
        KanidmVersion.parse(target),
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [
        ("1.10.5", "1.10.3"),
        ("1.10.5", "1.9.9"),
        ("1.10.3", "1.12.0"),
        ("1.8.0", "1.10.0"),
    ],
)
def test_validate_version_upgrade_refuses(current: str, target: str) -> None:
    with pytest.raises(VersionUpgradeError):
        validate_version_upgrade(
            KanidmVersion.parse(current),
            KanidmVersion.parse(target),
        )
