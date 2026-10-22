"""The one-time server setup: everything in `heal`, the deployer kept narrow,
and the setup script unable to blank a cluster's real settings."""
import subprocess

import pytest

from heal_deploy.cluster import BASE_DIR
from heal_deploy.cluster import REGISTRY_DEPLOYMENT
from heal_deploy.config import CLUSTER_REGISTRY_PORT

yaml = pytest.importorskip("yaml")

SCRIPT = BASE_DIR / "setup-server.sh"


def docs(name: str) -> list[dict]:
    return [d for d in yaml.safe_load_all((BASE_DIR / name).read_text()) if d]


def test_everything_lives_in_the_heal_namespace() -> None:
    for name in ("rbac/deployer.yaml", "registry/registry.yaml"):
        for doc in docs(name):
            if doc["kind"] != "Namespace":
                assert doc["metadata"]["namespace"] == "heal", (name, doc["kind"])


def test_deployer_can_port_forward_but_never_read_secrets() -> None:
    (role,) = [d for d in docs("rbac/deployer.yaml") if d["kind"] == "Role"]
    resources = {r for rule in role["rules"] for r in rule["resources"]}
    assert "pods/portforward" in resources
    assert "secrets" not in resources


def test_registry_listens_on_loopback_at_the_cli_port() -> None:
    (deployment,) = [
        d for d in docs("registry/registry.yaml") if d["kind"] == "Deployment"
    ]
    assert deployment["metadata"]["name"] == REGISTRY_DEPLOYMENT
    (container,) = deployment["spec"]["template"]["spec"]["containers"]
    env = {e["name"]: e["value"] for e in container["env"]}
    assert env["REGISTRY_HTTP_ADDR"] == f"localhost:{CLUSTER_REGISTRY_PORT}"
    assert f'"localhost:{CLUSTER_REGISTRY_PORT}"' in SCRIPT.read_text()


def test_setup_script_parses_and_never_applies_secrets_yaml() -> None:
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    text = SCRIPT.read_text()
    assert "secrets.yaml" not in text
    # Settings and secrets are only ever created when absent.
    assert "get configmap env-configmap" in text
    assert "get secret heal-secrets" in text
