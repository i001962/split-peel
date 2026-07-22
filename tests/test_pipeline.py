import json
import zipfile
from pathlib import Path

import pytest

from split_peel.pipeline import (
    PipelineError,
    build_pipeline_plan,
    load_pipeline_config,
    run_banny_post_build,
    run_youtube_upload,
    run_studio_pipeline,
    write_movie_export_handoff,
    write_pipeline_config_template,
    write_studio_qa_checklist,
)


def test_load_pipeline_config_resolves_relative_paths_from_cwd(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "duration_sec": 45,
                "background_gain": 0.18,
                "no_espn": True,
                "instructions": "Keep it tight.",
                "draft_only": True,
                "reuse_audio_from": "outputs/previous.bs",
                "skip_voice": True,
            }
        ),
        encoding="utf-8",
    )

    config = load_pipeline_config(config_path)

    assert config.episode_slug == "demo"
    assert config.template_path == tmp_path / "templates/base.bs"
    assert config.run_dir == tmp_path / "runs/demo"
    assert config.output_bs == tmp_path / "outputs/demo.bs"
    assert config.output_bannyshow == tmp_path / "outputs/demo.bannyshow"
    assert config.output_movie == tmp_path / "outputs/demo.mp4"
    assert config.duration_sec == 45
    assert config.background_gain == 0.18
    assert config.no_feed is False
    assert config.no_espn is True
    assert config.overwrite_script is False
    assert config.draft_only is True
    assert config.reuse_audio_from == tmp_path / "outputs/previous.bs"
    assert config.skip_voice is True
    assert config.banny_enabled is False


def test_build_pipeline_plan_lists_artifacts_and_stages(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "run_dir": "runs/demo",
                "output_bs": "outputs/demo.bs",
                "output_bannyshow": "outputs/demo.bannyshow",
                "no_espn": False,
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)

    plan = build_pipeline_plan(config)

    assert plan["episode_slug"] == "demo"
    assert "fetch-scoreboard" in plan["stages"]
    assert plan["artifacts"]["script"] == str(tmp_path / "runs/demo/script.json")
    assert plan["artifacts"]["output_bannyshow"] == str(tmp_path / "outputs/demo.bannyshow")
    assert plan["artifacts"]["output_movie"] == str(tmp_path / "outputs/demo.mp4")
    assert plan["artifacts"]["movie_handoff"] == str(tmp_path / "runs/demo/movie-export-handoff.md")
    assert plan["overwrite_script"] is False


def test_build_pipeline_plan_includes_banny_stages_when_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "banny_enabled": True,
                "banny_preview_times": [1.5, 3],
                "banny_ship": True,
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)

    plan = build_pipeline_plan(config)

    assert "banny-validate" in plan["stages"]
    assert "banny-info" in plan["stages"]
    assert "banny-preview" in plan["stages"]
    assert "banny-ship" in plan["stages"]
    assert plan["artifacts"]["banny_validate"] == str(tmp_path / "runs/demo/banny-validate.json")
    assert plan["artifacts"]["banny_previews"] == [
        str(tmp_path / "runs/demo/preview-01-500.png"),
        str(tmp_path / "runs/demo/preview-03-000.png"),
    ]


def test_build_pipeline_plan_includes_youtube_stage_when_enabled(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "youtube_upload_enabled": True,
                "youtube_title": "Demo Upload",
                "youtube_tags": ["football", "clips"],
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)

    plan = build_pipeline_plan(config)

    assert "youtube-upload" in plan["stages"]
    assert plan["artifacts"]["youtube_upload"] == str(tmp_path / "runs/demo/youtube-upload.json")
    assert config.youtube_title == "Demo Upload"
    assert config.youtube_tags == ("football", "clips")
    assert config.youtube_privacy_status == "private"


def test_build_pipeline_plan_uses_empty_feed_stage_when_no_feed(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "no_feed": True,
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)

    plan = build_pipeline_plan(config)

    assert "write-empty-feed" in plan["stages"]
    assert "fetch-feed" not in plan["stages"]


