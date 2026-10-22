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


def _env(container: dict) -> dict[str, dict]:
    return {e["name"]: e for e in container.get("env", [])}


def test_qdrant_is_deployed_internal_only_and_keyed() -> None:
    kustomization = yaml.safe_load((BASE_DIR / "kustomization.yaml").read_text())
    assert "qdrant-service-deployment.yaml" in kustomization["resources"]

    by_kind = {d["kind"]: d for d in docs("qdrant-service-deployment.yaml")}
    assert by_kind["Service"]["spec"]["type"] == "ClusterIP"
    (container,) = by_kind["StatefulSet"]["spec"]["template"]["spec"]["containers"]
    assert container["image"] == "qdrant/qdrant:v1.19.0"
    ref = _env(container)["QDRANT__SERVICE__API_KEY"]["valueFrom"]["secretKeyRef"]
    assert ref["name"] == "heal-secrets"
    assert ref["key"] == "qdrant_api_key"
    assert not ref.get("optional", False)


def test_api_server_shares_the_qdrant_key_and_url() -> None:
    (deployment,) = [
        d for d in docs("api_server-service-deployment.yaml") if d["kind"] == "Deployment"
    ]
    (container,) = deployment["spec"]["template"]["spec"]["containers"]
    ref = _env(container)["QDRANT_API_KEY"]["valueFrom"]["secretKeyRef"]
    assert (ref["name"], ref["key"]) == ("heal-secrets", "qdrant_api_key")

    (configmap,) = docs("env-configmap.yaml")
    assert configmap["data"]["QDRANT_URL"] == "http://qdrant-service:6333"
    assert "QDRANT_API_KEY" not in configmap["data"]
    assert "qdrant_api_key" in SCRIPT.read_text()
