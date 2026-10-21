from dataclasses import replace

import pytest
from fakes import FakeRunner

from heal_deploy import images
from heal_deploy.config import Config

BACKEND = images.SERVICES[0]


class TestRefs:
    def test_names_the_image_in_the_cluster_registry(self, cfg: Config) -> None:
        assert (
            images.local_ref(cfg, BACKEND, "abc") == "localhost:5050/heal-backend:abc"
        )


class TestBuild:
    def test_builds_for_the_cluster_platform_without_attestations(
        self, cfg: Config
    ) -> None:
        runner = FakeRunner(outputs={"{{.Os}}": "linux/amd64"})
        images.build(runner, cfg, BACKEND, "abc")
        build = runner.calls[0]
        assert "--platform linux/amd64" in build
        assert "--provenance=false" in build

    def test_platform_variant_is_ignored_when_comparing(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"{{.Os}}": "linux/arm64"})
        images.check_platform(runner, replace(cfg, platform="linux/arm64/v8"), "ref")

    def test_wrong_architecture_fails(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"{{.Os}}": "linux/arm64"})
        with pytest.raises(images.PlatformMismatch):
            images.build(runner, cfg, BACKEND, "abc")


class TestTorchVariant:
    def test_only_the_backend_gets_the_torch_variant(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"{{.Os}}": "linux/amd64"})
        cuda = replace(cfg, torch_variant="cuda")
        images.build(runner, cuda, images.SERVICES[0], "abc")
        images.build(runner, cuda, images.SERVICES[1], "abc")
        backend, web = (c for c in runner.calls if c.startswith("docker build"))
        assert "--build-arg TORCH_VARIANT=cuda" in backend
        assert "TORCH_VARIANT" not in web


class TestPush:
    DIGEST = "sha256:" + "c" * 64

    def test_pushes_with_crane_and_returns_the_digest(self, cfg: Config) -> None:
        ref = "localhost:5050/heal-backend:abc"
        runner = FakeRunner(outputs={"crane digest": self.DIGEST})

        pinned = images.push(runner, cfg, BACKEND, ref)

        tarball = cfg.state_dir / "tmp" / "heal-backend.tar"
        assert runner.calls == [
            f"docker save -o {tarball} {ref}",
            f"crane push {tarball} {ref}",
            f"crane digest {ref}",
        ]
        assert pinned == f"localhost:5050/heal-backend@{self.DIGEST}"
        assert not tarball.exists()

    def test_removes_the_tarball_when_the_push_fails(self, cfg: Config) -> None:
        tarball = cfg.state_dir / "tmp" / "heal-backend.tar"
        tarball.parent.mkdir(parents=True)
        tarball.write_text("layers")
        with pytest.raises(Exception):
            images.push(FakeRunner(fail=["crane push"]), cfg, BACKEND, "ref")
        assert not tarball.exists()

    def test_refuses_a_push_without_a_digest(self, cfg: Config) -> None:
        with pytest.raises(RuntimeError, match="no digest"):
            images.push(FakeRunner(), cfg, BACKEND, "ref")
