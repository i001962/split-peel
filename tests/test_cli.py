from pathlib import Path
import json

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


def test_draft_script_accepts_episode_cli_metadata(tmp_path: Path, monkeypatch):
    feed_path = tmp_path / "feed.json"
    script_path = tmp_path / "script.json"
    feed_path.write_text('{"casts":[]}', encoding="utf-8")
    monkeypatch.setenv("SPLIT_PEEL_VOICE_PROVIDER", "local")

    main(
        [
            "draft-script",
            "--feed",
            str(feed_path),
            "--out",
            str(script_path),
            "--episode-title",
            "ENG1 Game Week 01 Preview",
            "--episode-type",
            "game-week-preview",
        ]
    )

    assert '"title": "ENG1 Game Week 01 Preview"' in script_path.read_text(encoding="utf-8")


def test_draft_script_accepts_outtake_episode_type(tmp_path: Path, monkeypatch):
    feed_path = tmp_path / "feed.json"
    script_path = tmp_path / "script.json"
    feed_path.write_text('{"casts":[]}', encoding="utf-8")
    monkeypatch.setenv("SPLIT_PEEL_VOICE_PROVIDER", "local")

    main(
        [
            "draft-script",
            "--feed",
            str(feed_path),
            "--out",
            str(script_path),
            "--episode-title",
            "ENG1 Hot Mic",
            "--episode-type",
            "outtake",
        ]
    )

    payload = script_path.read_text(encoding="utf-8")
    assert '"episodeType": "outtake"' in payload
    assert '"type": "cold-open"' in payload


def test_make_draft_only_writes_script_without_building(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    script_path = run_dir / "script.json"
    output = tmp_path / "episode.bs"
    monkeypatch.setattr("split_peel.cli.fetch_feed", lambda url: {"casts": []})

    def fail_build(*args, **kwargs):
        raise AssertionError("draft-only should not build or synthesize audio")

    monkeypatch.setattr("split_peel.cli.build_show", fail_build)

    main(
        [
            "make",
            "--template",
            str(tmp_path / "missing-template.bs"),
            "--run-dir",
            str(run_dir),
            "--out",
            str(output),
            "--no-espn",
            "--memory-dir",
            str(tmp_path / "memory"),
            "--draft-only",
        ]
    )

    assert script_path.exists()
    assert not output.exists()
    assert not (tmp_path / "memory").exists()


def test_upload_youtube_dry_run_writes_request_metadata(tmp_path: Path, capsys):
    movie = tmp_path / "episode.mp4"
    out = tmp_path / "youtube-upload.json"
    movie.write_text("mp4", encoding="utf-8")

    main(
        [
            "upload-youtube",
            "--file",
            str(movie),
            "--title",
            "Episode Title",
            "--description",
            "Episode description",
            "--tags",
            "football,final whistle",
            "--out",
            str(out),
            "--dry-run",
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    written = json.loads(out.read_text(encoding="utf-8"))
    assert printed["dry_run"] is True
    assert written["request"]["body"]["snippet"]["title"] == "Episode Title"
    assert written["request"]["body"]["snippet"]["tags"] == ["football", "final whistle"]
    assert written["request"]["body"]["status"]["privacyStatus"] == "private"
    assert written["request"]["body"]["status"]["selfDeclaredMadeForKids"] is False
