"""Bounded, read-only Git object access for committed reference comparisons."""

from __future__ import annotations

import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from dataclasses import dataclass
from pathlib import Path

from evagix.safety import GIT_REVISION_POLICY

_TIMEOUT = 15
_TREE_LIMIT = 8_000_000
_OID = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})\Z")


@dataclass(frozen=True)
class TreeEntry:
    mode: str
    oid: str

    @property
    def regular(self) -> bool:
        return self.mode in {"100644", "100755"}


class GitSnapshot:
    def __init__(self, root: Path) -> None:
        self.root = root

    def read(self, *arguments: str, limit: int = 4096) -> bytes:
        # Ignore ambient repository/config overrides. Do not fetch missing objects
        # from partial clones, execute filters, or consult replacement objects.
        environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
        environment.update(
            GIT_CONFIG_NOSYSTEM="1",
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_NO_REPLACE_OBJECTS="1",
            GIT_NO_LAZY_FETCH="1",
            GIT_TERMINAL_PROMPT="0",
        )
        command = ["git", "--no-pager", "-c", "protocol.allow=never", "-c", "core.fsmonitor=false", *arguments]
        try:
            with subprocess.Popen(
                command, cwd=self.root, env=environment, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
            ) as process:
                if process.stdout is None:
                    process.kill()
                    raise RuntimeError("Git snapshot output is unavailable.")
                with ThreadPoolExecutor(max_workers=1) as pool:
                    reader = pool.submit(process.stdout.read, limit + 1)
                    try:
                        output = reader.result(timeout=_TIMEOUT)
                        if len(output) > limit:
                            raise RuntimeError("Git snapshot exceeded the inspection size limit.")
                        if process.wait(timeout=_TIMEOUT) != 0:
                            raise RuntimeError("Could not read Git snapshot; check refs, history, and local objects.")
                        return output
                    finally:
                        if process.poll() is None:
                            process.kill()
                        process.wait()
        except (TimeoutError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError("Git snapshot inspection timed out.") from exc
        except OSError as exc:
            raise RuntimeError("Could not access Git; check the repository and Git installation.") from exc

    def resolve(self, ref: str) -> str:
        clean = GIT_REVISION_POLICY.clean_ref(ref)
        output = self.read("rev-parse", "--verify", "--end-of-options", clean + "^{commit}")
        return self._oid(output)

    def merge_base(self, base: str, head: str) -> str:
        # Multiple merge bases must not silently select a different deletion set.
        return self._oid(self.read("merge-base", "--all", base, head))

    @staticmethod
    def _oid(output: bytes) -> str:
        value = output.decode("ascii", errors="replace").strip()
        if not _OID.fullmatch(value):
            raise RuntimeError("Git snapshot requires one unambiguous commit or object ID.")
        return value

    def tree(self, revision: str) -> dict[str, TreeEntry]:
        output = self.read("ls-tree", "-r", "-t", "-z", "--full-tree", revision, limit=_TREE_LIMIT)
        entries: dict[str, TreeEntry] = {}
        try:
            for record in output.split(b"\0"):
                if not record:
                    continue
                metadata, name = record.split(b"\t", 1)
                mode, _kind, oid = metadata.decode("ascii").split()
                entries[name.decode("utf-8")] = TreeEntry(mode, self._oid(oid.encode("ascii")))
        except (UnicodeError, ValueError) as exc:
            raise RuntimeError("Git tree contains unsupported metadata or non-UTF-8 paths.") from exc
        return entries

    def text(self, entry: TreeEntry, *, limit: int) -> str:
        size = self.read("cat-file", "-s", entry.oid)
        if not size.strip().isdigit() or int(size) > limit:
            raise ValueError("document exceeds the size limit")
        return self.read("cat-file", "blob", entry.oid, limit=limit).decode("utf-8-sig")
