"""
Controls the deployment of kanidm in the cluster.
Will read the kanidms.kanidm.github.io CRD to deploy either:
  - In High Availability mode : n read replicas of kanidm, 1 write replica with UI
  - In Single Instance mode : 1 kanidm instance with UI as a deployment
"""

import re
import time
from logging import Logger

import kopf
from kubernetes import client
from kubernetes.client.models.v1_pod import V1Pod
from kubernetes.client.models.v1_pod_status import V1PodStatus
from kubernetes.stream import stream

from kanidm_operator.deploy.version import (
    KanidmVersion,
    VersionUpgradeError,
    parse_server_image,
    validate_version_upgrade,
)
from kanidm_operator.deploy.kanidm_deployment import (
    KANIDM_DEPLOYMENT_NAME,
    get_deployed_server_image,
)
from kanidm_operator.deploy.kanidm_status import (
    ReconcileTrigger,
    get_deployment_replica_status,
    write_kanidm_status,
)
from kanidm_operator.deployer import Deployer
from kanidm_operator.typing.kanidm import KanidmResource


def parse_recover_account_password(output: str) -> str | None:
    """Extract a recovered password from kanidmd output (JSON or log format)."""
    json_match = re.search(r'\{"password"\s*:\s*"([^"]+)"\}', output)
    if json_match is not None:
        return json_match.group(1)

    log_match = re.search(r'new_password:\s*"([^"]+)"', output)
    if log_match is not None:
        return log_match.group(1)

    return None


def deploy_kanidm_static_resources(deployer: Deployer, spec: KanidmResource) -> None:
    """Create PVCs and other resources that should only be applied on initial create."""
    deployer.deploy(
        "pvc-backups.yaml",
        backup_storage_class=spec["backup"]["storageClass"],
        backup_storage_size=spec["backup"]["storageSize"],
        backup_storage_annotations=spec["backup"].get("storageAnnotations", {}),
        backup_storage_labels=spec["backup"].get("storageLabels", {}),
    )
    deployer.deploy(
        "pvc-db.yaml",
        db_storage_class=spec["database"]["storageClass"],
        db_storage_size=spec["database"]["storageSize"],
        db_storage_annotations=spec["database"].get("storageAnnotations", {}),
        db_storage_labels=spec["database"].get("storageLabels", {}),
    )


def deploy_kanidm_version_drift_resources(deployer: Deployer, spec: KanidmResource) -> None:
    """
    Patch only resources required to align a running server with spec.version.

    Used on operator resume when kopf's last-handled-configuration already matches
    the CR but the Deployment image drifted (for example after a no-op update handler).
    Re-rendering Certificate/Service/Ingress on resume is avoided: those objects are
    unchanged when only the server tag drifts, and a full reconcile could apply
    unrelated template churn for clusters created by older operator builds.
    """
    deployer.deploy(
        "server.toml",
        domain=spec["domain"],
        log_level=spec.get("logLevel", "info"),
        ldap_port=spec.get("ldapPort", "3890"),
        http_port=spec.get("webPort", "8443"),
        db_fs_type=spec["database"]["fsType"],
        db_arc_size=spec["database"]["arcSize"],
        backup_enabled=spec["backup"]["enabled"],
        backup_schedule=spec["backup"]["schedule"],
        backup_versions=spec["backup"]["versions"],
        trust_x_forwarded_for=spec["ingress"]["trustXForwardedFor"],
    )

    if not spec["highAvailability"]["enabled"]:
        deployer.deploy(
            "deployment.yaml",
            http_port=spec.get("webPort", "8443"),
            ldap_port=spec.get("ldapPort", "3890"),
            image=f"kanidm/server:{spec['version']}",
        )
    else:
        deployer.logger.warning(
            "highAvailability mode is not implemented; skipping Deployment drift reconcile"
        )


