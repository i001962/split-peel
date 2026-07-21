import json
from pathlib import Path

import pytest

from split_peel.pipeline import (
    PipelineError,
    build_pipeline_plan,
    load_pipeline_config,
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
    assert config.no_espn is True
    assert config.overwrite_script is False


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
