"""heal-deploy command line. See deployment/README.md § Kubernetes (k3s)."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from datetime import timezone
from typing import Callable

from heal_deploy import cluster
from heal_deploy import gates
from heal_deploy import images
from heal_deploy.config import Config
from heal_deploy.config import ConfigError
from heal_deploy.config import load
from heal_deploy.config import REPO_ROOT
from heal_deploy.runner import CommandFailed
from heal_deploy.runner import Runner

TOOLS = ("git", "docker", "kubectl", "trivy", "crane")


def required_tools(cfg: Config) -> tuple[str, ...]:
    return TOOLS + (("cosign",) if cfg.signing else ())


def _report(title: str, problems: list[str]) -> bool:
    if not problems:
        print(f"ok   {title}")
        return True
    print(f"FAIL {title}")
    for problem in problems:
        print(f"     - {problem}")
    return False


def run_gates(runner: Runner, cfg: Config) -> bool:
    git_ok = _report("code is committed and on GitHub", gates.check_git(runner, cfg))
    pins_ok = _report(
        "packages are pinned and stable", gates.check_stable_packages(REPO_ROOT)
    )
    if not (git_ok and pins_ok):
        return False
    gates.scan_dependencies(runner, cfg)
    print("ok   no fixable vulnerabilities or leaked secrets in dependencies")
    return True


def cmd_doctor(runner: Runner, cfg: Config) -> int:
    missing = [tool for tool in required_tools(cfg) if shutil.which(tool) is None]
    ok = _report("tools on PATH", [f"{t} not found" for t in missing])
    if not cfg.signing:
        print("warn images will not be signed (DEPLOY_COSIGN_KEY is empty)")
    if "kubectl" in missing:
        return 1

    # One call proves the URL, the CA, the token and the deployer's RBAC.
    api = f"API at {cfg.api_server_url}"
    try:
        allowed = cluster.can_i(runner, cfg, "update", "deployments")
    except CommandFailed as error:
        _report(api, [error.output or str(error)])
        return 1
    ok = (
        _report(
            f"{api} accepts the token",
            [] if allowed else [f"token cannot update deployments in {cfg.namespace}"],
        )
        and ok
    )
    try:
        ready = cluster.registry_ready(runner, cfg)
    except CommandFailed as error:
        ready, detail = False, error.output or str(error)
    else:
        detail = "run deployment/kubernetes/setup-server.sh (README § k3s)"
    ok = _report("registry inside k3s is running", [] if ready else [detail]) and ok
    return 0 if ok else 1


def cmd_check(runner: Runner, cfg: Config) -> int:
    return 0 if run_gates(runner, cfg) else 1


def cmd_deploy(runner: Runner, cfg: Config, ask: Callable[[str], str] = input) -> int:
    if not run_gates(runner, cfg):
        return 1

    sha = runner.capture(["git", "rev-parse", "HEAD"])
    tag = sha[:12]
    built = {}
    for service in images.SERVICES:
        ref = images.build(runner, cfg, service, tag)
        images.scan(
            runner, cfg, ref, cfg.state_dir / "sbom" / f"{tag}-{service.image}.cdx.json"
        )
        built[service] = ref
    print("ok   images built and scanned")

    print(
        f"\nAbout to push and deploy commit {tag}\n"
        f"  images     {', '.join(built.values())}\n"
        f"  platform   {cfg.platform}, torch {cfg.torch_variant}\n"
        f"  cluster    {cfg.api_server_url}\n"
        f"  namespace  {cfg.namespace}\n"
        f"  signed     {'yes' if cfg.signing else 'NO'}\n"
    )
    try:
        answer = ask(f"Type the namespace ({cfg.namespace}) to continue: ")
    except EOFError:
        answer = ""
    if answer.strip() != cfg.namespace:
        print("Not confirmed; nothing was pushed or deployed.")
        return 1

    pinned = {}
    with cluster.registry_forward(cfg, runner):
        for service, ref in built.items():
            digest_ref = images.push(runner, cfg, service, ref)
            if cfg.signing:
                images.sign(runner, cfg, digest_ref)
                images.verify(runner, cfg, digest_ref)
            pinned[service.image] = digest_ref

    started = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    manifest = cluster.render(
        runner, cfg, pinned, cfg.state_dir / "releases" / f"{started}-{tag}.yaml"
    )
    by = runner.capture(["git", "config", "user.email"]) or "unknown"
    succeeded = cluster.release(runner, cfg, manifest, f"{tag} by {by}")

    _record(
        cfg,
        {
            "at": started,
            "commit": sha,
            "by": by,
            "cluster": cfg.api_server_url,
            "namespace": cfg.namespace,
            "platform": cfg.platform,
            "torch": cfg.torch_variant,
            "images": pinned,
            "signed": cfg.signing,
            "manifest": str(manifest),
            "outcome": "deployed" if succeeded else "rolled back",
        },
    )
    print("Deployed." if succeeded else "Deploy failed and was rolled back.")
    return 0 if succeeded else 1


def _record(cfg: Config, entry: dict) -> None:
    cfg.state_dir.mkdir(parents=True, exist_ok=True)
    with open(cfg.state_dir / "history.jsonl", "a") as history:
        history.write(json.dumps(entry) + "\n")


def cmd_status(runner: Runner, cfg: Config) -> int:
    cluster.status(runner, cfg)
    return 0


def cmd_rollback(runner: Runner, cfg: Config, ask: Callable[[str], str] = input) -> int:
    answer = ask(f"Type the namespace ({cfg.namespace}) to roll back: ")
    if answer.strip() != cfg.namespace:
        print("Not confirmed; nothing was rolled back.")
        return 1
    cluster.rollback(runner, cfg)
    return 0


def cmd_logs(runner: Runner, cfg: Config, service: str = "api") -> int:
    try:
        cluster.logs(runner, cfg, service)
    except KeyboardInterrupt:
        pass
    return 0


def cmd_restart(runner: Runner, cfg: Config, ask: Callable[[str], str] = input) -> int:
    answer = ask(f"Type the namespace ({cfg.namespace}) to restart: ")
    if answer.strip() != cfg.namespace:
        print("Not confirmed; nothing was restarted.")
        return 1
    cluster.restart(runner, cfg)
    return 0


COMMANDS: dict[str, Callable[[Runner, Config], int]] = {
    "doctor": cmd_doctor,
    "check": cmd_check,
    "deploy": cmd_deploy,
    "status": cmd_status,
    "rollback": cmd_rollback,
    "logs": cmd_logs,
    "restart": cmd_restart,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="heal-deploy", description=__doc__)
    parser.add_argument("command", choices=COMMANDS)
    parser.add_argument(
        "service",
        nargs="?",
        choices=cluster.SHORT_NAMES,
        default="api",
        help="logs only: which deployment to follow",
    )
    args = parser.parse_args(argv)
    try:
        cfg = load()
    except ConfigError as error:
        print(f"config: {error}", file=sys.stderr)
        return 2
    try:
        with cluster.credentials(cfg) as connected:
            runner = Runner(REPO_ROOT)
            if args.command == "logs":
                return cmd_logs(runner, connected, args.service)
            return COMMANDS[args.command](runner, connected)
    except (CommandFailed, cluster.ForwardError, RuntimeError) as error:
        print(f"\nStopped: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
