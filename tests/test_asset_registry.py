import json
import math
import wave
import zipfile
from pathlib import Path

from split_peel.asset_registry import extract_asset_registry
from split_peel.cli import main
from split_peel.package import build_show_from_registry


def test_extract_asset_registry_captures_studio_stage(tmp_path: Path):
    source = tmp_path / "studio.bannyshow"
    registry_path = tmp_path / "registry.json"
    (source / "assets").mkdir(parents=True)
    (source / "assets" / "studio.png").write_bytes(b"png")
    (source / "show.json").write_text(json.dumps(_studio_show()), encoding="utf-8")

    registry = extract_asset_registry(source, registry_path, preset_id="instudio", preset_name="In Studio")

    assert registry["scenePresets"][0]["id"] == "instudio"
    assert registry["scenePresets"][0]["stage"]["characters"][1]["name"] == "Peel"
    assert registry["scenePresets"][0]["stage"]["reactionLibrary"][0]["id"] == "wide-eyes-open-mouth"
    assert registry_path.exists()


def test_build_show_from_registry_composes_fresh_bannyshow(tmp_path: Path):
    source = tmp_path / "studio.bannyshow"
    registry_path = tmp_path / "registry.json"
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "voice-manifest.json"
    output = tmp_path / "fresh.bannyshow"
    clip_id = "dialogue-fresh-one"
    (source / "assets").mkdir(parents=True)
    (source / "assets" / "studio.png").write_bytes(b"png")
    (source / "show.json").write_text(json.dumps(_studio_show()), encoding="utf-8")
    (tmp_path / "voice" / "audio").mkdir(parents=True)
    _write_test_wav(tmp_path / "voice" / "audio" / f"{clip_id}.wav", [(0.0, 0.4, 7000)])
    script_path.write_text(json.dumps({"dialogue": [{"id": "split-001", "speaker": "split", "line": "Fresh build."}]}), encoding="utf-8")
    manifest_path.write_text(json.dumps(_voice_manifest(clip_id)), encoding="utf-8")
    extract_asset_registry(source, registry_path, preset_id="instudio")

    build_show_from_registry(registry_path, script_path, output, scene_preset_id="instudio", voice_manifest=manifest_path)

    rendered = json.loads((output / "show.json").read_text(encoding="utf-8"))
    assert (output / "assets" / "studio.png").exists()
    assert (output / "audio" / f"{clip_id}.wav").exists()
    assert rendered["stage"]["characters"][0]["subs"][0]["text"] == "Fresh build."
    assert rendered["stage"]["audioTracks"][0]["clips"][0]["id"] == clip_id


def test_extract_and_compose_commands_round_trip_registry(tmp_path: Path):
    source = tmp_path / "studio.bannyshow"
    registry_path = tmp_path / "registry.json"
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "voice-manifest.json"
    output = tmp_path / "fresh.bs"
    clip_id = "dialogue-cli-compose"
    (source / "assets").mkdir(parents=True)
    (source / "assets" / "studio.png").write_bytes(b"png")
    (source / "show.json").write_text(json.dumps(_studio_show()), encoding="utf-8")
    (tmp_path / "voice" / "audio").mkdir(parents=True)
    _write_test_wav(tmp_path / "voice" / "audio" / f"{clip_id}.wav", [(0.0, 0.25, 7000)])
    script_path.write_text(json.dumps({"dialogue": [{"id": "split-001", "speaker": "split", "line": "Fresh build."}]}), encoding="utf-8")
    manifest_path.write_text(json.dumps(_voice_manifest(clip_id)), encoding="utf-8")

    main(["extract-studio-assets", "--source", str(source), "--out", str(registry_path), "--preset-id", "instudio"])
    main(
        [
            "compose-show",
            "--registry",
            str(registry_path),
            "--scene-preset",
            "instudio",
            "--script",
            str(script_path),
            "--voice-manifest",
            str(manifest_path),
            "--out",
            str(output),
        ]
    )

    with zipfile.ZipFile(output) as archive:
        rendered = json.loads(archive.read("show.json"))
        names = archive.namelist()
    assert "assets/studio.png" in names
    assert rendered["stage"]["audioTracks"][0]["clips"][0]["id"] == clip_id


def _studio_show():
    return {
        "version": 3,
        "assets": [{"id": "studio-bg", "name": "Studio", "kind": "image", "file": "studio.png"}],
        "settings": {"activeScene": 0, "lightSize": 0, "frameW": 16, "frameH": 9},
        "show": [{"sceneID": "", "name": "Studio", "from": 0, "to": 5}],
        "stage": {
            "reactionLibrary": [
                {
                    "id": "wide-eyes-open-mouth",
                    "name": "Wide Eyes Open Mouth",
                    "dur": 1.0,
                    "events": [{"t": 0, "code": "Comma", "down": True}],
                }
            ],
            "audioTracks": [{"id": "dialogue", "name": "Dialogue", "clips": []}],
            "backgroundTracks": [
                {
                    "id": "background",
                    "name": "Background",
                    "hidden": False,
                    "presence": [],
                    "cues": [{"id": "bg", "assetID": "studio-bg", "start": 0, "dur": 5, "crop": "cover"}],
                }
            ],
            "imageTracks": [],
            "lightTracks": [],
            "lights": [],
            "characters": [
                {"name": "Split", "body": "orange", "x": 0.34, "face": 1, "events": [], "subs": []},
                {"name": "Peel", "body": "pink", "x": 0.66, "face": -1, "events": [], "subs": []},
            ],
        },
    }


def _voice_manifest(clip_id):
    return {
        "version": 1,
        "script_path": "script.json",
        "audio_dir": "voice/audio",
        "clips": [
            {
                "line_id": "split-001",
                "line_index": 0,
                "speaker": "split",
                "text": "Fresh build.",
                "tone": "",
                "text_hash": "abc",
                "audio_id": clip_id,
                "start": 0.5,
                "duration": 0.4,
                "path": f"voice/audio/{clip_id}.wav",
                "mouth_events": [],
                "eye_events": [],
            }
        ],
    }


def _write_test_wav(path: Path, segments, sample_rate: int = 22050) -> None:
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
    path.write_bytes(buffer.getvalue())