def deploy_kanidm_reconciled_resources(deployer: Deployer, spec: KanidmResource) -> None:
    """Render and patch operator-managed Kanidm resources from the CR spec."""
    deployer.deploy(
        "certificate.yaml",
        hostname=spec["domain"],
        certificate_issuer=spec["certificate"]["issuer"],
        version=spec["version"],
    )
    deployer.deploy(
        "service.yaml",
        http_port=spec["webPort"],
        ldap_port=spec["ldapPort"],
    )
    deployer.deploy(
        "server.toml",
        domain=spec["domain"],
        log_level=spec.get("logLevel", "info"),
        ldap_port=spec.get("ldapPort", "3890"),
        http_port=spec.get("webPort", "8443"),
        db_fs_type=spec["database"]["fsType"],
        db_arc_size=spec["database"]["arcSize"],
        backup_enabled=spec["backup"]["enabled"],
        backup_schedule=spec["backup"]["schedule"],
        backup_versions=spec["backup"]["versions"],
        trust_x_forwarded_for=spec["ingress"]["trustXForwardedFor"],
    )

    if not spec["highAvailability"]["enabled"]:
        deployer.deploy(
            "deployment.yaml",
            http_port=spec.get("webPort", "8443"),
            ldap_port=spec.get("ldapPort", "3890"),
            image=f"kanidm/server:{spec['version']}",
        )
    else:
        deployer.logger.warning(
            "highAvailability mode is not implemented; skipping Deployment reconcile"
        )

    if spec.get("ingress").get("enabled", False):
        deployer.deploy(
            "ingress.yaml",
            hostname=spec["domain"],
            http_port=spec["webPort"],
            ingress_class_name=spec["ingress"].get("ingressClassName", "nginx"),
            annotations={}
            if "annotations" not in spec["ingress"]
            else spec["ingress"]["annotations"],
        )


def spec_needs_reconcile(old_spec: KanidmResource, new_spec: KanidmResource) -> bool:
    """Return True when a spec change should re-render reconciled child resources."""
    reconcile_keys = (
        "version",
        "domain",
        "logLevel",
        "webPort",
        "ldapPort",
        "database",
        "backup",
        "certificate",
        "ingress",
        "highAvailability",
    )
    for key in reconcile_keys:
        if old_spec.get(key) != new_spec.get(key):
            return True
    return False


def deployment_version_drifts_from_spec(namespace: str, spec_version: str) -> bool:
    """Return True when the live Deployment image tag differs from spec.version."""
    image = get_deployed_server_image(namespace)
    if image is None:
        return False
    try:
        deployed = parse_server_image(image)
        target = KanidmVersion.parse(spec_version)
    except ValueError:
        return True
    return deployed != target


def validate_spec_version_upgrade(
    namespace: str,
    target_version: str,
    logger: Logger,
) -> None:
    image = get_deployed_server_image(namespace)
    if image is None:
        logger.info("No kanidm Deployment found; skipping version upgrade validation")
        return
    try:
        current = parse_server_image(image)
    except ValueError as exc:
        logger.error("Cannot parse deployed kanidm image %s: %s", image, exc)
        raise kopf.PermanentError(str(exc)) from exc
    try:
        target = parse_server_image(f"kanidm/server:{target_version}")
    except ValueError as exc:
        logger.error("Invalid spec.version %s: %s", target_version, exc)
        raise kopf.PermanentError(str(exc)) from exc
    try:
        validate_version_upgrade(current, target)
    except VersionUpgradeError as exc:
        logger.error("%s", exc)
        raise kopf.PermanentError(str(exc)) from exc


def _finalize_kanidm_status(
    patch: dict,
    meta: dict,
    spec: KanidmResource,
    namespace: str,
    trigger: ReconcileTrigger,
    *,
    reconcile_error: BaseException | None = None,
    existing_status: dict | None = None,
) -> None:
    if reconcile_error is not None:
        result = "Failed"
    else:
        result = "Success"
    write_kanidm_status(
        patch,
        meta=meta,
        spec=spec,
        namespace=namespace,
        trigger=trigger,
        reconcile_result=result,
        reconcile_error=reconcile_error,
        existing_status=existing_status,
    )
    if reconcile_error is None and trigger in ("update", "resume"):
        deployment = get_deployment_replica_status(namespace)
        if deployment["availableReplicas"] < 1 or deployment["readyReplicas"] < 1:
            raise kopf.TemporaryError(
                "Waiting for Kanidm Deployment to become ready after reconcile",
                delay=10,
            )


