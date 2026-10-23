"""Portable artifact identity and durable local job state."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    if path.is_dir():
        for child in sorted(path.rglob("*")):
            if child.is_file() and child.name != ".DS_Store":
                hasher.update(child.relative_to(path).as_posix().encode())
                hasher.update(b"\0")
                hasher.update(bytes.fromhex(digest(child)))
    else:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                hasher.update(block)
    return hasher.hexdigest()


def identity(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, ensure_ascii=False, default=str)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextmanager
def job_lock(path: Path):
    """Advisory lock released by the OS after crashes; supported on Mac/Linux."""
    import fcntl
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(f"Another process is working on {path.parent}") from error
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


class StageJournal:
    def __init__(self, path: Path, resume: bool = True):
        self.path = path
        self.resume = resume
        self.state = read_json(path) if path.exists() else {"version": 1, "stages": {}}

    def run(self, name, inputs, outputs, action):
        fingerprint = identity(inputs)
        previous = self.state["stages"].get(name, {})
        current_outputs = outputs() if callable(outputs) else outputs
        if (self.resume and previous.get("status") == "complete"
                and previous.get("inputs") == fingerprint
                and len(current_outputs) == len(previous.get("outputs", {}))
                and all(p.exists() and digest(p) == previous.get("outputs", {}).get(str(i))
                        for i, p in enumerate(current_outputs))):
            return previous.get("result")
        entry = {"status": "running", "inputs": fingerprint, "started_at": datetime.now(timezone.utc).isoformat()}
        self.state["stages"][name] = entry
        atomic_json(self.path, self.state)
        try:
            result = action()
            current_outputs = outputs() if callable(outputs) else outputs
            entry.update(status="complete", result=result,
                         outputs={str(i): digest(p) for i, p in enumerate(current_outputs)})
        except Exception as error:
            entry.update(status="failed", error_type=type(error).__name__)
            atomic_json(self.path, self.state)
            raise
        atomic_json(self.path, self.state)
        return result


def approve_artifact(path: Path, out: Path, purpose: str) -> dict:
    result = {"version": 1, "purpose": purpose, "sha256": digest(path),
              "artifact": os.path.relpath(path.resolve(), out.resolve().parent),
              "approved_at": datetime.now(timezone.utc).isoformat()}
    atomic_json(out, result)
    return result


def require_approval(path: Path, receipt: Path, purpose: str) -> None:
    value = read_json(receipt)
    if value.get("version") != 1 or value.get("purpose") != purpose or value.get("sha256") != digest(path):
        raise ValueError(f"Approval does not match the current {purpose} artifact: {path}")
