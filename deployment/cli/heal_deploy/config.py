"""Deploy settings, from deployment/deploy.env with the environment on top.

Everything goes through the k3s API as the heal-deployer service account:
manifests are applied with its token, and images are pushed to the registry
inside k3s through a port-forward on the same API. No SSH, no other registry.

No setting has an address default: the API URL is specific to one cluster and
must be written down by whoever owns it.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from dataclasses import field
from pathlib import Path
from typing import Mapping

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_ENV_FILE = REPO_ROOT / "deployment" / "deploy.env"

REQUIRED = (
    "DEPLOY_API_SERVER",
    "DEPLOY_KUBE_TOKEN",
    "DEPLOY_KUBE_CA",
    "DEPLOY_NAMESPACE",
)

# Must match kubernetes/registry/registry.yaml. The same port on both ends of
# the port-forward, so one image name is valid on this machine and on the node.
CLUSTER_REGISTRY_PORT = 5050

# The backend's PyTorch build; see TORCH_VARIANT in backend/Dockerfile.
TORCH_VARIANTS = ("cpu", "cuda")


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    api_server_url: str
    kube_ca: str
    namespace: str
    remote: str
    branch: str
    platform: str
    fail_severity: str
    cosign_key: str
    cosign_pubkey: str
    torch_variant: str
    state_dir: Path
    # repr=False keeps the token out of tracebacks and debug prints.
    kube_token: str = field(default="", repr=False)
    # Written per command by cluster.credentials(); empty until then.
    kubeconfig: str = ""

    @property
    def registry(self) -> str:
        return f"localhost:{CLUSTER_REGISTRY_PORT}"

    @property
    def signing(self) -> bool:
        return bool(self.cosign_key)


def parse_env_file(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        # Trailing comments are allowed only after whitespace, so a `#` inside
        # a value (rare, but legal in a URL fragment) survives.
        value = value.split(" #", 1)[0].strip().strip('"').strip("'")
        values[key.strip()] = value
    return values


def load(
    env_file: Path = DEFAULT_ENV_FILE, environ: Mapping[str, str] = os.environ
) -> Config:
    values = parse_env_file(env_file.read_text()) if env_file.exists() else {}
    # An empty variable does not blank the file's value: `make` always passes
    # DEPLOY_KUBE_TOKEN, empty when the Keychain has none.
    values.update({k: v for k, v in environ.items() if k.startswith("DEPLOY_") and v})

    missing = [key for key in REQUIRED if not values.get(key)]
    if missing:
        raise ConfigError(
            f"missing {', '.join(missing)}; copy deployment/deploy.env.template "
            "to deployment/deploy.env and fill it in"
        )

    api_server_url = values["DEPLOY_API_SERVER"].rstrip("/")
    if not api_server_url.startswith("https://"):
        raise ConfigError("DEPLOY_API_SERVER must be an https:// URL")

    cosign_key = os.path.expanduser(values.get("DEPLOY_COSIGN_KEY", ""))
    cosign_pubkey = os.path.expanduser(values.get("DEPLOY_COSIGN_PUBKEY", ""))
    if cosign_key and not cosign_pubkey:
        raise ConfigError(
            "DEPLOY_COSIGN_KEY is set, so DEPLOY_COSIGN_PUBKEY is required: "
            "every signature is verified before it is deployed"
        )

    torch_variant = values.get("DEPLOY_TORCH_VARIANT") or "cpu"
    if torch_variant not in TORCH_VARIANTS:
        raise ConfigError(
            f"DEPLOY_TORCH_VARIANT must be one of {', '.join(TORCH_VARIANTS)}, "
            f"got {torch_variant!r}"
        )

    return Config(
        api_server_url=api_server_url,
        kube_ca=os.path.expanduser(values["DEPLOY_KUBE_CA"]),
        kube_token=values["DEPLOY_KUBE_TOKEN"],
        namespace=values["DEPLOY_NAMESPACE"],
        remote=values.get("DEPLOY_GIT_REMOTE") or "origin",
        branch=values.get("DEPLOY_BRANCH") or "main",
        platform=values.get("DEPLOY_PLATFORM") or "linux/amd64",
        fail_severity=values.get("DEPLOY_FAIL_SEVERITY") or "CRITICAL,HIGH",
        cosign_key=cosign_key,
        cosign_pubkey=cosign_pubkey,
        torch_variant=torch_variant,
        state_dir=Path(
            values.get("DEPLOY_STATE_DIR") or REPO_ROOT / "deployment" / ".deploy"
        ),
    )
