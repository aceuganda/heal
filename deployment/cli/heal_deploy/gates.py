"""What has to be true before anything is built.

Each check returns a list of problems rather than raising, so one run reports
everything that is wrong instead of the first thing.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from heal_deploy.config import Config
from heal_deploy.runner import Runner

PYTHON_REQUIREMENTS = Path("backend/requirements/default.txt")
PACKAGE_JSON = Path("web/package.json")
PACKAGE_LOCK = Path("web/package-lock.json")
DOCKERFILES = (Path("backend/Dockerfile"), Path("web/Dockerfile"))

# Scanned for vulnerabilities. dev.txt and npm devDependencies are not in
# either image, so a finding there cannot reach the cluster.
DEPENDENCY_MANIFESTS = (PYTHON_REQUIREMENTS, PACKAGE_LOCK)
SECRET_SCAN_SKIP = ".git,.venv,web/node_modules,web/.next,deployment/.deploy"

_PIN = re.compile(
    r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?\s*==\s*"
    r"(?P<version>[^\s;#,]+)\s*(;.*)?$"
)
# PEP 440 pre-releases: 1.0a1, 2.0b2, 3.0rc1, 1.0.dev0. Post-releases are fine.
_PY_PRERELEASE = re.compile(r"\d(a|b|c|rc)\d*$|\d(a|b|c|rc)\d*[.+]|\.?dev\d*", re.I)
_EXACT_TAG = re.compile(r"(^|[^\d.])\d+\.\d+\.\d+")


def check_python_pins(text: str, source: str = str(PYTHON_REQUIREMENTS)) -> list[str]:
    problems = []
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #", 1)[0].strip()
        if not line or line.startswith("#"):
            continue
        where = f"{source}:{number}"
        if line.startswith("-"):
            problems.append(f"{where}: options and includes are not allowed: {line}")
            continue
        match = _PIN.match(line)
        if not match or "*" in match["version"]:
            problems.append(f"{where}: not pinned to one exact version: {line}")
        elif _PY_PRERELEASE.search(match["version"]):
            problems.append(f"{where}: pre-release version: {line}")
    return problems


def check_npm_lock(package_json: str, package_lock: str | None) -> list[str]:
    if package_lock is None:
        return [
            f"{PACKAGE_LOCK} is missing; the image would resolve versions at build time"
        ]
    manifest = json.loads(package_json)
    lock = json.loads(package_lock)
    if lock.get("lockfileVersion", 1) < 2:
        return [
            f"{PACKAGE_LOCK} is lockfileVersion 1; regenerate it with a current npm"
        ]

    problems = []
    packages = lock.get("packages", {})
    for name in manifest.get("dependencies", {}):
        resolved = packages.get(f"node_modules/{name}", {}).get("version")
        if resolved is None:
            problems.append(
                f"{name} is in package.json but not in the lockfile; run npm install"
            )
        elif "-" in resolved:
            problems.append(f"{name} resolves to pre-release {resolved}")
    return problems


def check_base_images(dockerfile: str, source: str) -> list[str]:
    problems = []
    stages: set[str] = set()
    continued = False
    for number, raw in enumerate(dockerfile.splitlines(), 1):
        # A line after a trailing backslash belongs to the previous
        # instruction, e.g. Python inside a RUN that starts `from x import y`.
        was_continued, continued = continued, raw.rstrip().endswith("\\")
        parts = raw.split()
        if was_continued or not parts or parts[0].upper() != "FROM":
            continue
        args = [p for p in parts[1:] if not p.startswith("--")]
        image = args[0]
        if len(args) >= 3 and args[1].upper() == "AS":
            stages.add(args[2])
        if image in stages or image == "scratch":
            continue
        if "@sha256:" in image:
            continue
        tag = image.rsplit(":", 1)[1] if ":" in image.split("/")[-1] else ""
        if not _EXACT_TAG.search(tag):
            problems.append(
                f"{source}:{number}: base image {image} floats; pin a full "
                "x.y.z tag or a digest"
            )
    return problems


def check_stable_packages(root: Path) -> list[str]:
    problems = check_python_pins((root / PYTHON_REQUIREMENTS).read_text())
    lock_path = root / PACKAGE_LOCK
    problems += check_npm_lock(
        (root / PACKAGE_JSON).read_text(),
        lock_path.read_text() if lock_path.exists() else None,
    )
    for dockerfile in DOCKERFILES:
        problems += check_base_images((root / dockerfile).read_text(), str(dockerfile))
    return problems


def check_git(runner: Runner, cfg: Config) -> list[str]:
    problems = []
    # Untracked files count: they are in the docker build context, so an image
    # built with them would not match the commit it is labelled with.
    if runner.capture(["git", "status", "--porcelain"]):
        problems.append("the working tree has uncommitted or untracked changes")
    runner.capture(["git", "fetch", "--quiet", cfg.remote, cfg.branch])
    upstream = f"{cfg.remote}/{cfg.branch}"
    if not runner.succeeds(["git", "merge-base", "--is-ancestor", "HEAD", upstream]):
        problems.append(
            f"HEAD is not on {upstream}; merge and push it first so GitHub "
            "holds every commit that is deployed"
        )
    return problems


def scan_dependencies(runner: Runner, cfg: Config) -> None:
    """Fail on known vulnerabilities with a fix available, and on leaked secrets.

    `--ignore-unfixed` keeps the gate actionable: a finding with no patched
    release cannot be fixed by upgrading, so it would block every deploy.
    Accepted exceptions go in .trivyignore with a reason.
    """
    for manifest in DEPENDENCY_MANIFESTS:
        runner.run(
            [
                "trivy",
                "fs",
                "--quiet",
                "--exit-code",
                "1",
                "--scanners",
                "vuln",
                "--severity",
                cfg.fail_severity,
                "--ignore-unfixed",
                str(manifest),
            ]
        )
    runner.run(
        [
            "trivy",
            "fs",
            "--quiet",
            "--exit-code",
            "1",
            "--scanners",
            "secret",
            "--skip-dirs",
            SECRET_SCAN_SKIP,
            ".",
        ]
    )
