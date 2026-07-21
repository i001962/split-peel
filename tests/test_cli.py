from pathlib import Path

import pytest

from split_peel.cli import main


def test_draft_script_refuses_to_overwrite_existing_script(tmp_path: Path):
    script_path = tmp_path / "script.json"
    script_path.write_text('{"dialogue":[]}', encoding="utf-8")

    with pytest.raises(SystemExit, match="already exists"):
        main(["draft-script", "--feed", str(tmp_path / "missing-feed.json"), "--out", str(script_path)])


def test_draft_script_backs_up_existing_script_before_explicit_overwrite(tmp_path: Path, monkeypatch):
    feed_path = tmp_path / "feed.json"
    script_path = tmp_path / "script.json"
    feed_path.write_text('{"casts":[]}', encoding="utf-8")
    script_path.write_text('{"dialogue":[{"line":"manual edit"}]}', encoding="utf-8")
    monkeypatch.setenv("SPLIT_PEEL_VOICE_PROVIDER", "local")

    main(["draft-script", "--feed", str(feed_path), "--out", str(script_path), "--overwrite-script"])

    assert script_path.with_suffix(".json.bak").read_text(encoding="utf-8") == '{"dialogue":[{"line":"manual edit"}]}'
