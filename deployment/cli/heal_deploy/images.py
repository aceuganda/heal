"""Build, scan and push the two Heal images to the registry inside k3s."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from heal_deploy.config import Config
from heal_deploy.runner import Runner


@dataclass(frozen=True)
class Service:
    image: str  # also the logical name the manifests use
    context: str
    uses_torch: bool = False


SERVICES = (
    Service("heal-backend", "backend", uses_torch=True),
    Service("heal-web", "web"),
)


class PlatformMismatch(RuntimeError):
    pass


def local_ref(cfg: Config, service: Service, tag: str) -> str:
    return f"{cfg.registry}/{service.image}:{tag}"


def check_platform(runner: Runner, cfg: Config, ref: str) -> None:
    """Fail if the built image is not for the cluster's architecture.

    Building on an Apple Silicon Mac defaults to arm64; an arm64 image on an
    amd64 node only fails at container start with `exec format error`.
    """
    built = runner.capture(
        ["docker", "image", "inspect", "--format", "{{.Os}}/{{.Architecture}}", ref]
    )
    wanted = "/".join(cfg.platform.split("/")[:2])
    if built != wanted:
        raise PlatformMismatch(
            f"{ref} was built for {built}, the cluster needs {wanted}"
        )


def build(runner: Runner, cfg: Config, service: Service, tag: str) -> str:
    ref = local_ref(cfg, service, tag)
    # --pull refreshes the pinned base tag, which upstream re-publishes with
    # OS security patches; the cache would otherwise keep the old layers.
    runner.run(
        [
            "docker",
            "build",
            "--pull",
            # Attestations turn the image into a multi-manifest index, which
            # a `docker save` tarball does not round-trip cleanly.
            "--provenance=false",
            "--platform",
            cfg.platform,
            "--build-arg",
            f"HEAL_VERSION={tag}",
            *(
                ["--build-arg", f"TORCH_VARIANT={cfg.torch_variant}"]
                if service.uses_torch
                else []
            ),
            "-t",
            ref,
            service.context,
        ]
    )
    check_platform(runner, cfg, ref)
    return ref


def scan(runner: Runner, cfg: Config, ref: str, sbom: Path) -> None:
    runner.run(
        [
            "trivy",
            "image",
            "--quiet",
            "--exit-code",
            "1",
            "--scanners",
            "vuln",
            "--severity",
            cfg.fail_severity,
            "--ignore-unfixed",
            ref,
        ]
    )
    sbom.parent.mkdir(parents=True, exist_ok=True)
    runner.run(
        [
            "trivy",
            "image",
            "--quiet",
            "--format",
            "cyclonedx",
            "--output",
            str(sbom),
            ref,
        ]
    )


def sign(runner: Runner, cfg: Config, digest_ref: str) -> None:
    # --tlog-upload=false keeps image names out of the public Rekor log.
    runner.run(
        [
            "cosign",
            "sign",
            "--yes",
            "--tlog-upload=false",
            "--key",
            cfg.cosign_key,
            digest_ref,
        ]
    )


def verify(runner: Runner, cfg: Config, digest_ref: str) -> None:
    runner.run(
        [
            "cosign",
            "verify",
            "--insecure-ignore-tlog=true",
            "--key",
            cfg.cosign_pubkey,
            digest_ref,
        ]
    )


def push(runner: Runner, cfg: Config, service: Service, ref: str) -> str:
    """Push through the registry port-forward and return the digest reference
    -- the only form that gets deployed. crane runs on this machine.

    `docker push` would not do: with Docker Desktop the daemon runs in a VM,
    where localhost is not the forward. crane uploads only layers the
    registry lacks, so after the first deploy only the changed ones travel.
    """
    tarball = cfg.state_dir / "tmp" / f"{service.image}.tar"
    tarball.parent.mkdir(parents=True, exist_ok=True)
    try:
        runner.run(["docker", "save", "-o", str(tarball), ref])
        runner.run(["crane", "push", str(tarball), ref])
    finally:
        tarball.unlink(missing_ok=True)
    digest = runner.capture(["crane", "digest", ref])
    if not digest.startswith("sha256:"):
        raise RuntimeError(f"pushed {ref} but crane reports no digest ({digest!r})")
    return f"{cfg.registry}/{service.image}@{digest}"
