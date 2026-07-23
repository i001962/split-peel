import json
import math
import wave
import zipfile
from pathlib import Path
from typing import List, Tuple

from split_peel.package import (
    _apply_character_appearance,
    _set_background_audio_gain,
    _trim_timeline_to_duration,
    _replace_character_subtitles,
    build_show,
    inspect_package,
    repair_banny_wardrobe,
    retime_mouth_events,
    roundtrip_package,
    unpack_package,
    write_starter_show,
)
from split_peel.audio import VoiceClip
from split_peel.package_ids import make_id


def test_roundtrip_package_preserves_show_json(tmp_path: Path):
    template = tmp_path / "template.bs"
    output = tmp_path / "output.bs"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "backgroundTracks": [],
            "characters": [],
        },
    }

    with zipfile.ZipFile(template, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("show.json", json.dumps(show))
        archive.writestr("assets/background.png", b"fake")

    roundtrip_package(template, output)

    assert inspect_package(output)["hasShowJson"] is True
    with zipfile.ZipFile(output) as archive:
        assert json.loads(archive.read("show.json")) == show


def test_unpack_package_extracts_show_folder(tmp_path: Path):
    template = tmp_path / "template.bs"
    output = tmp_path / "output.bannyshow"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "backgroundTracks": [],
            "characters": [],
        },
    }

    with zipfile.ZipFile(template, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("show.json", json.dumps(show))
        archive.writestr("assets/background.png", b"fake")

    unpack_package(template, output)

    assert json.loads((output / "show.json").read_text(encoding="utf-8")) == show
    assert (output / "assets" / "background.png").exists()


def test_write_starter_show_creates_editable_bannyshow(tmp_path: Path):
    output = tmp_path / "starter.bannyshow"

    write_starter_show(output, character_count=2)

    show = json.loads((output / "show.json").read_text(encoding="utf-8"))
    assert show["version"] == 3
    assert show["stage"]["characters"][0]["name"] == "Split"
    assert show["stage"]["characters"][1]["name"] == "Peel"
    assert show["stage"]["characters"][0]["armedGroups"] == ["move", "depth", "tilt", "talk", "blink", "jump", "spin", "zoom"]
    assert show["stage"]["characters"][0]["size"] == 2
    assert show["stage"]["characters"][1]["size"] == 2
    assert show["stage"]["audioTracks"][0]["name"] == "Dialogue"


def test_set_background_audio_gain_updates_tracks_and_clips():
    stage = {
        "audioTracks": [
            {"fx": {"gain": 1}, "clips": [{"fx": {"gain": 1}}]},
            {"fx": {"gain": 1}, "clips": [{"fx": {"gain": 1}}]},
        ]
    }

    _set_background_audio_gain(stage, 0.18)

    assert stage["audioTracks"][0]["fx"]["gain"] == 1
    assert stage["audioTracks"][0]["clips"][0]["fx"]["gain"] == 1
    assert stage["audioTracks"][1]["fx"]["gain"] == 0.18
    assert stage["audioTracks"][1]["clips"][0]["fx"]["gain"] == 0.18


def test_trim_timeline_to_duration_cuts_non_dialogue_tracks():
    stage = {
        "audioTracks": [
            {"name": "Dialogue", "clips": [{"start": 0.5, "dur": 10.0}]},
            {"name": "Media 2", "clips": [{"start": 0.2, "dur": 156.36}], "cues": [{"start": 20, "dur": 5}]},
        ],
        "imageTracks": [
            {"name": "Overlay", "cues": [{"start": 2.0, "dur": 20.0}, {"start": 60.0, "dur": 5.0}]}
        ],
    }

    _trim_timeline_to_duration(stage, 12.0)

    assert stage["audioTracks"][0]["clips"][0]["dur"] == 10.0
    assert stage["audioTracks"][1]["clips"][0]["dur"] == 11.8
    assert stage["audioTracks"][1]["cues"] == []
    assert stage["imageTracks"][0]["cues"] == [{"start": 2.0, "dur": 10.0}]


def test_replace_character_subtitles_uses_dialogue_timing(monkeypatch):
    stage = {
        "characters": [
            {"subs": [{"start": 0, "dur": 99, "text": "stale"}]},
            {"subs": []},
        ]
    }
    monkeypatch.setenv("SPLIT_PEEL_CAPTION_MAX_CHARS", "24")
    clips = [
        VoiceClip("split1", "split", "Split line with enough words to split", 0.5, 3.0, []),
        VoiceClip("peel1", "peel", "Peel line", 2.0, 1.6, []),
    ]

    _replace_character_subtitles(stage, clips)

    assert stage["characters"][0]["subs"] == [
        {"dur": 1.833, "start": 0.5, "text": "Split line with enough"},
        {"dur": 1.167, "start": 2.333, "text": "words to split"},
    ]
    assert stage["characters"][1]["subs"] == [{"dur": 1.6, "start": 2.0, "text": "Peel line"}]


def test_apply_character_appearance_sets_split_default_look():
    stage = {
        "characters": [
            {"baseOutfit": {"11": "zipper-jacket", "12": "headphones"}},
            {"baseOutfit": {"12": "headphones"}},
        ]
    }
    characters = {
        "characters": [
            {
                "id": "split",
                "appearance": {
                    "baseOutfit": {
                        "5": "eyeliner",
                        "7": "gapteeth",
                        "9": "sweatsuit",
                        "12": "dorthy-hair",
                    }
                },
            },
            {"id": "peel"},
        ]
    }

    _apply_character_appearance(stage, characters)

    assert stage["characters"][0]["baseOutfit"] == {
        "5": "eyeliner",
        "7": "gapteeth",
        "9": "sweatsuit",
        "12": "dorthy-hair",
    }
    assert stage["characters"][1]["baseOutfit"] == {"12": "headphones"}


def test_build_show_appends_static_disconnect_outro_effect(tmp_path: Path, monkeypatch):
    template = tmp_path / "template.bs"
    script_path = tmp_path / "script.json"
    output = tmp_path / "output.bs"
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
    script_path.write_text(
        json.dumps(
            {
                "dialogue": [{"speaker": "split", "line": "One more private note.", "tone": "dry"}],
                "outroEffect": {"type": "static-disconnect", "enabled": True, "durationSec": 0.5},
            }
        ),
        encoding="utf-8",
    )

    def fake_synthesize_dialogue(dialogue, audio_dir, characters=None, **kwargs):
        return [VoiceClip("dialogue-one", "split", "One more private note.", 0.5, 1.0, [])]

    monkeypatch.setattr("split_peel.package.synthesize_dialogue", fake_synthesize_dialogue)

    build_show(template, script_path, output)

    with zipfile.ZipFile(output) as archive:
        rendered = json.loads(archive.read("show.json"))
        names = archive.namelist()
        effect_clip = rendered["stage"]["audioTracks"][0]["clips"][-1]

    assert "audio/static-disconnect.wav" in names
    assert effect_clip["id"] == "static-disconnect"
    assert "effect" not in effect_clip
    assert effect_clip["fx"]["pan"] == "follow"
    assert effect_clip["start"] == 1.62
    assert effect_clip["dur"] == 0.5
    assert rendered["show"][0]["to"] == 3.12


def test_build_show_reuses_audio_from_existing_package_when_skip_voice(tmp_path: Path):
    template = tmp_path / "template.bs"
    reuse = tmp_path / "reuse.bs"
    script_path = tmp_path / "script.json"
    output = tmp_path / "output.bs"
    line = {"speaker": "split", "line": "Reusable line.", "tone": "dry"}
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
        archive.writestr(f"audio/{clip_id}.wav", _test_wav_bytes([(0.0, 0.35, 7000)]))
    script_path.write_text(json.dumps({"dialogue": [line], "outroEffect": {"enabled": False}}), encoding="utf-8")

    build_show(template, script_path, output, reuse_audio_from=reuse, skip_voice=True)

    with zipfile.ZipFile(output) as archive:
        rendered = json.loads(archive.read("show.json"))
        names = archive.namelist()

    assert f"audio/{clip_id}.wav" in names
    assert "_reuse_audio" not in "\n".join(names)
    assert rendered["stage"]["audioTracks"][0]["clips"][0]["id"] == clip_id


def test_build_show_uses_voice_manifest_without_synthesizing(tmp_path: Path, monkeypatch):
    template = tmp_path / "template.bannyshow"
    audio_source = tmp_path / "voice" / "audio"
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "voice-manifest.json"
    output = tmp_path / "output.bs"
    clip_id = "dialogue-manifest-one"
    template.mkdir()
    (template / "show.json").write_text(
        json.dumps(
            {
                "show": [{"from": 0, "to": 5}],
                "assets": [],
                "stage": {
                    "audioTracks": [{"clips": []}],
                    "backgroundTracks": [],
                    "characters": [{"events": [], "subs": []}, {"events": [], "subs": []}],
                },
            }
        ),
        encoding="utf-8",
    )
    audio_source.mkdir(parents=True)
    _write_test_wav(audio_source / f"{clip_id}.wav", [(0.0, 0.35, 7000)])
    script_path.write_text(
        json.dumps({"dialogue": [{"id": "split-open", "speaker": "split", "line": "Manifest line."}]}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "script_path": "script.json",
                "audio_dir": "voice/audio",
                "clips": [
                    {
                        "line_id": "split-open",
                        "line_index": 0,
                        "speaker": "split",
                        "text": "Manifest line.",
                        "tone": "",
                        "text_hash": "abc",
                        "audio_id": clip_id,
                        "start": 0.5,
                        "duration": 0.35,
                        "path": f"voice/audio/{clip_id}.wav",
                        "mouth_events": [{"code": "KeyM", "down": True, "t": 0.52}],
                        "eye_events": [{"code": "Comma", "down": True, "t": 0.55}],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    def fail_synthesize(*args, **kwargs):
        raise AssertionError("voice manifest builds must not synthesize")

    monkeypatch.setattr("split_peel.package.synthesize_dialogue", fail_synthesize)

    build_show(template, script_path, output, voice_manifest=manifest_path)

    with zipfile.ZipFile(output) as archive:
        rendered = json.loads(archive.read("show.json"))
        names = archive.namelist()

    assert f"audio/{clip_id}.wav" in names
    assert rendered["stage"]["audioTracks"][0]["clips"][0]["id"] == clip_id
    assert rendered["stage"]["characters"][0]["subs"][0]["text"] == "Manifest line."


def test_build_show_applies_script_anchored_reaction_and_camera_plan(tmp_path: Path):
    template = tmp_path / "template.bannyshow"
    audio_source = tmp_path / "voice" / "audio"
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "voice-manifest.json"
    plan_path = tmp_path / "performance-plan.json"
    output = tmp_path / "output.bs"
    clip_id = "dialogue-reaction-one"
    template.mkdir()
    (template / "show.json").write_text(
        json.dumps(
            {
                "show": [{"from": 0, "to": 5}],
                "assets": [{"id": "studio-bg", "name": "Studio", "kind": "image", "file": "studio.png"}],
                "stage": {
                    "audioTracks": [{"clips": []}],
                    "backgroundTracks": [
                        {
                            "id": "background",
                            "name": "Background",
                            "hidden": False,
                            "presence": [],
                            "cues": [{"id": "bg", "assetID": "studio-bg", "start": 0, "dur": 10, "crop": "cover"}],
                        }
                    ],
                    "characters": [
                        {"name": "Split", "events": [], "subs": []},
                        {"name": "Peel", "events": [], "subs": []},
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    audio_source.mkdir(parents=True)
    _write_test_wav(audio_source / f"{clip_id}.wav", [(0.0, 0.35, 7000)])
    script_path.write_text(
        json.dumps({"dialogue": [{"id": "peel-shock", "speaker": "peel", "line": "Manifest line."}]}),
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(
            {
                "version": 1,
                "script_path": "script.json",
                "audio_dir": "voice/audio",
                "clips": [
                    {
                        "line_id": "peel-shock",
                        "line_index": 0,
                        "speaker": "peel",
                        "text": "Manifest line.",
                        "tone": "",
                        "text_hash": "abc",
                        "audio_id": clip_id,
                        "start": 3.0,
                        "duration": 0.5,
                        "path": f"voice/audio/{clip_id}.wav",
                        "mouth_events": [],
                        "eye_events": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    plan_path.write_text(
        json.dumps(
            {
                "reactionLibrary": [
                    {
                        "id": "wide-eyes-open-mouth",
                        "name": "Wide Eyes Open Mouth",
                        "dur": 1.2,
                        "events": [
                            {"t": 0, "code": "Comma", "down": True},
                            {"t": 0, "code": "KeyM", "down": True},
                        ],
                    }
                ],
                "beats": [
                    {
                        "id": "peel-closeup-shock",
                        "line_id": "peel-shock",
                        "anchor": "end",
                        "offset": -0.25,
                        "character": "peel",
                        "reaction": "wide-eyes-open-mouth",
                        "duration": 1.2,
                        "camera": {"x": 0.68, "y": 0.48, "zoom": 2.0},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    build_show(template, script_path, output, voice_manifest=manifest_path, performance_plan=plan_path)

    with zipfile.ZipFile(output) as archive:
        rendered = json.loads(archive.read("show.json"))

    stage = rendered["stage"]
    assert stage["reactionLibrary"][0]["id"] == "wide-eyes-open-mouth"
    assert stage["characters"][1]["reactions"][0]["reactionID"] == "wide-eyes-open-mouth"
    assert stage["characters"][1]["reactions"][0]["start"] == 3.25
    camera_track = stage["backgroundTracks"][-1]
    assert camera_track["id"] == "camera-beats"
    assert camera_track["cues"][0]["camFrom"] == {"x": 0.68, "y": 0.48, "zoom": 2.0}
    assert rendered["show"][0]["to"] == 5.45


def test_retime_mouth_events_replaces_stale_keym_events(tmp_path: Path, monkeypatch):
    package_dir = tmp_path / "show.bannyshow"
    audio_dir = package_dir / "audio"
    audio_dir.mkdir(parents=True)
    _write_test_wav(audio_dir / "dialogue.wav", [(0.0, 0.20, 0), (0.20, 0.60, 8000), (0.60, 0.80, 0)])
    (package_dir / "show.json").write_text(
        json.dumps(
            {
                "assets": [],
                "stage": {
                    "audioTracks": [
                        {
                            "clips": [
                                {
                                    "id": "dialogue",
                                    "name": "peel-1",
                                    "start": 1.0,
                                    "dur": 0.8,
                                }
                            ]
                        }
                    ],
                    "backgroundTracks": [],
                    "characters": [
                        {"events": [{"code": "KeyT", "down": True, "t": 1.2}]},
                        {
                            "events": [
                                {"code": "KeyM", "down": True, "t": 1.0},
                                {"code": "KeyM", "down": False, "t": 9.0},
                                {"code": "Comma", "down": True, "t": 1.1},
                                {"code": "Comma", "down": False, "t": 1.2},
                            ]
                        },
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("SPLIT_PEEL_MOUTH_MAX_OPEN_SEC", "0.12")

    out_dir = tmp_path / "retimed.bannyshow"
    retime_mouth_events(package_dir, out_dir)

    stage = json.loads((out_dir / "show.json").read_text(encoding="utf-8"))["stage"]
    assert stage["characters"][0]["events"] == [{"code": "KeyT", "down": True, "t": 1.2}]
    peel_events = stage["characters"][1]["events"]
    assert all(event["t"] < 2.0 for event in peel_events)
    assert len([event for event in peel_events if event["code"] == "KeyM"]) >= 4
    assert any(event["code"] in {"Comma", "Period", "Slash"} for event in peel_events)


def test_repair_banny_wardrobe_removes_invalid_base_outfits(tmp_path: Path):
    package = tmp_path / "show.bs"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "backgroundTracks": [],
            "characters": [
                {"baseOutfit": {"6": "proff-glasses", "5": "eyeliner", "7": "gapteeth", "14": "fake"}},
                {"baseOutfit": {"11": "zipper-jacket"}},
            ],
        },
    }
    catalog = {
        "slots": [
            {"slot": 6, "outfits": [{"name": "proff-glasses"}]},
            {"slot": 11, "outfits": [{"name": "zipper-jacket"}]},
        ],
        "eyes": ["default", "eyeliner"],
        "mouths": ["default", "gapteeth"],
    }
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("show.json", json.dumps(show))

    repairs = repair_banny_wardrobe(package, catalog)

    assert repairs == [
        {
            "character": "0",
            "slot": "14",
            "outfit": "fake",
            "action": "removed-invalid-baseOutfit",
        }
    ]
    with zipfile.ZipFile(package) as archive:
        repaired = json.loads(archive.read("show.json"))
    assert repaired["stage"]["characters"][0]["baseOutfit"] == {"6": "proff-glasses", "5": "eyeliner", "7": "gapteeth"}
    assert repaired["stage"]["characters"][1]["baseOutfit"] == {"11": "zipper-jacket"}


def _write_test_wav(path: Path, segments: List[Tuple[float, float, int]], sample_rate: int = 22050) -> None:
    path.write_bytes(_test_wav_bytes(segments, sample_rate=sample_rate))


def _test_wav_bytes(segments: List[Tuple[float, float, int]], sample_rate: int = 22050) -> bytes:
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
