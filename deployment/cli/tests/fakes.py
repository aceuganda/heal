from __future__ import annotations

from typing import Sequence

from heal_deploy.runner import CommandFailed


class FakeProcess:
    def __init__(self, exited: bool = False) -> None:
        self.exited = exited
        self.terminated = False

    def poll(self) -> int | None:
        return 255 if self.exited else None

    def terminate(self) -> None:
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        return 0


class FakeRunner:
    """Records commands. `outputs`, `fail` and `fail_once` match on a substring
    of the command; a `fail_once` pattern fails its first match only."""

    def __init__(
        self,
        outputs: dict[str, str] | None = None,
        fail: Sequence[str] = (),
        fail_once: Sequence[str] = (),
        process: FakeProcess | None = None,
    ) -> None:
        self.calls: list[str] = []
        self.outputs = outputs or {}
        self.fail = fail
        self.fail_once = list(fail_once)
        self.process = process or FakeProcess()

    def _record(self, args: Sequence[str]) -> str:
        line = " ".join(args)
        self.calls.append(line)
        return line

    def _fails(self, line: str) -> bool:
        for pattern in self.fail_once:
            if pattern in line:
                self.fail_once.remove(pattern)
                return True
        return any(pattern in line for pattern in self.fail)

    def run(self, args: Sequence[str]) -> None:
        if self._fails(self._record(args)):
            raise CommandFailed(args, 1)

    def pipe(self, producer: Sequence[str], consumer: Sequence[str]) -> None:
        line = f"{' '.join(producer)} | {' '.join(consumer)}"
        self.calls.append(line)
        if self._fails(line):
            raise CommandFailed(consumer, 1)

    def capture(self, args: Sequence[str]) -> str:
        line = self._record(args)
        if self._fails(line):
            raise CommandFailed(args, 1)
        for pattern, output in self.outputs.items():
            if pattern in line:
                return output
        return ""

    def succeeds(self, args: Sequence[str]) -> bool:
        return not self._fails(self._record(args))

    def spawn(self, args: Sequence[str]) -> FakeProcess:
        self._record(args)
        return self.process

    def ran(self, pattern: str) -> bool:
        return any(pattern in line for line in self.calls)
