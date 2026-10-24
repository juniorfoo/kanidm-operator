from logging import Logger

import kopf
from kanidm_operator.typing.user import UserResource

from .concurrency import dependent_reconcile_slot
from .readiness import require_kanidm_cli_ready
from .util import KanidmCLIClient


def _reconcile_user(spec: UserResource, namespace: str, logger: Logger) -> None:
    require_kanidm_cli_ready(spec["kanidmName"], namespace)
    cli_client = KanidmCLIClient(spec["kanidmName"], namespace, logger)
    cli_client.create_user(spec["name"], spec["displayName"])
    cli_client.set_user_emails(spec["name"], spec["emails"])


@kopf.on.create("kanidm.github.io", "v1alpha1", "users")
@kopf.on.update("kanidm.github.io", "v1alpha1", "users")
def on_create_user(
    spec: UserResource,
    patch: dict,
    namespace: str,
    logger: Logger,
    body: dict,
    **kwargs,
):
    logger.info(f"Trying to add user {spec['name']} to kanidm in the namespace {namespace}")
    with dependent_reconcile_slot():
        _reconcile_user(spec, namespace, logger)

    patch.setdefault("metadata", {}).setdefault("annotations", {})["kanidm.github.io/processed"] = "true"


@kopf.on.delete("kanidm.github.io", "v1alpha1", "users")
def on_delete_user(
    spec: UserResource,
    name: str,
    namespace: str,
    logger: Logger,
    annotations: dict[str, str],
    **kwargs,
):
    logger.info(f"Trying to delete user {spec['name']} from kanidm in the namespace {namespace}")
    cli_client = KanidmCLIClient(
        spec["kanidmName"], namespace, logger, silence_missing_kanidm=True
    )
    if cli_client.kanidm_spec is not None:
        cli_client.delete_user(spec["name"])
