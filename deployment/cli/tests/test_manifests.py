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


def test_deployer_can_port_forward_and_only_patch_heal_secrets() -> None:
    (role,) = [d for d in docs("rbac/deployer.yaml") if d["kind"] == "Role"]
    resources = {r for rule in role["rules"] for r in rule["resources"]}
    assert "pods/portforward" in resources
    (rule,) = [r for r in role["rules"] if "secrets" in r["resources"]]
    assert rule["resources"] == ["secrets"]
    assert rule["resourceNames"] == ["heal-secrets"]
    assert rule["verbs"] == ["patch"]


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
        d
        for d in docs("api_server-service-deployment.yaml")
        if d["kind"] == "Deployment"
    ]
    (container,) = deployment["spec"]["template"]["spec"]["containers"]
    ref = _env(container)["QDRANT_API_KEY"]["valueFrom"]["secretKeyRef"]
    assert (ref["name"], ref["key"]) == ("heal-secrets", "qdrant_api_key")

    (configmap,) = docs("env-configmap.yaml")
    assert configmap["data"]["QDRANT_URL"] == "http://qdrant-service:6333"
    assert "QDRANT_API_KEY" not in configmap["data"]
    assert "qdrant_api_key" in SCRIPT.read_text()


# env var -> heal-secrets key. Only SECRET is required: empty, it signs reset
# and verification tokens with a known key.
API_SERVER_SECRETS = {
    "POSTGRES_USER": "postgres_user",
    "POSTGRES_PASSWORD": "postgres_password",
    "GEN_AI_API_KEY": "gen_ai_api_key",
    "QDRANT_API_KEY": "qdrant_api_key",
    "SECRET": "user_auth_secret",
    "TRANSLATION_API_KEY": "translation_api_key",
    "HEAL_SELF_HOSTED_API_KEY": "self_hosted_api_key",
    "SMTP_PASS": "smtp_pass",
    "HEAL_BOOTSTRAP_ADMIN_EMAIL": "bootstrap_admin_email",
    "HEAL_BOOTSTRAP_ADMIN_PASSWORD": "bootstrap_admin_password",
    "GOOGLE_OAUTH_CLIENT_ID": "google_oauth_client_id",
    "GOOGLE_OAUTH_CLIENT_SECRET": "google_oauth_client_secret",
}


def test_api_server_reads_every_credential_from_heal_secrets() -> None:
    (deployment,) = [
        d
        for d in docs("api_server-service-deployment.yaml")
        if d["kind"] == "Deployment"
    ]
    (container,) = deployment["spec"]["template"]["spec"]["containers"]
    env = _env(container)
    for name, key in API_SERVER_SECRETS.items():
        ref = env[name]["valueFrom"]["secretKeyRef"]
        assert (ref["name"], ref["key"]) == ("heal-secrets", key), name
    assert not env["SECRET"]["valueFrom"]["secretKeyRef"].get("optional", False)

    # Every key is documented in the template, and the required one is generated.
    template = (BASE_DIR / "secrets.yaml").read_text()
    for key in API_SERVER_SECRETS.values():
        assert f"  {key}:" in template, key
    assert "user_auth_secret=" in SCRIPT.read_text()


def test_deploy_secrets_offers_only_keys_the_api_server_reads() -> None:
    from heal_deploy.cluster import SECRET_KEYS

    assert set(SECRET_KEYS) <= set(API_SERVER_SECRETS.values())
    assert {"user_auth_secret", "qdrant_api_key"} <= set(SECRET_KEYS)
    assert not {"postgres_user", "postgres_password"} & set(SECRET_KEYS)


def test_configmap_carries_settings_not_credentials() -> None:
    (configmap,) = docs("env-configmap.yaml")
    data = configmap["data"]
    for name in (
        "TRANSLATION_EN_URL",
        "TRANSLATION_LUG_URL",
        "HEAL_SELF_HOSTED_URL",
        "HEAL_SELF_HOSTED_MODEL",
        "QDRANT_URL",
    ):
        assert name in data, name
    assert not set(API_SERVER_SECRETS) & set(data)
