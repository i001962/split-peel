import json
import math
import wave
import zipfile
from pathlib import Path
from typing import List, Tuple

from split_peel.package import (
    _set_background_audio_gain,
    _trim_timeline_to_duration,
    _replace_character_subtitles,
    inspect_package,
    retime_mouth_events,
    roundtrip_package,
    unpack_package,
)
from split_peel.audio import VoiceClip


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
                        {"events": [{"code": "Period", "down": True, "t": 1.2}]},
                        {
                            "events": [
                                {"code": "KeyM", "down": True, "t": 1.0},
                                {"code": "KeyM", "down": False, "t": 9.0},
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
    assert stage["characters"][0]["events"] == [{"code": "Period", "down": True, "t": 1.2}]
    peel_events = stage["characters"][1]["events"]
    assert all(event["t"] < 2.0 for event in peel_events)
    assert len([event for event in peel_events if event["code"] == "KeyM"]) >= 4


def _write_test_wav(path: Path, segments: List[Tuple[float, float, int]], sample_rate: int = 22050) -> None:
    samples = []
    for start, end, amplitude in segments:
        frame_count = int((end - start) * sample_rate)
        for index in range(frame_count):
            value = int(amplitude * math.sin(2 * math.pi * 220 * (index / sample_rate))) if amplitude else 0
            samples.append(value)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))
