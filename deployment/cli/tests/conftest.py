import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from heal_deploy.config import Config  # noqa: E402


@pytest.fixture
def cfg(tmp_path: Path) -> Config:
    return Config(
        api_server_url="https://heal-node.internal:6443",
        kube_ca=str(tmp_path / "ca.crt"),
        kube_token="s3cret-token",
        kubeconfig="/kube/deployer.yaml",
        namespace="heal",
        remote="origin",
        branch="main",
        platform="linux/amd64",
        fail_severity="CRITICAL,HIGH",
        cosign_key="",
        cosign_pubkey="",
        torch_variant="cpu",
        state_dir=tmp_path / ".deploy",
    )
