from kanidm_operator.deployer import prepare_deployment_patch_body


def test_prepare_deployment_patch_body_clears_rolling_update_for_recreate() -> None:
    body = {
        "metadata": {"name": "kanidm"},
        "spec": {
            "strategy": {"type": "Recreate"},
            "template": {"spec": {"containers": [{"name": "kanidm", "image": "x"}]}},
        },
    }
    patched = prepare_deployment_patch_body(body)
    assert patched["spec"]["strategy"] == {"type": "Recreate", "rollingUpdate": None}
    assert body["spec"]["strategy"] == {"type": "Recreate"}


def test_prepare_deployment_patch_body_unchanged_for_other_strategies() -> None:
    body = {
        "spec": {
            "strategy": {
                "type": "RollingUpdate",
                "rollingUpdate": {"maxSurge": "25%"},
            }
        }
    }
    assert prepare_deployment_patch_body(body) is body
