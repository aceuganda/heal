"""Reaching the k3s API with the deployer's token, and rolling a release out."""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import ssl
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from typing import Callable, Collection, Generator, Mapping

from heal_deploy.config import CLUSTER_REGISTRY_PORT
from heal_deploy.config import Config
from heal_deploy.config import REPO_ROOT
from heal_deploy.runner import CommandFailed
from heal_deploy.runner import Runner

BASE_DIR = REPO_ROOT / "deployment" / "kubernetes"
DEPLOYMENTS = ("api-server-deployment", "web-server-deployment")
SHORT_NAMES = {"api": DEPLOYMENTS[0], "web": DEPLOYMENTS[1]}
ROLLOUT_TIMEOUT = "5m"
REGISTRY_DEPLOYMENT = "heal-registry"
STATEFUL_RESTARTS = ("qdrant-statefulset",)
SECRETS_NAME = "heal-secrets"
# What `make deploy-secrets` offers, with the prompt hint. The Postgres
# credentials are left out: the data directory keeps the original password.
SECRET_KEYS = {
    "user_auth_secret": "required; signs reset/verify tokens",
    "qdrant_api_key": "required; Qdrant and the API server share it",
    "gen_ai_api_key": "LLM provider key",
    "translation_api_key": "bearer token for the MT services",
    "self_hosted_api_key": "vLLM endpoint key",
    "smtp_pass": "SMTP password",
    "bootstrap_admin_email": "first admin; seeds an EMPTY user table only",
    "bootstrap_admin_password": "first admin's password",
    "google_oauth_client_id": "Google OAuth client id",
    "google_oauth_client_secret": "Google OAuth client secret",
}

_HEAL_IMAGE = re.compile(r"^\s*-?\s*image:\s*(\S*heal-(?:backend|web)\S*)\s*$", re.M)


class ForwardError(RuntimeError):
    pass


def kubectl(cfg: Config, *args: str) -> list[str]:
    return [
        "kubectl",
        "--kubeconfig",
        cfg.kubeconfig,
        "--namespace",
        cfg.namespace,
        *args,
    ]


def token_kubeconfig(cfg: Config) -> dict:
    return {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": "heal",
                "cluster": {
                    "server": cfg.api_server_url,
                    "certificate-authority": os.path.abspath(cfg.kube_ca),
                },
            }
        ],
        "users": [{"name": "heal-deployer", "user": {"token": cfg.kube_token}}],
        "contexts": [
            {
                "name": "heal",
                "context": {
                    "cluster": "heal",
                    "user": "heal-deployer",
                    "namespace": cfg.namespace,
                },
            }
        ],
        "current-context": "heal",
    }


@contextmanager
def credentials(cfg: Config) -> Generator[Config, None, None]:
    """A kubeconfig built from the token for the life of the command:
    owner-only, never in the repo, and the token never on a command line
    where `ps` would show it."""
    if not os.path.isfile(cfg.kube_ca):
        raise RuntimeError(f"DEPLOY_KUBE_CA {cfg.kube_ca} is not a file")
    workdir = tempfile.mkdtemp(prefix="heal-deploy-")  # mode 0700
    try:
        path = os.path.join(workdir, "kubeconfig")
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(token_kubeconfig(cfg), handle)
        yield replace(cfg, kubeconfig=path)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def _port_open(port: int) -> bool:
    try:
        with socket.create_connection(("localhost", port), timeout=0.5):
            return True
    except OSError:
        return False


@contextmanager
def registry_forward(
    cfg: Config,
    runner: Runner,
    wait_seconds: float = 20.0,
    port_open: Callable[[int], bool] = _port_open,
) -> Generator[None, None, None]:
    """Forward the in-cluster registry to this machine through the API.

    The registry listens on the node's loopback only, so this forward -- which
    needs the deployer's token -- is the one way in from outside.
    """
    port = CLUSTER_REGISTRY_PORT
    if port_open(port):
        raise ForwardError(
            f"port {port} is already in use here; close whatever holds it so "
            "images cannot be pushed somewhere else"
        )
    proc = runner.spawn(
        kubectl(
            cfg,
            "port-forward",
            "--address",
            "localhost",
            f"deployment/{REGISTRY_DEPLOYMENT}",
            f"{port}:{port}",
        )
    )
    try:
        deadline = time.monotonic() + wait_seconds
        while not port_open(port):
            if proc.poll() is not None:
                raise ForwardError(
                    "kubectl port-forward to the registry exited; check that "
                    "setup-server.sh has run (README § k3s)"
                )
            if time.monotonic() > deadline:
                raise ForwardError(
                    f"registry port-forward did not open in {wait_seconds:.0f}s"
                )
            time.sleep(0.2)
        yield
    finally:
        proc.terminate()
        proc.wait(timeout=5)


def registry_ready(runner: Runner, cfg: Config) -> bool:
    ready = runner.capture(
        kubectl(
            cfg,
            "get",
            "deployment",
            REGISTRY_DEPLOYMENT,
            "-o",
            "jsonpath={.status.readyReplicas}",
        )
    )
    return ready not in ("", "0")


def can_i(runner: Runner, cfg: Config, verb: str, resource: str) -> bool:
    return runner.capture(kubectl(cfg, "auth", "can-i", verb, resource)) == "yes"


