import json
from pathlib import Path

from split_peel.cli import main
from split_peel.social_clips import build_social_clip_specs, write_social_clip_artifacts


def test_build_social_clip_specs_selects_two_funny_ranges(tmp_path: Path):
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "voice-manifest.json"
    script_path.write_text(json.dumps({"title": "Derby Day", "dialogue": []}), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "script_path": "script.json",
                "audio_dir": "voice/audio",
                "clips": [
                    _clip("split-001", "split", "Team news is in.", "calm", 0.5, 2.0),
                    _clip("peel-002", "peel", "Wait, their left back brought a spreadsheet to a knife fight?", "shocked", 4.0, 3.0),
                    _clip("split-003", "split", "That is not inverted, that is emotionally folded.", "deadpan", 8.0, 3.2),
                    _clip("peel-004", "peel", "Please tell the mascot to stop warming up.", "mock-serious", 16.0, 2.8),
                ],
            }
        ),
        encoding="utf-8",
    )

    specs = build_social_clip_specs(script_path, manifest_path, count=2)

    assert len(specs) == 2
    assert specs[0].slug == "sound-bite-01"
    assert specs[0].start >= 0
    assert specs[0].duration <= 22
    assert specs[0].line_ids
    assert specs[1].line_ids
    assert set(specs[0].line_ids).isdisjoint(specs[1].line_ids)


def test_social_clips_command_exports_banny_ranges(tmp_path: Path):
    fake = tmp_path / "banny"
    fake.write_text(
        "\n".join(
            [
                "#!/bin/sh",
                "case \"$1\" in",
                "  ship) mkdir -p \"$(dirname \"$3\")\"; printf '%s' \"$*\" > \"$3\" ;;",
                "  *) exit 9 ;;",
                "esac",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "voice-manifest.json"
    show_path = tmp_path / "show.bs"
    show_path.write_text("show", encoding="utf-8")
    script_path.write_text(json.dumps({"title": "Derby Day"}), encoding="utf-8")
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "script_path": "script.json",
                "audio_dir": "voice/audio",
                "clips": [
                    _clip("split-001", "split", "Wait, this press is wearing roller skates?", "shocked", 1.0, 2.0),
                    _clip("peel-002", "peel", "Sir, the midfield is a lost property desk.", "mock-serious", 5.0, 2.0),
                ],
            }
        ),
        encoding="utf-8",
    )
    out_dir = tmp_path / "social"

    main(
        [
            "social-clips",
            "--script",
            str(script_path),
            "--voice-manifest",
            str(manifest_path),
            "--show",
            str(show_path),
            "--out-dir",
            str(out_dir),
            "--banny-bin",
            str(fake),
        ]
    )

    manifest = json.loads((out_dir / "social-clips.json").read_text(encoding="utf-8"))
    assert manifest["clip_count"] == 2
    assert (out_dir / "sound-bite-01.mp4").exists()
    assert "--range" in (out_dir / "sound-bite-01.mp4").read_text(encoding="utf-8")
    assert "Farcaster" in (out_dir / "social-posts.md").read_text(encoding="utf-8")


def test_write_social_clip_artifacts_records_platform_posts(tmp_path: Path):
    result = {
        "version": 1,
        "clip_count": 1,
        "platforms": ["x", "farcaster"],
        "clips": [
            {
                "slug": "sound-bite-01",
                "title": "Clip",
                "path": str(tmp_path / "clip.mp4"),
                "start": 1,
                "end": 7,
                "duration": 6,
                "line_ids": ["split-001"],
                "x_post": "x copy",
                "farcaster_cast": "fc copy",
            }
        ],
    }

    paths = write_social_clip_artifacts(result, tmp_path)

    assert Path(paths["manifest"]).exists()
    assert "x copy" in Path(paths["handoff"]).read_text(encoding="utf-8")


def _clip(line_id: str, speaker: str, text: str, tone: str, start: float, duration: float) -> dict:
    return {
        "line_id": line_id,
        "line_index": 0,
        "speaker": speaker,
        "text": text,
        "tone": tone,
        "audio_id": line_id,
        "start": start,
        "duration": duration,
        "path": f"voice/audio/{line_id}.wav",
    }
