from pathlib import Path

import pytest

from heal_deploy.config import ConfigError
from heal_deploy.config import load
from heal_deploy.config import parse_env_file

REQUIRED = {
    "DEPLOY_API_SERVER": "https://heal-node.internal:6443/",
    "DEPLOY_KUBE_TOKEN": "s3cret-token",
    "DEPLOY_KUBE_CA": "~/heal-ca.crt",
    "DEPLOY_NAMESPACE": "heal",
}


class TestParseEnvFile:
    def test_skips_comments_and_strips_quotes_and_trailing_comments(self) -> None:
        text = '# note\n\nA="one"\nB=two  # why\nC=\n'
        assert parse_env_file(text) == {"A": "one", "B": "two", "C": ""}


class TestLoad:
    def test_environment_overrides_the_file(self, tmp_path: Path) -> None:
        env_file = tmp_path / "deploy.env"
        env_file.write_text("DEPLOY_NAMESPACE=from-file\n")
        cfg = load(env_file, {**REQUIRED, "DEPLOY_NAMESPACE": "from-env"})
        assert cfg.namespace == "from-env"

    def test_an_empty_variable_keeps_the_file_value(self, tmp_path: Path) -> None:
        env_file = tmp_path / "deploy.env"
        env_file.write_text("DEPLOY_KUBE_TOKEN=from-file\n")
        cfg = load(env_file, {**REQUIRED, "DEPLOY_KUBE_TOKEN": ""})
        assert cfg.kube_token == "from-file"

    def test_applies_defaults(self, tmp_path: Path) -> None:
        cfg = load(tmp_path / "absent.env", REQUIRED)
        assert cfg.api_server_url == "https://heal-node.internal:6443"
        assert not cfg.kube_ca.startswith("~")
        assert cfg.registry == "localhost:5050"
        assert (cfg.remote, cfg.branch, cfg.platform) == (
            "origin",
            "main",
            "linux/amd64",
        )
        assert not cfg.signing

    def test_names_every_missing_required_value(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError) as error:
            load(tmp_path / "absent.env", {"DEPLOY_NAMESPACE": "heal"})
        assert "DEPLOY_API_SERVER, DEPLOY_KUBE_TOKEN, DEPLOY_KUBE_CA" in str(
            error.value
        )

    def test_refuses_plain_http(self, tmp_path: Path) -> None:
        env = {**REQUIRED, "DEPLOY_API_SERVER": "http://heal-node.internal:6443"}
        with pytest.raises(ConfigError, match="https"):
            load(tmp_path / "absent.env", env)

    def test_keeps_the_token_out_of_repr(self, tmp_path: Path) -> None:
        cfg = load(tmp_path / "absent.env", REQUIRED)
        assert cfg.kube_token == "s3cret-token"
        assert "s3cret-token" not in repr(cfg)

    def test_signing_key_needs_the_public_key(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="DEPLOY_COSIGN_PUBKEY"):
            load(tmp_path / "absent.env", {**REQUIRED, "DEPLOY_COSIGN_KEY": "k"})

    def test_signs_when_keyed(self, tmp_path: Path) -> None:
        env = {**REQUIRED, "DEPLOY_COSIGN_KEY": "k", "DEPLOY_COSIGN_PUBKEY": "p"}
        assert load(tmp_path / "absent.env", env).signing

    def test_torch_variant_defaults_to_cpu_and_is_validated(
        self, tmp_path: Path
    ) -> None:
        assert load(tmp_path / "absent.env", REQUIRED).torch_variant == "cpu"
        with pytest.raises(ConfigError, match="DEPLOY_TORCH_VARIANT"):
            load(tmp_path / "absent.env", {**REQUIRED, "DEPLOY_TORCH_VARIANT": "rocm"})
