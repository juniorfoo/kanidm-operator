from logging import Logger

import kopf

from kanidm_operator.typing.group import GroupResource
from .concurrency import dependent_reconcile_slot
from .readiness import require_kanidm_cli_ready
from .util import KanidmCLIClient


@kopf.on.create("kanidm.github.io", "v1alpha1", "groups")
def on_create_group(
    spec: GroupResource,
    patch: dict,
    namespace: str,
    logger: Logger,
    **kwargs,
):
    logger.info(f"Trying to create group {spec['name']} to kanidm in the namespace {namespace}")
    with dependent_reconcile_slot():
        require_kanidm_cli_ready(spec["kanidmName"], namespace)
        cli_client = KanidmCLIClient(spec["kanidmName"], namespace, logger)
        cli_client.create_group(spec["name"])
        cli_client.set_group_members(spec["name"], spec["members"])

    patch.setdefault("metadata", {}).setdefault("annotations", {})["kanidm.github.io/processed"] = "true"


@kopf.on.field("kanidm.github.io", "v1alpha1", "groups", field="spec.members")
def on_update_group_members(
    spec: GroupResource,
    namespace: str,
    logger: Logger,
    patch: dict,
    **kwargs,
):
    with dependent_reconcile_slot():
        require_kanidm_cli_ready(spec["kanidmName"], namespace)
        cli_client = KanidmCLIClient(spec["kanidmName"], namespace, logger)
        cli_client.set_group_members(spec["name"], spec["members"])


@kopf.on.delete("kanidm.github.io", "v1alpha1", "groups")
def on_delete_group(
    spec: GroupResource,
    namespace: str,
    logger: Logger,
    **kwargs,
):
    cli_client = KanidmCLIClient(
        spec["kanidmName"], namespace, logger, silence_missing_kanidm=True
    )
    if cli_client.kanidm_spec is not None:
        cli_client.delete_group(spec["name"])
