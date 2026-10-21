"""The one place subprocesses start, so tests can swap in a fake."""
from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Sequence


class CommandFailed(RuntimeError):
    def __init__(self, args: Sequence[str], code: int, output: str = "") -> None:
        self.command = list(args)
        self.code = code
        self.output = output
        super().__init__(f"`{shlex.join(args)}` exited {code}")


class Runner:
    def __init__(self, cwd: Path) -> None:
        self.cwd = cwd

    def run(self, args: Sequence[str]) -> None:
        """Run with output streamed to the terminal; raise on failure."""
        print(f"$ {shlex.join(args)}", flush=True)
        code = subprocess.run(list(args), cwd=self.cwd).returncode
        if code:
            raise CommandFailed(args, code)

    def pipe(self, producer: Sequence[str], consumer: Sequence[str]) -> None:
        """Run `producer | consumer`, streamed, raising if either side fails."""
        print(f"$ {shlex.join(producer)} | {shlex.join(consumer)}", flush=True)
        first = subprocess.Popen(list(producer), cwd=self.cwd, stdout=subprocess.PIPE)
        second = subprocess.Popen(list(consumer), cwd=self.cwd, stdin=first.stdout)
        assert first.stdout is not None
        # Closed here so the producer gets SIGPIPE if the consumer dies early.
        first.stdout.close()
        consumer_code = second.wait()
        producer_code = first.wait()
        if producer_code:
            raise CommandFailed(producer, producer_code)
        if consumer_code:
            raise CommandFailed(consumer, consumer_code)

    def capture(self, args: Sequence[str]) -> str:
        proc = subprocess.run(list(args), cwd=self.cwd, capture_output=True, text=True)
        if proc.returncode:
            raise CommandFailed(args, proc.returncode, proc.stderr.strip())
        return proc.stdout.strip()

    def succeeds(self, args: Sequence[str]) -> bool:
        return (
            subprocess.run(list(args), cwd=self.cwd, capture_output=True).returncode
            == 0
        )

    def spawn(self, args: Sequence[str]) -> subprocess.Popen:
        return subprocess.Popen(list(args), cwd=self.cwd)