@kopf.on.create("kanidm.github.io", "v1alpha1", "kanidms")
async def on_create_kanidms(
    spec: KanidmResource,
    name: str,
    namespace: str,
    logger: Logger,
    patch: dict,
    meta: dict,
    status: dict | None = None,
    **kwargs,
):
    logger.info(f"Creating kanidm instance {name} in namespace {namespace}")
    write_kanidm_status(
        patch,
        meta=meta,
        spec=spec,
        namespace=namespace,
        trigger="create",
        reconcile_result="InProgress",
        existing_status=status,
    )
    reconcile_error: BaseException | None = None
    try:
        deployer = Deployer(namespace, spec["version"], logger)

        deploy_kanidm_static_resources(deployer, spec)
        deploy_kanidm_reconciled_resources(deployer, spec)

        logger.info(
            f"All k8s resources for kanidm {name} have been deployed, waiting for pod to be ready"
        )
        done = False
        core = client.CoreV1Api()
        while not done:
            pods: list[V1Pod] = core.list_namespaced_pod(
                namespace,
                label_selector="app.kubernetes.io/name=kanidm",
            ).items

            if len(pods) == 0:
                logger.info(f"Waiting for kanidm {name} pod to be created")
                time.sleep(5)
                continue

            pod = pods[0]
            pod_status: V1PodStatus = pod.status

            if pod_status.phase != "Running":
                logger.info(
                    f"Waiting for kanidm {name} pod to be ready, current status: {pod_status.phase}"
                )
                time.sleep(5)
                continue

            logger.info(
                "Kanidm pod is running, trying to fetch admin and idm_admin passwords"
            )

            resp = stream(
                core.connect_get_namespaced_pod_exec,
                pod.metadata.name,
                namespace,
                container="kanidm",
                command=["kanidmd", "recover-account", "admin"],
                stderr=False,
                stdin=False,
                stdout=True,
                tty=False,
            )
            admin_password = parse_recover_account_password(resp)
            if admin_password is None:
                logger.info(
                    "Failed to parse admin password, perhaps kanidm is still booting? Retrying"
                )
                time.sleep(2)
                continue
            resp = stream(
                core.connect_get_namespaced_pod_exec,
                pod.metadata.name,
                namespace,
                container="kanidm",
                command=["kanidmd", "recover-account", "idm_admin"],
                stderr=False,
                stdin=False,
                stdout=True,
                tty=False,
            )
            idm_admin_password = parse_recover_account_password(resp)
            if idm_admin_password is None:
                logger.warning(
                    "Failed to parse idm_admin password, this should not happen!"
                )
                time.sleep(2)
                continue
            deployer.deploy(
                "usersecret.yaml",
                username="admin",
                password=admin_password,
            )
            deployer.deploy(
                "usersecret.yaml",
                username="idm_admin",
                password=idm_admin_password,
            )
            logger.info(
                "Kanidm admin and idm_admin passwords have been fetched and stored in secrets"
            )
            done = True

        patch.setdefault("metadata", {}).setdefault("annotations", {})[
            "kanidm.github.io/processed"
        ] = "true"
    except BaseException as exc:
        reconcile_error = exc
        raise
    finally:
        _finalize_kanidm_status(
            patch,
            meta,
            spec,
            namespace,
            "create",
            reconcile_error=reconcile_error,
            existing_status=status,
        )


@kopf.on.update("kanidm.github.io", "v1alpha1", "kanidms")
async def on_update_kanidms(
    spec: KanidmResource,
    old: dict,
    name: str,
    namespace: str,
    logger: Logger,
    patch: dict,
    meta: dict,
    status: dict | None = None,
    **kwargs,
):
    reconcile_error: BaseException | None = None
    try:
        old_spec = old.get("spec", {})
        if not spec_needs_reconcile(old_spec, spec):
            logger.debug(
                "Kanidm spec change does not require workload reconcile; refreshing status only"
            )
            return

        if old_spec.get("version") != spec.get("version"):
            validate_spec_version_upgrade(namespace, spec["version"], logger)

        logger.info(f"Reconciling kanidm instance {name} in namespace {namespace}")
        deployer = Deployer(namespace, spec["version"], logger)
        deploy_kanidm_reconciled_resources(deployer, spec)
    except BaseException as exc:
        reconcile_error = exc
        raise
    finally:
        _finalize_kanidm_status(
            patch,
            meta,
            spec,
            namespace,
            "update",
            reconcile_error=reconcile_error,
            existing_status=status,
        )


@kopf.on.resume("kanidm.github.io", "v1alpha1", "kanidms")
async def on_resume_kanidms(
    spec: KanidmResource,
    name: str,
    namespace: str,
    logger: Logger,
    patch: dict,
    meta: dict,
    status: dict | None = None,
    **kwargs,
):
    reconcile_error: BaseException | None = None
    try:
        if not deployment_version_drifts_from_spec(namespace, spec["version"]):
            logger.debug(
                "Kanidm Deployment image matches spec.version on resume; skipping drift reconcile"
            )
            return

        logger.info(
            "Kanidm Deployment image drifts from spec.version on resume for %s/%s",
            namespace,
            name,
        )
        validate_spec_version_upgrade(namespace, spec["version"], logger)
        deployer = Deployer(namespace, spec["version"], logger)
        deploy_kanidm_version_drift_resources(deployer, spec)
    except BaseException as exc:
        reconcile_error = exc
        raise
    finally:
        _finalize_kanidm_status(
            patch,
            meta,
            spec,
            namespace,
            "resume",
            reconcile_error=reconcile_error,
            existing_status=status,
        )
