from pathlib import Path

import pytest

from split_peel.banny_cli import BannyCliError, resolve_banny_cli


def test_resolve_banny_cli_prefers_explicit_binary(tmp_path: Path):
    fake = tmp_path / "banny"
    fake.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")

    cli = resolve_banny_cli(banny_bin=fake)

    assert cli.command_prefix == [str(fake)]
    assert cli.cwd is None


def test_resolve_banny_cli_supports_local_checkout(tmp_path: Path, monkeypatch):
    checkout = tmp_path / "banny-studio"
    checkout.mkdir()
    (checkout / "Package.swift").write_text("// package", encoding="utf-8")
    monkeypatch.setenv("PATH", "")

    cli = resolve_banny_cli(checkout_path=checkout)

    assert cli.command_prefix == ["swift", "run", "banny"]
    assert cli.cwd == checkout


def test_banny_cli_raises_on_failed_command(tmp_path: Path):
    fake = tmp_path / "banny"
    fake.write_text("#!/bin/sh\necho bad >&2\nexit 2\n", encoding="utf-8")
    fake.chmod(0o755)
    cli = resolve_banny_cli(banny_bin=fake)

    with pytest.raises(BannyCliError, match="exit 2"):
        cli.validate(tmp_path / "show.bs")
