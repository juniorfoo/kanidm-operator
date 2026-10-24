"""Shared helpers for end-to-end verification of the operator."""

from __future__ import annotations

import base64
import json
import os
import ssl
import subprocess
import time
import urllib.error
import urllib.request
import yaml

from kanidm_operator.kanidm_cli_cache import isolated_kanidm_cli_env

KANIDM_NAMESPACE = "kanidm"
KANIDM_DOMAIN = "idm.example.com"
KANIDM_VERSION = "1.10.5"

KANIDM_AUTH_READY_TIMEOUT_S = 120.0
KANIDM_AUTH_POLL_INTERVAL_S = 2.0
KANIDM_LOGIN_503_RETRIES = 5


def major_minor(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2:
        raise ValueError(f"invalid version: {version}")
    return f"{parts[0]}.{parts[1]}"


def _resolve_ca_bundle(env: dict[str, str]) -> str | None:
    for key in ("KANIDM_CA_PATH", "REQUESTS_CA_BUNDLE"):
        path = env.get(key) or os.environ.get(key)
        if path and os.path.isfile(path):
            return path
    project_ca = os.path.join(
        os.path.dirname(__file__), "..", "KanidmCA.crt"
    )
    if os.path.isfile(project_ca):
        return os.path.abspath(project_ca)
    system_ca = "/etc/ssl/certs/ca-certificates.crt"
    if os.path.isfile(system_ca):
        return system_ca
    return None


def _status_online(status_url: str, ca_bundle: str | None) -> bool:
    ctx = ssl.create_default_context(cafile=ca_bundle) if ca_bundle else ssl.create_default_context()
    try:
        with urllib.request.urlopen(status_url, context=ctx, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, ValueError):
        return False
    if isinstance(payload, bool):
        return payload
    if isinstance(payload, dict):
        return payload.get("status") is True
    return False


def _login_transient_503(combined_output: str) -> bool:
    return "503" in combined_output and (
        "missing_kopid" in combined_output or "Http(503" in combined_output
    )


def wait_for_kanidm_auth_ready(
    kanidm_exec: str,
    env: dict[str, str],
    *,
    timeout: float = KANIDM_AUTH_READY_TIMEOUT_S,
    interval: float = KANIDM_AUTH_POLL_INTERVAL_S,
) -> None:
    """Poll until /status is true and kanidm login is not rejected with HTTP 503."""
    status_url = f"{env['KANIDM_URL'].rstrip('/')}/status"
    ca_bundle = _resolve_ca_bundle(env)
    deadline = time.monotonic() + timeout
    last_login_error = ""

    while time.monotonic() < deadline:
        if not _status_online(status_url, ca_bundle):
            time.sleep(interval)
            continue

        probe = subprocess.run(
            [kanidm_exec, "login"],
            env=env,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return

        combined = f"{probe.stderr or ''}{probe.stdout or ''}"
        if _login_transient_503(combined):
            last_login_error = combined.strip()
            time.sleep(interval)
            continue

        raise AssertionError(
            f"kanidm login failed while waiting for auth readiness: {combined.strip()}"
        )

    detail = last_login_error or "GET /status never reported ready=true"
    raise AssertionError(
        f"Kanidm auth endpoint not ready after {timeout}s ({detail})"
    )


def kubectl(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["kubectl", *args],
        capture_output=True,
        text=True,
        check=check,
    )


def kubectl_json(*args: str) -> dict:
    result = kubectl(*args, "-o", "json")
    return json.loads(result.stdout)


def secret_data(namespace: str, name: str, key: str) -> str:
    secret = kubectl_json("get", "secret", name, "-n", namespace)
    return base64.b64decode(secret["data"][key]).decode("utf-8")


def assert_kanidm_cr_status(
    version: str = KANIDM_VERSION,
    *,
    ready: bool = True,
    reconcile_result: str = "Success",
    timeout: float = 120.0,
    interval: float = 2.0,
) -> None:
    """Assert the Kanidm CR status reflects a reconciled server."""
    deadline = time.monotonic() + timeout
    last_error: AssertionError | None = None
    while time.monotonic() < deadline:
        try:
            cr = kubectl_json("get", "kanidm", "kanidm-instance", "-n", KANIDM_NAMESPACE)
            status = cr.get("status") or {}
            assert status.get("version") == version, status
            assert status.get("image") == f"kanidm/server:{version}", status
            assert status.get("lastReconcileResult") == reconcile_result, status
            conditions = {item["type"]: item for item in status.get("conditions", [])}
            assert conditions["Ready"]["status"] == ("True" if ready else "False"), conditions
            assert conditions["Degraded"]["status"] == (
                "False" if ready else "True"
            ), conditions
            annotations = cr.get("metadata", {}).get("annotations", {})
            for key, value in annotations.items():
                if key.startswith("kopf.zalando.org/") and value:
                    assert "422" not in value, f"stale kopf annotation {key}: {value}"
            return
        except AssertionError as exc:
            last_error = exc
            time.sleep(interval)
    if last_error is not None:
        raise last_error
    raise AssertionError("Kanidm CR status was not populated")


def wait_processed(resource: str, name: str, timeout: str = "180s") -> None:
    kubectl(
        "wait",
        "-n",
        KANIDM_NAMESPACE,
        resource,
        name,
        "--for=jsonpath={.metadata.annotations.kanidm\\.github\\.io/processed}=true",
        f"--timeout={timeout}",
    )


class KanidmVerifier:
    """Log into Kanidm and assert server-side state via the CLI."""

    def __init__(self) -> None:
        self.kanidm_exec = os.environ.get("KANIDM_EXEC", "kanidm")
        base_env = os.environ.copy()
        password = secret_data(KANIDM_NAMESPACE, "idm-admin-credentials", "password")
        base_env.update(
            {
                "KANIDM_URL": f"https://{KANIDM_DOMAIN}",
                "KANIDM_NAME": "idm_admin",
                "KANIDM_PASSWORD": password,
            }
        )
        ca_path = os.environ.get("KANIDM_CA_PATH")
        if ca_path:
            base_env["KANIDM_CA_PATH"] = ca_path
        self.env, self._kanidm_cli_cache = isolated_kanidm_cli_env(base_env)
        wait_for_kanidm_auth_ready(self.kanidm_exec, self.env)
        self._login()

    def _login(self) -> None:
        last_combined = ""
        for attempt in range(1, KANIDM_LOGIN_503_RETRIES + 1):
            result = subprocess.run(
                [self.kanidm_exec, "login"],
                env=self.env,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                return
            last_combined = f"{result.stderr or ''}{result.stdout or ''}".strip()
            if attempt < KANIDM_LOGIN_503_RETRIES and _login_transient_503(
                last_combined
            ):
                time.sleep(KANIDM_AUTH_POLL_INTERVAL_S)
                continue
            break
        raise AssertionError(f"kanidm login failed: {last_combined}")

    def kanidm(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.kanidm_exec, *args],
            env=self.env,
            capture_output=True,
            text=True,
        )

    def assert_person(self, username: str, display_name: str, emails: list[str]) -> None:
        result = self.kanidm("person", "get", "-o", "json", username)
        assert result.returncode == 0, result.stderr or result.stdout
        assert "No matching entries" not in result.stdout, result.stdout

        data = json.loads(result.stdout)
        assert isinstance(data, dict), data
        attrs = data["attrs"]
        assert attrs["displayname"] == [display_name]
        for email in emails:
            assert email in attrs.get("mail", []), attrs.get("mail")

    def assert_group(self, name: str, members: list[str]) -> None:
        result = self.kanidm("group", "get", "-o", "json", name)
        assert result.returncode == 0, result.stderr or result.stdout

        output = result.stdout.strip()
        if "No matching group" in output:
            raise AssertionError(f"group {name!r} does not exist in Kanidm")

        data = json.loads(output)
        if isinstance(data, str):
            raise AssertionError(f"group {name!r} does not exist in Kanidm: {data}")

        group_members = data["attrs"].get("member", [])
        for member in members:
            matched = any(
                group_member == member
                or group_member.startswith(f"{member}@")
                for group_member in group_members
            )
            assert matched, group_members

    def assert_oauth2_client(self, name: str, display_name: str, origin: str) -> None:
        result = self.kanidm("system", "oauth2", "get", name)
        assert result.returncode == 0, result.stderr or result.stdout
        assert "No matching entries" not in result.stdout, result.stdout

        output = result.stdout.lstrip("-\n")
        skip_prefixes = ("oauth2_rs_scope_map:", "key_internal_data:")
        output = "\n".join(
            line for line in output.split("\n") if not line.startswith(skip_prefixes)
        )
        data = yaml.safe_load(output)
        assert data is not None, result.stdout
        rendered = yaml.safe_dump(data)
        assert display_name in rendered, rendered
        assert origin in rendered, rendered

    def assert_oauth2_k8s_secret(self, client_name: str, secret_name: str) -> None:
        result = self.kanidm("system", "oauth2", "show-basic-secret", client_name)
        assert result.returncode == 0, result.stderr or result.stdout
        kanidm_secret = result.stdout.strip()

        stored_secret = secret_data(KANIDM_NAMESPACE, secret_name, "secret")
        stored_client_id = secret_data(KANIDM_NAMESPACE, secret_name, "key")
        assert kanidm_secret == stored_secret
        assert stored_client_id == client_name


def assert_kanidm_deployment(version: str = KANIDM_VERSION) -> None:
    deployment = kubectl_json("get", "deployment", "kanidm", "-n", KANIDM_NAMESPACE)
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    assert container["image"] == f"kanidm/server:{version}"
    assert deployment["status"].get("readyReplicas") == 1
    strategy = deployment["spec"]["strategy"]
    assert strategy["type"] == "Recreate"
    assert "rollingUpdate" not in strategy


def stamp_legacy_rolling_update_deployment(image_tag: str = "1.10.3") -> None:
    """Simulate Deployments created by pre-Recreate operator versions."""
    kubectl(
        "patch",
        "deployment",
        "kanidm",
        "-n",
        KANIDM_NAMESPACE,
        "--type=strategic",
        "-p",
        json.dumps(
            {
                "spec": {
                    "strategy": {
                        "type": "RollingUpdate",
                        "rollingUpdate": {
                            "maxSurge": "25%",
                            "maxUnavailable": "25%",
                        },
                    },
                    "template": {
                        "spec": {
                            "containers": [
                                {
                                    "name": "kanidm",
                                    "image": f"kanidm/server:{image_tag}",
                                }
                            ]
                        }
                    },
                }
            }
        ),
    )


def stamp_kopf_last_handled_configuration(resource: str, name: str) -> None:
    """Make kopf believe the current CR body is already handled (Joe's drift scenario)."""
    import kopf
    from kopf._cogs.configs.diffbase import StatusDiffBaseStorage

    cr = kubectl_json("get", resource, name, "-n", KANIDM_NAMESPACE)
    storage = StatusDiffBaseStorage(name="kopf")
    essence = storage.build(body=kopf.Body(cr))
    encoded = json.dumps(essence, separators=(",", ":"))
    kubectl(
        "patch",
        resource,
        name,
        "-n",
        KANIDM_NAMESPACE,
        "--type=merge",
        "-p",
        json.dumps(
            {
                "status": {
                    "kopf": {"last-handled-configuration": encoded},
                }
            }
        ),
    )


def stamp_kopf_failure_annotation(handler_id: str, message: str) -> None:
    """Simulate a stale kopf progress annotation from a prior failed reconcile."""
    kubectl(
        "patch",
        "kanidm",
        "kanidm-instance",
        "-n",
        KANIDM_NAMESPACE,
        "--type=merge",
        "-p",
        json.dumps(
            {
                "metadata": {
                    "annotations": {
                        f"kopf.zalando.org/{handler_id}": json.dumps(
                            {
                                "failure": True,
                                "success": False,
                                "message": message,
                            }
                        ),
                    }
                }
            }
        ),
    )


def deployment_image_version() -> str:
    deployment = kubectl_json("get", "deployment", "kanidm", "-n", KANIDM_NAMESPACE)
    image = deployment["spec"]["template"]["spec"]["containers"][0]["image"]
    return image.split(":", 1)[1]


def assert_kanidm_configmap() -> None:
    configmap = kubectl_json("get", "configmap", "kanidm-config", "-n", KANIDM_NAMESPACE)
    server_toml = configmap["data"]["server.toml"]
    assert 'version = "2"' in server_toml
    assert "[http_client_address_info]" in server_toml
    assert f'domain = "{KANIDM_DOMAIN}"' in server_toml
    assert 'db_path = "/db/kanidm.db"' in server_toml


def assert_kanidm_ingress() -> None:
    ingress = kubectl_json("get", "ingress", "kanidm-ingress", "-n", KANIDM_NAMESPACE)
    rules = ingress["spec"]["rules"]
    assert any(rule["host"] == KANIDM_DOMAIN for rule in rules)
    assert ingress["spec"].get("ingressClassName") == "nginx"


def assert_admin_secrets() -> None:
    for secret_name in ("admin-credentials", "idm-admin-credentials"):
        secret = kubectl_json("get", "secret", secret_name, "-n", KANIDM_NAMESPACE)
        assert "password" in secret["data"]
        assert len(secret_data(KANIDM_NAMESPACE, secret_name, "password")) >= 8


def assert_https_reachable(ca_bundle: str) -> None:
    result = subprocess.run(
        ["curl", "-sI", "--cacert", ca_bundle, f"https://{KANIDM_DOMAIN}"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr.strip() or result.stdout.strip()
    status_line = result.stdout.splitlines()[0] if result.stdout else ""
    assert status_line.startswith("HTTP/"), status_line
