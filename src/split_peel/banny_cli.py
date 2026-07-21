from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


class BannyCliError(RuntimeError):
    pass


@dataclass
class BannyCommandResult:
    command: list[str]
    returncode: int
    stdout: str
    stderr: str


@dataclass
class BannyCli:
    command_prefix: list[str]
    cwd: Optional[Path] = None

    def run(self, args: list[str]) -> BannyCommandResult:
        command = [*self.command_prefix, *args]
        completed = subprocess.run(
            command,
            cwd=self.cwd,
            text=True,
            capture_output=True,
            check=False,
        )
        result = BannyCommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
        if completed.returncode != 0:
            raise BannyCliError(_format_failure(result))
        return result

    def catalog(self) -> BannyCommandResult:
        return self.run(["catalog", "--json"])

    def validate(self, show: Path) -> BannyCommandResult:
        return self.run(["validate", str(show), "--json"])

    def info(self, show: Path) -> BannyCommandResult:
        return self.run(["info", str(show), "--json"])

    def preview(self, show: Path, out: Path, timestamp: float) -> BannyCommandResult:
        out.parent.mkdir(parents=True, exist_ok=True)
        return self.run(["preview", str(show), str(out), "--t", _seconds(timestamp)])

    def ship(self, show: Path, out: Path, render_size: str) -> BannyCommandResult:
        out.parent.mkdir(parents=True, exist_ok=True)
        return self.run(["ship", str(show), str(out), f"--{render_size}"])


def resolve_banny_cli(banny_bin: Optional[Path] = None, checkout_path: Optional[Path] = None) -> BannyCli:
    explicit_bin = banny_bin or _env_path("BANNY_BIN")
    if explicit_bin:
        if not explicit_bin.exists():
            raise BannyCliError(f"Banny CLI not found at {explicit_bin}")
        return BannyCli([str(explicit_bin)])

    path_bin = shutil.which("banny")
    if path_bin:
        return BannyCli([path_bin])

    checkout = checkout_path or _env_path("BANNY_STUDIO_CHECKOUT")
    if checkout:
        package_file = checkout / "Package.swift"
        if not package_file.exists():
            raise BannyCliError(f"Banny Studio checkout missing Package.swift: {checkout}")
        return BannyCli(["swift", "run", "banny"], cwd=checkout)

    raise BannyCliError(
        "Banny CLI is enabled but unavailable. Install `banny`, set BANNY_BIN, "
        "or set BANNY_STUDIO_CHECKOUT to a local banny-studio checkout."
    )


def _env_path(name: str) -> Optional[Path]:
    raw = os.environ.get(name)
    if not raw:
        return None
    return Path(raw).expanduser()


def _seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _format_failure(result: BannyCommandResult) -> str:
    pieces = [
        f"Banny command failed with exit {result.returncode}: {' '.join(result.command)}",
    ]
    if result.stdout.strip():
        pieces.append(f"stdout:\n{result.stdout.strip()}")
    if result.stderr.strip():
        pieces.append(f"stderr:\n{result.stderr.strip()}")
    return "\n".join(pieces)
