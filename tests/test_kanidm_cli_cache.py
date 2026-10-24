import os
import subprocess
import tempfile

import pytest

from kanidm_operator.kanidm_cli_cache import isolated_kanidm_cli_env


def test_isolated_kanidm_cli_env_uses_private_home() -> None:
    env, holder = isolated_kanidm_cli_env({"KANIDM_URL": "https://example.test"})
    try:
        assert env["KANIDM_URL"] == "https://example.test"
        assert env["HOME"] != os.environ.get("HOME")
        assert os.path.isdir(env["HOME"])
        assert os.path.basename(env["HOME"]).startswith("kanidm-cli-cache-")
        token_path = os.path.join(env["HOME"], ".cache", "kanidm_tokens")
        assert token_path.startswith(env["HOME"])
    finally:
        holder.cleanup()


def test_isolated_kanidm_cli_env_instances_do_not_share_home() -> None:
    env_a, holder_a = isolated_kanidm_cli_env({})
    env_b, holder_b = isolated_kanidm_cli_env({})
    try:
        assert env_a["HOME"] != env_b["HOME"]
    finally:
        holder_a.cleanup()
        holder_b.cleanup()


def test_kanidm_verifier_subprocess_env_carries_isolated_home(monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.helpers import KanidmVerifier

    monkeypatch.setattr("tests.helpers.secret_data", lambda *_args, **_kwargs: "secret")
    monkeypatch.setattr("tests.helpers.wait_for_kanidm_auth_ready", lambda *_a, **_k: None)

    captured_envs: list[dict[str, str]] = []

    def fake_run(cmd, env=None, **_kwargs):
        captured_envs.append(dict(env or {}))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    verifier = KanidmVerifier()
    verifier.kanidm("person", "get", "nobody")

    real_home = os.environ.get("HOME")
    for env in captured_envs:
        assert env["HOME"] != real_home
        assert env["HOME"].startswith(tempfile.gettempdir())
        assert os.path.basename(env["HOME"]).startswith("kanidm-cli-cache-")

    assert captured_envs[0]["HOME"] == captured_envs[1]["HOME"]
