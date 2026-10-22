import json
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path

import pytest
from fakes import FakeRunner

from heal_deploy import __main__ as cli
from heal_deploy import gates
from heal_deploy import images
from heal_deploy.config import Config

DIGEST = "sha256:" + "b" * 64
TAG = "0123456789ab"


@pytest.fixture(autouse=True)
def stable_packages(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gates, "check_stable_packages", lambda root: [])


@pytest.fixture(autouse=True)
def forwarded(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The forward has its own tests; here it would open a real port."""
    opened: list[str] = []
    monkeypatch.setattr(
        cli.cluster,
        "registry_forward",
        lambda cfg, runner: opened.append(cfg.namespace) or nullcontext(),
    )
    return opened


def _runner() -> FakeRunner:
    return FakeRunner(
        outputs={
            "rev-parse HEAD": "0123456789abcdef0123",
            "{{.Os}}/{{.Architecture}}": "linux/amd64",
            "crane digest": DIGEST,
            "user.email": "deployer@example.org",
            "kustomize": f"image: localhost:5050/heal-web@{DIGEST}\n"
            f"image: localhost:5050/heal-backend@{DIGEST}",
        }
    )


class TestDeploy:
    def test_gate_failure_stops_before_building(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"status": " M web/app.tsx"})
        assert cli.cmd_deploy(runner, cfg, ask=lambda _: "heal") == 1
        assert not runner.ran("docker build")

    def test_vulnerable_dependency_stops_before_building(self, cfg: Config) -> None:
        runner = FakeRunner(fail=["trivy fs"])
        with pytest.raises(Exception):
            cli.cmd_deploy(runner, cfg, ask=lambda _: "heal")
        assert not runner.ran("docker build")

    def test_wrong_confirmation_pushes_nothing(
        self, cfg: Config, forwarded: list[str]
    ) -> None:
        runner = _runner()
        assert cli.cmd_deploy(runner, cfg, ask=lambda _: "yes") == 1
        assert runner.ran("docker build") and runner.ran("trivy image")
        assert not forwarded
        assert not runner.ran("crane push")
        assert not runner.ran("apply")

    def test_confirmed_deploy_pushes_applies_and_records(
        self, cfg: Config, forwarded: list[str]
    ) -> None:
        runner = _runner()
        assert cli.cmd_deploy(runner, cfg, ask=lambda _: "heal") == 0
        assert forwarded == ["heal"]
        assert runner.ran("crane push") and runner.ran(f"localhost:5050/heal-web:{TAG}")
        assert not any(call.startswith(("ssh", "docker push")) for call in runner.calls)
        assert runner.ran("--dry-run=server")
        assert runner.ran(f"kubernetes.io/change-cause={TAG} by deployer@example.org")
        overlay = (cfg.state_dir / "overlay" / "kustomization.yaml").read_text()
        assert f"digest: {DIGEST}" in overlay
        entry = json.loads((cfg.state_dir / "history.jsonl").read_text())
        assert entry["outcome"] == "deployed"
        assert entry["cluster"] == cfg.api_server_url
        assert entry["images"]["heal-web"] == f"localhost:5050/heal-web@{DIGEST}"
        assert Path(entry["manifest"]).exists()

    def test_unchecked_deploy_skips_gates_and_scans(
        self, cfg: Config, forwarded: list[str]
    ) -> None:
        runner = _runner()
        runner.outputs["status"] = " M web/app.tsx"
        assert cli.cmd_deploy(runner, cfg, ask=lambda _: "heal", checked=False) == 0
        assert not runner.ran("trivy")
        assert runner.ran("docker build") and runner.ran("crane push")
        entry = json.loads((cfg.state_dir / "history.jsonl").read_text())
        assert entry["checked"] is False

    def test_unchecked_deploy_confirms_the_namespace_itself(
        self, cfg: Config, forwarded: list[str]
    ) -> None:
        runner = _runner()
        assert cli.cmd_deploy_unchecked(runner, cfg) == 0
        assert forwarded == ["heal"] and runner.ran("crane push")

    def test_signing_verifies_each_digest_before_deploying(self, cfg: Config) -> None:
        runner = _runner()
        signed = replace(cfg, cosign_key="cosign.key", cosign_pubkey="cosign.pub")
        assert cli.cmd_deploy(runner, signed, ask=lambda _: "heal") == 0
        verify = max(
            i for i, c in enumerate(runner.calls) if c.startswith("cosign verify")
        )
        apply = min(i for i, c in enumerate(runner.calls) if "apply" in c)
        assert verify < apply
        assert runner.ran("--use-signing-config=false --tlog-upload=false")

    def test_failed_push_applies_nothing(self, cfg: Config) -> None:
        runner = _runner()
        runner.fail = ["crane push"]
        with pytest.raises(Exception):
            cli.cmd_deploy(runner, cfg, ask=lambda _: "heal")
        assert not runner.ran("apply")


class TestPlatform:
    def test_an_arm_build_for_an_amd_cluster_stops_the_deploy(
        self, cfg: Config
    ) -> None:
        runner = _runner()
        runner.outputs["{{.Os}}/{{.Architecture}}"] = "linux/arm64"
        with pytest.raises(images.PlatformMismatch, match="needs linux/amd64"):
            cli.cmd_deploy(runner, cfg, ask=lambda _: "heal")
        assert not runner.ran("crane push")


class TestDoctor:
    def test_passes_when_the_token_works_and_the_registry_runs(
        self, cfg: Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli.shutil, "which", lambda tool: f"/bin/{tool}")
        runner = FakeRunner(outputs={"auth can-i": "yes", "readyReplicas": "1"})
        assert cli.cmd_doctor(runner, cfg) == 0

    def test_reports_an_unreachable_api(
        self, cfg: Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli.shutil, "which", lambda tool: f"/bin/{tool}")
        assert cli.cmd_doctor(FakeRunner(fail=["auth can-i"]), cfg) == 1

    def test_reports_a_missing_registry(
        self, cfg: Config, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(cli.shutil, "which", lambda tool: f"/bin/{tool}")
        runner = FakeRunner(outputs={"auth can-i": "yes", "readyReplicas": ""})
        assert cli.cmd_doctor(runner, cfg) == 1

    def test_needs_crane_and_cosign_only_when_signing(self, cfg: Config) -> None:
        assert "crane" in cli.required_tools(cfg)
        assert "cosign" not in cli.required_tools(cfg)
        assert "ssh" not in cli.required_tools(cfg)
        signed = replace(cfg, cosign_key="k", cosign_pubkey="p")
        assert "cosign" in cli.required_tools(signed)


class TestRollback:
    def test_needs_the_namespace_typed(self, cfg: Config) -> None:
        runner = FakeRunner()
        assert cli.cmd_rollback(runner, cfg, ask=lambda _: "y") == 1
        assert not runner.ran("rollout undo")


class TestRestart:
    def test_wrong_confirmation_restarts_nothing(self, cfg: Config) -> None:
        runner = FakeRunner()
        assert cli.cmd_restart(runner, cfg, ask=lambda _: "nope") == 1
        assert not runner.calls

    def test_confirmed_restart_rolls_both(self, cfg: Config) -> None:
        runner = FakeRunner()
        assert cli.cmd_restart(runner, cfg, ask=lambda _: cfg.namespace) == 0
        assert runner.ran("rollout restart deployment/api-server-deployment")
        assert runner.ran("rollout restart deployment/web-server-deployment")
        assert runner.ran("rollout restart statefulset/qdrant-statefulset")


class TestSecrets:
    @staticmethod
    def answers(**given: str):
        return lambda prompt: given.get(prompt.split()[0], "")

    @staticmethod
    def run(cfg: Config, runner: FakeRunner, confirm: str = "heal", **given: str):
        sent: list[dict] = []
        code = cli.cmd_secrets(
            runner,
            cfg,
            ask=lambda _: confirm,
            secret=TestSecrets.answers(**given),
            patch=lambda _cfg, values: sent.append(values),
        )
        return code, sent

    def test_stops_before_prompting_without_patch_rights(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"auth can-i": "no"})
        code, sent = self.run(cfg, runner, smtp_pass="x")
        assert code == 1
        assert not sent

    def test_blank_answers_change_nothing(self, cfg: Config) -> None:
        assert self.run(cfg, FakeRunner(outputs={"auth can-i": "yes"})) == (0, [])

    def test_unconfirmed_patch_is_not_sent(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"auth can-i": "yes"})
        assert self.run(cfg, runner, confirm="nope", smtp_pass="pw") == (1, [])

    def test_random_generates_and_blank_keeps(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"auth can-i": "yes"})
        code, (values,) = self.run(
            cfg, runner, user_auth_secret="random", smtp_pass="pw-123"
        )
        assert code == 0
        assert values["smtp_pass"] == "pw-123"
        assert len(values["user_auth_secret"]) == 64
        assert set(values) == {"user_auth_secret", "smtp_pass"}
        assert not any("pw-123" in call for call in runner.calls)
