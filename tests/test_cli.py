from pathlib import Path
import json
import math
import wave
import zipfile

import pytest

from split_peel.cli import main
from split_peel.package_ids import make_id


def test_draft_script_refuses_to_overwrite_existing_script(tmp_path: Path):
    script_path = tmp_path / "script.json"
    script_path.write_text('{"dialogue":[]}', encoding="utf-8")

    with pytest.raises(SystemExit, match="already exists"):
        main(["draft-script", "--feed", str(tmp_path / "missing-feed.json"), "--out", str(script_path)])


def test_new_show_command_writes_starter_show(tmp_path: Path):
    output = tmp_path / "starter.bannyshow"

    main(["new-show", "--out", str(output), "--characters", "2"])

    show = json.loads((output / "show.json").read_text(encoding="utf-8"))
    assert show["stage"]["characters"][0]["name"] == "Split"
    assert show["stage"]["characters"][1]["name"] == "Peel"


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


def test_make_writes_voice_manifest_and_builds_from_reused_audio(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    template = tmp_path / "template.bs"
    reuse = tmp_path / "reuse.bs"
    output = tmp_path / "episode.bs"
    line = {"id": "split-setup", "speaker": "split", "line": "Manifest first.", "tone": "dry"}
    clip_id = make_id(f"000-split-{line['line']}-{line['tone']}")
    show = {
        "show": [{"from": 0, "to": 5}],
        "assets": [],
        "stage": {
            "audioTracks": [{"clips": []}],
            "backgroundTracks": [],
            "characters": [{"events": [], "subs": []}, {"events": [], "subs": []}],
        },
    }
    with zipfile.ZipFile(template, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("show.json", json.dumps(show))
    with zipfile.ZipFile(reuse, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("show.json", json.dumps(show))
        archive.writestr(f"audio/{clip_id}.wav", _test_wav_bytes([(0.0, 0.3, 7000)]))

    monkeypatch.setattr("split_peel.cli.fetch_feed", lambda url: {"casts": []})
    monkeypatch.setattr(
        "split_peel.cli.draft_script",
        lambda *args, **kwargs: {"dialogue": [line], "outroEffect": {"enabled": False}},
    )

    main(
        [
            "make",
            "--template",
            str(template),
            "--run-dir",
            str(run_dir),
            "--out",
            str(output),
            "--no-espn",
            "--no-memory",
            "--reuse-audio-from",
            str(reuse),
            "--skip-voice",
        ]
    )

    manifest = json.loads((run_dir / "voice-manifest.json").read_text(encoding="utf-8"))
    with zipfile.ZipFile(output) as archive:
        rendered = json.loads(archive.read("show.json"))

    assert manifest["clips"][0]["line_id"] == "split-setup"
    assert (run_dir / manifest["clips"][0]["path"]).exists()
    assert rendered["stage"]["audioTracks"][0]["clips"][0]["id"] == clip_id


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


def test_upload_youtube_dry_run_can_build_metadata_from_script(tmp_path: Path, capsys):
    movie = tmp_path / "episode.mp4"
    script = tmp_path / "script.json"
    out = tmp_path / "youtube-upload.json"
    movie.write_text("mp4", encoding="utf-8")
    script.write_text(
        json.dumps(
            {
                "title": "Script Built Title",
                "beats": ["Beat one", "Beat two"],
            }
        ),
        encoding="utf-8",
    )

    main(
        [
            "upload-youtube",
            "--file",
            str(movie),
            "--script",
            str(script),
            "--tags",
            "football,final whistle",
            "--out",
            str(out),
            "--dry-run",
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    snippet = printed["request"]["body"]["snippet"]
    assert snippet["title"] == "Script Built Title"
    assert snippet["description"] == "Script Built Title\n\nThe whistle goes, the takes stay loud."


def test_upload_youtube_requires_title_or_script_title(tmp_path: Path):
    movie = tmp_path / "episode.mp4"
    movie.write_text("mp4", encoding="utf-8")

    with pytest.raises(SystemExit, match="--title is required"):
        main(["upload-youtube", "--file", str(movie), "--dry-run"])


def test_update_youtube_dry_run_builds_public_metadata_from_script(tmp_path: Path, capsys):
    script = tmp_path / "script.json"
    script.write_text(json.dumps({"title": "Script Built Title", "beats": ["internal note"]}), encoding="utf-8")

    main(
        [
            "update-youtube",
            "--video-id",
            "abc123",
            "--script",
            str(script),
            "--tags",
            "football,final whistle",
            "--out",
            str(tmp_path / "youtube-update.json"),
            "--dry-run",
        ]
    )

    printed = json.loads(capsys.readouterr().out)
    snippet = printed["request"]["body"]["snippet"]
    assert snippet["title"] == "Script Built Title"
    assert snippet["description"] == "Script Built Title\n\nThe whistle goes, the takes stay loud."
    assert "internal note" not in snippet["description"]


def test_generate_youtube_thumbnail_command_writes_image(tmp_path: Path, capsys):
    out = tmp_path / "youtube-thumbnail.png"

    main(["generate-youtube-thumbnail", "--out", str(out), "--title", "Shopping For A Club"])

    result = json.loads(capsys.readouterr().out)
    assert result["width"] == 1280
    assert result["height"] == 720
    assert out.exists()


def test_generate_youtube_banner_command_writes_image(tmp_path: Path, capsys):
    out = tmp_path / "channel-banner.png"

    main(["generate-youtube-banner", "--out", str(out), "--show-safe-area"])

    result = json.loads(capsys.readouterr().out)
    assert result["width"] == 2560
    assert result["height"] == 1440
    assert result["safe_area"]["width"] == 1546
    assert out.exists()


def _test_wav_bytes(segments, sample_rate: int = 22050) -> bytes:
    import io

    samples = []
    for start, end, amplitude in segments:
        frame_count = int((end - start) * sample_rate)
        for index in range(frame_count):
            value = int(amplitude * math.sin(2 * math.pi * 220 * (index / sample_rate))) if amplitude else 0
            samples.append(value)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))
    return buffer.getvalue()
