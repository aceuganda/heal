import io
import json
import urllib.error
from contextlib import nullcontext
from pathlib import Path

import pytest
from fakes import FakeProcess
from fakes import FakeRunner

from heal_deploy import cluster
from heal_deploy.config import Config

DIGEST = "localhost:5050/heal-backend@sha256:" + "a" * 64


class TestKubectl:
    def test_always_names_the_kubeconfig_and_namespace(self, cfg: Config) -> None:
        assert cluster.kubectl(cfg, "get", "pods") == [
            "kubectl",
            "--kubeconfig",
            "/kube/deployer.yaml",
            "--namespace",
            "heal",
            "get",
            "pods",
        ]


class TestOverlay:
    def test_pins_each_image_by_digest_against_the_base(self, tmp_path: Path) -> None:
        text = cluster.write_overlay(
            tmp_path / "overlay", {"heal-backend": DIGEST}
        ).read_text()
        assert "  - name: heal-backend\n" in text
        assert "    newName: localhost:5050/heal-backend\n" in text
        assert f"    digest: sha256:{'a' * 64}\n" in text
        base = text.split("resources:\n  - ")[1].split("\n")[0]
        assert (tmp_path / "overlay" / base).resolve() == cluster.BASE_DIR
        assert "patches:" not in text

    def test_only_the_images_just_built_are_accepted(self) -> None:
        manifest = (
            f"        image: {DIGEST}\n"
            "        image: heal-web\n"
            "        image: registry.test/heal/heal-web:abc123\n"
            "        image: nginx:1.23.4-alpine\n"
        )
        assert cluster.unexpected_images(manifest, {DIGEST}) == [
            "heal-web",
            "registry.test/heal/heal-web:abc123",
        ]

    def test_render_refuses_a_manifest_with_a_stray_image(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"kustomize": "image: heal-web"})
        with pytest.raises(RuntimeError, match="not the ones just built"):
            cluster.render(runner, cfg, {}, cfg.state_dir / "out.yaml")


class TestRelease:
    def test_dry_runs_before_applying(self, cfg: Config, tmp_path: Path) -> None:
        runner = FakeRunner()
        assert cluster.release(runner, cfg, tmp_path / "m.yaml", "abc by me")
        dry = next(i for i, c in enumerate(runner.calls) if "--dry-run=server" in c)
        real = next(
            i
            for i, c in enumerate(runner.calls)
            if c.endswith(f"apply -f {tmp_path}/m.yaml")
        )
        assert dry < real
        assert not runner.ran("rollout undo")

    def test_failed_rollout_is_undone(self, cfg: Config, tmp_path: Path) -> None:
        runner = FakeRunner(
            fail_once=["rollout status deployment/web-server-deployment"]
        )
        assert not cluster.release(runner, cfg, tmp_path / "m.yaml", "abc by me")
        assert runner.ran("rollout undo deployment/api-server-deployment")
        assert runner.ran("rollout undo deployment/web-server-deployment")


class TestCredentials:
    def test_writes_an_owner_only_kubeconfig_and_removes_it(self, cfg: Config) -> None:
        Path(cfg.kube_ca).write_text("CERT")
        with cluster.credentials(cfg) as connected:
            path = Path(connected.kubeconfig)
            assert path.stat().st_mode & 0o777 == 0o600
            written = json.loads(path.read_text())
            assert written["users"][0]["user"]["token"] == "s3cret-token"
            assert written["clusters"][0]["cluster"] == {
                "server": "https://heal-node.internal:6443",
                "certificate-authority": cfg.kube_ca,
            }
            assert "s3cret-token" not in " ".join(cluster.kubectl(connected, "get"))
        assert not path.exists()

    def test_refuses_a_missing_ca_file(self, cfg: Config) -> None:
        with pytest.raises(RuntimeError, match="DEPLOY_KUBE_CA"):
            with cluster.credentials(cfg):
                pass


class TestRegistryForward:
    def test_forwards_the_registry_through_the_api(self, cfg: Config) -> None:
        runner = FakeRunner()
        opened = iter([False, True])
        with cluster.registry_forward(cfg, runner, port_open=lambda _: next(opened)):
            pass
        assert runner.calls == [
            "kubectl --kubeconfig /kube/deployer.yaml --namespace heal "
            "port-forward --address localhost deployment/heal-registry 5050:5050"
        ]
        assert runner.process.terminated

    def test_refuses_a_port_already_in_use(self, cfg: Config) -> None:
        with pytest.raises(cluster.ForwardError, match="already in use"):
            with cluster.registry_forward(cfg, FakeRunner(), port_open=lambda _: True):
                pass

    def test_reports_the_forward_exiting(self, cfg: Config) -> None:
        runner = FakeRunner(process=FakeProcess(exited=True))
        with pytest.raises(cluster.ForwardError, match="setup-server.sh"):
            with cluster.registry_forward(cfg, runner, port_open=lambda _: False):
                pass
        assert runner.process.terminated

    @pytest.mark.parametrize(
        "ready, expected", [("1", True), ("", False), ("0", False)]
    )
    def test_registry_ready(self, cfg: Config, ready: str, expected: bool) -> None:
        runner = FakeRunner(outputs={"readyReplicas": ready})
        assert cluster.registry_ready(runner, cfg) is expected
        assert runner.ran("--namespace heal get deployment heal-registry")

    @pytest.mark.parametrize("answer, expected", [("yes", True), ("no", False)])
    def test_can_i(self, cfg: Config, answer: str, expected: bool) -> None:
        runner = FakeRunner(outputs={"auth can-i": answer})
        assert cluster.can_i(runner, cfg, "update", "deployments") is expected


class TestLogsAndRestart:
    def test_logs_follows_the_chosen_deployment(self, cfg: Config) -> None:
        runner = FakeRunner()
        cluster.logs(runner, cfg, "web")
        assert runner.ran("logs deployment/web-server-deployment --tail=200 --follow")

    def test_restart_restarts_api_web_and_qdrant_then_waits(self, cfg: Config) -> None:
        runner = FakeRunner()
        cluster.restart(runner, cfg)
        restarts = [i for i, c in enumerate(runner.calls) if "rollout restart" in c]
        waits = [i for i, c in enumerate(runner.calls) if "rollout status" in c]
        assert len(restarts) == len(waits) == 3
        assert max(restarts) < min(waits)


class TestPatchSecret:
    def test_one_merge_patch_with_the_token_in_a_header(self, cfg: Config) -> None:
        seen = []

        def opener(request, context, timeout):
            seen.append(request)
            return nullcontext()

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cluster.ssl, "create_default_context", lambda cafile: None)
            cluster.patch_secret(cfg, {"smtp_pass": "pw"}, opener=opener)
        (request,) = seen
        assert request.get_method() == "PATCH"
        assert request.full_url == (
            "https://heal-node.internal:6443"
            "/api/v1/namespaces/heal/secrets/heal-secrets"
        )
        assert request.get_header("Authorization") == "Bearer s3cret-token"
        assert request.get_header("Content-type") == "application/merge-patch+json"
        assert json.loads(request.data) == {"stringData": {"smtp_pass": "pw"}}

    def test_a_refusal_names_the_reason(self, cfg: Config) -> None:
        def opener(request, context, timeout):
            body = io.BytesIO(b'{"message": "secrets is forbidden"}')
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, body)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(cluster.ssl, "create_default_context", lambda cafile: None)
            with pytest.raises(RuntimeError, match="403.*forbidden"):
                cluster.patch_secret(cfg, {"smtp_pass": "pw"}, opener=opener)
