"""Kanidm server image version parsing and upgrade policy checks."""

from __future__ import annotations

import re
from dataclasses import dataclass

SERVER_IMAGE_RE = re.compile(r"^kanidm/server:(?P<version>.+)$")


class VersionUpgradeError(ValueError):
    """Raised when spec.version is not an allowed upgrade from the deployed image."""


@dataclass(frozen=True, order=True)
class KanidmVersion:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, version: str) -> KanidmVersion:
        parts = version.strip().split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError(f"invalid Kanidm version: {version!r}")
        return cls(int(parts[0]), int(parts[1]), int(parts[2]))


def parse_server_image(image: str) -> KanidmVersion:
    match = SERVER_IMAGE_RE.match(image.strip())
    if match is None:
        raise ValueError(f"unexpected kanidm server image: {image!r}")
    return KanidmVersion.parse(match.group("version"))


def validate_version_upgrade(current: KanidmVersion, target: KanidmVersion) -> None:
    """
    Enforce Kanidm's sequential upgrade policy.

    Patch upgrades within the same major.minor are allowed. Downgrades are refused.
    Skipping a minor release (for example 1.10.x to 1.12.x) is refused. A single
    minor bump (1.10.x to 1.11.y) or major bump to the next major with minor 0
    (1.10.x to 2.0.y) is allowed.
    """
    if target < current:
        raise VersionUpgradeError(
            f"downgrading Kanidm is not supported (deployed {current}, requested {target})"
        )

    current_line = (current.major, current.minor)
    target_line = (target.major, target.minor)
    if current_line == target_line:
        return

    if target_line[0] == current_line[0]:
        if target_line[1] == current_line[1] + 1:
            return
        raise VersionUpgradeError(
            f"Kanidm upgrades must advance one minor version at a time "
            f"(deployed {current}, requested {target})"
        )

    if target_line == (current_line[0] + 1, 0):
        return

    raise VersionUpgradeError(
        f"Kanidm upgrades must advance one minor version at a time "
        f"(deployed {current}, requested {target})"
    )