def patch_secret(
    cfg: Config,
    values: Mapping[str, str],
    opener: Callable[..., object] = urllib.request.urlopen,
) -> None:
    """Merge `values` into heal-secrets with one PATCH to the API. `kubectl
    patch` GETs the Secret first, which the deployer may not do. The reply
    carries every key, so it is discarded unread."""
    request = urllib.request.Request(
        f"{cfg.api_server_url.rstrip('/')}/api/v1/namespaces/{cfg.namespace}"
        f"/secrets/{SECRETS_NAME}",
        data=json.dumps({"stringData": dict(values)}).encode(),
        method="PATCH",
        headers={
            "Authorization": f"Bearer {cfg.kube_token}",
            "Content-Type": "application/merge-patch+json",
        },
    )
    context = ssl.create_default_context(cafile=cfg.kube_ca)
    print(f"$ PATCH secrets/{SECRETS_NAME} in {cfg.namespace}", flush=True)
    try:
        with opener(request, context=context, timeout=30):
            pass
    except urllib.error.HTTPError as error:
        reason = json.loads(error.read() or b"{}").get("message", error.reason)
        raise RuntimeError(f"API refused the patch ({error.code}): {reason}")
    except urllib.error.URLError as error:
        raise RuntimeError(f"cannot reach {cfg.api_server_url}: {error.reason}")


def write_overlay(overlay_dir: Path, pinned: Mapping[str, str]) -> Path:
    """A kustomization that pins each logical image to `name@digest`."""
    overlay_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        "apiVersion: kustomize.config.k8s.io/v1beta1",
        "kind: Kustomization",
        "resources:",
        f"  - {os.path.relpath(BASE_DIR, overlay_dir)}",
        "images:",
    ]
    for name, ref in sorted(pinned.items()):
        new_name, digest = ref.split("@", 1)
        lines += [
            f"  - name: {name}",
            f"    newName: {new_name}",
            f"    digest: {digest}",
        ]
    path = overlay_dir / "kustomization.yaml"
    path.write_text("\n".join(lines) + "\n")
    return path


def unexpected_images(manifest: str, expected: Collection[str]) -> list[str]:
    """Heal images in the rendered manifest that are not exactly what was built."""
    found = (m.group(1) for m in _HEAL_IMAGE.finditer(manifest))
    return [image for image in found if image not in expected]


def render(runner: Runner, cfg: Config, pinned: Mapping[str, str], out: Path) -> Path:
    overlay = write_overlay(cfg.state_dir / "overlay", pinned)
    manifest = runner.capture(["kubectl", "kustomize", str(overlay.parent)])
    leftover = unexpected_images(manifest, set(pinned.values()))
    if leftover:
        raise RuntimeError(
            f"manifest has Heal images that are not the ones just built: {leftover}"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(manifest + "\n")
    return out


def release(runner: Runner, cfg: Config, manifest: Path, cause: str) -> bool:
    """Apply, then wait for the rollout. A rollout that fails is undone.

    The server-side dry run goes first so admission and schema errors stop the
    release before anything on the cluster changes.
    """
    runner.run(kubectl(cfg, "apply", "--dry-run=server", "-f", str(manifest)))
    runner.run(kubectl(cfg, "apply", "-f", str(manifest)))
    for name in DEPLOYMENTS:
        runner.run(
            kubectl(
                cfg,
                "annotate",
                "deployment",
                name,
                f"kubernetes.io/change-cause={cause}",
                "--overwrite",
            )
        )

    failed = []
    for name in DEPLOYMENTS:
        try:
            runner.run(
                kubectl(
                    cfg,
                    "rollout",
                    "status",
                    f"deployment/{name}",
                    f"--timeout={ROLLOUT_TIMEOUT}",
                )
            )
        except CommandFailed:
            failed.append(name)
    if failed:
        print(f"Rollout failed for {', '.join(failed)}; rolling both back.", flush=True)
        rollback(runner, cfg)
        return False
    return True


def rollback(runner: Runner, cfg: Config) -> None:
    for name in DEPLOYMENTS:
        runner.run(kubectl(cfg, "rollout", "undo", f"deployment/{name}"))
    for name in DEPLOYMENTS:
        runner.run(
            kubectl(
                cfg,
                "rollout",
                "status",
                f"deployment/{name}",
                f"--timeout={ROLLOUT_TIMEOUT}",
            )
        )


def status(runner: Runner, cfg: Config) -> None:
    runner.run(kubectl(cfg, "get", "deployments,statefulsets,pods", "-o", "wide"))
    for name in DEPLOYMENTS:
        runner.run(kubectl(cfg, "rollout", "history", f"deployment/{name}"))


def logs(runner: Runner, cfg: Config, service: str) -> None:
    runner.run(
        kubectl(
            cfg, "logs", f"deployment/{SHORT_NAMES[service]}", "--tail=200", "--follow"
        )
    )


def restart(runner: Runner, cfg: Config) -> None:
    """New pods with the same images, so ConfigMap and Secret edits take effect."""
    targets = [f"deployment/{name}" for name in DEPLOYMENTS]
    targets += [f"statefulset/{name}" for name in STATEFUL_RESTARTS]
    for target in targets:
        runner.run(kubectl(cfg, "rollout", "restart", target))
    for target in targets:
        runner.run(
            kubectl(cfg, "rollout", "status", target, f"--timeout={ROLLOUT_TIMEOUT}")
        )
