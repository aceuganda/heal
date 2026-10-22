import json

from fakes import FakeRunner

from heal_deploy.config import Config
from heal_deploy.gates import check_base_images
from heal_deploy.gates import check_git
from heal_deploy.gates import check_npm_lock
from heal_deploy.gates import check_python_pins


class TestPythonPins:
    def test_exact_pins_pass_including_extras_markers_and_post_releases(self) -> None:
        text = (
            "# comment\n"
            "fastapi==0.103.0\n"
            "uvicorn[standard]==0.21.1  # server\n"
            'tomli==2.0.1 ; python_version < "3.11"\n'
            "pytz==2023.3.post1\n"
        )
        assert check_python_pins(text) == []

    def test_ranges_wildcards_and_bare_names_fail(self) -> None:
        problems = check_python_pins("requests>=2.0\nnumpy==1.*\nrich\n")
        assert len(problems) == 3
        assert all("not pinned" in p for p in problems)

    def test_pre_releases_fail(self) -> None:
        problems = check_python_pins("a==2.0.0rc1\nb==1.0b2\nc==1.0.dev0\nd==3.0a1\n")
        assert len(problems) == 4
        assert all("pre-release" in p for p in problems)

    def test_option_lines_fail(self) -> None:
        assert "options" in check_python_pins("-r other.txt\n")[0]


class TestNpmLock:
    MANIFEST = json.dumps({"dependencies": {"next": "^14.0.0"}})

    def _lock(self, version: str) -> str:
        return json.dumps(
            {
                "lockfileVersion": 3,
                "packages": {"node_modules/next": {"version": version}},
            }
        )

    def test_stable_resolution_passes(self) -> None:
        assert check_npm_lock(self.MANIFEST, self._lock("14.2.3")) == []

    def test_pre_release_resolution_fails(self) -> None:
        assert (
            "pre-release"
            in check_npm_lock(self.MANIFEST, self._lock("15.0.0-canary.1"))[0]
        )

    def test_missing_lockfile_or_entry_fails(self) -> None:
        assert "missing" in check_npm_lock(self.MANIFEST, None)[0]
        empty = json.dumps({"lockfileVersion": 3, "packages": {}})
        assert "not in the lockfile" in check_npm_lock(self.MANIFEST, empty)[0]


class TestBaseImages:
    def test_exact_tags_digests_and_stage_names_pass(self) -> None:
        dockerfile = (
            "FROM python:3.11.7-slim-bookworm\n"
            "FROM --platform=linux/amd64 node:24.22.0-alpine3.24 AS base\n"
            "FROM base AS deps\n"
            "FROM nginx@sha256:abc\n"
        )
        assert check_base_images(dockerfile, "Dockerfile") == []

    def test_continuation_lines_are_not_instructions(self) -> None:
        dockerfile = (
            "FROM python:3.11.7-slim\n"
            'RUN python -c "import os; \\\n'
            'from os import path"\n'
        )
        assert check_base_images(dockerfile, "Dockerfile") == []

    def test_floating_latest_and_untagged_images_fail(self) -> None:
        dockerfile = "FROM node:24-alpine\nFROM busybox:latest\nFROM alpine\n"
        assert len(check_base_images(dockerfile, "Dockerfile")) == 3


class TestGit:
    def test_clean_commit_on_the_branch_passes(self, cfg: Config) -> None:
        runner = FakeRunner()
        assert check_git(runner, cfg) == []
        assert runner.ran("git fetch --quiet origin main")

    def test_dirty_tree_and_unpushed_commit_both_reported(self, cfg: Config) -> None:
        runner = FakeRunner(outputs={"status": "?? notes.txt"}, fail=["merge-base"])
        problems = check_git(runner, cfg)
        assert len(problems) == 2
        assert "origin/main" in problems[1]
