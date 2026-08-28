"""Guard against network addresses creeping back into the source.

Hard-coded hosts are how the old translation module ended up pointing at a
public IP over plain HTTP with no timeout. This test is the standing rule, not
a one-off cleanup: endpoints belong in the environment.
"""
import re
from pathlib import Path

import pytest

# backend/tests/unit/heal/ -> backend/
BACKEND = Path(__file__).resolve().parents[3]

# Live source only. `deprecated/` is frozen text that nothing imports.
LIVE_TREES = ["heal", "danswer"]

_IP_URL = re.compile(r"https?://\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}")

# Loopback is fine: it is a local-development default, not someone's server.
_ALLOWED = re.compile(r"https?://(127\.0\.0\.1|0\.0\.0\.0)")


def _python_sources() -> list[Path]:
    return [p for tree in LIVE_TREES for p in (BACKEND / tree).rglob("*.py")]


@pytest.mark.parametrize("tree", LIVE_TREES)
def test_tree_exists(tree: str) -> None:
    """Fails loudly if a rename silently empties this test's scope."""
    assert (BACKEND / tree).is_dir()


def test_no_hardcoded_ip_endpoints() -> None:
    offenders = []
    for path in _python_sources():
        for lineno, line in enumerate(
            path.read_text(errors="replace").splitlines(), start=1
        ):
            for match in _IP_URL.finditer(line):
                if _ALLOWED.match(match.group()):
                    continue
                offenders.append(
                    f"{path.relative_to(BACKEND)}:{lineno}: {match.group()}"
                )

    assert not offenders, (
        "Hard-coded network addresses found. Move them to heal/config.py and "
        "read them from the environment:\n  " + "\n  ".join(offenders)
    )


def test_deprecated_code_is_never_imported() -> None:
    """`deprecated/` is frozen. Live code importing it defeats the point."""
    pattern = re.compile(r"^\s*(from|import)\s+deprecated\b", re.MULTILINE)
    offenders = [
        str(p.relative_to(BACKEND))
        for p in _python_sources()
        if pattern.search(p.read_text(errors="replace"))
    ]
    assert not offenders, f"Live code imports deprecated modules: {offenders}"