def test_build_pipeline_plan_skips_package_stages_when_draft_only(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "draft_only": True,
                "banny_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)

    plan = build_pipeline_plan(config)

    assert "draft-script" in plan["stages"]
    assert "build-show" not in plan["stages"]
    assert "unpack" not in plan["stages"]
    assert "banny-validate" not in plan["stages"]
    assert "youtube-upload" not in plan["stages"]


def test_run_banny_post_build_writes_validation_preview_and_movie(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    fake = tmp_path / "banny"
    fake.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "case \"$1\" in",
                "  catalog) echo '{\"slots\":[{\"slot\":6,\"outfits\":[{\"name\":\"proff-glasses\"}]}]}' ;;",
                "  validate) echo '{\"diagnostics\":[]}' ;;",
                "  info) echo '{\"tracks\":1}' ;;",
                "  preview) mkdir -p \"$(dirname \"$3\")\"; printf 'png' > \"$3\" ;;",
                "  ship) mkdir -p \"$(dirname \"$3\")\"; printf 'mp4' > \"$3\" ;;",
                "  *) exit 9 ;;",
                "esac",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    show_path = tmp_path / "outputs/demo.bs"
    show_path.parent.mkdir(parents=True)
    with zipfile.ZipFile(show_path, "w") as archive:
        archive.writestr(
            "show.json",
            json.dumps(
                {
                    "assets": [],
                    "stage": {
                        "audioTracks": [],
                        "backgroundTracks": [],
                        "characters": [{"baseOutfit": {"6": "proff-glasses"}}],
                    },
                }
            ),
        )
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "output_bs": "outputs/demo.bs",
                "output_movie": "outputs/demo.mp4",
                "banny_enabled": True,
                "banny_bin": str(fake),
                "banny_preview_times": [2],
                "banny_ship": True,
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)
    config.run_dir.mkdir(parents=True)

    result = run_banny_post_build(config)

    assert (tmp_path / "runs/demo/banny-validate.json").read_text(encoding="utf-8").strip() == '{"diagnostics":[]}'
    assert (tmp_path / "runs/demo/banny-catalog.json").read_text(encoding="utf-8").strip().startswith('{"slots"')
    assert json.loads((tmp_path / "runs/demo/banny-wardrobe-repairs.json").read_text(encoding="utf-8")) == []
    assert (tmp_path / "runs/demo/banny-info.json").read_text(encoding="utf-8").strip() == '{"tracks":1}'
    assert (tmp_path / "runs/demo/preview-02-000.png").read_text(encoding="utf-8") == "png"
    assert (tmp_path / "outputs/demo.mp4").read_text(encoding="utf-8") == "mp4"
    assert result["movie"] == str(tmp_path / "outputs/demo.mp4")


def test_run_youtube_upload_requires_existing_movie(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "youtube_upload_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)

    with pytest.raises(PipelineError, match="movie file does not exist"):
        run_youtube_upload(config, {"title": "Demo"})


def test_run_youtube_upload_uses_generated_metadata_and_writes_result(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "output_movie": "outputs/demo.mp4",
                "youtube_upload_enabled": True,
                "youtube_tags": "football,final whistle",
                "youtube_token": ".secrets/token.json",
            }
        ),
        encoding="utf-8",
    )
    movie = tmp_path / "outputs/demo.mp4"
    movie.parent.mkdir(parents=True)
    movie.write_text("mp4", encoding="utf-8")
    config = load_pipeline_config(config_path)
    config.run_dir.mkdir(parents=True)
    calls = {}

    def fake_upload(video_path, metadata, **kwargs):
        calls["video_path"] = video_path
        calls["metadata"] = metadata
        calls["kwargs"] = kwargs
        result = {"video_id": "abc123", "url": "https://youtu.be/abc123"}
        kwargs["out_path"].write_text(json.dumps(result), encoding="utf-8")
        return result

    monkeypatch.setattr("split_peel.pipeline.upload_video", fake_upload)

    result = run_youtube_upload(config, {"title": "Script Title", "beats": ["One", "Two"]})

    assert result["video_id"] == "abc123"
    assert calls["video_path"] == movie
    assert calls["metadata"].title == "Script Title"
    assert calls["metadata"].tags == ("football", "final whistle")
    assert "Episode beats:" in calls["metadata"].description
    assert calls["kwargs"]["token_path"] == tmp_path / ".secrets/token.json"
    assert (tmp_path / "runs/demo/youtube-upload.json").exists()


def test_studio_pipeline_refuses_to_overwrite_existing_script(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "no_espn": True,
            }
        ),
        encoding="utf-8",
    )
    script_path = tmp_path / "runs/demo/script.json"
    script_path.parent.mkdir(parents=True)
    script_path.write_text('{"dialogue":[]}', encoding="utf-8")

    with pytest.raises(PipelineError, match="already exists"):
        run_studio_pipeline(load_pipeline_config(config_path))


def test_studio_pipeline_backs_up_script_when_overwrite_is_explicit(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
                "overwrite_script": True,
            }
        ),
        encoding="utf-8",
    )
    script_path = tmp_path / "runs/demo/script.json"
    script_path.parent.mkdir(parents=True)
    script_path.write_text('{"dialogue":[{"line":"manual edit"}]}', encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        run_studio_pipeline(load_pipeline_config(config_path))

    assert script_path.with_suffix(".json.bak").read_text(encoding="utf-8") == '{"dialogue":[{"line":"manual edit"}]}'


def test_write_studio_qa_checklist_includes_review_gates(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)
    checklist_path = tmp_path / "qa.md"

    write_studio_qa_checklist(config, checklist_path)

    checklist = checklist_path.read_text(encoding="utf-8")
    assert "Studio QA Checklist: demo" in checklist
    assert "Dialogue is audible" in checklist
    assert "outputs/demo.mp4" in checklist


def test_write_movie_export_handoff_includes_package_and_movie_paths(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"
    config_path.write_text(
        json.dumps(
            {
                "episode_slug": "demo",
                "template_path": "templates/base.bs",
            }
        ),
        encoding="utf-8",
    )
    config = load_pipeline_config(config_path)
    handoff_path = tmp_path / "handoff.md"

    write_movie_export_handoff(config, handoff_path)

    handoff = handoff_path.read_text(encoding="utf-8")
    assert "Movie Export Handoff: demo" in handoff
    assert "outputs/demo.bs" in handoff
    assert "outputs/demo.mp4" in handoff


def test_write_pipeline_config_template_roundtrips(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "pipeline.json"

    write_pipeline_config_template(config_path)
    config = load_pipeline_config(config_path)

    assert config.episode_slug == "pipeline-smoke"
    assert config.output_bs == tmp_path / "outputs/pipeline-smoke.bs"
    assert config.output_movie == tmp_path / "outputs/pipeline-smoke.mp4"
    assert config.banny_enabled is True
    assert config.banny_preview_times == (2.0, 8.0, 14.0)
    assert config.banny_ship is True
    assert config.youtube_upload_enabled is False
    assert config.youtube_token == tmp_path / ".secrets/youtube-token.json"
